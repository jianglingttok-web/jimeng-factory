from __future__ import annotations

from datetime import timedelta

from src.auth.password import hash_password, verify_password
from src.auth.token import create_access_token, decode_access_token

_SECRET = "test-secret-key-for-unit-tests"


def test_hash_and_verify_password() -> None:
    plain = "my-secure-password"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed) is True


def test_wrong_password_fails() -> None:
    hashed = hash_password("correct-password")
    assert verify_password("wrong-password", hashed) is False


def test_create_and_decode_token() -> None:
    data = {"sub": "alice", "role": "admin"}
    token = create_access_token(data, secret_key=_SECRET)
    payload = decode_access_token(token, secret_key=_SECRET)
    assert payload is not None
    assert payload["sub"] == "alice"
    assert payload["role"] == "admin"


def test_expired_token_returns_none() -> None:
    data = {"sub": "bob"}
    # expires_delta_minutes accepts int; use a very negative value to force expiry
    token = create_access_token(
        data,
        secret_key=_SECRET,
        expires_delta_minutes=-1,
    )
    result = decode_access_token(token, secret_key=_SECRET)
    assert result is None


def test_invalid_token_returns_none() -> None:
    result = decode_access_token("this.is.not.a.valid.jwt", secret_key=_SECRET)
    assert result is None
