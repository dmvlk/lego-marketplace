"""Add disputes, evidence, audit history, and resolution outbox."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261119_03"
down_revision = "20261119_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE disputereason AS ENUM "
        "('NOT_AS_DESCRIBED', 'DAMAGED', 'MISSING_PARTS', 'WRONG_ITEM', 'NOT_DELIVERED', 'OTHER')"
    )
    op.execute(
        "CREATE TYPE disputestatus AS ENUM "
        "('WAITING_SELLER', 'WAITING_BUYER', 'UNDER_REVIEW', 'RESOLVING', 'RESOLVED')"
    )
    op.execute("CREATE TYPE evidencetype AS ENUM ('TEXT', 'IMAGE', 'MESSAGE', 'TRACKING')")
    op.execute(
        "CREATE TYPE disputedecision AS ENUM "
        "('REFUND_BUYER', 'PAY_SELLER', 'PARTIAL_REFUND')"
    )

    dispute_reason = postgresql.ENUM(
        "NOT_AS_DESCRIBED",
        "DAMAGED",
        "MISSING_PARTS",
        "WRONG_ITEM",
        "NOT_DELIVERED",
        "OTHER",
        name="disputereason",
        create_type=False,
    )
    dispute_status = postgresql.ENUM(
        "WAITING_SELLER",
        "WAITING_BUYER",
        "UNDER_REVIEW",
        "RESOLVING",
        "RESOLVED",
        name="disputestatus",
        create_type=False,
    )
    evidence_type = postgresql.ENUM(
        "TEXT",
        "IMAGE",
        "MESSAGE",
        "TRACKING",
        name="evidencetype",
        create_type=False,
    )
    dispute_decision = postgresql.ENUM(
        "REFUND_BUYER",
        "PAY_SELLER",
        "PARTIAL_REFUND",
        name="disputedecision",
        create_type=False,
    )

    op.create_table(
        "disputes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("opened_by", sa.Uuid(), nullable=False),
        sa.Column("reason", dispute_reason, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", dispute_status, nullable=False),
        sa.Column("response_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_missed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", dispute_decision, nullable=True),
        sa.Column("refund_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deal_id"),
    )
    op.create_table(
        "dispute_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dispute_id", sa.Uuid(), nullable=False),
        sa.Column("submitted_by", sa.Uuid(), nullable=False),
        sa.Column("evidence_type", evidence_type, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("image_key", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dispute_id"], ["disputes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dispute_evidence_dispute_id", "dispute_evidence", ["dispute_id"])
    op.create_table(
        "dispute_audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dispute_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dispute_id"], ["disputes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dispute_audit_logs_dispute_id", "dispute_audit_logs", ["dispute_id"])
    op.create_table(
        "dispute_resolution_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dispute_id", sa.Uuid(), nullable=False),
        sa.Column("decision", dispute_decision, nullable=False),
        sa.Column("refund_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["dispute_id"], ["disputes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dispute_id"),
    )
    op.create_index(
        "ix_dispute_resolution_outbox_due",
        "dispute_resolution_outbox",
        ["next_attempt_at"],
        postgresql_where=sa.text("completed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_dispute_resolution_outbox_due", table_name="dispute_resolution_outbox")
    op.drop_table("dispute_resolution_outbox")
    op.drop_index("ix_dispute_audit_logs_dispute_id", table_name="dispute_audit_logs")
    op.drop_table("dispute_audit_logs")
    op.drop_index("ix_dispute_evidence_dispute_id", table_name="dispute_evidence")
    op.drop_table("dispute_evidence")
    op.drop_table("disputes")
    op.execute("DROP TYPE disputedecision")
    op.execute("DROP TYPE evidencetype")
    op.execute("DROP TYPE disputestatus")
    op.execute("DROP TYPE disputereason")
