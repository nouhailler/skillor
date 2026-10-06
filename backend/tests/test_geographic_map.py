from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models
from app.db import Base
from app.services.geographic_map import build_geographic_map


def test_geographic_map_rolls_up_departments_and_filters_by_skill(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path}/map.sqlite3"); Base.metadata.create_all(engine)
    with Session(engine) as db:
        source=models.Source(slug="france_travail",name="France Travail",source_type="observed")
        occupation=models.Occupation(canonical_name="Data Engineer")
        skill=models.Skill(canonical_name="Python",skill_type="skill")
        db.add_all([source,occupation,skill]); db.flush()
        db.add(models.OccupationSkill(occupation_id=occupation.id,skill_id=skill.id,source_id=source.id))
        for geography_code,geography_name,month,value in [
            ("75101","Paris 1er",1,10),("92050","Nanterre",1,5),("75101","Paris 1er",2,20),
            ("33063","Bordeaux",1,8),("33063","Bordeaux",2,12),
        ]:
            db.add(models.Observation(occupation_id=occupation.id,source_id=source.id,metric="job_offers",value=value,
                unit="offer",period=date(2026,month,1),geography_code=geography_code,geography_name=geography_name,
                metadata_json={"geography_level":"commune","is_official":True}))
        for metric,value in [("recruitment_difficulty",60),("recruitment_difficulty",80),("salary_average",48000),("salary_average",52000)]:
            db.add(models.Observation(occupation_id=occupation.id,source_id=source.id,metric=metric,value=value,
                unit="percent" if metric=="recruitment_difficulty" else "EUR/year",period=date(2026,2,1),
                geography_code="75",geography_name="Paris",metadata_json={"geography_level":"department","is_official":True}))
        db.commit(); demand=build_geographic_map(db,"demand",skill_id=skill.id); evolution=build_geographic_map(db,"evolution",occupation_id=occupation.id)
        tension=build_geographic_map(db,"tension",occupation_id=occupation.id); salary=build_geographic_map(db,"salary",occupation_id=occupation.id)
    by_name={item["name"]:item for item in demand["items"]}
    assert by_name["Île-de-France"]["value"]==20
    assert by_name["Nouvelle-Aquitaine"]["value"]==12
    assert demand["methodology"]["entity_scope"]=="linked_occupations_proxy"
    evolution_by_name={item["name"]:item for item in evolution["items"]}
    assert evolution_by_name["Île-de-France"]["value"]==round(100*(20-15)/15,2)
    assert evolution["coverage"]["regions_with_data"]==2
    assert next(item for item in tension["items"] if item["name"]=="Île-de-France")["value"]==70
    assert next(item for item in salary["items"] if item["name"]=="Île-de-France")["value"]==50000


def test_geographic_map_prefers_direct_skill_mentions_and_nuts_codes(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path}/map-skill.sqlite3"); Base.metadata.create_all(engine)
    with Session(engine) as db:
        source=models.Source(slug="france_travail",name="France Travail",source_type="observed")
        skill=models.Skill(canonical_name="Python",skill_type="skill")
        db.add_all([source,skill]); db.flush()
        db.add(models.Observation(skill_id=skill.id,source_id=source.id,metric="skill_offer_mentions",value=7,
            unit="mention",period=date(2026,2,1),geography_code="FRK2",geography_name="Rhône-Alpes",
            metadata_json={"geography_level":"nuts2","is_official":True}))
        db.commit(); result=build_geographic_map(db,"demand",skill_id=skill.id)
    region=next(item for item in result["items"] if item["name"]=="Auvergne-Rhône-Alpes")
    assert region["value"]==7
    assert result["metric"]=="skill_offer_mentions"
    assert result["methodology"]["entity_scope"]=="direct_skill_mentions"
