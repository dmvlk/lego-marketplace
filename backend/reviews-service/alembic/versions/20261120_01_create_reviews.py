"""Create reviews table."""

from alembic import op
import sqlalchemy as sa

revision = "20261120_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("seller_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_review_rating_range"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deal_id", name="uq_review_deal_id"),
    )
    op.create_index("ix_reviews_reviewer_id", "reviews", ["reviewer_id"])
    op.create_index("ix_reviews_seller_created_at", "reviews", ["seller_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_reviews_seller_created_at", table_name="reviews")
    op.drop_index("ix_reviews_reviewer_id", table_name="reviews")
    op.drop_table("reviews")
