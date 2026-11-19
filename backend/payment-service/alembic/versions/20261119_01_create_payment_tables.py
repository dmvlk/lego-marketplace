"""Create payments, refunds, payouts, and provider events."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261119_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    payment_status = postgresql.ENUM(
        "PENDING",
        "AUTHORIZED",
        "FAILED",
        "PARTIALLY_REFUNDED",
        "REFUNDED",
        "PAID_OUT",
        name="paymentstatus",
        create_type=False,
    )
    refund_status = postgresql.ENUM(
        "PENDING",
        "SUCCEEDED",
        "FAILED",
        name="refundstatus",
        create_type=False,
    )
    payout_status = postgresql.ENUM(
        "PENDING",
        "RELEASED",
        "FAILED",
        name="payoutstatus",
        create_type=False,
    )
    payment_status.create(bind, checkfirst=True)
    refund_status.create(bind, checkfirst=True)
    payout_status.create(bind, checkfirst=True)

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("seller_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("platform_fee", sa.Numeric(12, 2), nullable=False),
        sa.Column("seller_payout", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("provider_reference", sa.String(length=120), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", payment_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("buyer_id", "idempotency_key", name="uq_payment_buyer_idempotency"),
        sa.UniqueConstraint("provider_reference"),
    )
    op.create_index("ix_payments_deal_id", "payments", ["deal_id"])
    op.create_index("ix_payments_buyer_id", "payments", ["buyer_id"])
    op.create_index("ix_payments_seller_id", "payments", ["seller_id"])
    op.create_index(
        "uq_payment_active_deal",
        "payments",
        ["deal_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('PENDING', 'AUTHORIZED', 'PARTIALLY_REFUNDED', 'PAID_OUT')"
        ),
    )
    op.create_table(
        "refunds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("provider_reference", sa.String(length=120), nullable=True),
        sa.Column("status", refund_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_id", "idempotency_key", name="uq_refund_payment_idempotency"),
        sa.UniqueConstraint("provider_reference"),
    )
    op.create_index("ix_refunds_payment_id", "refunds", ["payment_id"])
    op.create_table(
        "payouts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("provider_reference", sa.String(length=120), nullable=True),
        sa.Column("status", payout_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_id", name="uq_payout_payment"),
        sa.UniqueConstraint("provider_reference"),
    )
    op.create_index("ix_payouts_payment_id", "payouts", ["payment_id"])
    op.create_table(
        "payment_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("event_id", sa.String(length=120), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "event_id", name="uq_payment_event_provider_id"),
    )
    op.create_index("ix_payment_events_payment_id", "payment_events", ["payment_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_events_payment_id", table_name="payment_events")
    op.drop_table("payment_events")
    op.drop_index("ix_payouts_payment_id", table_name="payouts")
    op.drop_table("payouts")
    op.drop_index("ix_refunds_payment_id", table_name="refunds")
    op.drop_table("refunds")
    op.drop_index("uq_payment_active_deal", table_name="payments")
    op.drop_index("ix_payments_seller_id", table_name="payments")
    op.drop_index("ix_payments_buyer_id", table_name="payments")
    op.drop_index("ix_payments_deal_id", table_name="payments")
    op.drop_table("payments")
    op.execute("DROP TYPE IF EXISTS payoutstatus")
    op.execute("DROP TYPE IF EXISTS refundstatus")
    op.execute("DROP TYPE IF EXISTS paymentstatus")
