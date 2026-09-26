"""Phase 10 identity, sessions and organisation tenancy.

Revision ID: 20260820_0003
Revises: 20260819_0002
"""

from alembic import op
import sqlalchemy as sa

revision = "20260820_0003"
down_revision = "20260819_0002"
branch_labels = None
depends_on = None

LEGACY_ORG = "00000000-0000-0000-0000-000000000001"
LEGACY_USER = "00000000-0000-0000-0000-000000000002"
OWNED_TABLES = (
    "regflow_runs", "preflight_snapshots", "artifact_metadata", "audit_events",
    "idempotency_records", "mapping_profiles", "mapping_profile_versions",
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "external_identities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("issuer", "subject", name="uq_external_identity_issuer_subject"),
    )
    op.create_table(
        "organisations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "organisation_memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organisation_id", "user_id", name="uq_organisation_membership"),
        sa.CheckConstraint("role IN ('OWNER','MEMBER')", name="ck_membership_role"),
    )
    op.create_table(
        "invitations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invited_email", sa.String(320), nullable=False),
        sa.Column("invited_role", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("inviter_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("invited_role IN ('OWNER','MEMBER')", name="ck_invitation_role"),
    )
    op.create_index("ix_invitation_organisation_email", "invitations", ["organisation_id", "invited_email"])
    op.create_index("ix_invitation_token_hash", "invitations", ["token_hash"], unique=True)
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_hash", sa.String(64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("active_organisation_id", sa.String(36), sa.ForeignKey("organisations.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_user_session_hash", "user_sessions", ["session_hash"], unique=True)
    op.create_index("ix_user_session_expiry", "user_sessions", ["expires_at"])
    op.create_table(
        "oidc_transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("transaction_hash", sa.String(64), nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("nonce", sa.String(160), nullable=False),
        sa.Column("code_verifier", sa.Text(), nullable=False),
        sa.Column("return_to", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_oidc_transaction_hash", "oidc_transactions", ["transaction_hash"], unique=True)
    op.create_index("ix_oidc_transaction_expiry", "oidc_transactions", ["expires_at"])

    op.execute(sa.text("INSERT INTO users (id,email,display_name,active,created_at,updated_at) VALUES (:id,:email,:name,true,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)").bindparams(id=LEGACY_USER, email="legacy-workspace@local.invalid", name="Legacy workspace custodian"))
    op.execute(sa.text("INSERT INTO organisations (id,name,slug,active,created_at,updated_at) VALUES (:id,:name,:slug,true,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)").bindparams(id=LEGACY_ORG, name="Legacy RegBridge Workspace", slug="legacy-workspace"))
    op.execute(sa.text("INSERT INTO organisation_memberships (id,organisation_id,user_id,role,created_at,updated_at) VALUES (:id,:org,:user,'OWNER',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)").bindparams(id="00000000-0000-0000-0000-000000000003", org=LEGACY_ORG, user=LEGACY_USER))

    for table in OWNED_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("organisation_id", sa.String(36), nullable=False, server_default=LEGACY_ORG))
            batch.create_foreign_key(f"fk_{table}_organisation", "organisations", ["organisation_id"], ["id"], ondelete="RESTRICT")
            batch.create_index(f"ix_{table}_organisation", ["organisation_id"])
            batch.alter_column("organisation_id", server_default=None)
    with op.batch_alter_table("idempotency_records") as batch:
        batch.drop_constraint("uq_idempotency_operation_key", type_="unique")
        batch.create_unique_constraint("uq_idempotency_organisation_operation_key", ["organisation_id", "operation", "key"])


def downgrade() -> None:
    with op.batch_alter_table("idempotency_records") as batch:
        batch.drop_constraint("uq_idempotency_organisation_operation_key", type_="unique")
        batch.create_unique_constraint("uq_idempotency_operation_key", ["operation", "key"])
    for table in reversed(OWNED_TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_organisation")
            batch.drop_constraint(f"fk_{table}_organisation", type_="foreignkey")
            batch.drop_column("organisation_id")
    op.drop_table("oidc_transactions")
    op.drop_table("user_sessions")
    op.drop_table("invitations")
    op.drop_table("organisation_memberships")
    op.drop_table("organisations")
    op.drop_table("external_identities")
    op.drop_table("users")
