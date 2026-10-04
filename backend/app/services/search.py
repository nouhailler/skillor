import re
import unicodedata
from collections.abc import Iterable
from difflib import SequenceMatcher

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app import models


def normalize_term(value: str | None) -> str:
    if not value:
        return ""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).split())


def _values(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _values(nested)
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            yield from _values(nested)


def _append(terms: list[dict], seen: set[tuple], value: str | None, language: str | None,
            source: str, term_type: str, identifier: str | None = None) -> None:
    normalized = normalize_term(value)
    if not normalized:
        return
    key = (normalized, language, source, term_type)
    if key in seen:
        return
    seen.add(key)
    terms.append({"term": str(value).strip(), "normalized_term": normalized, "language": language,
                  "source": source, "term_type": term_type, "identifier": identifier})


def _entity_terms(db: Session, entity_type: str, entity) -> list[dict]:
    terms, seen = [], set()
    canonical_language = next((language for language, value in (entity.multilingual_labels or {}).items()
                               if any(normalize_term(label) == normalize_term(entity.canonical_name) for label in _values(value))), "fr")
    _append(terms, seen, entity.canonical_name, canonical_language, "skillor", "canonical")
    for language, values in (entity.aliases or {}).items():
        for value in _values(values):
            _append(terms, seen, value, language, "esco", "alias")
    for language, value in (entity.multilingual_labels or {}).items():
        for label in _values(value):
            _append(terms, seen, label, language, "esco", "translated_label")
    if entity.esco_uri:
        _append(terms, seen, entity.esco_uri, None, "esco", "source_identifier", entity.esco_uri)
        _append(terms, seen, entity.esco_uri.rstrip("/").split("/")[-1], None, "esco", "source_identifier", entity.esco_uri)
    if entity_type == "occupation":
        if entity.isco_code:
            _append(terms, seen, entity.isco_code, None, "isco", "occupation_code", entity.isco_code)
        mappings = db.scalars(select(models.ExternalOccupationMapping).where(models.ExternalOccupationMapping.occupation_id == entity.id)).all()
        for mapping in mappings:
            _append(terms, seen, mapping.external_label, "fr" if mapping.source_system.startswith("rome") else None,
                    mapping.source_system, "external_alias", mapping.external_code)
            _append(terms, seen, mapping.external_code, None, mapping.source_system, "occupation_code", mapping.external_code)
            for alias in (mapping.metadata_json or {}).get("observed_aliases", []):
                _append(terms, seen, alias, "fr", "france_travail", "observed_alias", mapping.external_code)
    return terms


def index_entity(db: Session, entity_type: str, entity) -> int:
    db.execute(delete(models.SearchTerm).where(models.SearchTerm.entity_type == entity_type, models.SearchTerm.entity_id == entity.id))
    terms = _entity_terms(db, entity_type, entity)
    db.add_all(models.SearchTerm(entity_type=entity_type, entity_id=entity.id, **term) for term in terms)
    return len(terms)


def rebuild_search_index(db: Session) -> int:
    db.execute(delete(models.SearchTerm))
    count = 0
    for occupation in db.scalars(select(models.Occupation)).all():
        count += index_entity(db, "occupation", occupation)
    for skill in db.scalars(select(models.Skill)).all():
        count += index_entity(db, "skill", skill)
    db.commit()
    return count


def ensure_search_index(db: Session) -> int:
    indexed = db.scalar(select(func.count(models.SearchTerm.id))) or 0
    entities = (db.scalar(select(func.count(models.Occupation.id))) or 0) + (db.scalar(select(func.count(models.Skill.id))) or 0)
    return rebuild_search_index(db) if entities and not indexed else indexed


def _score(query: str, candidate: str) -> tuple[float, str]:
    if candidate == query:
        return 1.0, "exact"
    if candidate.startswith(query):
        return max(0.9, 0.98 - (len(candidate) - len(query)) * 0.004), "prefix"
    if query in candidate:
        return 0.88, "contains"
    ratio = SequenceMatcher(None, query, candidate).ratio()
    query_tokens, candidate_tokens = set(query.split()), set(candidate.split())
    token_score = len(query_tokens & candidate_tokens) / max(len(query_tokens | candidate_tokens), 1)
    return max(ratio, token_score * 0.92), "fuzzy"


def search_entities(db: Session, query: str, *, entity_type: str | None = None, language: str | None = None,
                    source: str | None = None, sector: str | None = None, skill_type: str | None = None,
                    limit: int = 10, fuzzy: bool = True) -> list[dict]:
    normalized = normalize_term(query)
    if not normalized:
        return []
    stmt = select(models.SearchTerm)
    if entity_type:
        stmt = stmt.where(models.SearchTerm.entity_type == entity_type)
    if language:
        stmt = stmt.where(models.SearchTerm.language == language)
    if source:
        stmt = stmt.where(models.SearchTerm.source == source)
    dialect = db.bind.dialect.name
    if dialect == "postgresql" and fuzzy:
        similarity = func.similarity(models.SearchTerm.normalized_term, normalized)
        stmt = stmt.where(or_(models.SearchTerm.normalized_term.ilike(f"%{normalized}%"), models.SearchTerm.normalized_term.op("%")(normalized))).order_by(similarity.desc()).limit(2000)
    else:
        first = normalized[:1]
        stmt = stmt.where(or_(models.SearchTerm.normalized_term.ilike(f"%{normalized}%"), models.SearchTerm.normalized_term.ilike(f"{first}%"))).limit(2000)
    terms = db.scalars(stmt).all()
    threshold = 0.78 if len(normalized) <= 2 else 0.55
    best = {}
    for term in terms:
        score, match_type = _score(normalized, term.normalized_term)
        if (not fuzzy and match_type == "fuzzy") or score < threshold:
            continue
        current = best.get((term.entity_type, term.entity_id))
        if current is None or score > current[0]:
            best[(term.entity_type, term.entity_id)] = (score, match_type, term)
    ranked = sorted(best.items(), key=lambda item: (item[1][0], item[1][2].term_type == "canonical"), reverse=True)
    results = []
    for (kind, entity_id), (score, match_type, matched) in ranked:
        entity = db.get(models.Occupation if kind == "occupation" else models.Skill, entity_id)
        if not entity or (sector and (kind != "occupation" or entity.sector != sector)) or (skill_type and (kind != "skill" or entity.skill_type != skill_type)):
            continue
        identifiers = db.scalars(select(models.SearchTerm).where(
            models.SearchTerm.entity_type == kind, models.SearchTerm.entity_id == entity_id,
            models.SearchTerm.identifier.is_not(None),
        )).all()
        unique_identifiers = []
        seen_identifiers = set()
        for item in identifiers:
            key = (item.source, item.identifier, item.term_type)
            if key not in seen_identifiers:
                seen_identifiers.add(key)
                unique_identifiers.append({"source": item.source, "value": item.identifier, "type": item.term_type})
        results.append({
            "id": entity.id, "name": entity.canonical_name, "type": kind,
            "description": entity.description, "sector": entity.sector if kind == "occupation" else None,
            "skill_type": entity.skill_type if kind == "skill" else None,
            "matched_term": matched.term, "matched_language": matched.language,
            "matched_source": matched.source, "match_type": match_type, "score": round(score, 4),
            "identifiers": unique_identifiers,
        })
        if len(results) >= limit:
            break
    return results


def search_filters(db: Session) -> dict:
    return {
        "languages": [value for value in db.scalars(select(models.SearchTerm.language).where(models.SearchTerm.language.is_not(None)).distinct().order_by(models.SearchTerm.language)).all()],
        "sources": [value for value in db.scalars(select(models.SearchTerm.source).distinct().order_by(models.SearchTerm.source)).all()],
        "sectors": [value for value in db.scalars(select(models.Occupation.sector).where(models.Occupation.sector.is_not(None)).distinct().order_by(models.Occupation.sector)).all()],
        "skill_types": [value for value in db.scalars(select(models.Skill.skill_type).where(models.Skill.skill_type.is_not(None)).distinct().order_by(models.Skill.skill_type)).all()],
        "entity_types": ["occupation", "skill"],
    }
