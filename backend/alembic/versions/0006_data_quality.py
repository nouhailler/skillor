"""Add calculated data-quality scores.

Revision ID: 0006_data_quality
Revises: 0005_trend_analytics
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_data_quality"
down_revision = "0005_trend_analytics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("data_quality_scores",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("source_datasets.id", ondelete="CASCADE")),
        sa.Column("scope_key", sa.String(80), nullable=False), sa.Column("metric", sa.String(80), nullable=False),
        sa.Column("period", sa.Date(), nullable=False), sa.Column("score", sa.Float(), nullable=False),
        sa.Column("source_quality", sa.Float(), nullable=False), sa.Column("recency", sa.Float(), nullable=False),
        sa.Column("coverage", sa.Float(), nullable=False), sa.Column("consistency", sa.Float(), nullable=False),
        sa.Column("cross_source_agreement", sa.Float(), nullable=False), sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("diagnostics", sa.JSON(), nullable=False), sa.Column("method_version", sa.String(20), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("is_official", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("source_id", "scope_key", "metric", "period", "method_version"))
    for column in ("source_id", "dataset_id", "metric", "period"):
        op.create_index(f"ix_data_quality_scores_{column}", "data_quality_scores", [column])


def downgrade() -> None:
    op.drop_table("data_quality_scores")
