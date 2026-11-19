import pytest
from pydantic import ValidationError

from app.schemas import MessageCreate


def test_message_content_is_trimmed() -> None:
    assert MessageCreate(content="  Привет!  ").content == "Привет!"


def test_message_cannot_be_blank() -> None:
    with pytest.raises(ValidationError):
        MessageCreate(content="   ")
