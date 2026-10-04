import hashlib
import json
from datetime import date, datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app import models
from app.config import settings
from app.connectors import EscoConnector, EurostatConnector, FranceTravailConnector
from app.eurostat_catalog import eurostat_profiles
from app.services.occupation_mapping import resolve_occupation, resolve_skill
from app.services.search import index_entity
from app.services.trend_analytics import recompute_skill_trends

CONNECTORS = {"esco": EscoConnector, "eurostat": EurostatConnector, "france_travail": FranceTravailConnector}

async def run_eurostat_catalog_import(db: Session, profiles: str | list[str] | None = None,
                                     geography: str = "FR", since: int = 2021) -> list[models.ImportJob]:
    jobs = []
    for profile in eurostat_profiles(profiles):
        jobs.append(await run_import(db, "eurostat", profile=profile, geography=geography, since=since))
    return jobs

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

def _observation_key(slug: str, dataset: str, row: dict) -> str:
    identity = {
        "source": slug, "dataset": dataset, "esco_uri": row.get("esco_uri"), "isco_code": row.get("isco_code"),
        "metric": row["metric"], "unit": row["unit"], "period": _period(row.get("period")).isoformat(),
        "geography_code": row.get("geography_code", "FR"), "dimensions": row.get("dimensions", {}),
        "external_occupation_code": row.get("occupation_external_code"),
        "external_occupation_label": row.get("occupation_label"),
        "external_skill_code": row.get("skill_external_code"), "external_skill_label": row.get("skill_label"),
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()

async def run_import(db: Session, slug: str, **parameters) -> models.ImportJob:
    if slug not in CONNECTORS: raise ValueError(f"Connecteur inconnu: {slug}")
    source = _source(db, slug)
    job = models.ImportJob(source_id=source.id, status="running", parameters=parameters)
    db.add(job); db.commit(); db.refresh(job)
    connector = CONNECTORS[slug]()
    try:
        payload = await connector.fetch(**parameters)
        raw_suffix = payload.get("_skillor_profile") or payload.get("_skillor_dataset") or "response"
        raw_suffix = "".join(char if char.isalnum() or char in "-_" else "-" for char in str(raw_suffix))
        job.raw_path = connector.store_raw(payload, suffix=raw_suffix)
        normalized = connector.normalize(payload)
        job.records_fetched = len(normalized.get("entities", [])) + len(normalized.get("relations", [])) if slug == "esco" else len(normalized)
        stored = 0
        if slug == "esco":
            entities_by_uri = {}
            for row in normalized["entities"]:
                model = models.Occupation if row["entity_type"] == "occupation" else models.Skill
                existing = db.scalar(select(model).where(model.esco_uri == row["esco_uri"]))
                if existing:
                    existing.canonical_name = row["canonical_name"]
                    existing.description = row.get("description") or existing.description
                    existing.aliases = row.get("aliases", existing.aliases)
                    existing.multilingual_labels = row.get("multilingual_labels", existing.multilingual_labels)
                    existing.multilingual_descriptions = row.get("multilingual_descriptions", existing.multilingual_descriptions)
                    if row["entity_type"] == "occupation":
                        existing.isco_code = row.get("isco_code") or existing.isco_code
                    else:
                        existing.skill_type = row.get("skill_type") or existing.skill_type
                else:
                    fields = {"canonical_name": row["canonical_name"], "description": row.get("description"), "esco_uri": row["esco_uri"], "aliases": row.get("aliases", {}), "multilingual_labels": row.get("multilingual_labels", {}), "multilingual_descriptions": row.get("multilingual_descriptions", {})}
                    if row["entity_type"] == "occupation": fields["isco_code"] = row.get("isco_code")
                    else: fields["skill_type"] = row.get("skill_type")
                    existing = model(**fields)
                    db.add(existing)
                db.flush()
                entities_by_uri[row["esco_uri"]] = existing
                index_entity(db, row["entity_type"], existing)
                stored += 1
            for relation in normalized["relations"]:
                occupation = entities_by_uri.get(relation["occupation_uri"]) or db.scalar(select(models.Occupation).where(models.Occupation.esco_uri == relation["occupation_uri"]))
                skill = entities_by_uri.get(relation["skill_uri"]) or db.scalar(select(models.Skill).where(models.Skill.esco_uri == relation["skill_uri"]))
                if not occupation or not skill:
                    continue
                existing_relation = db.get(models.OccupationSkill, (occupation.id, skill.id))
                if existing_relation:
                    existing_relation.relationship_type = relation["relationship_type"]
                    existing_relation.weight = relation["weight"]
                    existing_relation.source_id = source.id
                    existing_relation.confidence_score = 1.0
                else:
                    db.add(models.OccupationSkill(occupation_id=occupation.id, skill_id=skill.id, relationship_type=relation["relationship_type"], weight=relation["weight"], source_id=source.id, confidence_score=1.0))
                stored += 1
        else:
            dataset_code = payload.get("_skillor_dataset", slug)
            dataset = db.scalar(select(models.SourceDataset).where(models.SourceDataset.source_id==source.id, models.SourceDataset.external_id==dataset_code))
            if not dataset:
                dataset = models.SourceDataset(source_id=source.id, external_id=dataset_code, name=payload.get("label", dataset_code), version=payload.get("updated"), metadata_json={})
                db.add(dataset); db.flush()
            dataset.name = payload.get("label", dataset.name)
            dataset.version = payload.get("updated") or dataset.version
            dataset.metadata_json = {"profile": payload.get("_skillor_profile"), "family": payload.get("_skillor_family"),
                                     "geography_level": payload.get("_skillor_geography_level"),
                                     "filters": payload.get("_skillor_filters", {})}
            affected_occupations = set()
            affected_skills = set()
            for row in normalized:
                occupation_id = skill_id = None
                resolution = None
                if slug == "france_travail":
                    resolution = resolve_occupation(db, row)
                    occupation_id = resolution.occupation.id if resolution.occupation else None
                    skill = resolve_skill(db, row.get("skill_label"))
                    skill_id = skill.id if skill else None
                    if resolution.occupation:
                        affected_occupations.add(resolution.occupation.id)
                        external_code = row.get("occupation_external_code")
                        external_scheme = row.get("occupation_external_scheme") or "rome_v4"
                        if external_code:
                            mapping = db.scalar(select(models.ExternalOccupationMapping).where(
                                models.ExternalOccupationMapping.occupation_id == resolution.occupation.id,
                                models.ExternalOccupationMapping.source_system == external_scheme,
                                models.ExternalOccupationMapping.external_code == str(external_code),
                            ))
                            if not mapping:
                                mapping = models.ExternalOccupationMapping(
                                    occupation_id=resolution.occupation.id, source_system=external_scheme,
                                    external_code=str(external_code), external_label=row.get("occupation_label"),
                                    mapping_relation="observedMatch", mapping_method=resolution.method,
                                    confidence_score=resolution.confidence, metadata_json={},
                                )
                                db.add(mapping)
                            metadata = dict(mapping.metadata_json or {})
                            aliases = list(metadata.get("observed_aliases", []))
                            for label in (row.get("occupation_label"), row.get("occupation_appellation_label")):
                                if label and label not in aliases: aliases.append(label)
                            metadata["observed_aliases"] = aliases
                            mapping.metadata_json = metadata
                    if skill: affected_skills.add(skill.id)
                    if resolution.occupation and row.get("sector_name") and not resolution.occupation.sector:
                        resolution.occupation.sector = row["sector_name"]
                natural_key = _observation_key(slug, dataset_code, row)
                observation = db.scalar(select(models.Observation).where(models.Observation.natural_key == natural_key))
                fields = {
                    "occupation_id": occupation_id, "skill_id": skill_id, "source_id": source.id,
                    "dataset_id": dataset.id, "metric": row["metric"], "value": row["value"], "unit": row["unit"],
                    "period": _period(row.get("period")), "geography_code": row.get("geography_code", "FR"),
                    "geography_name": row.get("geography_name") or ("France" if row.get("geography_code", "FR") == "FR" else row.get("geography_code", "FR")),
                    "natural_key": natural_key,
                    "metadata_json": {
                        "dimensions": row.get("dimensions", {}), "is_official": True,
                        "dimension_labels": row.get("dimension_labels", {}), "status": row.get("status"),
                        "dataset": row.get("dataset"), "profile": row.get("profile"), "family": row.get("family"),
                        "geography_level": row.get("geography_level", "country"),
                        "occupation_resolution": None if not resolution else {"method": resolution.method, "confidence": resolution.confidence},
                        "external_occupation": {"scheme": row.get("occupation_external_scheme"), "code": row.get("occupation_external_code"), "label": row.get("occupation_label")},
                        "external_skill": {"code": row.get("skill_external_code"), "label": row.get("skill_label")},
                    },
                }
                if observation:
                    for key, value in fields.items(): setattr(observation, key, value)
                else:
                    db.add(models.Observation(**fields))
                stored += 1
            db.flush()
            for occupation_id in affected_occupations:
                index_entity(db, "occupation", db.get(models.Occupation, occupation_id))
            for skill_id in affected_skills:
                index_entity(db, "skill", db.get(models.Skill, skill_id))
        source.last_success_at = datetime.now(timezone.utc)
        job.records_stored = stored; job.status = "success"; job.finished_at = datetime.now(timezone.utc)
        db.commit()
        if slug == "france_travail":
            try:
                recompute_skill_trends(db)
            except Exception as analytics_error:
                db.rollback()
                job = db.get(models.ImportJob, job.id)
                parameters = dict(job.parameters or {})
                parameters["trend_analytics_error"] = str(analytics_error)[:1000]
                job.parameters = parameters
                db.commit()
        db.refresh(job); return job
    except Exception as exc:
        db.rollback()
        job = db.get(models.ImportJob, job.id)
        job.status = "failed"; job.error = str(exc)[:4000]; job.finished_at = datetime.now(timezone.utc)
        db.commit(); db.refresh(job); return job
    finally:
        await connector.close()
