from collections import Counter, defaultdict
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app import models


def _month_index(value: date) -> int:
    return value.year * 12 + value.month


def _latest_average(rows, metrics):
    matches=[row for row in rows if row.metric in metrics]
    if not matches: return None,None,None
    latest=max(row.period for row in matches); selected=[row for row in matches if row.period==latest]
    unit=Counter(row.unit for row in selected).most_common(1)[0][0]; values=[row.value for row in selected if row.unit==unit]
    return round(sum(values)/len(values),2),unit,latest


def compare_skills(db: Session, skill_ids: list[str]) -> dict:
    ids=list(dict.fromkeys(skill_ids))
    if not 2 <= len(ids) <= 5: raise ValueError("Sélectionnez entre 2 et 5 compétences distinctes")
    skills=db.scalars(select(models.Skill).options(
        selectinload(models.Skill.occupations).selectinload(models.OccupationSkill.occupation)
    ).where(models.Skill.id.in_(ids))).all(); by_id={row.id:row for row in skills}
    missing=[item for item in ids if item not in by_id]
    if missing: raise LookupError(f"Compétences introuvables: {', '.join(missing)}")
    occupation_ids={rel.occupation_id for skill in skills for rel in skill.occupations}
    observations=db.scalars(select(models.Observation).where(or_(
        models.Observation.skill_id.in_(ids),models.Observation.occupation_id.in_(occupation_ids)
    )).order_by(models.Observation.period)).all() if occupation_ids else db.scalars(select(models.Observation).where(models.Observation.skill_id.in_(ids)).order_by(models.Observation.period)).all()
    latest_trends={}
    for trend in db.scalars(select(models.TrendScore).where(models.TrendScore.entity_type=="skill",models.TrendScore.entity_id.in_(ids)).order_by(models.TrendScore.period.desc())).all(): latest_trends.setdefault(trend.entity_id,trend)
    latest_projections={}
    projection_rows=db.execute(select(models.ProspectiveSkillProjection,models.ProspectiveEdition).join(
        models.ProspectiveEdition,models.ProspectiveEdition.id==models.ProspectiveSkillProjection.edition_id
    ).where(models.ProspectiveSkillProjection.skill_id.in_(ids)).order_by(models.ProspectiveEdition.publication_year.desc())).all()
    for projection,edition in projection_rows: latest_projections.setdefault(projection.skill_id,(projection,edition))

    items=[]
    for skill_id in ids:
        skill=by_id[skill_id]; related_ids={rel.occupation_id for rel in skill.occupations}
        direct=[row for row in observations if row.skill_id==skill_id and row.metric=="skill_offer_mentions"]
        signal_rows=direct or [row for row in observations if row.occupation_id in related_ids and row.metric=="job_offers"]
        signal_metric="skill_offer_mentions" if direct else "job_offers_proxy"
        groups=defaultdict(list)
        for row in signal_rows: groups[row.period].append(row.value)
        series=[{"period":period,"value":round(sum(values),2)} for period,values in sorted(groups.items())]
        latest=max((point["period"] for point in series),default=None)
        demand=sum(point["value"] for point in series if latest and 0<=_month_index(latest)-_month_index(point["period"])<12) if latest else None
        evolution=None
        if len(series)>=2 and series[0]["value"]: evolution=round((series[-1]["value"]-series[0]["value"])/abs(series[0]["value"])*100,2)
        proxy_obs=[row for row in observations if row.occupation_id in related_ids]
        salary,salary_unit,salary_period=_latest_average(proxy_obs,{"salary_average","mean_monthly_earnings"})
        tension,tension_unit,tension_period=_latest_average(proxy_obs,{"recruitment_difficulty","tension_index","tension_score"})
        regions=sorted({row.geography_name for row in proxy_obs if row.geography_name and (row.metadata_json or {}).get("geography_level") in {"region","nuts1","nuts2","nuts3"}})
        countries=sorted({row.geography_name for row in proxy_obs if row.geography_name and (row.metadata_json or {}).get("geography_level","country")=="country"})
        trend=latest_trends.get(skill_id); prospective=latest_projections.get(skill_id)
        items.append({"id":skill.id,"name":skill.canonical_name,"skill_type":skill.skill_type,
            "occupations":[{"id":rel.occupation.id,"name":rel.occupation.canonical_name,"sector":rel.occupation.sector,"relationship":rel.relationship_type} for rel in skill.occupations],
            "sectors":sorted({rel.occupation.sector for rel in skill.occupations if rel.occupation.sector}),
            "demand":round(demand,2) if demand is not None else None,"demand_metric":signal_metric,
            "demand_unit":"mention" if direct else "offer","demand_period":latest,"evolution":evolution,"demand_series":series,
            "salary":salary,"salary_unit":salary_unit,"salary_period":salary_period,"tension":tension,"tension_unit":tension_unit,"tension_period":tension_period,
            "regions":regions,"countries":countries,
            "trend":None if not trend else {"score":trend.score,"growth":trend.raw_growth if trend.raw_growth is not None else trend.growth,"period":trend.period,"method_version":trend.method_version,"is_official":False},
            "prospective":None if not prospective else {"projected_change":prospective[0].projected_change,"central_share":prospective[0].central_share,"edition":prospective[1].edition,"horizon_year":prospective[1].horizon_year,"figure_table":prospective[0].figure_table}})

    occupation_sets={row["id"]:{item["id"] for item in row["occupations"]} for row in items}
    occupation_names={item["id"]:item["name"] for row in items for item in row["occupations"]}
    common=set.intersection(*(occupation_sets[row["id"]] for row in items)) if items else set(); pairs=[]
    for index,left in enumerate(items):
        for right in items[index+1:]:
            intersection=occupation_sets[left["id"]]&occupation_sets[right["id"]]; union=occupation_sets[left["id"]]|occupation_sets[right["id"]]
            pairs.append({"left_id":left["id"],"right_id":right["id"],"shared_count":len(intersection),"jaccard":round(100*len(intersection)/len(union),1) if union else 0,"shared_occupations":[occupation_names[item] for item in sorted(intersection,key=lambda item:occupation_names[item])]})
    maxima={"occupations":max((len(row["occupations"]) for row in items),default=1) or 1,"demand":max((row["demand"] or 0 for row in items),default=1) or 1,"geography":max((len(row["regions"])+len(row["countries"]) for row in items),default=1) or 1}
    salary_units={row["salary_unit"] for row in items if row["salary"] is not None}; salary_comparable=len(salary_units)<=1; max_salary=max((row["salary"] or 0 for row in items),default=1) or 1
    radar=[{"skill_id":row["id"],"values":{"métiers":round(100*len(row["occupations"])/maxima["occupations"],1),"demande":round(100*(row["demand"] or 0)/maxima["demand"],1),"tendance":None if not row["trend"] else row["trend"]["score"],"évolution":None if row["evolution"] is None else max(0,min(100,50+row["evolution"]/2)),"tension":None if row["tension"] is None else max(0,min(100,row["tension"])),"géographie":round(100*(len(row["regions"])+len(row["countries"]))/maxima["geography"],1),"salaire":round(100*(row["salary"] or 0)/max_salary,1) if salary_comparable else None}} for row in items]
    matrix=[{"key":key,"label":label,"values":[{"skill_id":row["id"],"value":row.get(key),"unit":row.get(unit_key) if unit_key else unit} for row in items]} for key,label,unit_key,unit in [("demand","Demande · 12 mois","demand_unit",None),("evolution","Évolution",None,"percent"),("salary","Salaire","salary_unit",None),("tension","Tension","tension_unit",None)]]
    return {"skills":items,"radar":{"axes":["métiers","demande","tendance","évolution","tension","géographie","salaire"],"series":radar,"salary_comparable":salary_comparable},"matrix":matrix,
        "overlap":{"common_occupations":[occupation_names[item] for item in sorted(common,key=lambda item:occupation_names[item])],"pairs":pairs},
        "methodology":{"demand":"Mentions directes si disponibles, sinon offres des métiers liés","salary":"Moyenne de la dernière période, sans conversion d'unité","radar":"Normalisation relative aux compétences sélectionnées","is_official":False}}
