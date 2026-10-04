"""Add multilingual fuzzy search index.

Revision ID: 0004_search_index
Revises: 0003_france_travail_graph
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_search_index"
down_revision = "0003_france_travail_graph"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_terms",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("term", sa.String(500), nullable=False),
        sa.Column("normalized_term", sa.String(500), nullable=False),
        sa.Column("language", sa.String(12)),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("term_type", sa.String(40), nullable=False),
        sa.Column("identifier", sa.String(500)),
        sa.UniqueConstraint("entity_type", "entity_id", "normalized_term", "language", "source", "term_type", name="uq_search_term_identity"),
    )
    for column in ("entity_type", "entity_id", "normalized_term", "language", "source", "term_type", "identifier"):
        op.create_index(f"ix_search_terms_{column}", "search_terms", [column])
    op.create_index("ix_search_terms_entity", "search_terms", ["entity_type", "entity_id"])
def downgrade() -> None:
    op.drop_table("search_terms")
