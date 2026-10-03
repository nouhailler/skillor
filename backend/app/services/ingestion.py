from datetime import date, datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app import models
from app.config import settings
from app.connectors import EscoConnector, EurostatConnector, FranceTravailConnector

CONNECTORS = {"esco": EscoConnector, "eurostat": EurostatConnector, "france_travail": FranceTravailConnector}

def _period(value: str | None) -> date:
    if not value:
        return date.today().replace(day=1)
    try:
        if len(value) == 4: return date(int(value), 1, 1)
        if "Q" in value:
            year, quarter = value.split("Q"); return date(int(year), (int(quarter)-1)*3+1, 1)
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return date.today().replace(day=1)

def _source(db: Session, slug: str) -> models.Source:
    source = db.scalar(select(models.Source).where(models.Source.slug == slug))
    if source: return source
    names = {"esco":"ESCO","eurostat":"Eurostat","france_travail":"France Travail"}
    source = models.Source(slug=slug, name=names[slug], source_type="taxonomy" if slug=="esco" else "observed", requires_credentials=slug=="france_travail")
    db.add(source); db.flush(); return source

async def run_import(db: Session, slug: str, **parameters) -> models.ImportJob:
    if slug not in CONNECTORS: raise ValueError(f"Connecteur inconnu: {slug}")
    source = _source(db, slug)
    job = models.ImportJob(source_id=source.id, status="running", parameters=parameters)
    db.add(job); db.commit(); db.refresh(job)
    connector = CONNECTORS[slug]()
    try:
        payload = await connector.fetch(**parameters)
        job.raw_path = connector.store_raw(payload)
        rows = connector.normalize(payload)
        job.records_fetched = len(rows)
        stored = 0
        if slug == "esco":
            for row in rows:
                model = models.Occupation if row["entity_type"] == "occupation" else models.Skill
                existing = db.scalar(select(model).where(model.esco_uri == row["esco_uri"]))
                if existing:
                    existing.canonical_name = row["canonical_name"]
                    existing.description = row.get("description") or existing.description
                else:
                    db.add(model(canonical_name=row["canonical_name"], description=row.get("description"), esco_uri=row["esco_uri"], aliases=row.get("aliases", [])))
                stored += 1
        else:
            dataset_code = payload.get("_skillor_dataset", slug)
            dataset = db.scalar(select(models.SourceDataset).where(models.SourceDataset.source_id==source.id, models.SourceDataset.external_id==dataset_code))
            if not dataset:
                dataset = models.SourceDataset(source_id=source.id, external_id=dataset_code, name=payload.get("label", dataset_code), version=payload.get("updated"))
                db.add(dataset); db.flush()
            for row in rows:
                db.add(models.Observation(source_id=source.id, dataset_id=dataset.id, metric=row["metric"], value=row["value"], unit=row["unit"], period=_period(row.get("period")), geography_code=row.get("geography_code","FR"), geography_name="France" if row.get("geography_code","FR")=="FR" else row.get("geography_code","FR"), metadata_json={"dimensions": row.get("dimensions", {}), "is_official": True}))
                stored += 1
        source.last_success_at = datetime.now(timezone.utc)
        job.records_stored = stored; job.status = "success"; job.finished_at = datetime.now(timezone.utc)
        db.commit(); db.refresh(job); return job
    except Exception as exc:
        db.rollback()
        job = db.get(models.ImportJob, job.id)
        job.status = "failed"; job.error = str(exc)[:4000]; job.finished_at = datetime.now(timezone.utc)
        db.commit(); db.refresh(job); return job
    finally:
        await connector.close()
