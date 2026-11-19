"""Create catalog tables."""

from alembic import op
import sqlalchemy as sa

revision = "20261119_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "themes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "listings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("seller_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("theme_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("condition", sa.Enum("NEW", "USED", "RESTORATION", name="listingcondition"), nullable=False),
        sa.Column("completeness", sa.String(length=300), nullable=True),
        sa.Column("missing_parts", sa.Text(), nullable=True),
        sa.Column("has_box", sa.Boolean(), nullable=False),
        sa.Column("has_instructions", sa.Boolean(), nullable=False),
        sa.Column("known_defects", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum("DRAFT", "ACTIVE", "RESERVED", "SOLD", "ARCHIVED", "BLOCKED", name="listingstatus"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["theme_id"], ["themes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_listings_seller_id", "listings", ["seller_id"])
    op.create_table(
        "listing_images",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("object_reference", sa.String(length=500), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_listing_images_listing_id", "listing_images", ["listing_id"])
    op.create_table(
        "favorites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "listing_id", name="uq_favorite_user_listing"),
    )
    op.create_index("ix_favorites_user_id", "favorites", ["user_id"])

    categories = sa.table("categories", sa.column("id", sa.Uuid()), sa.column("name", sa.String()), sa.column("slug", sa.String()))
    themes = sa.table("themes", sa.column("id", sa.Uuid()), sa.column("name", sa.String()), sa.column("slug", sa.String()))
    op.bulk_insert(categories, [
        {"id": "10000000-0000-0000-0000-000000000001", "name": "LEGO Наборы", "slug": "lego-sets"},
        {"id": "10000000-0000-0000-0000-000000000002", "name": "LEGO Минифигурки", "slug": "lego-minifigures"},
        {"id": "10000000-0000-0000-0000-000000000003", "name": "LEGO Детали", "slug": "lego-parts"},
    ])
    op.bulk_insert(themes, [
        {"id": "20000000-0000-0000-0000-000000000001", "name": "City", "slug": "city"},
        {"id": "20000000-0000-0000-0000-000000000002", "name": "Star Wars", "slug": "star-wars"},
        {"id": "20000000-0000-0000-0000-000000000003", "name": "Technic", "slug": "technic"},
        {"id": "20000000-0000-0000-0000-000000000004", "name": "NINJAGO", "slug": "ninjago"},
        {"id": "20000000-0000-0000-0000-000000000005", "name": "Creator", "slug": "creator"},
        {"id": "20000000-0000-0000-0000-000000000006", "name": "Friends", "slug": "friends"},
        {"id": "20000000-0000-0000-0000-000000000007", "name": "Architecture", "slug": "architecture"},
    ])


def downgrade() -> None:
    op.drop_index("ix_favorites_user_id", table_name="favorites")
    op.drop_table("favorites")
    op.drop_index("ix_listing_images_listing_id", table_name="listing_images")
    op.drop_table("listing_images")
    op.drop_index("ix_listings_seller_id", table_name="listings")
    op.drop_table("listings")
    op.drop_table("themes")
    op.drop_table("categories")
