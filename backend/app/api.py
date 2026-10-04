from datetime import date
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from app import models, schemas
from app.config import settings
from app.db import get_db
from app.eurostat_catalog import eurostat_catalog
from app.services.dashboard import build_dashboard
from app.services.ingestion import run_eurostat_catalog_import, run_import
from app.services.occupation_mapping import sync_rome_esco_crosswalk
from app.services.occupation_profile import build_occupation_profile
from app.services.skill_profile import build_skill_profile
from app.services.trend_analytics import recompute_skill_trends
from app.services.search import ensure_search_index, search_entities, search_filters

router = APIRouter(prefix="/api/v1")

@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1)); return {"status":"ok", "database":"connected", "version":"1.0.0"}

@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    return build_dashboard(db)

@router.get("/search")
def search(q: str = Query(min_length=1, max_length=100), entity_type: str | None=Query(None,pattern="^(occupation|skill)$"),
           language: str | None=None, source: str | None=None, sector: str | None=None, skill_type: str | None=None,
           fuzzy: bool=True, limit: int=Query(10,ge=1,le=50), db: Session=Depends(get_db)):
    ensure_search_index(db)
    return search_entities(db,q,entity_type=entity_type,language=language,source=source,sector=sector,
                           skill_type=skill_type,fuzzy=fuzzy,limit=limit)

@router.get("/search/suggestions")
def search_suggestions(q: str=Query(min_length=1,max_length=100), entity_type: str | None=Query(None,pattern="^(occupation|skill)$"),
                       language: str | None=None, source: str | None=None, sector: str | None=None,
                       skill_type: str | None=None, limit: int=Query(8,ge=1,le=20),
                       db: Session=Depends(get_db)):
    ensure_search_index(db)
    return search_entities(db,q,entity_type=entity_type,language=language,source=source,sector=sector,
                           skill_type=skill_type,limit=limit,fuzzy=True)

@router.get("/search/filters")
def available_search_filters(db: Session=Depends(get_db)):
    ensure_search_index(db)
    return search_filters(db)

@router.get("/catalog/occupations")
def occupation_catalog(q: str | None=None, sector: str | None=None, offset: int=Query(0,ge=0),
                       limit: int=Query(30,ge=1,le=100), db: Session=Depends(get_db)):
    stmt=select(models.Occupation).options(selectinload(models.Occupation.skills).selectinload(models.OccupationSkill.skill))
    if q: stmt=stmt.where(models.Occupation.canonical_name.ilike(f"%{q}%"))
    if sector: stmt=stmt.where(models.Occupation.sector==sector)
    occupations=db.scalars(stmt.order_by(models.Occupation.canonical_name).offset(offset).limit(limit)).all()
    ids=[row.id for row in occupations]; metrics={}
    if ids:
        rows=db.execute(select(models.Observation.occupation_id,models.Observation.metric,func.sum(models.Observation.value),func.max(models.Observation.period)).where(models.Observation.occupation_id.in_(ids)).group_by(models.Observation.occupation_id,models.Observation.metric)).all()
        for occupation_id,metric,value,period in rows: metrics.setdefault(occupation_id,{})[metric]={"value":value,"period":period}
    return [{"id":row.id,"canonical_name":row.canonical_name,"description":row.description,"sector":row.sector,
             "esco_uri":row.esco_uri,"isco_code":row.isco_code,
             "skills":[{"id":rel.skill.id,"name":rel.skill.canonical_name,"relationship":rel.relationship_type} for rel in row.skills[:5]],
             "market":metrics.get(row.id,{})} for row in occupations]

@router.get("/catalog/skills")
def skill_catalog(q: str | None=None, skill_type: str | None=None, offset: int=Query(0,ge=0),
                  limit: int=Query(30,ge=1,le=100), db: Session=Depends(get_db)):
    stmt=select(models.Skill).options(selectinload(models.Skill.occupations))
    if q: stmt=stmt.where(models.Skill.canonical_name.ilike(f"%{q}%"))
    if skill_type: stmt=stmt.where(models.Skill.skill_type==skill_type)
    skills=db.scalars(stmt.order_by(models.Skill.canonical_name).offset(offset).limit(limit)).all()
    ids=[row.id for row in skills]; trends={}
    if ids:
        trend_rows=db.scalars(select(models.TrendScore).where(models.TrendScore.entity_type=="skill",models.TrendScore.entity_id.in_(ids)).order_by(models.TrendScore.period.desc())).all()
        for trend in trend_rows: trends.setdefault(trend.entity_id,trend)
    return [{"id":row.id,"canonical_name":row.canonical_name,"description":row.description,
             "skill_type":row.skill_type,"esco_uri":row.esco_uri,"occupation_count":len(row.occupations),
             "trend":None if row.id not in trends else {"score":trends[row.id].score,"growth":trends[row.id].raw_growth if trends[row.id].raw_growth is not None else trends[row.id].growth,
                                                        "period":trends[row.id].period,"method_version":trends[row.id].method_version,
                                                        "is_official":False}} for row in skills]

@router.get("/market/series")
def market_series(metric: str="job_offers", geography_code: str | None=None, db: Session=Depends(get_db)):
    stmt=select(models.Observation.period,func.sum(models.Observation.value)).where(models.Observation.metric==metric)
    if geography_code: stmt=stmt.where(models.Observation.geography_code==geography_code)
    rows=db.execute(stmt.group_by(models.Observation.period).order_by(models.Observation.period)).all()
    return [{"period":period,"value":value,"metric":metric} for period,value in rows]

@router.get("/market/geographies")
def market_geographies(metric: str="job_offers", limit: int=Query(30,ge=1,le=200), db: Session=Depends(get_db)):
    latest=db.scalar(select(func.max(models.Observation.period)).where(models.Observation.metric==metric))
    if latest is None and metric=="job_offers":
        metric="regional_unemployment_rate"
        latest=db.scalar(select(func.max(models.Observation.period)).where(models.Observation.metric==metric))
    if latest is None: return {"metric":metric,"period":None,"items":[]}
    rows=db.execute(select(models.Observation.geography_code,models.Observation.geography_name,func.sum(models.Observation.value),models.Observation.unit).where(models.Observation.metric==metric,models.Observation.period==latest).group_by(models.Observation.geography_code,models.Observation.geography_name,models.Observation.unit).order_by(func.sum(models.Observation.value).desc()).limit(limit)).all()
    return {"metric":metric,"period":latest,"items":[{"code":code,"name":name,"value":value,"unit":unit} for code,name,value,unit in rows]}

@router.get("/occupations", response_model=list[schemas.OccupationOut])
def occupations(q: str | None=None, sector: str | None=None, offset: int=Query(0,ge=0), limit: int=Query(30,ge=1,le=100), db: Session=Depends(get_db)):
    stmt=select(models.Occupation)
    if q: stmt=stmt.where(models.Occupation.canonical_name.ilike(f"%{q}%"))
    if sector: stmt=stmt.where(models.Occupation.sector==sector)
    return db.scalars(stmt.order_by(models.Occupation.canonical_name).offset(offset).limit(limit)).all()

@router.get("/occupations/{occupation_id}")
def occupation_detail(occupation_id: str, db: Session=Depends(get_db)):
    profile=build_occupation_profile(db,occupation_id)
    if not profile: raise HTTPException(404,"Métier introuvable")
    return profile

@router.get("/skills", response_model=list[schemas.SkillOut])
def skills(q: str | None=None, skill_type: str | None=None, offset: int=Query(0,ge=0), limit: int=Query(30,ge=1,le=100), db: Session=Depends(get_db)):
    stmt=select(models.Skill)
    if q: stmt=stmt.where(models.Skill.canonical_name.ilike(f"%{q}%"))
    if skill_type: stmt=stmt.where(models.Skill.skill_type==skill_type)
    return db.scalars(stmt.order_by(models.Skill.canonical_name).offset(offset).limit(limit)).all()

@router.get("/skills/{skill_id}")
def skill_detail(skill_id: str, db: Session=Depends(get_db)):
    profile=build_skill_profile(db,skill_id)
    if not profile: raise HTTPException(404,"Compétence introuvable")
    return profile

@router.get("/trends/skills", response_model=list[schemas.TrendOut])
def skill_trends(limit: int=Query(20,ge=1,le=100), db: Session=Depends(get_db)):
    rows=db.execute(select(models.TrendScore,models.Skill.canonical_name).join(models.Skill,models.Skill.id==models.TrendScore.entity_id).where(models.TrendScore.entity_type=="skill").order_by(models.TrendScore.score.desc()).limit(limit)).all()
    return [schemas.TrendOut(entity_id=t.entity_id,name=n,score=t.score,growth=t.raw_growth if t.raw_growth is not None else t.growth,
            period=t.period,method_version=t.method_version,is_official=False,
            components={"growth":t.growth,"acceleration":t.acceleration,"volume":t.volume,
                        "geographic_spread":t.geographic_spread,"source_confidence":t.source_confidence},
            calculation=t.calculation_metadata) for t,n in rows]

@router.post("/trends/recompute")
def recompute_trends(x_admin_key: str | None=Header(None), db: Session=Depends(get_db)):
    if not settings.admin_api_key or x_admin_key != settings.admin_api_key: raise HTTPException(403,"Clé d'administration requise")
    return recompute_skill_trends(db)

@router.get("/sources")
def sources(db: Session=Depends(get_db)):
    rows=db.scalars(select(models.Source).order_by(models.Source.name)).all()
    return [{"id":x.id,"slug":x.slug,"name":x.name,"type":x.source_type,"enabled":x.enabled,"requires_credentials":x.requires_credentials,"last_success_at":x.last_success_at} for x in rows]

@router.get("/sources/france_travail/coverage")
def france_travail_coverage(db: Session=Depends(get_db)):
    source=db.scalar(select(models.Source).where(models.Source.slug=="france_travail"))
    if not source: return {"total":0,"resolved":0,"unresolved":0,"coverage_percent":0.0,"metrics":[]}
    rows=db.execute(select(models.Observation.metric,func.count(models.Observation.id),func.count(models.Observation.occupation_id)).where(models.Observation.source_id==source.id).group_by(models.Observation.metric).order_by(models.Observation.metric)).all()
    metrics=[{"metric":metric,"total":total,"resolved":resolved,"coverage_percent":round(100*resolved/total,1) if total else 0.0} for metric,total,resolved in rows]
    total=sum(row["total"] for row in metrics); resolved=sum(row["resolved"] for row in metrics)
    return {"total":total,"resolved":resolved,"unresolved":total-resolved,"coverage_percent":round(100*resolved/total,1) if total else 0.0,"metrics":metrics}

@router.get("/eurostat/datasets")
def eurostat_datasets(db: Session=Depends(get_db)):
    source=db.scalar(select(models.Source).where(models.Source.slug=="eurostat"))
    imported={}
    if source:
        imported={row.external_id:row for row in db.scalars(select(models.SourceDataset).where(models.SourceDataset.source_id==source.id)).all()}
    return [{"profile":profile,**spec,"imported":spec["code"] in imported,
             "last_update":imported[spec["code"]].version if spec["code"] in imported else None}
            for profile,spec in eurostat_catalog().items()]

@router.get("/eurostat/indicators")
def eurostat_indicators(metric: str | None=None, geography_code: str | None=None,
                        geography_level: str | None=None, since: date | None=None,
                        limit: int=Query(500,ge=1,le=5000), db: Session=Depends(get_db)):
    source=db.scalar(select(models.Source).where(models.Source.slug=="eurostat"))
    if not source: return []
    stmt=select(models.Observation).where(models.Observation.source_id==source.id)
    if metric: stmt=stmt.where(models.Observation.metric==metric)
    if geography_code: stmt=stmt.where(models.Observation.geography_code==geography_code)
    if since: stmt=stmt.where(models.Observation.period>=since)
    rows=db.scalars(stmt.order_by(models.Observation.period.desc(),models.Observation.geography_code).limit(5000)).all()
    selected=[row for row in rows if not geography_level or row.metadata_json.get("geography_level","country")==geography_level][:limit]
    return [{"metric":row.metric,"value":row.value,"unit":row.unit,"period":row.period,
             "geography_code":row.geography_code,"geography_name":row.geography_name,
             "geography_level":row.metadata_json.get("geography_level","country"),
             "dataset":row.metadata_json.get("dataset"),"profile":row.metadata_json.get("profile"),
             "family":row.metadata_json.get("family"),"dimensions":row.metadata_json.get("dimensions",{}),
             "dimension_labels":row.metadata_json.get("dimension_labels",{}),"status":row.metadata_json.get("status")}
            for row in selected]

@router.post("/imports/{source}", response_model=schemas.ImportOut)
async def import_source(source: str, query: str="data", limit: int=50, max_relation_skills: int | None=None, dataset: str | None=None, profile: str | None=None, territory: str="FR", geography: str="FR", since: int=2021, rome_code: str | None=None, endpoint: str="indicateurs", x_admin_key: str | None=Header(None), db: Session=Depends(get_db)):
    if not settings.admin_api_key or x_admin_key != settings.admin_api_key: raise HTTPException(403,"Clé d'administration requise")
    job=await run_import(db,source,query=query,limit=limit,max_relation_skills=max_relation_skills,dataset=dataset,profile=profile,territory=territory,geography=geography,since=since,rome_code=rome_code,endpoint=endpoint)
    if job.status=="failed": raise HTTPException(502,{"job_id":job.id,"error":job.error})
    return job

@router.post("/imports/eurostat/catalog")
async def import_eurostat_catalog(profiles: str="all", geography: str="FR", since: int=2021,
                                  x_admin_key: str | None=Header(None), db: Session=Depends(get_db)):
    if not settings.admin_api_key or x_admin_key != settings.admin_api_key: raise HTTPException(403,"Clé d'administration requise")
    jobs=await run_eurostat_catalog_import(db,profiles,geography,since)
    return [{"id":job.id,"profile":job.parameters.get("profile"),"status":job.status,
             "records_fetched":job.records_fetched,"records_stored":job.records_stored,"error":job.error} for job in jobs]

@router.post("/imports/france_travail/crosswalk")
async def import_france_travail_crosswalk(x_admin_key: str | None=Header(None), db: Session=Depends(get_db)):
    if not settings.admin_api_key or x_admin_key != settings.admin_api_key: raise HTTPException(403,"Clé d'administration requise")
    try: return await sync_rome_esco_crosswalk(db)
    except Exception as exc: raise HTTPException(502,str(exc)) from exc
