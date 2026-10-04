from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import models
from app.db import Base
from app.services.trend_analytics import METHOD_VERSION, recompute_skill_trends


def test_trend_pipeline_derives_and_upserts_components_from_history(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/trend-analytics.sqlite3")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source = models.Source(slug="france_travail", name="France Travail", source_type="observed")
        skill = models.Skill(canonical_name="Python")
        db.add_all([source, skill]); db.flush()
        for period, value, geography in [
            (date(2026, 1, 1), 10, "FR10"),
            (date(2026, 2, 1), 20, "FR10"),
            (date(2026, 3, 1), 30, "FR20"),
        ]:
            db.add(models.Observation(skill_id=skill.id, source_id=source.id,
                metric="skill_offer_mentions", value=value, unit="mention", period=period,
                geography_code=geography, geography_name=geography,
                metadata_json={"is_official": True, "geography_level": "nuts2"}))
        db.commit()

        result = recompute_skill_trends(db)
        again = recompute_skill_trends(db)
        scores = db.scalars(select(models.TrendScore).order_by(models.TrendScore.period)).all()

    assert result["method_version"] == METHOD_VERSION
    assert result["scores_written"] == 2
    assert again["scores_written"] == 2
    assert len(scores) == 2
    assert scores[-1].raw_growth == 50
    assert scores[-1].growth == 75
    assert scores[-1].acceleration == 25
    assert scores[-1].calculation_metadata["signal"] == "direct_skill_observations"
    assert scores[-1].calculation_metadata["observation_count"] == 1
    assert scores[-1].is_official is False
