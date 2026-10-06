from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app import models
from app.db import Base
from app.schema_compat import LEGACY_BASELINE_REVISION, adopt_unversioned_schema


def test_adopt_unversioned_create_all_database_preserves_rows(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path}/legacy.sqlite3")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source=models.Source(slug="esco",name="ESCO",source_type="taxonomy")
        occupation=models.Occupation(canonical_name="Data Engineer")
        db.add_all([source,occupation]); db.commit()
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX ix_observations_natural_key"))
        for statement in [
            "ALTER TABLE occupations DROP COLUMN multilingual_labels",
            "ALTER TABLE occupations DROP COLUMN multilingual_descriptions",
            "ALTER TABLE skills DROP COLUMN multilingual_labels",
            "ALTER TABLE skills DROP COLUMN multilingual_descriptions",
            "ALTER TABLE observations DROP COLUMN natural_key",
            "ALTER TABLE trend_scores DROP COLUMN raw_growth",
            "ALTER TABLE trend_scores DROP COLUMN calculation_metadata",
        ]: connection.execute(text(statement))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
    with engine.begin() as connection:
        assert adopt_unversioned_schema(connection) is True
    inspector=inspect(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM occupations")).scalar()==1
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar()==LEGACY_BASELINE_REVISION
    assert {column["name"] for column in inspector.get_columns("occupations")} >= {"multilingual_labels","multilingual_descriptions"}
    assert {column["name"] for column in inspector.get_columns("trend_scores")} >= {"raw_growth","calculation_metadata"}


def test_versioned_database_is_not_adopted(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path}/versioned.sqlite3"); Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO alembic_version VALUES ('0007_future_of_jobs')"))
        assert adopt_unversioned_schema(connection) is False
