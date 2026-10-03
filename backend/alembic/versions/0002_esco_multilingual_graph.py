"""Add ESCO multilingual metadata.

Revision ID: 0002_esco_multilingual_graph
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_esco_multilingual_graph"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("occupations", sa.Column("multilingual_labels", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("occupations", sa.Column("multilingual_descriptions", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("skills", sa.Column("multilingual_labels", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("skills", sa.Column("multilingual_descriptions", sa.JSON(), nullable=False, server_default="{}"))

def downgrade() -> None:
    op.drop_column("skills", "multilingual_descriptions")
    op.drop_column("skills", "multilingual_labels")
    op.drop_column("occupations", "multilingual_descriptions")
    op.drop_column("occupations", "multilingual_labels")
