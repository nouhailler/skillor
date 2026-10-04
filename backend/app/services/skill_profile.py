from collections import defaultdict

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.services.occupation_profile import _aggregate


def build_skill_profile(db: Session, skill_id: str) -> dict | None:
    skill = db.scalar(select(models.Skill).options(
        selectinload(models.Skill.occupations).selectinload(models.OccupationSkill.occupation)
    ).where(models.Skill.id == skill_id))
    if not skill:
        return None
    occupation_ids = [rel.occupation_id for rel in skill.occupations]
    condition = models.Observation.skill_id == skill.id
    if occupation_ids:
        condition = or_(condition, models.Observation.occupation_id.in_(occupation_ids))
    observations = db.scalars(select(models.Observation).where(condition).order_by(
        models.Observation.period, models.Observation.metric)).all()
    source_ids = {row.source_id for row in observations} | {rel.source_id for rel in skill.occupations if rel.source_id}
    sources = {row.id: row for row in db.scalars(select(models.Source).where(models.Source.id.in_(source_ids))).all()} if source_ids else {}

    grouped = defaultdict(list)
    timeline_groups = defaultdict(list)
    for row in observations:
        grouped[(row.metric, row.unit)].append(row)
        timeline_groups[(row.metric, row.unit, row.period)].append(row)
    market_summary = []
    for (metric, unit), rows in sorted(grouped.items()):
        value, aggregation = _aggregate(metric, [row.value for row in rows])
        market_summary.append({"metric": metric, "unit": unit, "value": round(value, 2),
            "aggregation": aggregation, "observation_count": len(rows),
            "period_from": min(row.period for row in rows), "period_to": max(row.period for row in rows),
            "is_official": all((row.metadata_json or {}).get("is_official", True) for row in rows)})
    timeline = []
    for (metric, unit, period), rows in sorted(timeline_groups.items(), key=lambda item: item[0][2]):
        value, aggregation = _aggregate(metric, [row.value for row in rows])
        timeline.append({"metric": metric, "unit": unit, "period": period, "value": round(value, 2),
            "aggregation": aggregation, "observation_count": len(rows)})

    def metric_value(rows, names):
        matches = [row.value for row in rows if row.metric in names]
        return round(sum(matches) if names == {"job_offers"} else sum(matches) / len(matches), 2) if matches else None

    by_occupation = defaultdict(list)
    for row in observations:
        if row.occupation_id:
            by_occupation[row.occupation_id].append(row)
    occupations = [{"id": rel.occupation.id, "name": rel.occupation.canonical_name,
        "sector": rel.occupation.sector, "relationship": rel.relationship_type, "weight": rel.weight,
        "offers": metric_value(by_occupation[rel.occupation_id], {"job_offers"}),
        "salary": metric_value(by_occupation[rel.occupation_id], {"salary_average"}),
        "tension": metric_value(by_occupation[rel.occupation_id], {"tension_index", "tension_score", "recruitment_difficulty"})}
        for rel in skill.occupations]

    sector_groups = defaultdict(list)
    for row in occupations:
        sector_groups[row["sector"] or "Non renseigné"].append(row)
    sectors = [{"name": name, "occupation_count": len(rows),
        "offers": round(sum(row["offers"] or 0 for row in rows), 2)} for name, rows in sorted(sector_groups.items())]

    latest = {key: max(item.period for item in rows) for key, rows in grouped.items()}
    region_groups = defaultdict(list)
    for row in observations:
        level = (row.metadata_json or {}).get("geography_level", "country")
        if level != "country" and row.period == latest[(row.metric, row.unit)]:
            region_groups[(row.geography_code, row.geography_name, level, row.metric, row.unit, row.period)].append(row)
    regions = []
    for (code, name, level, metric, unit, period), rows in sorted(region_groups.items()):
        value, aggregation = _aggregate(metric, [row.value for row in rows])
        regions.append({"code": code, "name": name, "level": level, "metric": metric,
            "unit": unit, "period": period, "value": round(value, 2), "aggregation": aggregation})

    neighbor_rows = db.scalars(select(models.OccupationSkill).options(selectinload(models.OccupationSkill.skill)).where(
        models.OccupationSkill.occupation_id.in_(occupation_ids), models.OccupationSkill.skill_id != skill.id)).all() if occupation_ids else []
    neighbor_groups = defaultdict(list)
    for rel in neighbor_rows:
        neighbor_groups[rel.skill_id].append(rel)
    neighbors = [{"id": rels[0].skill.id, "name": rels[0].skill.canonical_name,
        "skill_type": rels[0].skill.skill_type, "shared_occupation_count": len({rel.occupation_id for rel in rels})}
        for rels in neighbor_groups.values()]
    neighbors.sort(key=lambda row: (-row["shared_occupation_count"], row["name"]))

    trends = db.scalars(select(models.TrendScore).where(models.TrendScore.entity_type == "skill",
        models.TrendScore.entity_id == skill.id).order_by(models.TrendScore.period)).all()
    provenance = [{"source_name": source.name, "source_slug": source.slug,
        "observation_count": sum(1 for row in observations if row.source_id == source_id),
        "relationship_count": sum(1 for rel in skill.occupations if rel.source_id == source_id),
        "metrics": sorted({row.metric for row in observations if row.source_id == source_id})}
        for source_id, source in sources.items()]
    provenance.sort(key=lambda row: row["source_name"])

    return {"id": skill.id, "canonical_name": skill.canonical_name, "description": skill.description,
        "skill_type": skill.skill_type, "esco_uri": skill.esco_uri, "aliases": skill.aliases,
        "multilingual_labels": skill.multilingual_labels, "multilingual_descriptions": skill.multilingual_descriptions,
        "created_at": skill.created_at, "updated_at": skill.updated_at, "occupations": occupations,
        "sectors": sectors, "regions": regions, "market_summary": market_summary, "timeline": timeline,
        "neighbors": neighbors, "trends": [{"period": row.period, "score": row.score,
            "growth": row.raw_growth if row.raw_growth is not None else row.growth,
            "components": {"growth": row.growth, "acceleration": row.acceleration, "volume": row.volume,
                "geographic_spread": row.geographic_spread, "source_confidence": row.source_confidence},
            "calculation": row.calculation_metadata, "method_version": row.method_version, "is_official": False} for row in trends],
        "trend": None if not trends else {"score": trends[-1].score,
            "growth": trends[-1].raw_growth if trends[-1].raw_growth is not None else trends[-1].growth,
            "components": {"growth": trends[-1].growth, "acceleration": trends[-1].acceleration,
                "volume": trends[-1].volume, "geographic_spread": trends[-1].geographic_spread,
                "source_confidence": trends[-1].source_confidence},
            "calculation": trends[-1].calculation_metadata,
            "method_version": trends[-1].method_version, "is_official": False}, "sources": provenance}
