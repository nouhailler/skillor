"""Initial Skillor schema."""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("sources", sa.Column("id", sa.String(36), primary_key=True), sa.Column("slug", sa.String(60), nullable=False), sa.Column("name", sa.String(120), nullable=False), sa.Column("source_type", sa.String(40), nullable=False), sa.Column("base_url", sa.String(500)), sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("requires_credentials", sa.Boolean(), nullable=False), sa.Column("last_success_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("slug"))
    op.create_index("ix_sources_slug", "sources", ["slug"])
    op.create_table("occupations", sa.Column("id", sa.String(36), primary_key=True), sa.Column("canonical_name", sa.String(300), nullable=False), sa.Column("description", sa.Text()), sa.Column("esco_uri", sa.String(500)), sa.Column("isco_code", sa.String(30)), sa.Column("sector", sa.String(120)), sa.Column("aliases", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("esco_uri"))
    op.create_index("ix_occupations_canonical_name", "occupations", ["canonical_name"])
    op.create_index("ix_occupations_isco_code", "occupations", ["isco_code"])
    op.create_index("ix_occupations_sector", "occupations", ["sector"])
    op.create_table("skills", sa.Column("id", sa.String(36), primary_key=True), sa.Column("canonical_name", sa.String(300), nullable=False), sa.Column("description", sa.Text()), sa.Column("esco_uri", sa.String(500)), sa.Column("skill_type", sa.String(80)), sa.Column("aliases", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("esco_uri"))
    op.create_index("ix_skills_canonical_name", "skills", ["canonical_name"])
    op.create_index("ix_skills_skill_type", "skills", ["skill_type"])
    op.create_table("source_datasets", sa.Column("id", sa.String(36), primary_key=True), sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False), sa.Column("external_id", sa.String(200), nullable=False), sa.Column("name", sa.String(300), nullable=False), sa.Column("version", sa.String(80)), sa.Column("metadata_json", sa.JSON(), nullable=False), sa.UniqueConstraint("source_id", "external_id"))
    op.create_index("ix_source_datasets_source_id", "source_datasets", ["source_id"])
    op.create_table("import_jobs", sa.Column("id", sa.String(36), primary_key=True), sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id"), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("finished_at", sa.DateTime(timezone=True)), sa.Column("records_fetched", sa.Integer(), nullable=False), sa.Column("records_stored", sa.Integer(), nullable=False), sa.Column("raw_path", sa.String(500)), sa.Column("error", sa.Text()), sa.Column("parameters", sa.JSON(), nullable=False))
    op.create_index("ix_import_jobs_source_id", "import_jobs", ["source_id"])
    op.create_index("ix_import_jobs_status", "import_jobs", ["status"])
    op.create_table("occupation_skills", sa.Column("occupation_id", sa.String(36), sa.ForeignKey("occupations.id", ondelete="CASCADE"), primary_key=True), sa.Column("skill_id", sa.String(36), sa.ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True), sa.Column("relationship_type", sa.String(40), nullable=False), sa.Column("weight", sa.Float(), nullable=False), sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id")), sa.Column("confidence_score", sa.Float(), nullable=False))
    op.create_table("observations", sa.Column("id", sa.String(36), primary_key=True), sa.Column("occupation_id", sa.String(36), sa.ForeignKey("occupations.id")), sa.Column("skill_id", sa.String(36), sa.ForeignKey("skills.id")), sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id"), nullable=False), sa.Column("dataset_id", sa.String(36), sa.ForeignKey("source_datasets.id")), sa.Column("metric", sa.String(80), nullable=False), sa.Column("value", sa.Float(), nullable=False), sa.Column("unit", sa.String(50), nullable=False), sa.Column("period", sa.Date(), nullable=False), sa.Column("geography_code", sa.String(30), nullable=False), sa.Column("geography_name", sa.String(150), nullable=False), sa.Column("metadata_json", sa.JSON(), nullable=False), sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False))
    for name, cols in [("ix_observations_occupation_id",["occupation_id"]),("ix_observations_skill_id",["skill_id"]),("ix_observations_source_id",["source_id"]),("ix_observations_metric",["metric"]),("ix_observations_period",["period"]),("ix_observations_geography_code",["geography_code"]),("ix_observation_lookup",["metric","period","geography_code"])]: op.create_index(name,"observations",cols)
    op.create_table("trend_scores", sa.Column("id", sa.String(36), primary_key=True), sa.Column("entity_type", sa.String(30), nullable=False), sa.Column("entity_id", sa.String(36), nullable=False), sa.Column("period", sa.Date(), nullable=False), sa.Column("score", sa.Float(), nullable=False), sa.Column("growth", sa.Float(), nullable=False), sa.Column("acceleration", sa.Float(), nullable=False), sa.Column("volume", sa.Float(), nullable=False), sa.Column("geographic_spread", sa.Float(), nullable=False), sa.Column("source_confidence", sa.Float(), nullable=False), sa.Column("method_version", sa.String(20), nullable=False), sa.Column("is_official", sa.Boolean(), nullable=False), sa.UniqueConstraint("entity_type", "entity_id", "period", "method_version"))
    for col in ["entity_type","entity_id","period"]: op.create_index(f"ix_trend_scores_{col}","trend_scores",[col])

def downgrade() -> None:
    for table in ["trend_scores","observations","occupation_skills","import_jobs","source_datasets","skills","occupations","sources"]: op.drop_table(table)
