"""Add inspection deadlines and durable payout actions."""

from alembic import op
import sqlalchemy as sa

revision = "20261119_02"
down_revision = "20261119_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "deals",
        sa.Column("inspection_deadline_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("deals", sa.Column("shipment_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint("uq_deals_shipment_id", "deals", ["shipment_id"])
    op.create_table(
        "deal_payout_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deal_id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_deal_payout_outbox_due",
        "deal_payout_outbox",
        ["next_attempt_at"],
        postgresql_where=sa.text("completed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_deal_payout_outbox_due", table_name="deal_payout_outbox")
    op.drop_table("deal_payout_outbox")
    op.drop_constraint("uq_deals_shipment_id", "deals", type_="unique")
    op.drop_column("deals", "shipment_id")
    op.drop_column("deals", "inspection_deadline_at")
