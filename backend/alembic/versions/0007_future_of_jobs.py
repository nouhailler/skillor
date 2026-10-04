"""Add prospective reports and skill projections."""
from alembic import op
import sqlalchemy as sa
revision="0007_future_of_jobs"; down_revision="0006_data_quality"; branch_labels=None; depends_on=None

def upgrade():
    op.create_table("prospective_editions",sa.Column("id",sa.String(36),primary_key=True),sa.Column("source_id",sa.String(36),sa.ForeignKey("sources.id",ondelete="CASCADE"),nullable=False),sa.Column("report_title",sa.String(300),nullable=False),sa.Column("edition",sa.String(80),nullable=False),sa.Column("publication_year",sa.Integer(),nullable=False),sa.Column("horizon_year",sa.Integer()),sa.Column("source_url",sa.String(500)),sa.Column("raw_path",sa.String(500)),sa.Column("metadata_json",sa.JSON(),nullable=False),sa.Column("imported_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("source_id","edition"))
    op.create_index("ix_prospective_editions_source_id","prospective_editions",["source_id"]); op.create_index("ix_prospective_editions_edition","prospective_editions",["edition"])
    op.create_table("prospective_skill_projections",sa.Column("id",sa.String(36),primary_key=True),sa.Column("edition_id",sa.String(36),sa.ForeignKey("prospective_editions.id",ondelete="CASCADE"),nullable=False),sa.Column("skill_id",sa.String(36),sa.ForeignKey("skills.id")),sa.Column("source_label",sa.String(300),nullable=False),sa.Column("category",sa.String(100)),sa.Column("central_share",sa.Float()),sa.Column("projected_change",sa.Float(),nullable=False),sa.Column("figure_table",sa.String(200),nullable=False),sa.Column("geography",sa.String(100),nullable=False),sa.Column("sector",sa.String(150)),sa.Column("mapping_method",sa.String(80)),sa.Column("mapping_confidence",sa.Float()),sa.Column("metadata_json",sa.JSON(),nullable=False),sa.UniqueConstraint("edition_id","source_label","figure_table","geography","sector"))
    op.create_index("ix_prospective_skill_projections_edition_id","prospective_skill_projections",["edition_id"]); op.create_index("ix_prospective_skill_projections_skill_id","prospective_skill_projections",["skill_id"])

def downgrade():
    op.drop_table("prospective_skill_projections"); op.drop_table("prospective_editions")
