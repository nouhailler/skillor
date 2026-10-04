"""Add observed analytics metadata to TrendScore.

Revision ID: 0005_trend_analytics
Revises: 0004_search_index
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_trend_analytics"
down_revision = "0004_search_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trend_scores", sa.Column("raw_growth", sa.Float()))
    op.add_column("trend_scores", sa.Column("calculation_metadata", sa.JSON(), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("trend_scores", "calculation_metadata")
    op.drop_column("trend_scores", "raw_growth")
