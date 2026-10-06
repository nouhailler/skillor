import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app import models


logger = logging.getLogger("alembic.runtime.migration")
LEGACY_BASELINE_REVISION = "0007_future_of_jobs"
LEGACY_TABLES = (
    models.ExternalOccupationMapping.__table__,
    models.SearchTerm.__table__,
    models.DataQualityScore.__table__,
    models.ProspectiveEdition.__table__,
    models.ProspectiveSkillProjection.__table__,
)

LEGACY_COLUMNS = {
    "occupations": {
        "multilingual_labels": "JSON NOT NULL DEFAULT '{}'",
        "multilingual_descriptions": "JSON NOT NULL DEFAULT '{}'",
    },
    "skills": {
        "multilingual_labels": "JSON NOT NULL DEFAULT '{}'",
        "multilingual_descriptions": "JSON NOT NULL DEFAULT '{}'",
    },
    "observations": {"natural_key": "VARCHAR(64)"},
    "trend_scores": {
        "raw_growth": "FLOAT",
        "calculation_metadata": "JSON NOT NULL DEFAULT '{}'",
    },
}


def adopt_unversioned_schema(connection: Connection) -> bool:
    """Bring pre-Alembic SQLite databases to the last legacy baseline.

    Early Skillor versions used ``metadata.create_all``. Such databases contain
    application tables but no Alembic revision, and create_all cannot add later
    columns. This one-time adoption preserves their rows, completes the known
    schema through revision 0007, and records that baseline so normal migrations
    can continue from there.
    """
    inspector=inspect(connection)
    tables=set(inspector.get_table_names())
    if "sources" not in tables: return False
    if "alembic_version" in tables:
        revision=connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
        if revision: return False
    for table in LEGACY_TABLES:
        table.create(bind=connection,checkfirst=True)
    inspector=inspect(connection)
    for table,column_specs in LEGACY_COLUMNS.items():
        existing={column["name"] for column in inspector.get_columns(table)}
        for column,specification in column_specs.items():
            if column not in existing:
                connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {specification}'))
    connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_observations_natural_key ON observations (natural_key)"))
    connection.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL, CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"))
    connection.execute(text("DELETE FROM alembic_version"))
    connection.execute(text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),{"revision":LEGACY_BASELINE_REVISION})
    logger.warning("Base SQLite historique adoptée à la révision %s sans suppression de données",LEGACY_BASELINE_REVISION)
    return True
