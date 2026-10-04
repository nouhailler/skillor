from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models
from app.db import Base
from app.services.search import rebuild_search_index, search_entities, search_filters


def test_search_indexes_aliases_languages_codes_and_external_sources(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/search.sqlite3")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        occupation = models.Occupation(
            canonical_name="Développeur logiciel",
            description="Conçoit des applications.",
            sector="Technologie",
            esco_uri="http://data.europa.eu/esco/occupation/abc-123",
            isco_code="2512",
            aliases={"fr": ["Programmeur"]},
            multilingual_labels={"en": "Software developer", "de": "Softwareentwickler"},
        )
        skill = models.Skill(
            canonical_name="Python",
            skill_type="skill",
            esco_uri="http://data.europa.eu/esco/skill/python",
            aliases={"en": ["Python programming"]},
            multilingual_labels={"fr": "Programmation Python"},
        )
        db.add_all([occupation, skill])
        db.flush()
        db.add_all([
            models.ExternalOccupationMapping(
                occupation_id=occupation.id, source_system="rome_v4", external_code="M1805",
                external_label="Études et développement informatique", mapping_relation="exactMatch",
                mapping_method="test", confidence_score=1.0,
            ),
            models.ExternalOccupationMapping(
                occupation_id=occupation.id, source_system="onet", external_code="15-1252",
                external_label="Software Developers", mapping_relation="closeMatch",
                mapping_method="test", confidence_score=0.8,
            ),
        ])
        db.commit()
        assert rebuild_search_index(db) >= 12

        typo = search_entities(db, "programuer")
        english = search_entities(db, "software developer", language="en", source="esco")
        rome = search_entities(db, "M1805", source="rome_v4")
        onet = search_entities(db, "15-1252", source="onet")
        isco = search_entities(db, "2512", source="isco")
        python = search_entities(db, "pythn", entity_type="skill")
        excluded = search_entities(db, "Python", sector="Technologie")
        filters = search_filters(db)

    assert typo[0]["name"] == "Développeur logiciel"
    assert typo[0]["match_type"] == "fuzzy"
    assert english[0]["matched_language"] == "en"
    assert any(item["value"] == "M1805" for item in rome[0]["identifiers"])
    assert onet[0]["matched_source"] == "onet"
    assert isco[0]["matched_term"] == "2512"
    assert python[0]["name"] == "Python"
    assert excluded == []
    assert {"esco", "isco", "onet", "rome_v4", "skillor"}.issubset(filters["sources"])
    assert {"de", "en", "fr"}.issubset(filters["languages"])
