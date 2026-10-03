from collections import defaultdict
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models


def _month_index(value: date) -> int:
    return value.year * 12 + value.month


def _within_last_months(value: date, latest: date, months: int = 12) -> bool:
    return 0 <= _month_index(latest) - _month_index(value) < months


def _latest_trends(db: Session, entity_type: str, limit: int = 5) -> list[dict]:
    model = models.Skill if entity_type == "skill" else models.Occupation
    rows = db.execute(
        select(models.TrendScore, model.canonical_name)
        .join(model, model.id == models.TrendScore.entity_id)
        .where(models.TrendScore.entity_type == entity_type)
        .order_by(models.TrendScore.period.desc(), models.TrendScore.score.desc())
    ).all()
    latest_by_entity = {}
    for trend, name in rows:
        latest_by_entity.setdefault(trend.entity_id, (trend, name))
    selected = sorted(latest_by_entity.values(), key=lambda row: row[0].score, reverse=True)[:limit]
    return [
        {
            "id": trend.entity_id,
            "name": name,
            "score": trend.score,
            "growth": trend.growth,
            "period": trend.period,
            "is_official": False,
            "method_version": trend.method_version,
        }
        for trend, name in selected
    ]


def _offer_summary(db: Session) -> tuple[float | None, date | None, list[dict], list[dict]]:
    rows = db.execute(
        select(
            models.Observation.occupation_id,
            models.Occupation.canonical_name,
            models.Observation.period,
            func.sum(models.Observation.value),
        )
        .outerjoin(models.Occupation, models.Occupation.id == models.Observation.occupation_id)
        .where(models.Observation.metric == "job_offers")
        .group_by(models.Observation.occupation_id, models.Occupation.canonical_name, models.Observation.period)
        .order_by(models.Observation.period)
    ).all()
    if not rows:
        return None, None, [], []

    latest = max(row.period for row in rows)
    recent = [row for row in rows if _within_last_months(row.period, latest)]
    total = sum(float(row[3]) for row in recent)
    by_occupation = defaultdict(float)
    history = defaultdict(list)
    names = {}
    for occupation_id, name, period, value in rows:
        if occupation_id:
            history[occupation_id].append((period, float(value)))
            names[occupation_id] = name
            if _within_last_months(period, latest):
                by_occupation[occupation_id] += float(value)
    top = [
        {"id": occupation_id, "name": names[occupation_id], "offers": value}
        for occupation_id, value in sorted(by_occupation.items(), key=lambda row: row[1], reverse=True)[:5]
    ]
    growth = []
    for occupation_id, points in history.items():
        points = sorted(points)
        first_period, first_value = points[0]
        last_period, last_value = points[-1]
        if first_period == last_period or first_value <= 0:
            continue
        growth.append(
            {
                "id": occupation_id,
                "name": names[occupation_id],
                "growth": round((last_value - first_value) / first_value * 100, 1),
                "volume": last_value,
                "period_from": first_period,
                "period_to": last_period,
                "is_official": False,
                "method_version": "dashboard_offer_growth_v1",
            }
        )
    growth.sort(key=lambda row: (row["growth"], row["volume"]), reverse=True)
    return total, latest, top, growth[:5]


def _geography_summary(db: Session) -> dict:
    rows = db.execute(select(models.Observation.geography_code, models.Observation.metadata_json)).all()
    countries, regions, territories = set(), set(), set()
    for code, metadata in rows:
        if not code:
            continue
        code = str(code)
        metadata = metadata or {}
        level = metadata.get("geography_level", "country")
        territories.add(code)
        if level in {"region", "nuts1", "nuts2", "nuts3"}:
            regions.add(code)
        if level == "country" and len(code) == 2 and code.isalpha():
            countries.add(code.upper())
        elif len(code) >= 2 and code[:2].isalpha():
            countries.add(code[:2].upper())
        elif code.isdigit():
            countries.add("FR")
    return {"countries": len(countries), "regions": len(regions), "territories": len(territories)}


def _salary_summary(db: Session) -> dict | None:
    rows = db.scalars(
        select(models.Observation)
        .where(models.Observation.metric.in_(("salary_average", "salary_min", "salary_max", "mean_monthly_earnings")))
        .order_by(models.Observation.period.desc())
    ).all()
    if not rows:
        return None
    latest = max(row.period for row in rows)
    rows = [row for row in rows if _within_last_months(row.period, latest)]
    by_unit = defaultdict(lambda: {"average": [], "min": [], "max": [], "sample_size": 0, "occupations": set()})
    for row in rows:
        bucket = by_unit[row.unit]
        key = "average" if row.metric == "mean_monthly_earnings" else row.metric.removeprefix("salary_")
        bucket[key].append(row.value)
        bucket["sample_size"] += int((row.metadata_json or {}).get("dimensions", {}).get("sample_size") or 1)
        if row.occupation_id:
            bucket["occupations"].add(row.occupation_id)
    summaries = []
    for unit, values in by_unit.items():
        if values["average"]:
            amount = sum(values["average"]) / len(values["average"])
            method = "observed_average"
        elif values["min"] and values["max"]:
            amount = ((sum(values["min"]) / len(values["min"])) + (sum(values["max"]) / len(values["max"]))) / 2
            method = "range_midpoint"
        else:
            available = values["min"] or values["max"]
            amount = sum(available) / len(available)
            method = "single_bound"
        summaries.append(
            {
                "value": round(amount, 2),
                "unit": unit,
                "period": latest,
                "sample_size": values["sample_size"],
                "occupation_count": len(values["occupations"]),
                "method": method,
                "is_official": method == "observed_average",
            }
        )
    summaries.sort(key=lambda row: (row["sample_size"], row["occupation_count"]), reverse=True)
    return {"primary": summaries[0], "by_unit": summaries}


def _tension_summary(db: Session) -> dict | None:
    for metric, is_official in (("recruitment_difficulty", True), ("tension_index", False)):
        latest = db.scalar(select(func.max(models.Observation.period)).where(models.Observation.metric == metric))
        if latest is None:
            continue
        value, count, unit = db.execute(
            select(func.avg(models.Observation.value), func.count(models.Observation.id), func.min(models.Observation.unit))
            .where(models.Observation.metric == metric, models.Observation.period == latest)
        ).one()
        return {
            "value": round(float(value), 1),
            "unit": unit,
            "period": latest,
            "sample_size": count,
            "metric": metric,
            "is_official": is_official,
            "method_version": None if is_official else "1.0",
        }
    return None


def build_dashboard(db: Session) -> dict:
    occupations = db.scalar(select(func.count(models.Occupation.id))) or 0
    skills = db.scalar(select(func.count(models.Skill.id))) or 0
    observations = db.scalar(select(func.count(models.Observation.id))) or 0
    latest_update = db.scalar(select(func.max(models.Observation.imported_at)))
    offers, offers_period, top_occupations, derived_occupation_trends = _offer_summary(db)
    occupation_trends = _latest_trends(db, "occupation") or derived_occupation_trends
    geography = _geography_summary(db)
    source_updates = [
        {"slug": source.slug, "name": source.name, "last_success_at": source.last_success_at}
        for source in db.scalars(select(models.Source).order_by(models.Source.name)).all()
    ]
    return {
        "kpis": {
            "occupations": occupations,
            "skills": skills,
            "observations": observations,
            "offers_12m": offers,
            "offers_latest_period": offers_period,
            **geography,
        },
        "latest_update": latest_update,
        "source_updates": source_updates,
        "salary": _salary_summary(db),
        "tension": _tension_summary(db),
        "top_skill_trends": _latest_trends(db, "skill"),
        "top_occupation_trends": occupation_trends,
        "top_occupations_by_offers": top_occupations,
        "provenance": {"sources": [source["name"] for source in source_updates], "mode": "database"},
    }
