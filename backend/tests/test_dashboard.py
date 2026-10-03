from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models
from app.db import Base
from app.services.dashboard import build_dashboard


def test_dashboard_aggregates_real_market_data(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/dashboard.sqlite3")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source = models.Source(
            slug="france_travail",
            name="France Travail",
            source_type="observed",
            last_success_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
        )
        first = models.Occupation(canonical_name="Data Engineer")
        second = models.Occupation(canonical_name="Infirmier")
        skill = models.Skill(canonical_name="Python")
        db.add_all([source, first, second, skill])
        db.flush()

        observations = [
            models.Observation(source_id=source.id, occupation_id=first.id, metric="job_offers", value=10, unit="offer", period=date(2026, 1, 1), geography_code="FR10", geography_name="Île-de-France", metadata_json={"geography_level": "nuts2"}),
            models.Observation(source_id=source.id, occupation_id=first.id, metric="job_offers", value=15, unit="offer", period=date(2026, 2, 1), geography_code="FR10", geography_name="Île-de-France", metadata_json={"geography_level": "nuts2"}),
            models.Observation(source_id=source.id, occupation_id=second.id, metric="job_offers", value=20, unit="offer", period=date(2026, 1, 1), geography_code="DE", geography_name="Allemagne", metadata_json={"geography_level": "country"}),
            models.Observation(source_id=source.id, occupation_id=second.id, metric="job_offers", value=10, unit="offer", period=date(2026, 2, 1), geography_code="DE", geography_name="Allemagne", metadata_json={"geography_level": "country"}),
            models.Observation(source_id=source.id, occupation_id=first.id, metric="salary_average", value=3000, unit="EUR/month", period=date(2026, 2, 1), geography_code="FR", geography_name="France", metadata_json={"geography_level": "country", "dimensions": {"sample_size": 4}}),
            models.Observation(source_id=source.id, occupation_id=first.id, metric="recruitment_difficulty", value=70, unit="percent", period=date(2026, 2, 1), geography_code="FR", geography_name="France", metadata_json={"geography_level": "country"}),
        ]
        db.add_all(observations)
        db.add_all([
            models.TrendScore(entity_type="skill", entity_id=skill.id, period=date(2025, 1, 1), score=90, growth=12, acceleration=0, volume=0, geographic_spread=0, source_confidence=0),
            models.TrendScore(entity_type="skill", entity_id=skill.id, period=date(2026, 1, 1), score=75, growth=8, acceleration=0, volume=0, geographic_spread=0, source_confidence=0),
        ])
        db.commit()

        result = build_dashboard(db)

    assert result["kpis"]["offers_12m"] == 55
    assert result["kpis"]["countries"] == 2
    assert result["kpis"]["regions"] == 1
    assert result["top_occupations_by_offers"][0]["name"] == "Infirmier"
    assert result["top_occupation_trends"][0]["name"] == "Data Engineer"
    assert result["top_occupation_trends"][0]["growth"] == 50
    assert result["salary"]["primary"]["value"] == 3000
    assert result["salary"]["primary"]["sample_size"] == 4
    assert result["tension"]["value"] == 70
    assert result["top_skill_trends"][0]["score"] == 75
