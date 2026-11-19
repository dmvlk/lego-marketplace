import pytest
from pydantic import ValidationError

from app.schemas import ReviewCreate


@pytest.mark.parametrize("rating", [1, 5])
def test_review_accepts_rating_boundaries(rating: int) -> None:
    assert ReviewCreate(rating=rating).rating == rating


@pytest.mark.parametrize("rating", [0, 6])
def test_review_rejects_rating_outside_range(rating: int) -> None:
    with pytest.raises(ValidationError):
        ReviewCreate(rating=rating)


def test_review_comment_is_trimmed_and_empty_comment_becomes_null() -> None:
    assert ReviewCreate(rating=4, comment="  Good set  ").comment == "Good set"
    assert ReviewCreate(rating=4, comment="   ").comment is None
