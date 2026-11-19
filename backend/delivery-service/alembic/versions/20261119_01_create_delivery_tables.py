"""Create shipments and tracking events."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261119_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    shipment_status = postgresql.ENUM(
        "CREATED",
        "IN_TRANSIT",
        "OUT_FOR_DELIVERY",
        "EXCEPTION",
        "RETURNED",
        "DELIVERED",
        name="shipmentstatus",
        create_type=False,
    )
    shipment_status.create(bind, checkfirst=True)
    op.create_table(
        "shipments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("seller_id", sa.Uuid(), nullable=False),
        sa.Column("carrier", sa.String(length=100), nullable=False),
        sa.Column("tracking_number", sa.String(length=120), nullable=True),
        sa.Column("status", shipment_status, nullable=False),
        sa.Column("deal_shipped_synced", sa.Boolean(), nullable=False),
        sa.Column("deal_delivered_synced", sa.Boolean(), nullable=False),
        sa.Column("sync_attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "sync_next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sync_last_error", sa.String(length=300), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deal_id"),
    )
    op.create_index("ix_shipments_buyer_id", "shipments", ["buyer_id"])
    op.create_index("ix_shipments_seller_id", "shipments", ["seller_id"])
    op.create_table(
        "tracking_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shipment_id", sa.Uuid(), nullable=False),
        sa.Column("status", shipment_status, nullable=False),
        sa.Column("tracking_number", sa.String(length=120), nullable=True),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tracking_events_shipment_id", "tracking_events", ["shipment_id"])


def downgrade() -> None:
    op.drop_index("ix_tracking_events_shipment_id", table_name="tracking_events")
    op.drop_table("tracking_events")
    op.drop_index("ix_shipments_seller_id", table_name="shipments")
    op.drop_index("ix_shipments_buyer_id", table_name="shipments")
    op.drop_table("shipments")
    op.execute("DROP TYPE IF EXISTS shipmentstatus")
