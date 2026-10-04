from collections import Counter, defaultdict
from datetime import datetime, timezone
from math import isfinite

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.services.scoring import confidence_score


METHOD_VERSION = "1.0-observed"
ADDITIVE_METRICS = {"job_offers", "job_seekers", "hires", "skill_offer_mentions", "employment_by_sector"}


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _source_quality(db: Session, source: models.Source, rows: list[models.Observation]) -> tuple[float, dict]:
    jobs = db.scalars(select(models.ImportJob).where(models.ImportJob.source_id == source.id,
        models.ImportJob.status.in_(("success", "failed")))).all()
    success_ratio = sum(job.status == "success" for job in jobs) / len(jobs) if jobs else 0.8
    official_ratio = sum(bool((row.metadata_json or {}).get("is_official", True)) for row in rows) / len(rows)
    base = {"taxonomy": 95, "observed": 90, "administrative": 92}.get(source.source_type, 75)
    value = min(100, base * 0.5 + success_ratio * 30 + official_ratio * 20)
    return round(value, 2), {"source_type_base": base, "successful_import_ratio": round(success_ratio, 4),
        "official_observation_ratio": round(official_ratio, 4), "import_job_count": len(jobs)}


def _recency(rows: list[models.Observation], now: datetime) -> tuple[float, dict]:
    latest = max(_aware(row.imported_at) for row in rows)
    age_days = max(0.0, (now - latest).total_seconds() / 86400)
    return round(max(0, 100 - age_days / 3.65), 2), {"latest_imported_at": latest.isoformat(), "age_days": round(age_days, 2)}


def _coverage(rows: list[models.Observation]) -> tuple[float, dict]:
    scores = []
    for row in rows:
        metadata = row.metadata_json or {}
        score = 20 * bool(row.geography_code and row.geography_name)
        score += 20 * bool(row.unit and row.period)
        score += 15 * bool(row.natural_key)
        score += 15 * bool(row.dataset_id)
        score += 15 * bool(metadata.get("dimensions") or metadata.get("dimension_labels"))
        score += 15 * bool(row.occupation_id or row.skill_id or metadata.get("profile") or metadata.get("family"))
        scores.append(score)
    value = sum(scores) / len(scores)
    return round(value, 2), {"complete_rows": sum(score == 100 for score in scores),
        "complete_row_ratio": round(sum(score == 100 for score in scores) / len(scores), 4)}


def _consistency(rows: list[models.Observation]) -> tuple[float, dict]:
    finite_ratio = sum(isfinite(row.value) for row in rows) / len(rows)
    units = Counter(row.unit for row in rows)
    dominant_unit_ratio = units.most_common(1)[0][1] / len(rows)
    nonnegative_ratio = (sum(row.value >= 0 for row in rows) / len(rows)) if rows[0].metric in ADDITIVE_METRICS else 1.0
    keys = [row.natural_key for row in rows if row.natural_key]
    uniqueness_ratio = len(set(keys)) / len(keys) if keys else 0.5
    value = 35 * finite_ratio + 25 * dominant_unit_ratio + 20 * nonnegative_ratio + 20 * uniqueness_ratio
    return round(value, 2), {"finite_ratio": round(finite_ratio, 4),
        "dominant_unit": units.most_common(1)[0][0], "dominant_unit_ratio": round(dominant_unit_ratio, 4),
        "nonnegative_ratio": round(nonnegative_ratio, 4), "natural_key_uniqueness_ratio": round(uniqueness_ratio, 4)}


def _agreement(rows: list[models.Observation], all_rows: list[models.Observation]) -> tuple[float, dict]:
    comparisons = defaultdict(list)
    for row in all_rows:
        key = (row.metric, row.period, row.geography_code, row.occupation_id, row.skill_id, row.unit)
        comparisons[key].append(row)
    scores = []
    for row in rows:
        key = (row.metric, row.period, row.geography_code, row.occupation_id, row.skill_id, row.unit)
        others = [item.value for item in comparisons[key] if item.source_id != row.source_id]
        for other in others:
            denominator = max(abs(row.value), abs(other), 1e-9)
            scores.append(100 * (1 - min(1, abs(row.value - other) / denominator)))
    if not scores:
        return 50.0, {"comparison_count": 0, "status": "no_cross_source_overlap", "neutral_default": True}
    return round(sum(scores) / len(scores), 2), {"comparison_count": len(scores),
        "mean_relative_agreement": round(sum(scores) / len(scores) / 100, 4), "neutral_default": False}


def recompute_data_quality(db: Session, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    all_rows = db.scalars(select(models.Observation)).all()
    sources = {row.id: row for row in db.scalars(select(models.Source)).all()}
    groups = defaultdict(list)
    for row in all_rows:
        groups[(row.source_id, row.dataset_id, row.metric)].append(row)
    written = 0
    results = []
    for (source_id, dataset_id, metric), rows in groups.items():
        source = sources[source_id]
        source_quality, source_diagnostics = _source_quality(db, source, rows)
        recency, recency_diagnostics = _recency(rows, now)
        coverage, coverage_diagnostics = _coverage(rows)
        consistency, consistency_diagnostics = _consistency(rows)
        agreement, agreement_diagnostics = _agreement(rows, all_rows)
        result = confidence_score(source_quality, recency, coverage, consistency, agreement)
        period = max(row.period for row in rows)
        scope_key = dataset_id or "__source__"
        existing = db.scalar(select(models.DataQualityScore).where(
            models.DataQualityScore.source_id == source_id, models.DataQualityScore.scope_key == scope_key,
            models.DataQualityScore.metric == metric, models.DataQualityScore.period == period,
            models.DataQualityScore.method_version == METHOD_VERSION))
        fields = {"dataset_id": dataset_id, "score": result["score"], "source_quality": source_quality,
            "recency": recency, "coverage": coverage, "consistency": consistency,
            "cross_source_agreement": agreement, "sample_size": len(rows), "calculated_at": now,
            "is_official": False, "diagnostics": {"source_quality": source_diagnostics,
                "recency": recency_diagnostics, "coverage": coverage_diagnostics,
                "consistency": consistency_diagnostics, "cross_source_agreement": agreement_diagnostics,
                "formula": "0.30 source_quality + 0.25 recency + 0.20 coverage + 0.15 consistency + 0.10 cross_source_agreement"}}
        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
        else:
            db.add(models.DataQualityScore(source_id=source_id, scope_key=scope_key, metric=metric,
                period=period, method_version=METHOD_VERSION, **fields))
        written += 1
        results.append({"source": source.slug, "dataset_id": dataset_id, "metric": metric,
            "period": period, "score": result["score"], "sample_size": len(rows)})
    db.commit()
    return {"method_version": METHOD_VERSION, "groups_evaluated": len(groups), "scores_written": written,
        "observations_evaluated": len(all_rows), "results": sorted(results, key=lambda row: (row["source"], row["metric"])),
        "is_official": False}
