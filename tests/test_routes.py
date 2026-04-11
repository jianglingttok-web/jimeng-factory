"""Tests for API routes — focus on path traversal protection."""
from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.models.user import User, UserRole
from src.web.dependencies import get_current_user, require_admin
from src.web.routes import _safe_product_dir, router


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _admin_user() -> User:
    return User(
        username="admin",
        hashed_password="hashed",
        role=UserRole.admin,
        is_active=True,
    )


def _make_app(data_dir: str = "data/products") -> FastAPI:
    """Build a minimal FastAPI app with auth bypassed."""

    class _FakeConfig:
        class auth:
            secret_key = "test-secret"
            algorithm = "HS256"
            token_expire_minutes = 480

        class paths:
            pass

    fake_config = _FakeConfig()
    fake_config.paths.data_dir = data_dir  # type: ignore[attr-defined]

    app = FastAPI()
    app.state.config = fake_config
    app.state.storage = None
    app.state.provider = None
    app.state.user_store = None

    # Override auth dependencies so tests don't need a real token
    admin = _admin_user()
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[require_admin] = lambda: admin

    app.include_router(router)
    return app


@pytest.fixture
def client() -> TestClient:
    app = _make_app()
    return TestClient(app, raise_server_exceptions=False)


# ── Unit tests for _safe_product_dir ─────────────────────────────────────────

class TestSafeProductDir:
    """Direct unit tests for the path traversal guard function.

    HTTP-level traversal attacks using '../../etc' are normalized away by
    Starlette's routing before they reach the handler, so the guard is tested
    directly here to confirm it raises HTTP 400 when invoked with a traversal
    name.
    """

    def test_dotdot_traversal_raises_400(self):
        """../../etc must not escape the base directory."""
        with pytest.raises(HTTPException) as exc_info:
            _safe_product_dir("data/products", "../../etc")
        assert exc_info.value.status_code == 400

    def test_absolute_path_raises_400(self):
        """An absolute path as name must not escape the base directory."""
        with pytest.raises(HTTPException) as exc_info:
            _safe_product_dir("data/products", "/etc/passwd")
        assert exc_info.value.status_code == 400

    def test_normal_name_returns_path(self, tmp_path):
        """A plain product name resolves safely inside the base."""
        result = _safe_product_dir(str(tmp_path), "my-product")
        assert result == (tmp_path / "my-product").resolve()

    def test_nested_safe_name_resolves_inside_base(self, tmp_path):
        """A single subfolder (no traversal) resolves safely."""
        result = _safe_product_dir(str(tmp_path), "category/product")
        assert result.is_relative_to(tmp_path.resolve())


# ── Path Traversal (HTTP layer) ───────────────────────────────────────────────

class TestPathTraversal:
    def test_delete_product_traversal_blocked(self, client):
        """Path traversal in product name should return 400.

        Note: Starlette normalises '../../etc' to '/etc' before routing,
        so it returns 404 (route not matched) rather than 400.  The actual
        guard is verified via TestSafeProductDir above.
        """
        response = client.delete("/api/products/../../etc")
        # HTTP layer normalises '../../etc' → '/etc' → no route → 404
        assert response.status_code in (400, 404)

    def test_get_product_traversal_blocked(self, client):
        response = client.get("/api/products/../../etc/passwd")
        assert response.status_code in (400, 404)

    def test_delete_product_normal_name_not_blocked(self, client):
        """A plain product name that doesn't exist returns 404, not 400."""
        response = client.delete("/api/products/nonexistent-product")
        assert response.status_code == 404

    def test_get_product_normal_name_not_blocked(self, client):
        """A plain product name that doesn't exist returns 404, not 400."""
        response = client.get("/api/products/nonexistent-product")
        assert response.status_code == 404
