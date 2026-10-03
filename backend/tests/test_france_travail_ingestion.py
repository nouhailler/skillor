import asyncio

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app import models
from app.connectors.france_travail import FranceTravailConnector
from app.db import Base
from app.services import ingestion

class FakeFranceTravailConnector:
    async def fetch(self, **_):
        return {"_skillor_kind":"offers","_skillor_dataset":"france_travail_offers_v2","resultats":[{
            "romeCode":"M1805","romeLibelle":"Études et développement informatique",
            "appellationlibelle":"Développeur / Développeuse web","dateCreation":"2026-09-12T10:00:00Z",
            "lieuTravail":{"commune":"75101","libelle":"Paris 1er"},
            "competences":[{"code":"120025","libelle":"Python"}],
        }]}

    def normalize(self, payload): return FranceTravailConnector().normalize(payload)
    def store_raw(self, payload, **_): return "/tmp/france-travail-test.json"
    async def close(self): pass

def test_france_travail_import_links_occupation_and_skill_and_is_idempotent(tmp_path, monkeypatch):
    engine=create_engine(f"sqlite:///{tmp_path}/test.sqlite3")
    Base.metadata.create_all(engine)
    monkeypatch.setitem(ingestion.CONNECTORS,"france_travail",FakeFranceTravailConnector)
    with Session(engine) as db:
        occupation=models.Occupation(canonical_name="développeur web",esco_uri="http://data.europa.eu/esco/occupation/dev")
        skill=models.Skill(canonical_name="Python",esco_uri="http://data.europa.eu/esco/skill/python")
        db.add_all([occupation,skill]); db.flush()
        db.add(models.ExternalOccupationMapping(occupation_id=occupation.id,source_system="rome_v4",
            external_code="M1805",external_label="Études et développement informatique",
            mapping_relation="exactMatch",mapping_method="test",confidence_score=1.0))
        db.commit()
        first=asyncio.run(ingestion.run_import(db,"france_travail",dataset="offers"))
        second=asyncio.run(ingestion.run_import(db,"france_travail",dataset="offers"))
        observations=db.scalars(select(models.Observation)).all()
        assert first.status == second.status == "success"
        assert len(observations) == 2
        assert {row.metric for row in observations} == {"job_offers","skill_offer_mentions"}
        assert all(row.occupation_id == occupation.id for row in observations)
        skill_observation=next(row for row in observations if row.metric == "skill_offer_mentions")
        assert skill_observation.skill_id == skill.id
        assert db.scalar(select(func.count(models.Observation.id))) == 2
