"""Add deal reservation reference to listings."""

from alembic import op
import sqlalchemy as sa

revision = "20261119_02"
down_revision = "20261119_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("reservation_deal_id", sa.Uuid(), nullable=True))
    op.create_index(
        "ix_listings_reservation_deal_id",
        "listings",
        ["reservation_deal_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_listings_reservation_deal_id", table_name="listings")
    op.drop_column("listings", "reservation_deal_id")
