from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models
from app.db import Base
from app.services.skill_profile import build_skill_profile


def test_skill_profile_aggregates_related_occupation_data(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/skill-profile.sqlite3")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source = models.Source(slug="france_travail", name="France Travail", source_type="observed")
        skill = models.Skill(canonical_name="Python", skill_type="skill")
        neighbor = models.Skill(canonical_name="SQL", skill_type="skill")
        occupation = models.Occupation(canonical_name="Data Engineer", sector="Technologie")
        db.add_all([source, skill, neighbor, occupation]); db.flush()
        db.add_all([
            models.OccupationSkill(occupation_id=occupation.id, skill_id=skill.id, source_id=source.id),
            models.OccupationSkill(occupation_id=occupation.id, skill_id=neighbor.id, source_id=source.id),
            models.Observation(occupation_id=occupation.id, source_id=source.id, metric="job_offers",
                value=12, unit="offer", period=date(2026, 9, 1), geography_code="FR10",
                geography_name="Île-de-France", metadata_json={"geography_level": "nuts2"}),
            models.Observation(occupation_id=occupation.id, source_id=source.id, metric="salary_average",
                value=48000, unit="EUR/year", period=date(2026, 9, 1), geography_code="FR10",
                geography_name="Île-de-France", metadata_json={"geography_level": "nuts2"}),
            models.TrendScore(entity_type="skill", entity_id=skill.id, period=date(2026, 9, 1),
                score=80, growth=25, acceleration=70, volume=70, geographic_spread=50,
                source_confidence=90, method_version="1.0"),
        ])
        db.commit()
        profile = build_skill_profile(db, skill.id)

    assert profile["occupations"][0]["offers"] == 12
    assert profile["sectors"] == [{"name": "Technologie", "occupation_count": 1, "offers": 12.0}]
    assert profile["regions"][0]["code"] == "FR10"
    assert profile["neighbors"][0]["name"] == "SQL"
    assert profile["trend"]["score"] == 80
    assert profile["sources"][0]["observation_count"] == 2
