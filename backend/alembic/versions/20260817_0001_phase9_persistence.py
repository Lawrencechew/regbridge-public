"""Phase 9 persistence schema.

Revision ID: 20260817_0001
Revises: None
"""
from alembic import op
import sqlalchemy as sa

revision = "20260817_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "regflow_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pack_id", sa.String(120), nullable=False),
        sa.Column("pack_version", sa.String(64), nullable=False),
        sa.Column("pack_fingerprint", sa.String(64), nullable=False),
        sa.Column("source_display_name", sa.String(255)),
        sa.Column("source_type", sa.String(16)),
        sa.Column("source_size_bytes", sa.Integer()),
        sa.Column("source_sha256", sa.String(64)),
        sa.Column("selected_sheet", sa.String(255)),
        sa.Column("header_row", sa.Integer()),
        sa.Column("source_header_signature", sa.String(64)),
        sa.Column("source_signature_version", sa.String(40)),
        sa.Column("canonical_schema_id", sa.String(120)),
        sa.Column("canonical_schema_version", sa.String(64)),
        sa.Column("mapping_fingerprint", sa.String(64)),
        sa.Column("mapping_definition", sa.JSON()),
        sa.Column("mapping_confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("mapping_profile_id", sa.String(36)),
        sa.Column("mapping_profile_version", sa.Integer()),
        sa.Column("dataset_fingerprint", sa.String(64)),
        sa.Column("validation_report_fingerprint", sa.String(64)),
        sa.Column("reconciliation_report_fingerprint", sa.String(64)),
        sa.Column("latest_blocking_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latest_review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latest_passed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latest_skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("preflight_ready", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_generate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("latest_preflight_snapshot_id", sa.String(36)),
        sa.Column("latest_artifact_id", sa.String(36)),
        sa.Column("invalidation_reason", sa.String(255)),
        sa.CheckConstraint("revision >= 1", name="ck_regflow_runs_revision"),
        sa.CheckConstraint("latest_blocking_count >= 0", name="ck_regflow_runs_blocking"),
        sa.CheckConstraint("latest_review_count >= 0", name="ck_regflow_runs_review"),
        sa.CheckConstraint("latest_passed_count >= 0", name="ck_regflow_runs_passed"),
        sa.CheckConstraint("latest_skipped_count >= 0", name="ck_regflow_runs_skipped"),
    )
    op.create_index("ix_regflow_runs_updated_at", "regflow_runs", ["updated_at"])
    op.create_index("ix_regflow_runs_state", "regflow_runs", ["state"])
    op.create_index("ix_regflow_runs_source_sha256", "regflow_runs", ["source_sha256"])

    op.create_table(
        "mapping_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "mapping_profile_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("mapping_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("display_name", sa.String(160)),
        sa.Column("pack_id", sa.String(120), nullable=False),
        sa.Column("pack_version", sa.String(64), nullable=False),
        sa.Column("pack_fingerprint", sa.String(64), nullable=False),
        sa.Column("canonical_schema_id", sa.String(120), nullable=False),
        sa.Column("canonical_schema_version", sa.String(64), nullable=False),
        sa.Column("source_header_signature", sa.String(64), nullable=False),
        sa.Column("source_signature_version", sa.String(40), nullable=False),
        sa.Column("mapping_fingerprint", sa.String(64), nullable=False),
        sa.Column("mapping_definition", sa.JSON(), nullable=False),
        sa.Column("recommendation_origins", sa.JSON(), nullable=False),
        sa.CheckConstraint("profile_version >= 1", name="ck_mapping_profile_version"),
        sa.UniqueConstraint("profile_id", "profile_version", name="uq_mapping_profile_version"),
    )
    op.create_index("ix_profile_signature", "mapping_profile_versions", ["source_header_signature"])
    op.create_index("ix_profile_pack", "mapping_profile_versions", ["pack_id", "pack_version"])

    op.create_table(
        "preflight_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("regflow_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pack_fingerprint", sa.String(64), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("source_header_signature", sa.String(64), nullable=False),
        sa.Column("mapping_fingerprint", sa.String(64), nullable=False),
        sa.Column("dataset_fingerprint", sa.String(64), nullable=False),
        sa.Column("validation_report_fingerprint", sa.String(64), nullable=False),
        sa.Column("reconciliation_report_fingerprint", sa.String(64), nullable=False),
        sa.Column("blocking_count", sa.Integer(), nullable=False),
        sa.Column("review_count", sa.Integer(), nullable=False),
        sa.Column("passed_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("ready", sa.Boolean(), nullable=False),
        sa.Column("can_generate", sa.Boolean(), nullable=False),
        sa.Column("current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("run_revision >= 1", name="ck_preflight_revision"),
        sa.CheckConstraint("blocking_count >= 0", name="ck_preflight_blocking"),
        sa.CheckConstraint("review_count >= 0", name="ck_preflight_review"),
        sa.CheckConstraint("passed_count >= 0", name="ck_preflight_passed"),
        sa.CheckConstraint("skipped_count >= 0", name="ck_preflight_skipped"),
    )
    op.create_index("ix_preflight_run_created", "preflight_snapshots", ["run_id", "created_at"])

    op.create_table(
        "artifact_metadata",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("regflow_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(160), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("byte_sha256", sa.String(64), nullable=False),
        sa.Column("pack_id", sa.String(120), nullable=False),
        sa.Column("pack_version", sa.String(64), nullable=False),
        sa.Column("pack_fingerprint", sa.String(64), nullable=False),
        sa.Column("dataset_fingerprint", sa.String(64), nullable=False),
        sa.Column("mapping_fingerprint", sa.String(64), nullable=False),
        sa.Column("output_definition_id", sa.String(120), nullable=False),
        sa.Column("output_definition_version", sa.String(64), nullable=False),
        sa.Column("logical_generation_fingerprint", sa.String(64), nullable=False),
        sa.Column("retained_bytes", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("storage_reference", sa.String(500)),
        sa.Column("current", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_artifact_run_created", "artifact_metadata", ["run_id", "created_at"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("regflow_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("run_revision", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_audit_run_occurred", "audit_events", ["run_id", "occurred_at"])

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("regflow_runs.id", ondelete="CASCADE")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("operation", "key", name="uq_idempotency_operation_key"),
    )
    op.create_index("ix_idempotency_created_at", "idempotency_records", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_created_at", table_name="idempotency_records")
    op.drop_table("idempotency_records")
    op.drop_index("ix_audit_run_occurred", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_artifact_run_created", table_name="artifact_metadata")
    op.drop_table("artifact_metadata")
    op.drop_index("ix_preflight_run_created", table_name="preflight_snapshots")
    op.drop_table("preflight_snapshots")
    op.drop_index("ix_profile_pack", table_name="mapping_profile_versions")
    op.drop_index("ix_profile_signature", table_name="mapping_profile_versions")
    op.drop_table("mapping_profile_versions")
    op.drop_table("mapping_profiles")
    op.drop_index("ix_regflow_runs_source_sha256", table_name="regflow_runs")
    op.drop_index("ix_regflow_runs_state", table_name="regflow_runs")
    op.drop_index("ix_regflow_runs_updated_at", table_name="regflow_runs")
    op.drop_table("regflow_runs")
