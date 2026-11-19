import uuid

from app.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    password = "StrongPass123!"
    password_hash = hash_password(password)

    assert password_hash != password
    assert verify_password(password, password_hash)
    assert not verify_password("WrongPass123!", password_hash)


def test_access_token_contains_subject_role_and_type() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "USER")
    payload = decode_access_token(token)

    assert payload["sub"] == str(user_id)
    assert payload["role"] == "USER"
    assert payload["type"] == "access"


def test_refresh_token_hash_is_deterministic_and_not_plaintext() -> None:
    token = "opaque-refresh-token"

    assert hash_refresh_token(token) != token
    assert hash_refresh_token(token) == hash_refresh_token(token)
