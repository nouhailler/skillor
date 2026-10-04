from datetime import date, datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import models
from app.db import Base
from app.services.data_quality import METHOD_VERSION, recompute_data_quality


def test_confidence_pipeline_calculates_five_auditable_inputs(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/quality.sqlite3")
    Base.metadata.create_all(engine)
    now = datetime(2026, 10, 4, tzinfo=timezone.utc)
    with Session(engine) as db:
        first = models.Source(slug="first", name="Première", source_type="observed")
        second = models.Source(slug="second", name="Seconde", source_type="observed")
        occupation = models.Occupation(canonical_name="Data Engineer")
        db.add_all([first, second, occupation]); db.flush()
        first_dataset = models.SourceDataset(source_id=first.id, external_id="offers", name="Offres")
        second_dataset = models.SourceDataset(source_id=second.id, external_id="offers", name="Offres")
        db.add_all([first_dataset, second_dataset]); db.flush()
        db.add(models.ImportJob(source_id=first.id, status="success", records_fetched=1, records_stored=1,
            started_at=now, finished_at=now))
        common = {"metric":"job_offers", "unit":"offer", "period":date(2026,10,1),
            "geography_code":"FR10", "geography_name":"Île-de-France", "occupation_id":occupation.id,
            "imported_at":now, "metadata_json":{"is_official":True,"dimensions":{"rome":"M1805"}}}
        db.add_all([
            models.Observation(source_id=first.id,dataset_id=first_dataset.id,value=100,natural_key="first",**common),
            models.Observation(source_id=second.id,dataset_id=second_dataset.id,value=90,natural_key="second",**common),
        ])
        db.commit()

        result = recompute_data_quality(db, now=now)
        again = recompute_data_quality(db, now=now)
        scores = db.scalars(select(models.DataQualityScore).order_by(models.DataQualityScore.score.desc())).all()

    assert result["method_version"] == METHOD_VERSION
    assert result["scores_written"] == 2
    assert again["scores_written"] == 2
    assert len(scores) == 2
    assert scores[0].source_quality == 95
    assert scores[0].recency == 100
    assert scores[0].coverage == 100
    assert scores[0].consistency == 100
    assert scores[0].cross_source_agreement == 90
    assert scores[0].score == 97.5
    assert scores[0].diagnostics["cross_source_agreement"]["comparison_count"] == 1
    assert scores[0].is_official is False
