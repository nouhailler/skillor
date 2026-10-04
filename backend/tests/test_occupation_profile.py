from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models
from app.db import Base
from app.services.occupation_profile import build_occupation_profile


def test_occupation_profile_exposes_six_traceable_sections(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/occupation-profile.sqlite3")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source = models.Source(slug="france_travail", name="France Travail", source_type="observed")
        dataset = models.SourceDataset(source_id=source.id, external_id="offers-v2", name="Offres v2", version="2026-10")
        occupation = models.Occupation(
            canonical_name="Data Engineer", description="Conçoit des pipelines.", sector="Technologie",
            esco_uri="http://data.europa.eu/esco/occupation/data-engineer", isco_code="2511",
            aliases={"fr": ["Ingénieur données"]}, multilingual_labels={"en": "Data engineer"},
        )
        skill = models.Skill(canonical_name="Python", skill_type="skill")
        db.add_all([source, occupation, skill])
        db.flush()
        dataset.source_id = source.id
        db.add(dataset)
        db.add(models.OccupationSkill(
            occupation_id=occupation.id, skill_id=skill.id, relationship_type="essential",
            weight=1.0, confidence_score=0.95, source_id=source.id,
        ))
        db.add(models.ExternalOccupationMapping(
            occupation_id=occupation.id, source_system="rome_v4", external_code="M1805",
            external_label="Études et développement informatique", mapping_relation="exactMatch",
            mapping_method="official_crosswalk", confidence_score=1.0,
        ))
        db.flush()
        db.add_all([
            models.Observation(occupation_id=occupation.id, source_id=source.id, dataset_id=dataset.id,
                metric="job_offers", value=10, unit="offer", period=date(2026, 1, 1),
                geography_code="FR10", geography_name="Île-de-France", metadata_json={"geography_level":"nuts2","is_official":True}),
            models.Observation(occupation_id=occupation.id, source_id=source.id, dataset_id=dataset.id,
                metric="job_offers", value=15, unit="offer", period=date(2026, 2, 1),
                geography_code="FR10", geography_name="Île-de-France", metadata_json={"geography_level":"nuts2","is_official":True}),
            models.Observation(occupation_id=occupation.id, source_id=source.id, dataset_id=dataset.id,
                metric="recruitment_difficulty", value=60, unit="percent", period=date(2026, 2, 1),
                geography_code="FR10", geography_name="Île-de-France", metadata_json={"geography_level":"nuts2","is_official":True}),
            models.Observation(occupation_id=occupation.id, source_id=source.id, dataset_id=dataset.id,
                metric="recruitment_difficulty", value=80, unit="percent", period=date(2026, 2, 1),
                geography_code="FR20", geography_name="Corse", metadata_json={"geography_level":"nuts2","is_official":True}),
        ])
        db.commit()
        profile = build_occupation_profile(db, occupation.id)

    assert profile["canonical_name"] == "Data Engineer"
    assert profile["skills"][0]["relationship"] == "essential"
    assert next(row for row in profile["market_summary"] if row["metric"] == "job_offers")["value"] == 25
    assert next(row for row in profile["market_summary"] if row["metric"] == "recruitment_difficulty")["value"] == 70
    assert len(profile["timeline"]) == 3
    assert {row["geography_code"] for row in profile["geographies"]} == {"FR10", "FR20"}
    assert profile["sources"][0]["source_name"] == "France Travail"
    assert profile["sources"][0]["dataset_code"] == "offers-v2"
    assert profile["sources"][0]["relationship_count"] == 1
    assert profile["market"][0]["source"] == "France Travail"
