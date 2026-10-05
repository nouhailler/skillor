from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app import models
from app.db import Base
from app.services.occupation_compare import compare_occupations

def test_compare_occupations_builds_real_visualization_payload(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path}/compare.sqlite3"); Base.metadata.create_all(engine)
    with Session(engine) as db:
        source=models.Source(slug="ft",name="France Travail",source_type="observed")
        first=models.Occupation(canonical_name="Data Engineer",sector="Tech"); second=models.Occupation(canonical_name="Data Scientist",sector="Tech")
        python=models.Skill(canonical_name="Python",skill_type="skill"); stats=models.Skill(canonical_name="Statistiques",skill_type="knowledge")
        db.add_all([source,first,second,python,stats]); db.flush()
        db.add_all([models.OccupationSkill(occupation_id=first.id,skill_id=python.id),models.OccupationSkill(occupation_id=second.id,skill_id=python.id),models.OccupationSkill(occupation_id=second.id,skill_id=stats.id)])
        for occupation,values in [(first,[10,20]),(second,[20,10])]:
            for month,value in enumerate(values,1): db.add(models.Observation(occupation_id=occupation.id,source_id=source.id,metric="job_offers",value=value,unit="offer",period=date(2026,month,1),geography_code="FR10",geography_name="Île-de-France",metadata_json={"geography_level":"nuts2"}))
        db.add_all([models.Observation(occupation_id=first.id,source_id=source.id,metric="salary_average",value=50000,unit="EUR/year",period=date(2026,2,1)),models.Observation(occupation_id=second.id,source_id=source.id,metric="salary_average",value=60000,unit="EUR/year",period=date(2026,2,1)),models.Observation(occupation_id=first.id,source_id=source.id,metric="recruitment_difficulty",value=80,unit="percent",period=date(2026,2,1))])
        db.commit(); result=compare_occupations(db,[first.id,second.id])
    assert result["occupations"][0]["offers_12m"]==30
    assert result["occupations"][0]["evolution"]==100
    assert result["occupations"][1]["evolution"]==-50
    assert result["occupations"][1]["knowledge"][0]["name"]=="Statistiques"
    assert result["overlap"]["common_skills"]==["Python"]
    assert result["overlap"]["pairs"][0]["jaccard"]==50
    assert result["radar"]["salary_comparable"] is True
    assert len(result["matrix"])==4
