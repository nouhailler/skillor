from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app import models
from app.db import Base
from app.services.skill_compare import compare_skills

def test_compare_skills_builds_market_overlap_and_radar(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path}/skill-compare.sqlite3"); Base.metadata.create_all(engine)
    with Session(engine) as db:
        source=models.Source(slug="ft",name="France Travail",source_type="observed")
        first=models.Skill(canonical_name="Python",skill_type="skill"); second=models.Skill(canonical_name="SQL",skill_type="skill")
        shared=models.Occupation(canonical_name="Data Engineer",sector="Tech"); extra=models.Occupation(canonical_name="Data Scientist",sector="Tech")
        db.add_all([source,first,second,shared,extra]); db.flush()
        db.add_all([models.OccupationSkill(occupation_id=shared.id,skill_id=first.id),models.OccupationSkill(occupation_id=shared.id,skill_id=second.id),models.OccupationSkill(occupation_id=extra.id,skill_id=first.id)])
        for skill,values in [(first,[10,20]),(second,[5,15])]:
            for month,value in enumerate(values,1): db.add(models.Observation(skill_id=skill.id,source_id=source.id,metric="skill_offer_mentions",value=value,unit="mention",period=date(2026,month,1)))
        db.add(models.Observation(occupation_id=shared.id,source_id=source.id,metric="salary_average",value=50000,unit="EUR/year",period=date(2026,2,1)))
        db.add(models.TrendScore(entity_type="skill",entity_id=first.id,period=date(2026,2,1),score=80,growth=70,raw_growth=40,acceleration=50,volume=80,geographic_spread=50,source_confidence=90,method_version="2.0-observed"))
        db.commit(); result=compare_skills(db,[first.id,second.id])
    assert result["skills"][0]["demand"]==30
    assert result["skills"][0]["demand_metric"]=="skill_offer_mentions"
    assert result["skills"][0]["trend"]["score"]==80
    assert result["overlap"]["common_occupations"]==["Data Engineer"]
    assert result["overlap"]["pairs"][0]["jaccard"]==50
    assert result["radar"]["salary_comparable"] is True
    assert len(result["matrix"])==4
