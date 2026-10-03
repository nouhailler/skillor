"""Link France Travail indicators to Skillor occupations.

Revision ID: 0003_france_travail_graph
Revises: 0002_esco_multilingual_graph
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_france_travail_graph"
down_revision = "0002_esco_multilingual_graph"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "external_occupation_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("occupation_id", sa.String(36), sa.ForeignKey("occupations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_system", sa.String(80), nullable=False),
        sa.Column("external_code", sa.String(120), nullable=False),
        sa.Column("external_label", sa.String(500)),
        sa.Column("mapping_relation", sa.String(80), nullable=False),
        sa.Column("mapping_method", sa.String(80), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("occupation_id", "source_system", "external_code"),
    )
    for column in ("occupation_id", "source_system", "external_code", "external_label"):
        op.create_index(f"ix_external_occupation_mappings_{column}", "external_occupation_mappings", [column])
    op.add_column("observations", sa.Column("natural_key", sa.String(64)))
    op.create_index("ix_observations_natural_key", "observations", ["natural_key"], unique=True)

def downgrade() -> None:
    op.drop_index("ix_observations_natural_key", table_name="observations")
    op.drop_column("observations", "natural_key")
    op.drop_table("external_occupation_mappings")
