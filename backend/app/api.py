from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from app import models, schemas
from app.config import settings
from app.db import get_db
from app.services.ingestion import run_import

router = APIRouter(prefix="/api/v1")

@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1)); return {"status":"ok", "database":"connected", "version":"1.0.0"}

@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    occupations = db.scalar(select(func.count(models.Occupation.id))) or 0
    skills = db.scalar(select(func.count(models.Skill.id))) or 0
    observed = db.scalar(select(func.count(models.Observation.id))) or 0
    latest = db.scalar(select(func.max(models.Observation.imported_at)))
    top = db.execute(select(models.TrendScore, models.Skill.canonical_name).join(models.Skill, models.Skill.id==models.TrendScore.entity_id).where(models.TrendScore.entity_type=="skill").order_by(models.TrendScore.score.desc()).limit(5)).all()
    return {"kpis":{"occupations":occupations,"skills":skills,"observations":observed,"countries":1},"latest_update":latest,"top_skill_trends":[{"id":trend.entity_id,"name":name,"score":trend.score,"growth":trend.growth,"is_official":False,"method_version":trend.method_version} for trend,name in top],"provenance":{"sources":["ESCO","France Travail","Eurostat"],"mode":"database"}}

@router.get("/search")
def search(q: str = Query(min_length=2, max_length=100), limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    term = f"%{q}%"
    occs = db.scalars(select(models.Occupation).where(models.Occupation.canonical_name.ilike(term)).limit(limit)).all()
    remaining = max(0, limit-len(occs))
    skills = db.scalars(select(models.Skill).where(models.Skill.canonical_name.ilike(term)).limit(remaining)).all()
    return [{"id":x.id,"name":x.canonical_name,"type":"occupation"} for x in occs]+[{"id":x.id,"name":x.canonical_name,"type":"skill"} for x in skills]

@router.get("/occupations", response_model=list[schemas.OccupationOut])
def occupations(q: str | None=None, sector: str | None=None, offset: int=Query(0,ge=0), limit: int=Query(30,ge=1,le=100), db: Session=Depends(get_db)):
    stmt=select(models.Occupation)
    if q: stmt=stmt.where(models.Occupation.canonical_name.ilike(f"%{q}%"))
    if sector: stmt=stmt.where(models.Occupation.sector==sector)
    return db.scalars(stmt.order_by(models.Occupation.canonical_name).offset(offset).limit(limit)).all()

@router.get("/occupations/{occupation_id}")
def occupation_detail(occupation_id: str, db: Session=Depends(get_db)):
    obj=db.scalar(select(models.Occupation).options(selectinload(models.Occupation.skills).selectinload(models.OccupationSkill.skill)).where(models.Occupation.id==occupation_id))
    if not obj: raise HTTPException(404,"Métier introuvable")
    observations=db.scalars(select(models.Observation).where(models.Observation.occupation_id==obj.id).order_by(models.Observation.period)).all()
    return {"id":obj.id,"canonical_name":obj.canonical_name,"description":obj.description,"sector":obj.sector,"esco_uri":obj.esco_uri,"isco_code":obj.isco_code,"aliases":obj.aliases,"multilingual_labels":obj.multilingual_labels,"multilingual_descriptions":obj.multilingual_descriptions,"skills":[{"id":rel.skill.id,"name":rel.skill.canonical_name,"relationship":rel.relationship_type,"weight":rel.weight,"skill_type":rel.skill.skill_type,"confidence":rel.confidence_score} for rel in obj.skills],"market":[{"metric":o.metric,"value":o.value,"unit":o.unit,"period":o.period,"is_official":o.metadata_json.get("is_official",True)} for o in observations]}

@router.get("/skills", response_model=list[schemas.SkillOut])
def skills(q: str | None=None, skill_type: str | None=None, offset: int=Query(0,ge=0), limit: int=Query(30,ge=1,le=100), db: Session=Depends(get_db)):
    stmt=select(models.Skill)
    if q: stmt=stmt.where(models.Skill.canonical_name.ilike(f"%{q}%"))
    if skill_type: stmt=stmt.where(models.Skill.skill_type==skill_type)
    return db.scalars(stmt.order_by(models.Skill.canonical_name).offset(offset).limit(limit)).all()

@router.get("/skills/{skill_id}")
def skill_detail(skill_id: str, db: Session=Depends(get_db)):
    obj=db.scalar(select(models.Skill).options(selectinload(models.Skill.occupations).selectinload(models.OccupationSkill.occupation)).where(models.Skill.id==skill_id))
    if not obj: raise HTTPException(404,"Compétence introuvable")
    trend=db.scalar(select(models.TrendScore).where(models.TrendScore.entity_id==obj.id).order_by(models.TrendScore.period.desc()))
    return {"id":obj.id,"canonical_name":obj.canonical_name,"description":obj.description,"skill_type":obj.skill_type,"esco_uri":obj.esco_uri,"aliases":obj.aliases,"multilingual_labels":obj.multilingual_labels,"multilingual_descriptions":obj.multilingual_descriptions,"occupations":[{"id":rel.occupation.id,"name":rel.occupation.canonical_name,"relationship":rel.relationship_type,"weight":rel.weight} for rel in obj.occupations],"trend":None if not trend else {"score":trend.score,"growth":trend.growth,"method_version":trend.method_version,"is_official":False}}

@router.get("/trends/skills", response_model=list[schemas.TrendOut])
def skill_trends(limit: int=Query(20,ge=1,le=100), db: Session=Depends(get_db)):
    rows=db.execute(select(models.TrendScore,models.Skill.canonical_name).join(models.Skill,models.Skill.id==models.TrendScore.entity_id).where(models.TrendScore.entity_type=="skill").order_by(models.TrendScore.score.desc()).limit(limit)).all()
    return [schemas.TrendOut(entity_id=t.entity_id,name=n,score=t.score,growth=t.growth,period=t.period,method_version=t.method_version,is_official=False) for t,n in rows]

@router.get("/sources")
def sources(db: Session=Depends(get_db)):
    rows=db.scalars(select(models.Source).order_by(models.Source.name)).all()
    return [{"id":x.id,"slug":x.slug,"name":x.name,"type":x.source_type,"enabled":x.enabled,"requires_credentials":x.requires_credentials,"last_success_at":x.last_success_at} for x in rows]

@router.post("/imports/{source}", response_model=schemas.ImportOut)
async def import_source(source: str, query: str="data", limit: int=50, max_relation_skills: int | None=None, x_admin_key: str | None=Header(None), db: Session=Depends(get_db)):
    if not settings.admin_api_key or x_admin_key != settings.admin_api_key: raise HTTPException(403,"Clé d'administration requise")
    job=await run_import(db,source,query=query,limit=limit,max_relation_skills=max_relation_skills)
    if job.status=="failed": raise HTTPException(502,{"job_id":job.id,"error":job.error})
    return job
