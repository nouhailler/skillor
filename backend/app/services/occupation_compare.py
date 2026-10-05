from collections import Counter, defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models


def _month_index(value: date) -> int:
    return value.year * 12 + value.month


def _latest_average(rows, metrics):
    matches=[row for row in rows if row.metric in metrics]
    if not matches: return None,None,None
    latest=max(row.period for row in matches); latest_rows=[row for row in matches if row.period==latest]
    unit=Counter(row.unit for row in latest_rows).most_common(1)[0][0]; values=[row.value for row in latest_rows if row.unit==unit]
    return round(sum(values)/len(values),2),unit,latest


def compare_occupations(db: Session, occupation_ids: list[str]) -> dict:
    ids=list(dict.fromkeys(occupation_ids))
    if not 2 <= len(ids) <= 5: raise ValueError("Sélectionnez entre 2 et 5 métiers distincts")
    rows=db.scalars(select(models.Occupation).options(
        selectinload(models.Occupation.skills).selectinload(models.OccupationSkill.skill)
    ).where(models.Occupation.id.in_(ids))).all()
    by_id={row.id:row for row in rows}
    missing=[item for item in ids if item not in by_id]
    if missing: raise LookupError(f"Métiers introuvables: {', '.join(missing)}")
    observations=db.scalars(select(models.Observation).where(models.Observation.occupation_id.in_(ids)).order_by(models.Observation.period)).all()
    obs_by_id=defaultdict(list)
    for row in observations: obs_by_id[row.occupation_id].append(row)
    latest_trends={}
    for trend in db.scalars(select(models.TrendScore).where(models.TrendScore.entity_type=="occupation",models.TrendScore.entity_id.in_(ids)).order_by(models.TrendScore.period.desc())).all(): latest_trends.setdefault(trend.entity_id,trend)

    occupations=[]
    for occupation_id in ids:
        occupation=by_id[occupation_id]; obs=obs_by_id[occupation_id]
        offer_rows=[row for row in obs if row.metric=="job_offers"]
        series=[]
        period_groups=defaultdict(list)
        for row in offer_rows: period_groups[row.period].append(row.value)
        for period,values in sorted(period_groups.items()): series.append({"period":period,"value":round(sum(values),2)})
        latest_offer=max((row.period for row in offer_rows),default=None)
        offers_12m=sum(row.value for row in offer_rows if latest_offer and 0<=_month_index(latest_offer)-_month_index(row.period)<12) if latest_offer else None
        evolution=None
        if len(series)>=2 and series[0]["value"]:
            evolution=round((series[-1]["value"]-series[0]["value"])/abs(series[0]["value"])*100,2)
        salary,salary_unit,salary_period=_latest_average(obs,{"salary_average","mean_monthly_earnings"})
        tension,tension_unit,tension_period=_latest_average(obs,{"recruitment_difficulty","tension_index","tension_score"})
        skill_items=[{"id":rel.skill.id,"name":rel.skill.canonical_name,"type":rel.skill.skill_type,"relationship":rel.relationship_type} for rel in occupation.skills]
        regions=sorted({row.geography_name for row in obs if (row.metadata_json or {}).get("geography_level") in {"region","nuts1","nuts2","nuts3"}})
        countries=sorted({row.geography_name for row in obs if (row.metadata_json or {}).get("geography_level","country")=="country"})
        trend=latest_trends.get(occupation_id)
        occupations.append({"id":occupation.id,"name":occupation.canonical_name,"sector":occupation.sector,
            "skills":[item for item in skill_items if item["type"]!="knowledge"],"knowledge":[item for item in skill_items if item["type"]=="knowledge"],
            "offers_12m":round(offers_12m,2) if offers_12m is not None else None,"offers_period":latest_offer,
            "evolution":evolution,"salary":salary,"salary_unit":salary_unit,"salary_period":salary_period,
            "tension":tension,"tension_unit":tension_unit,"tension_period":tension_period,
            "regions":regions,"countries":countries,"offer_series":series,
            "trend":None if not trend else {"score":trend.score,"growth":trend.raw_growth if trend.raw_growth is not None else trend.growth,"period":trend.period,"method_version":trend.method_version,"is_official":False}})

    skill_sets={row["id"]:{item["id"] for item in row["skills"]+row["knowledge"]} for row in occupations}
    skill_names={item["id"]:item["name"] for row in occupations for item in row["skills"]+row["knowledge"]}
    common=set.intersection(*(skill_sets[row["id"]] for row in occupations)) if occupations else set()
    pairs=[]
    for index,left in enumerate(occupations):
        for right in occupations[index+1:]:
            intersection=skill_sets[left["id"]]&skill_sets[right["id"]]; union=skill_sets[left["id"]]|skill_sets[right["id"]]
            pairs.append({"left_id":left["id"],"right_id":right["id"],"shared_count":len(intersection),
                "jaccard":round(100*len(intersection)/len(union),1) if union else 0,
                "shared_skills":[skill_names[item] for item in sorted(intersection,key=lambda item:skill_names[item])]})

    maxima={"skill_breadth":max((len(row["skills"])+len(row["knowledge"]) for row in occupations),default=1) or 1,
        "offers":max((row["offers_12m"] or 0 for row in occupations),default=1) or 1,
        "geography":max((len(row["regions"])+len(row["countries"]) for row in occupations),default=1) or 1}
    salary_units={row["salary_unit"] for row in occupations if row["salary"] is not None}; salary_comparable=len(salary_units)<=1
    max_salary=max((row["salary"] or 0 for row in occupations),default=1) or 1
    radar=[]
    for row in occupations:
        radar.append({"occupation_id":row["id"],"values":{"compétences":round(100*(len(row["skills"])+len(row["knowledge"]))/maxima["skill_breadth"],1),
            "offres":round(100*(row["offers_12m"] or 0)/maxima["offers"],1),"évolution":None if row["evolution"] is None else max(0,min(100,50+row["evolution"]/2)),
            "salaire":round(100*(row["salary"] or 0)/max_salary,1) if salary_comparable else None,
            "tension":max(0,min(100,row["tension"] or 0)),"géographie":round(100*(len(row["regions"])+len(row["countries"]))/maxima["geography"],1)}})
    matrix=[{"key":key,"label":label,"values":[{"occupation_id":row["id"],"value":row.get(key),"unit":row.get(unit_key) if unit_key else unit} for row in occupations]}
        for key,label,unit_key,unit in [("offers_12m","Offres · 12 mois",None,"offer"),("evolution","Évolution",None,"percent"),("salary","Salaire","salary_unit",None),("tension","Tension","tension_unit",None)]]
    return {"occupations":occupations,"radar":{"axes":["compétences","offres","évolution","salaire","tension","géographie"],"series":radar,"salary_comparable":salary_comparable},
        "matrix":matrix,"overlap":{"common_skills":[skill_names[item] for item in sorted(common,key=lambda item:skill_names[item])],"pairs":pairs},
        "methodology":{"offers":"Somme des 12 dernières périodes mensuelles","evolution":"Première à dernière période d'offres","salary":"Moyenne de la dernière période, sans conversion d'unité","tension":"Moyenne de la dernière période disponible","radar":"Normalisation relative aux métiers sélectionnés","is_official":False}}
