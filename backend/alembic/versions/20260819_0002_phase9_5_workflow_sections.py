"""Phase 9.5 generic workflow-section persistence.

Revision ID: 20260819_0002
Revises: 20260817_0001
"""

from alembic import op
import sqlalchemy as sa

revision = "20260819_0002"
down_revision = "20260817_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("regflow_runs", sa.Column("workflow_sections", sa.JSON(), nullable=True))
    op.add_column("preflight_snapshots", sa.Column("section_summaries", sa.JSON(), nullable=True))
    op.add_column("mapping_profile_versions", sa.Column("section_id", sa.String(120), nullable=True))
    op.create_index(
        "ix_profile_section_compatibility",
        "mapping_profile_versions",
        [
            "pack_id", "pack_version", "section_id", "canonical_schema_id",
            "canonical_schema_version", "source_header_signature",
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_profile_section_compatibility", table_name="mapping_profile_versions")
    op.drop_column("mapping_profile_versions", "section_id")
    op.drop_column("preflight_snapshots", "section_summaries")
    op.drop_column("regflow_runs", "workflow_sections")
