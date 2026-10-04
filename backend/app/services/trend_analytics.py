from collections import defaultdict
from math import log1p

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import models
from app.services.scoring import TrendComponents, trend_score


METHOD_VERSION = "2.0-observed"
DIRECT_METRICS = {"skill_offer_mentions", "job_offers"}


def _change(current: float, previous: float) -> float:
    return 0.0 if previous == 0 else (current - previous) / abs(previous) * 100


def _centered(value: float) -> float:
    return round(50 + max(-100, min(100, value)) / 2, 2)


def _confidence(row: models.Observation) -> float:
    metadata = row.metadata_json or {}
    value = metadata.get("source_confidence")
    if value is not None:
        value = float(value)
        return max(0, min(100, value * 100 if value <= 1 else value))
    return 90.0 if metadata.get("is_official", True) else 65.0


def _signal_rows(db: Session, skill: models.Skill) -> tuple[list[tuple[models.Observation, float]], str]:
    direct = db.scalars(select(models.Observation).where(
        models.Observation.skill_id == skill.id, models.Observation.metric.in_(DIRECT_METRICS))).all()
    if len({row.period for row in direct}) >= 2:
        return [(row, 1.0) for row in direct], "direct_skill_observations"
    relations = db.scalars(select(models.OccupationSkill).where(models.OccupationSkill.skill_id == skill.id)).all()
    weights = {row.occupation_id: max(0.0, row.weight) * max(0.0, row.confidence_score) for row in relations}
    if not weights:
        return [], "unavailable"
    rows = db.scalars(select(models.Observation).where(
        models.Observation.occupation_id.in_(weights), models.Observation.metric == "job_offers")).all()
    return [(row, weights[row.occupation_id]) for row in rows], "occupation_offer_proxy"


def recompute_skill_trends(db: Session) -> dict:
    skills = db.scalars(select(models.Skill).order_by(models.Skill.id)).all()
    candidates = {}
    skipped = []
    all_geographies = set()
    for skill in skills:
        rows, signal = _signal_rows(db, skill)
        periods = defaultdict(list)
        for row, weight in rows:
            periods[row.period].append((row, weight))
            all_geographies.add(row.geography_code)
        if len(periods) < 2:
            skipped.append({"id": skill.id, "name": skill.canonical_name, "reason": "minimum_two_periods"})
            continue
        series = []
        for period, items in sorted(periods.items()):
            series.append({"period": period, "value": sum(row.value * weight for row, weight in items),
                "geographies": {row.geography_code for row, _ in items},
                "sources": {row.source_id for row, _ in items},
                "confidence": sum(_confidence(row) * weight for row, weight in items) / max(sum(weight for _, weight in items), 1e-9),
                "observations": len(items)})
        candidates[skill.id] = {"skill": skill, "signal": signal, "series": series}

    max_volume = max((point["value"] for item in candidates.values() for point in item["series"]), default=0)
    geography_denominator = max(1, len(all_geographies))
    written = 0
    for skill_id, item in candidates.items():
        series = item["series"]
        raw_growth_history = []
        for index in range(1, len(series)):
            current, previous = series[index], series[index - 1]
            raw_growth = _change(current["value"], previous["value"])
            prior_growth = raw_growth_history[-1] if raw_growth_history else raw_growth
            raw_acceleration = raw_growth - prior_growth
            raw_growth_history.append(raw_growth)
            components = TrendComponents(
                growth=_centered(raw_growth), acceleration=_centered(raw_acceleration),
                volume=round(100 * log1p(max(0, current["value"])) / log1p(max_volume), 2) if max_volume else 0,
                geographic_spread=round(100 * len(current["geographies"]) / geography_denominator, 2),
                source_confidence=round(current["confidence"], 2),
            )
            result = trend_score(components)
            existing = db.scalar(select(models.TrendScore).where(
                models.TrendScore.entity_type == "skill", models.TrendScore.entity_id == skill_id,
                models.TrendScore.period == current["period"], models.TrendScore.method_version == METHOD_VERSION))
            fields = {"score": result["score"], **result["components"], "raw_growth": round(raw_growth, 2),
                "is_official": False, "calculation_metadata": {"signal": item["signal"],
                    "current_value": round(current["value"], 4), "previous_value": round(previous["value"], 4),
                    "raw_acceleration": round(raw_acceleration, 2), "observation_count": current["observations"],
                    "source_count": len(current["sources"]), "geography_count": len(current["geographies"]),
                    "formula": "0.35 growth + 0.25 acceleration + 0.20 volume + 0.10 geographic_spread + 0.10 source_confidence"}}
            if existing:
                for key, value in fields.items():
                    setattr(existing, key, value)
            else:
                db.add(models.TrendScore(entity_type="skill", entity_id=skill_id, period=current["period"],
                    method_version=METHOD_VERSION, **fields))
            written += 1
    db.commit()
    return {"method_version": METHOD_VERSION, "skills_evaluated": len(skills),
        "skills_scored": len(candidates), "scores_written": written, "skipped": skipped, "is_official": False}
