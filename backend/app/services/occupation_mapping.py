import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.config import settings

RELATION_CONFIDENCE = {
    "skos:exactMatch": 1.0,
    "skos:narrowMatch": 0.85,
    "skos:broadMatch": 0.8,
    "skos:closeMatch": 0.7,
}

def normalized_label(value: str | None) -> str:
    if not value: return ""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).split())

def parse_rome_esco_crosswalk(content: str) -> list[dict]:
    lines = content.splitlines()
    header_index = next((i for i, line in enumerate(lines) if line.lower().startswith("classification 1 id,")), None)
    if header_index is None: raise ValueError("En-tête du tableau ROME–ESCO introuvable")
    rows = []
    for row in csv.DictReader(io.StringIO("\n".join(lines[header_index:]))):
        esco_uri = (row.get("classification 1 ID") or "").strip()
        external_code = (row.get("classification 2 ID") or "").strip()
        if not esco_uri or not external_code: continue
        relation = (row.get("mapping relation") or "skos:closeMatch").strip()
        rows.append({
            "esco_uri": esco_uri,
            "esco_label": (row.get("classification 1 prefered label") or "").strip(),
            "external_code": external_code,
            "external_label": (row.get("classification 2 prefered label") or "").strip(),
            "mapping_relation": relation,
            "confidence_score": RELATION_CONFIDENCE.get(relation, 0.6),
        })
    return rows

async def sync_rome_esco_crosswalk(db: Session, url: str | None = None) -> dict:
    crosswalk_url = url or settings.france_travail_crosswalk_url
    if crosswalk_url.startswith(("http://", "https://")):
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=15), follow_redirects=True) as client:
            response = await client.get(crosswalk_url)
            response.raise_for_status()
            content = response.content
    else:
        content = Path(crosswalk_url).read_bytes()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_directory = Path(settings.raw_data_dir) / "france_travail" / stamp[:8]
    raw_directory.mkdir(parents=True, exist_ok=True)
    raw_path = raw_directory / f"{stamp}-rome-esco-crosswalk.csv"
    raw_path.write_bytes(content)
    rows = parse_rome_esco_crosswalk(content.decode("utf-8-sig"))
    occupations = {x.esco_uri: x for x in db.scalars(select(models.Occupation).where(models.Occupation.esco_uri.is_not(None))).all()}
    existing_mappings = {(x.occupation_id, x.external_code): x for x in db.scalars(
        select(models.ExternalOccupationMapping).where(models.ExternalOccupationMapping.source_system == "rome_appellation_v3")
    ).all()}
    stored = skipped = 0
    for row in rows:
        occupation = occupations.get(row["esco_uri"])
        if not occupation:
            skipped += 1; continue
        existing = existing_mappings.get((occupation.id, row["external_code"]))
        fields = {"external_label": row["external_label"], "mapping_relation": row["mapping_relation"],
                  "mapping_method": "official_eures_crosswalk", "confidence_score": row["confidence_score"],
                  "metadata_json": {"source_url": crosswalk_url, "esco_label": row["esco_label"],
                                    "esco_version": "1.1", "rome_version": "3.0", "raw_path": str(raw_path)}}
        if existing:
            for key, value in fields.items(): setattr(existing, key, value)
        else:
            existing = models.ExternalOccupationMapping(occupation_id=occupation.id, source_system="rome_appellation_v3",
                                                        external_code=row["external_code"], **fields)
            db.add(existing); existing_mappings[(occupation.id, row["external_code"])] = existing
        stored += 1
    db.commit()
    return {"rows": len(rows), "stored": stored, "skipped_missing_esco": skipped,
            "url": crosswalk_url, "raw_path": str(raw_path)}

@dataclass
class Resolution:
    occupation: models.Occupation | None
    method: str
    confidence: float

def _unique_top(candidates: list[tuple[models.Occupation, float]]) -> tuple[models.Occupation, float] | None:
    by_id = {}
    for occupation, confidence in candidates:
        by_id[occupation.id] = (occupation, max(confidence, by_id.get(occupation.id, (occupation, 0))[1]))
    ranked = sorted(by_id.values(), key=lambda item: item[1], reverse=True)
    if not ranked or (len(ranked) > 1 and ranked[0][1] == ranked[1][1]): return None
    return ranked[0]

def resolve_occupation(db: Session, row: dict) -> Resolution:
    if row.get("esco_uri"):
        occupation = db.scalar(select(models.Occupation).where(models.Occupation.esco_uri == row["esco_uri"]))
        if occupation: return Resolution(occupation, "esco_uri", 1.0)
    code = row.get("occupation_external_code")
    scheme = row.get("occupation_external_scheme") or "rome_v4"
    if code:
        mappings = db.scalars(select(models.ExternalOccupationMapping).options(selectinload(models.ExternalOccupationMapping.occupation)).where(
            models.ExternalOccupationMapping.source_system == scheme,
            models.ExternalOccupationMapping.external_code == str(code),
        )).all()
        best = _unique_top([(m.occupation, m.confidence_score) for m in mappings])
        if best: return Resolution(best[0], "external_code", best[1])
    labels = [row.get("occupation_appellation_label"), row.get("occupation_label")]
    normalized = {normalized_label(label) for label in labels if label}
    if normalized:
        mappings = db.scalars(select(models.ExternalOccupationMapping).options(selectinload(models.ExternalOccupationMapping.occupation))).all()
        best = _unique_top([(m.occupation, m.confidence_score) for m in mappings
                            if normalized_label(m.external_label) in normalized])
        if best:
            occupation, confidence = best
            if code:
                existing = db.scalar(select(models.ExternalOccupationMapping).where(
                    models.ExternalOccupationMapping.occupation_id == occupation.id,
                    models.ExternalOccupationMapping.source_system == scheme,
                    models.ExternalOccupationMapping.external_code == str(code),
                ))
                if not existing:
                    db.add(models.ExternalOccupationMapping(occupation_id=occupation.id, source_system=scheme,
                                                            external_code=str(code), external_label=row.get("occupation_label"),
                                                            mapping_relation="derivedMatch", mapping_method="official_label_crosswalk",
                                                            confidence_score=confidence))
            return Resolution(occupation, "official_label_crosswalk", confidence)
        candidates = []
        for occupation in db.scalars(select(models.Occupation)).all():
            names = {normalized_label(occupation.canonical_name)}
            names.update(normalized_label(x) for values in (occupation.aliases or {}).values() for x in values)
            names.update(normalized_label(x) for x in (occupation.multilingual_labels or {}).values())
            if names & normalized: candidates.append((occupation, 0.9))
        best = _unique_top(candidates)
        if best: return Resolution(best[0], "exact_label", best[1])
    isco_code = row.get("isco_code")
    if isco_code:
        occupations = db.scalars(select(models.Occupation).where(models.Occupation.isco_code == str(isco_code))).all()
        if len(occupations) == 1: return Resolution(occupations[0], "unique_isco", 0.75)
    return Resolution(None, "unresolved", 0.0)

def resolve_skill(db: Session, label: str | None) -> models.Skill | None:
    target = normalized_label(label)
    if not target: return None
    matches = []
    for skill in db.scalars(select(models.Skill)).all():
        names = {normalized_label(skill.canonical_name)}
        names.update(normalized_label(x) for values in (skill.aliases or {}).values() for x in values)
        names.update(normalized_label(x) for x in (skill.multilingual_labels or {}).values())
        if target in names: matches.append(skill)
    return matches[0] if len(matches) == 1 else None
