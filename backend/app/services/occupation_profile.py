from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models


ADDITIVE_METRICS = {"job_offers", "job_seekers", "hires", "skill_offer_mentions", "employment_by_sector"}


def _aggregate(metric: str, values: list[float]) -> tuple[float, str]:
    if metric in ADDITIVE_METRICS:
        return sum(values), "sum"
    return sum(values) / len(values), "average"


def build_occupation_profile(db: Session, occupation_id: str) -> dict | None:
    occupation = db.scalar(
        select(models.Occupation)
        .options(
            selectinload(models.Occupation.skills).selectinload(models.OccupationSkill.skill),
            selectinload(models.Occupation.external_mappings),
        )
        .where(models.Occupation.id == occupation_id)
    )
    if not occupation:
        return None

    observations = db.scalars(
        select(models.Observation)
        .where(models.Observation.occupation_id == occupation.id)
        .order_by(models.Observation.period, models.Observation.metric)
    ).all()
    source_ids = {row.source_id for row in observations} | {rel.source_id for rel in occupation.skills if rel.source_id}
    if occupation.esco_uri:
        esco_source = db.scalar(select(models.Source).where(models.Source.slug == "esco"))
        if esco_source:
            source_ids.add(esco_source.id)
    dataset_ids = {row.dataset_id for row in observations if row.dataset_id}
    sources = {row.id: row for row in db.scalars(select(models.Source).where(models.Source.id.in_(source_ids))).all()} if source_ids else {}
    datasets = {row.id: row for row in db.scalars(select(models.SourceDataset).where(models.SourceDataset.id.in_(dataset_ids))).all()} if dataset_ids else {}

    summary_groups = defaultdict(list)
    timeline_groups = defaultdict(list)
    latest_periods = {}
    for row in observations:
        summary_groups[(row.metric, row.unit)].append(row)
        timeline_groups[(row.metric, row.unit, row.period)].append(row)
        latest_periods[(row.metric, row.unit)] = max(row.period, latest_periods.get((row.metric, row.unit), row.period))

    market_summary = []
    for (metric, unit), rows in sorted(summary_groups.items()):
        value, aggregation = _aggregate(metric, [row.value for row in rows])
        market_summary.append({
            "metric": metric, "unit": unit, "value": round(value, 2), "aggregation": aggregation,
            "observation_count": len(rows), "period_from": min(row.period for row in rows),
            "period_to": max(row.period for row in rows),
            "is_official": all((row.metadata_json or {}).get("is_official", True) for row in rows),
        })

    timeline = []
    for (metric, unit, period), rows in sorted(timeline_groups.items(), key=lambda item: item[0][2]):
        value, aggregation = _aggregate(metric, [row.value for row in rows])
        timeline.append({
            "metric": metric, "unit": unit, "period": period, "value": round(value, 2),
            "aggregation": aggregation, "observation_count": len(rows),
            "geography_count": len({row.geography_code for row in rows}),
            "source_count": len({row.source_id for row in rows}),
        })

    geography_groups = defaultdict(list)
    for row in observations:
        if row.period == latest_periods[(row.metric, row.unit)]:
            geography_groups[(row.metric, row.unit, row.period, row.geography_code, row.geography_name)].append(row)
    geographies = []
    for (metric, unit, period, code, name), rows in sorted(geography_groups.items()):
        value, aggregation = _aggregate(metric, [row.value for row in rows])
        geographies.append({
            "metric": metric, "unit": unit, "period": period, "geography_code": code,
            "geography_name": name, "geography_level": (rows[0].metadata_json or {}).get("geography_level", "country"),
            "value": round(value, 2), "aggregation": aggregation, "observation_count": len(rows),
        })

    provenance_groups = defaultdict(list)
    for row in observations:
        provenance_groups[(row.source_id, row.dataset_id)].append(row)
    provenance = []
    for (source_id, dataset_id), rows in provenance_groups.items():
        source, dataset = sources.get(source_id), datasets.get(dataset_id)
        provenance.append({
            "kind": "observations",
            "source_id": source_id, "source_slug": source.slug if source else None,
            "source_name": source.name if source else "Source inconnue",
            "dataset_id": dataset_id, "dataset_code": dataset.external_id if dataset else None,
            "dataset_name": dataset.name if dataset else None, "dataset_version": dataset.version if dataset else None,
            "observation_count": len(rows), "metrics": sorted({row.metric for row in rows}),
            "period_from": min(row.period for row in rows), "period_to": max(row.period for row in rows),
            "last_imported_at": max(row.imported_at for row in rows),
            "relationship_count": sum(1 for rel in occupation.skills if rel.source_id == source_id),
        })
    observed_source_ids = {row["source_id"] for row in provenance}
    for source_id in source_ids - observed_source_ids:
        source = sources.get(source_id)
        relation_count = sum(1 for rel in occupation.skills if rel.source_id == source_id)
        provenance.append({
            "kind": "reference", "source_id": source_id,
            "source_slug": source.slug if source else None, "source_name": source.name if source else "Source inconnue",
            "dataset_id": None, "dataset_code": None, "dataset_name": None, "dataset_version": None,
            "observation_count": 0, "relationship_count": relation_count,
            "metrics": ["occupation_skills"] if relation_count else ["occupation_reference"],
            "period_from": None, "period_to": None, "last_imported_at": None,
        })
    provenance.sort(key=lambda row: (row["source_name"], row["dataset_code"] or ""))

    skills = [{
        "id": rel.skill.id, "name": rel.skill.canonical_name, "description": rel.skill.description,
        "relationship": rel.relationship_type, "weight": rel.weight, "skill_type": rel.skill.skill_type,
        "confidence": rel.confidence_score, "source": sources[rel.source_id].name if rel.source_id in sources else None,
    } for rel in sorted(occupation.skills, key=lambda rel: (rel.relationship_type != "essential", rel.skill.canonical_name))]

    market = [{
        "metric": row.metric, "value": row.value, "unit": row.unit, "period": row.period,
        "geography_code": row.geography_code, "geography_name": row.geography_name,
        "geography_level": (row.metadata_json or {}).get("geography_level", "country"),
        "source": sources[row.source_id].name if row.source_id in sources else None,
        "source_slug": sources[row.source_id].slug if row.source_id in sources else None,
        "dataset": datasets[row.dataset_id].external_id if row.dataset_id in datasets else None,
        "dimensions": (row.metadata_json or {}).get("dimensions", {}),
        "resolution": (row.metadata_json or {}).get("occupation_resolution"),
        "is_official": (row.metadata_json or {}).get("is_official", True),
        "imported_at": row.imported_at,
    } for row in observations]

    return {
        "id": occupation.id, "canonical_name": occupation.canonical_name,
        "description": occupation.description, "sector": occupation.sector,
        "esco_uri": occupation.esco_uri, "isco_code": occupation.isco_code,
        "aliases": occupation.aliases, "multilingual_labels": occupation.multilingual_labels,
        "multilingual_descriptions": occupation.multilingual_descriptions,
        "created_at": occupation.created_at, "updated_at": occupation.updated_at,
        "external_mappings": [{
            "system": mapping.source_system, "code": mapping.external_code,
            "label": mapping.external_label, "relation": mapping.mapping_relation,
            "method": mapping.mapping_method, "confidence": mapping.confidence_score,
        } for mapping in occupation.external_mappings],
        "skills": skills, "market": market, "market_summary": market_summary,
        "geographies": geographies, "timeline": timeline, "sources": provenance,
    }
