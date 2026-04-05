from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.auth.init_admin import ensure_admin_user
from src.auth.password import hash_password
from src.models.user import UserRole
from src.runtime.user_store import UserStore
from src.web.auth_routes import auth_router
from src.web.dependencies import get_current_user, require_admin
from src.web.routes import router


# ── Test app factory ──────────────────────────────────────────────────────────

def _make_app(user_store: UserStore) -> FastAPI:
    """Build a minimal FastAPI app wired to the given in-memory user_store."""
    from src.config import AuthConfig, AppConfig, PathsConfig, ProvidersConfig, JimengProviderConfig

    app = FastAPI()

    # Minimal config — no real file needed
    class _FakeConfig:
        class auth:
            secret_key = "test-secret-key-for-unit-tests"
            algorithm = "HS256"
            token_expire_minutes = 480

    app.state.config = _FakeConfig()
    app.state.user_store = user_store
    # Minimal storage stub so protected business routes don't crash when invoked
    app.state.storage = None
    app.state.provider = None

    app.include_router(auth_router)
    app.include_router(router)
    return app


@pytest.fixture()
def user_store() -> UserStore:
    store = UserStore(":memory:")
    store.init_db()
    ensure_admin_user(store)
    return store


@pytest.fixture()
def client(user_store: UserStore) -> TestClient:
    app = _make_app(user_store)
    return TestClient(app, raise_server_exceptions=True)


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_token(client: TestClient, username: str = "admin", password: str = "changeme123") -> str:
    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_login_success(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "changeme123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_login_wrong_password(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "wrongpassword"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


def test_me_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_returns_user(client: TestClient) -> None:
    token = _get_token(client)
    resp = client.get("/api/auth/me", headers=_auth_header(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "admin"
    assert body["role"] == "admin"
    assert "hashed_password" not in body


def test_change_password(client: TestClient, user_store: UserStore) -> None:
    token = _get_token(client)
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "changeme123", "new_password": "newpass456"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 200

    # Old password should now fail
    resp2 = client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "changeme123"},
    )
    assert resp2.status_code == 401

    # New password should work
    resp3 = client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "newpass456"},
    )
    assert resp3.status_code == 200


def test_protected_route_requires_auth(client: TestClient) -> None:
    """Business routes return 401 without a valid token."""
    resp = client.get("/api/products")
    assert resp.status_code == 401


def test_admin_only_route(client: TestClient, user_store: UserStore) -> None:
    """Non-admin user gets 403 when accessing /api/auth/users."""
    # Create a normal operator user
    user_store.create_user(
        username="operator1",
        hashed_password=hash_password("oppass123"),
        role=UserRole.operator,
        is_active=True,
    )
    token = _get_token(client, username="operator1", password="oppass123")
    resp = client.get("/api/auth/users", headers=_auth_header(token))
    assert resp.status_code == 403


def test_admin_can_list_users(client: TestClient) -> None:
    """Admin user can access /api/auth/users."""
    token = _get_token(client)
    resp = client.get("/api/auth/users", headers=_auth_header(token))
    assert resp.status_code == 200
    users = resp.json()
    assert isinstance(users, list)
    assert any(u["username"] == "admin" for u in users)


def test_admin_can_create_user(client: TestClient) -> None:
    """Admin can create a new user."""
    token = _get_token(client)
    resp = client.post(
        "/api/auth/users",
        json={"username": "newuser", "password": "newpass123", "role": "operator"},
        headers=_auth_header(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "newuser"
    assert "hashed_password" not in body


def test_login_inactive_user(client: TestClient, user_store: UserStore) -> None:
    """Inactive user cannot log in."""
    user_store.create_user(
        username="inactive",
        hashed_password=hash_password("pass123"),
        role=UserRole.operator,
        is_active=True,
    )
    user_store.update_user("inactive", is_active=False)

    resp = client.post(
        "/api/auth/login",
        data={"username": "inactive", "password": "pass123"},
    )
    assert resp.status_code == 401
