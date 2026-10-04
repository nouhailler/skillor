import json
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app import models
from app.db import Base
from app.services.future_of_jobs import future_of_jobs, import_wef_edition

def test_wef_import_preserves_edition_provenance_and_compares_observed_trend(tmp_path, monkeypatch):
    engine=create_engine(f"sqlite:///{tmp_path}/future.sqlite3"); Base.metadata.create_all(engine)
    monkeypatch.setattr("app.services.future_of_jobs.settings.raw_data_dir",str(tmp_path/"raw"))
    source_file=tmp_path/"wef.json"
    source_file.write_text(json.dumps({"metadata":{"report_title":"Future of Jobs","edition":"2025","publication_year":2025,"horizon_year":2030,"source_url":"https://example.test/report"},"projections":[{"skill":"AI and big data","category":"technology","central_share":87,"projected_change":42,"figure_table":"Figure 3.2","geography":"Global"}]}),encoding="utf-8")
    with Session(engine) as db:
        skill=models.Skill(canonical_name="AI and big data"); db.add(skill); db.flush()
        db.add(models.TrendScore(entity_type="skill",entity_id=skill.id,period=date(2026,9,1),score=80,growth=75,raw_growth=30,acceleration=50,volume=80,geographic_spread=60,source_confidence=90,method_version="2.0-observed")); db.commit()
        imported=import_wef_edition(db,str(source_file)); result=future_of_jobs(db)
    assert imported["stored"]==1 and imported["resolved"]==1
    assert result["selected_edition"]=="2025" and result["horizon_year"]==2030
    assert result["items"][0]["figure_table"]=="Figure 3.2"
    assert result["items"][0]["observed_growth"]==30
    assert result["items"][0]["difference"]==-12
    assert "causalité" in result["warning"]
