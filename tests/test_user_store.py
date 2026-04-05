from __future__ import annotations

import sqlite3

import pytest

from src.auth.init_admin import ensure_admin_user
from src.auth.password import verify_password
from src.models.user import UserRole
from src.runtime.user_store import UserStore


@pytest.fixture()
def store() -> UserStore:
    """In-memory SQLite UserStore, freshly initialised for each test."""
    s = UserStore(":memory:")
    s.init_db()
    return s


# ── Basic CRUD ────────────────────────────────────────────────────────────────


def test_create_and_get_user(store: UserStore) -> None:
    store.create_user("alice", "hashed_pw_123", UserRole.operator)
    user = store.get_user_by_username("alice")
    assert user is not None
    assert user.username == "alice"
    assert user.hashed_password == "hashed_pw_123"
    assert user.role == UserRole.operator
    assert user.is_active is True


def test_get_nonexistent_user_returns_none(store: UserStore) -> None:
    result = store.get_user_by_username("nobody")
    assert result is None


def test_list_users(store: UserStore) -> None:
    store.create_user("alice", "pw1", UserRole.operator)
    store.create_user("bob", "pw2", UserRole.admin)
    users = store.list_users()
    assert len(users) == 2
    usernames = {u.username for u in users}
    assert usernames == {"alice", "bob"}


def test_update_user_password(store: UserStore) -> None:
    store.create_user("alice", "old_hash", UserRole.operator)
    updated = store.update_user("alice", hashed_password="new_hash")
    assert updated is not None
    assert updated.hashed_password == "new_hash"
    # Persisted correctly
    fetched = store.get_user_by_username("alice")
    assert fetched is not None
    assert fetched.hashed_password == "new_hash"


def test_update_user_is_active(store: UserStore) -> None:
    store.create_user("alice", "pw", UserRole.operator)
    updated = store.update_user("alice", is_active=False)
    assert updated is not None
    assert updated.is_active is False


def test_update_user_role(store: UserStore) -> None:
    store.create_user("alice", "pw", UserRole.operator)
    updated = store.update_user("alice", role=UserRole.admin)
    assert updated is not None
    assert updated.role == UserRole.admin


def test_update_nonexistent_user_returns_none(store: UserStore) -> None:
    result = store.update_user("ghost", is_active=False)
    assert result is None


def test_delete_user(store: UserStore) -> None:
    store.create_user("alice", "pw", UserRole.operator)
    deleted = store.delete_user("alice")
    assert deleted is True
    assert store.get_user_by_username("alice") is None


def test_delete_nonexistent_user_returns_false(store: UserStore) -> None:
    result = store.delete_user("nobody")
    assert result is False


def test_create_duplicate_user_raises(store: UserStore) -> None:
    store.create_user("alice", "pw1", UserRole.operator)
    with pytest.raises(sqlite3.IntegrityError):
        store.create_user("alice", "pw2", UserRole.admin)


# ── ensure_admin_user ─────────────────────────────────────────────────────────


def test_ensure_admin_user_creates_once(store: UserStore) -> None:
    # First call: no admin exists — should create one.
    ensure_admin_user(store)
    admins = [u for u in store.list_users() if u.role == UserRole.admin]
    assert len(admins) == 1
    assert admins[0].username == "admin"

    # Second call: admin already exists — should not create another.
    ensure_admin_user(store)
    admins_after = [u for u in store.list_users() if u.role == UserRole.admin]
    assert len(admins_after) == 1


def test_ensure_admin_user_uses_env_password(
    store: UserStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JIMENG_ADMIN_PASSWORD", "super_secret_42")
    ensure_admin_user(store)
    admin = store.get_user_by_username("admin")
    assert admin is not None
    assert verify_password("super_secret_42", admin.hashed_password) is True


def test_ensure_admin_user_uses_default_password(store: UserStore) -> None:
    ensure_admin_user(store)
    admin = store.get_user_by_username("admin")
    assert admin is not None
    assert verify_password("changeme123", admin.hashed_password) is True
