import csv, json
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.services.search import normalize_term


def _load(path: str) -> dict:
    target=Path(path).expanduser().resolve()
    if not target.is_file(): raise ValueError("Fichier prospectif introuvable")
    if target.suffix.lower()==".json": return json.loads(target.read_text(encoding="utf-8"))
    if target.suffix.lower()==".csv":
        with target.open(encoding="utf-8-sig",newline="") as stream: rows=list(csv.DictReader(stream))
        return {"projections":rows}
    raise ValueError("Format accepté : JSON ou CSV")


def _skill_match(skills, label):
    needle=normalize_term(label); scored=[]
    for skill in skills:
        terms=[skill.canonical_name]+[str(x) for values in (skill.aliases or {}).values() for x in (values if isinstance(values,list) else [values])]
        score=max((SequenceMatcher(None,needle,normalize_term(term)).ratio() for term in terms),default=0)
        scored.append((score,skill))
    scored.sort(key=lambda row:row[0],reverse=True)
    if not scored or scored[0][0]<.72: return None,"unresolved",None
    return scored[0][1],"exact_label" if scored[0][0]==1 else "fuzzy_label",round(scored[0][0],3)


def import_wef_edition(db: Session, path: str, report_title: str | None=None, edition: str | None=None,
                       publication_year: int | None=None, horizon_year: int | None=None,
                       source_url: str | None=None) -> dict:
    payload=_load(path); metadata=payload.get("metadata",{})
    report_title=report_title or metadata.get("report_title") or payload.get("report_title")
    edition=edition or metadata.get("edition") or payload.get("edition")
    publication_year=publication_year or metadata.get("publication_year") or payload.get("publication_year")
    horizon_year=horizon_year or metadata.get("horizon_year") or payload.get("horizon_year")
    source_url=source_url or metadata.get("source_url") or payload.get("source_url")
    if not report_title or not edition or not publication_year: raise ValueError("Rapport, édition et année de publication obligatoires")
    projections=payload.get("projections") or []
    if not projections: raise ValueError("Aucune projection dans le fichier")
    source=db.scalar(select(models.Source).where(models.Source.slug=="wef"))
    if not source:
        source=models.Source(slug="wef",name="World Economic Forum",source_type="prospective",base_url="https://www.weforum.org/publications/")
        db.add(source); db.flush()
    record=db.scalar(select(models.ProspectiveEdition).where(models.ProspectiveEdition.source_id==source.id,models.ProspectiveEdition.edition==str(edition)))
    if not record:
        record=models.ProspectiveEdition(source_id=source.id,edition=str(edition),report_title=report_title,publication_year=int(publication_year))
        db.add(record); db.flush()
    record.report_title=report_title; record.publication_year=int(publication_year); record.horizon_year=int(horizon_year) if horizon_year else None; record.source_url=source_url; record.metadata_json=metadata
    raw_dir=Path(settings.raw_data_dir)/"wef"; raw_dir.mkdir(parents=True,exist_ok=True)
    raw_target=raw_dir/f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{normalize_term(str(edition)).replace(' ','-')}.json"
    raw_target.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8"); record.raw_path=str(raw_target)
    db.execute(delete(models.ProspectiveSkillProjection).where(models.ProspectiveSkillProjection.edition_id==record.id))
    skills=db.scalars(select(models.Skill)).all(); resolved=0
    for row in projections:
        label=row.get("skill") or row.get("source_label") or row.get("label")
        figure=row.get("figure_table") or row.get("figure") or row.get("table")
        if not label or not figure or row.get("projected_change") in (None,""): raise ValueError("Chaque projection exige skill, projected_change et figure_table")
        skill,method,confidence=_skill_match(skills,label); resolved+=bool(skill)
        central=row.get("central_share")
        db.add(models.ProspectiveSkillProjection(edition_id=record.id,skill_id=skill.id if skill else None,source_label=label,
            category=row.get("category"),central_share=float(central) if central not in (None,"") else None,
            projected_change=float(row["projected_change"]),figure_table=figure,geography=row.get("geography") or "Global",
            sector=row.get("sector") or None,mapping_method=method,mapping_confidence=confidence,metadata_json=row.get("metadata",{})))
    source.last_success_at=datetime.now(timezone.utc); db.commit()
    return {"edition_id":record.id,"edition":record.edition,"stored":len(projections),"resolved":resolved,"unresolved":len(projections)-resolved,"raw_path":record.raw_path}


def future_of_jobs(db: Session, edition: str | None=None) -> dict:
    editions=db.scalars(select(models.ProspectiveEdition).order_by(models.ProspectiveEdition.publication_year.desc())).all()
    if not editions: return {"editions":[],"selected_edition":None,"items":[],"warning":"Aucune édition prospective importée."}
    selected=next((row for row in editions if row.edition==edition),editions[0])
    projections=db.scalars(select(models.ProspectiveSkillProjection).where(models.ProspectiveSkillProjection.edition_id==selected.id)).all()
    skills={row.id:row for row in db.scalars(select(models.Skill)).all()}
    trends={}
    for row in db.scalars(select(models.TrendScore).where(models.TrendScore.entity_type=="skill").order_by(models.TrendScore.period.desc())).all(): trends.setdefault(row.entity_id,row)
    items=[]
    for row in projections:
        trend=trends.get(row.skill_id); observed_growth=None if not trend else (trend.raw_growth if trend.raw_growth is not None else trend.growth)
        items.append({"id":row.id,"skill_id":row.skill_id,"name":skills[row.skill_id].canonical_name if row.skill_id in skills else row.source_label,
            "source_label":row.source_label,"category":row.category,"central_share":row.central_share,"projected_change":row.projected_change,
            "figure_table":row.figure_table,"geography":row.geography,"sector":row.sector,"mapping_method":row.mapping_method,
            "mapping_confidence":row.mapping_confidence,"observed_growth":observed_growth,"observed_period":None if not trend else trend.period,
            "difference":None if observed_growth is None else round(observed_growth-row.projected_change,2)})
    return {"editions":[{"edition":row.edition,"report_title":row.report_title,"publication_year":row.publication_year,"horizon_year":row.horizon_year,"source_url":row.source_url} for row in editions],
        "selected_edition":selected.edition,"report_title":selected.report_title,"horizon_year":selected.horizon_year,"items":items,
        "warning":"Projection documentaire et observation de marché ne prouvent aucune causalité."}
