from collections import Counter, defaultdict
from datetime import date
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


REGIONS = {
    "11": {"name": "Île-de-France", "nuts": ["FR10"], "departments": ["75", "77", "78", "91", "92", "93", "94", "95"]},
    "24": {"name": "Centre-Val de Loire", "nuts": ["FRB0"], "departments": ["18", "28", "36", "37", "41", "45"]},
    "27": {"name": "Bourgogne-Franche-Comté", "nuts": ["FRC1", "FRC2"], "departments": ["21", "25", "39", "58", "70", "71", "89", "90"]},
    "28": {"name": "Normandie", "nuts": ["FRD1", "FRD2"], "departments": ["14", "27", "50", "61", "76"]},
    "32": {"name": "Hauts-de-France", "nuts": ["FRE1", "FRE2"], "departments": ["02", "59", "60", "62", "80"]},
    "44": {"name": "Grand Est", "nuts": ["FRF1", "FRF2", "FRF3"], "departments": ["08", "10", "51", "52", "54", "55", "57", "67", "68", "88"]},
    "52": {"name": "Pays de la Loire", "nuts": ["FRG0"], "departments": ["44", "49", "53", "72", "85"]},
    "53": {"name": "Bretagne", "nuts": ["FRH0"], "departments": ["22", "29", "35", "56"]},
    "75": {"name": "Nouvelle-Aquitaine", "nuts": ["FRI1", "FRI2", "FRI3"], "departments": ["16", "17", "19", "23", "24", "33", "40", "47", "64", "79", "86", "87"]},
    "76": {"name": "Occitanie", "nuts": ["FRJ1", "FRJ2"], "departments": ["09", "11", "12", "30", "31", "32", "34", "46", "48", "65", "66", "81", "82"]},
    "84": {"name": "Auvergne-Rhône-Alpes", "nuts": ["FRK1", "FRK2"], "departments": ["01", "03", "07", "15", "26", "38", "42", "43", "63", "69", "73", "74"]},
    "93": {"name": "Provence-Alpes-Côte d’Azur", "nuts": ["FRL0"], "departments": ["04", "05", "06", "13", "83", "84"]},
    "94": {"name": "Corse", "nuts": ["FRM0"], "departments": ["2A", "2B", "20"]},
    "01": {"name": "Guadeloupe", "nuts": ["FRY1"], "departments": ["971"]},
    "02": {"name": "Martinique", "nuts": ["FRY2"], "departments": ["972"]},
    "03": {"name": "Guyane", "nuts": ["FRY3"], "departments": ["973"]},
    "04": {"name": "La Réunion", "nuts": ["FRY4"], "departments": ["974"]},
    "06": {"name": "Mayotte", "nuts": ["FRY5"], "departments": ["976"]},
}

INDICATORS = {
    "demand": {"metrics": ["job_offers"], "aggregation": "sum", "label": "Demande", "fallback_unit": "offer"},
    "evolution": {"metrics": ["job_offers"], "aggregation": "evolution", "label": "Évolution", "fallback_unit": "percent"},
    "tension": {"metrics": ["recruitment_difficulty", "tension_index", "tension_score"], "aggregation": "average", "label": "Tension", "fallback_unit": "score_0_100"},
    "salary": {"metrics": ["salary_average", "mean_monthly_earnings", "salary_min", "salary_max"], "aggregation": "average", "label": "Salaire", "fallback_unit": "EUR/year"},
}


def _normalized(value: str | None) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", value or "").lower() if char.isalnum())


def _region_code(observation: models.Observation) -> str | None:
    code=(observation.geography_code or "").upper().replace(" ", "")
    level=(observation.metadata_json or {}).get("geography_level", "").lower()
    name=_normalized(observation.geography_name)
    for region_code,region in REGIONS.items():
        if name==_normalized(region["name"]): return region_code
        if code in region["nuts"] or any(code.startswith(nuts) for nuts in region["nuts"]): return region_code
    if level in {"region", "nuts1", "nuts2"} and code in REGIONS: return code
    department=code[:3] if code.startswith(("97", "98")) else code[:2]
    for region_code,region in REGIONS.items():
        if department in region["departments"]: return region_code
    return None


def _entity_scope(db: Session, occupation_id: str | None, skill_id: str | None, indicator: str):
    if occupation_id and skill_id: raise ValueError("Filtrez par métier ou par compétence, pas les deux")
    if occupation_id and not db.get(models.Occupation,occupation_id): raise LookupError("Métier introuvable")
    if not skill_id: return occupation_id,None,"direct" if occupation_id else "all"
    skill=db.get(models.Skill,skill_id)
    if not skill: raise LookupError("Compétence introuvable")
    if indicator=="demand":
        direct=db.scalars(select(models.Observation).where(models.Observation.skill_id==skill_id,models.Observation.metric=="skill_offer_mentions")).all()
        if any(_region_code(row) for row in direct): return None,skill_id,"direct_skill_mentions"
    occupation_ids=db.scalars(select(models.OccupationSkill.occupation_id).where(models.OccupationSkill.skill_id==skill_id)).all()
    return occupation_ids,None,"linked_occupations_proxy"


def build_geographic_map(db: Session, indicator: str="demand", occupation_id: str | None=None,
                         skill_id: str | None=None, period: date | None=None) -> dict:
    if indicator not in INDICATORS: raise ValueError("Indicateur cartographique inconnu")
    spec=INDICATORS[indicator]
    occupation_scope,direct_skill_id,scope_method=_entity_scope(db,occupation_id,skill_id,indicator)
    metrics=["skill_offer_mentions"] if scope_method=="direct_skill_mentions" else spec["metrics"]
    stmt=select(models.Observation,models.Source.name).join(models.Source,models.Source.id==models.Observation.source_id).where(models.Observation.metric.in_(metrics))
    if isinstance(occupation_scope,str): stmt=stmt.where(models.Observation.occupation_id==occupation_scope)
    elif occupation_scope is not None: stmt=stmt.where(models.Observation.occupation_id.in_(occupation_scope))
    if direct_skill_id: stmt=stmt.where(models.Observation.skill_id==direct_skill_id)
    rows=[(row,source) for row,source in db.execute(stmt.order_by(models.Observation.period)).all() if _region_code(row)]
    selected_metric=next((metric for metric in metrics if any(row.metric==metric for row,_ in rows)),metrics[0])
    rows=[item for item in rows if item[0].metric==selected_metric]
    available_periods=sorted({row.period for row,_ in rows},reverse=True)
    selected_period=period if period in available_periods else (available_periods[0] if available_periods else None)
    if period and period not in available_periods: raise LookupError("Période introuvable pour cette sélection")
    dominant_unit=Counter(row.unit for row,_ in rows).most_common(1)[0][0] if rows else spec["fallback_unit"]
    rows=[item for item in rows if item[0].unit==dominant_unit]
    by_region=defaultdict(list)
    for row,source in rows: by_region[_region_code(row)].append((row,source))
    values={}; details={}
    for region_code,region_rows in by_region.items():
        by_period=defaultdict(list)
        for row,source in region_rows: by_period[row.period].append(row.value)
        if spec["aggregation"]=="evolution":
            timeline=sorted((key,sum(values)) for key,values in by_period.items() if not selected_period or key<=selected_period)[-12:]
            value=round(100*(timeline[-1][1]-timeline[0][1])/abs(timeline[0][1]),2) if len(timeline)>=2 and timeline[0][1] else None
            region_period=timeline[-1][0] if timeline else None
            sample_size=sum(len(by_period[key]) for key,_ in timeline)
        else:
            current=[row for row,_ in region_rows if row.period==selected_period]
            value=(sum(row.value for row in current) if spec["aggregation"]=="sum" else sum(row.value for row in current)/len(current)) if current else None
            value=round(value,2) if value is not None else None; region_period=selected_period; sample_size=len(current)
        values[region_code]=value
        details[region_code]={"period":region_period,"sample_size":sample_size,"sources":sorted({source for _,source in region_rows})}
    numeric=[value for value in values.values() if value is not None]
    minimum=min(numeric) if numeric else None; maximum=max(numeric) if numeric else None
    breaks=[round(minimum+(maximum-minimum)*index/5,2) for index in range(6)] if numeric else []
    entity_name=None
    if occupation_id: entity_name=db.get(models.Occupation,occupation_id).canonical_name
    if skill_id: entity_name=db.get(models.Skill,skill_id).canonical_name
    items=[]
    for code,region in REGIONS.items():
        detail=details.get(code,{"period":None,"sample_size":0,"sources":[]})
        items.append({"code":code,"name":region["name"],"geometry_codes":region["nuts"],"value":values.get(code),"unit":"percent" if indicator=="evolution" else dominant_unit,**detail})
    return {"indicator":indicator,"label":spec["label"],"metric":selected_metric,"period":selected_period,
        "available_periods":available_periods,"unit":"percent" if indicator=="evolution" else dominant_unit,
        "items":items,"legend":{"min":minimum,"max":maximum,"breaks":breaks},
        "coverage":{"regions_with_data":len(numeric),"regions_total":len(REGIONS)},
        "filter":{"occupation_id":occupation_id,"skill_id":skill_id,"entity_name":entity_name},
        "methodology":{"aggregation":"Somme à la période sélectionnée" if spec["aggregation"]=="sum" else "Évolution entre la première et la dernière des 12 périodes disponibles" if spec["aggregation"]=="evolution" else "Moyenne à la période sélectionnée",
            "entity_scope":scope_method,"geography":"Rattachement aux régions administratives françaises depuis les codes NUTS, région, département ou commune","geometry":"Eurostat/GISCO NUTS 2024 · EPSG:4326","is_official":False}}
