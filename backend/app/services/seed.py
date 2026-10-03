from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session
from app import models
from app.services.scoring import TrendComponents, trend_score

OCCUPATIONS = [
    ("Data Scientist", "Analyse et modélise des données pour éclairer les décisions.", "Technologie", "18 420", 16.8, 74),
    ("Data Engineer", "Conçoit les architectures et pipelines de données.", "Technologie", "14 870", 22.4, 82),
    ("Ingénieur·e cybersécurité", "Protège les systèmes, réseaux et données.", "Technologie", "12 640", 29.1, 89),
    ("Infirmier·ère", "Prodigue des soins et accompagne les patients.", "Santé", "38 210", 8.7, 91),
    ("Technicien·ne maintenance", "Maintient et fiabilise les équipements industriels.", "Industrie", "27 560", 11.2, 86),
    ("Responsable RSE", "Pilote la stratégie sociale et environnementale.", "Conseil", "6 420", 18.9, 68),
]
SKILLS = [
    ("IA générative", "Technologie", 38, 92), ("Cybersécurité cloud", "Technologie", 29, 88),
    ("Pensée analytique", "Cognitive", 21, 84), ("Analyse du cycle de vie", "Environnement", 24, 82),
    ("Orchestration de données", "Data", 21, 79), ("Leadership collaboratif", "Relationnelle", 12, 73),
]

def seed_database(db: Session) -> None:
    if db.scalar(select(models.Source.id).limit(1)):
        return
    sources = {
        "esco": models.Source(slug="esco", name="ESCO", source_type="taxonomy", base_url="https://ec.europa.eu/esco/api"),
        "france_travail": models.Source(slug="france_travail", name="France Travail", source_type="observed", base_url="https://api.francetravail.io", requires_credentials=True),
        "eurostat": models.Source(slug="eurostat", name="Eurostat", source_type="observed", base_url="https://ec.europa.eu/eurostat/api"),
    }
    db.add_all(sources.values()); db.flush()
    occupations = []
    for name, desc, sector, _, growth, tension in OCCUPATIONS:
        occ = models.Occupation(canonical_name=name, description=desc, sector=sector)
        db.add(occ); db.flush(); occupations.append(occ)
        db.add(models.Observation(occupation_id=occ.id, source_id=sources["france_travail"].id, metric="growth", value=growth, unit="percent", period=date(2026,9,30)))
        db.add(models.Observation(occupation_id=occ.id, source_id=sources["france_travail"].id, metric="tension_index", value=tension, unit="score_0_100", period=date(2026,9,30), metadata_json={"is_official": False, "method_version": "1.0"}))
    skills = []
    for name, kind, growth, score in SKILLS:
        skill = models.Skill(canonical_name=name, skill_type=kind)
        db.add(skill); db.flush(); skills.append(skill)
        detail = trend_score(TrendComponents(growth=min(100,growth*2), acceleration=score, volume=78, geographic_spread=72, source_confidence=86))
        db.add(models.TrendScore(entity_type="skill", entity_id=skill.id, period=date(2026,9,30), score=detail["score"], growth=growth, acceleration=score, volume=78, geographic_spread=72, source_confidence=86))
    links = [(0,0),(0,2),(1,4),(1,0),(2,1),(3,5),(4,2),(5,3),(5,5)]
    for oi, si in links:
        db.add(models.OccupationSkill(occupation_id=occupations[oi].id, skill_id=skills[si].id, source_id=sources["esco"].id, relationship_type="essential", confidence_score=.86))
    db.commit()
