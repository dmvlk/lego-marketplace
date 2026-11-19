"""Create deals and offers tables."""

from alembic import op
import sqlalchemy as sa

revision = "20261119_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("seller_id", sa.Uuid(), nullable=False),
        sa.Column("source_offer_id", sa.Uuid(), nullable=True),
        sa.Column("agreed_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("transaction_type", sa.Enum("OFFLINE", "ONLINE_PROTECTED", name="transactiontype"), nullable=False),
        sa.Column("status", sa.Enum("PENDING_CONFIRMATION", "AWAITING_PAYMENT", "PAID", "SHIPPED", "INSPECTION", "DISPUTED", "COMPLETED", "CANCELLED", name="dealstatus"), nullable=False),
        sa.Column("buyer_confirmed", sa.Boolean(), nullable=False),
        sa.Column("seller_confirmed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_offer_id"),
    )
    op.create_index("ix_deals_listing_id", "deals", ["listing_id"])
    op.create_index("ix_deals_buyer_id", "deals", ["buyer_id"])
    op.create_index("ix_deals_seller_id", "deals", ["seller_id"])
    op.create_table(
        "offers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("seller_id", sa.Uuid(), nullable=False),
        sa.Column("sender_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("previous_offer_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.Enum("OPEN", "COUNTERED", "ACCEPTED", "REJECTED", name="offerstatus"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["previous_offer_id"], ["offers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_offers_listing_id", "offers", ["listing_id"])
    op.create_index("ix_offers_buyer_id", "offers", ["buyer_id"])
    op.create_index("ix_offers_seller_id", "offers", ["seller_id"])
    op.create_table(
        "deal_listing_snapshots",
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("listed_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("condition", sa.String(length=30), nullable=False),
        sa.Column("completeness", sa.String(length=300), nullable=True),
        sa.Column("missing_parts", sa.Text(), nullable=True),
        sa.Column("has_box", sa.Boolean(), nullable=False),
        sa.Column("has_instructions", sa.Boolean(), nullable=False),
        sa.Column("known_defects", sa.Text(), nullable=True),
        sa.Column("image_references", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("deal_id"),
    )
    op.create_table(
        "deal_status_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("previous_status", sa.String(length=40), nullable=True),
        sa.Column("new_status", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deal_status_history_deal_id", "deal_status_history", ["deal_id"])


def downgrade() -> None:
    op.drop_index("ix_deal_status_history_deal_id", table_name="deal_status_history")
    op.drop_table("deal_status_history")
    op.drop_table("deal_listing_snapshots")
    op.drop_index("ix_offers_seller_id", table_name="offers")
    op.drop_index("ix_offers_buyer_id", table_name="offers")
    op.drop_index("ix_offers_listing_id", table_name="offers")
    op.drop_table("offers")
    op.drop_index("ix_deals_seller_id", table_name="deals")
    op.drop_index("ix_deals_buyer_id", table_name="deals")
    op.drop_index("ix_deals_listing_id", table_name="deals")
    op.drop_table("deals")
    op.execute("DROP TYPE IF EXISTS offerstatus")
    op.execute("DROP TYPE IF EXISTS dealstatus")
    op.execute("DROP TYPE IF EXISTS transactiontype")
