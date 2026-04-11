"""Integration tests for web routes using FastAPI TestClient.

The app lifespan starts background loops and reaches out to the browser;
we bypass it by creating a minimal FastAPI app that shares the same router
but mounts test-scoped storage and config directly on app.state.
"""
from __future__ import annotations

import tempfile
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.config import AppConfig, PathsConfig, ProvidersConfig, JimengProviderConfig
from src.models.account import Account, AccountStatus
from src.models.product import PromptVariant
from src.runtime.product_store import create_product
from src.runtime.storage import Storage
from src.web.routes import router


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _make_config(data_dir: str, db_path: str) -> AppConfig:
    return AppConfig(
        paths=PathsConfig(data_dir=data_dir, output_dir=str(Path(db_path).parent / "outputs"), database_path=db_path),
        providers=ProvidersConfig(
            jimeng=JimengProviderConfig(
                base_url="http://jimeng.test",
                enabled=False,
            )
        ),
    )


@pytest.fixture
def client(tmp_path):
    data_dir = str(tmp_path / "products")
    db_path = str(tmp_path / "test.db")
    Path(data_dir).mkdir(parents=True, exist_ok=True)

    config = _make_config(data_dir, db_path)

    storage = Storage(db_path)
    storage.init_db()
    storage.sync_accounts([
        Account(
            name="test-account",
            space_id="space-test",
            cdp_url="http://localhost:9222",
            web_port=3000,
            status=AccountStatus.ACTIVE,
        )
    ])

    app = FastAPI()
    app.include_router(router)
    app.state.config = config
    app.state.storage = storage
    # provider is only used by account-discovery routes, not tested here
    app.state.provider = SimpleNamespace(
        provider_config=SimpleNamespace(accounts=[]),
        get_account=lambda name: (_ for _ in ()).throw(ValueError(name)),
    )

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── GET /api/health ───────────────────────────────────────────────────────────

class TestHealth:
    def test_returns_200(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_returns_ok_status(self, client):
        resp = client.get("/api/health")
        assert resp.json() == {"status": "ok"}


# ── GET /api/products ─────────────────────────────────────────────────────────

class TestListProducts:
    def test_empty_product_list(self, client):
        resp = client.get("/api/products")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_product_after_creation(self, client):
        client.post("/api/products", json={
            "name": "my-product",
            "variants": [{"prompt": "a test prompt", "title": "T"}],
        })
        resp = client.get("/api/products")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "my-product"


# ── POST /api/products ────────────────────────────────────────────────────────

class TestCreateProduct:
    def test_create_product_returns_200(self, client):
        resp = client.post("/api/products", json={
            "name": "new-prod",
            "variants": [{"prompt": "some prompt", "title": "V1"}],
        })
        assert resp.status_code == 200

    def test_create_product_returns_name(self, client):
        resp = client.post("/api/products", json={
            "name": "named-prod",
            "variants": [{"prompt": "p", "title": "T"}],
        })
        assert resp.json()["name"] == "named-prod"

    def test_create_duplicate_returns_409(self, client):
        payload = {"name": "dup-prod", "variants": [{"prompt": "p", "title": "T"}]}
        client.post("/api/products", json=payload)
        resp = client.post("/api/products", json=payload)
        assert resp.status_code == 409

    def test_create_assigns_variant_ids(self, client):
        resp = client.post("/api/products", json={
            "name": "id-prod",
            "variants": [{"prompt": "p", "title": "T"}],
        })
        variants = resp.json()["prompt_variants"]
        assert variants[0]["id"] != ""


# ── PUT /api/products/{name} ──────────────────────────────────────────────────

class TestUpdateProduct:
    def test_update_existing_product(self, client):
        client.post("/api/products", json={
            "name": "upd-prod",
            "variants": [{"prompt": "old", "title": "Old"}],
        })
        resp = client.put("/api/products/upd-prod", json={
            "variants": [{"prompt": "new prompt", "title": "New"}],
        })
        assert resp.status_code == 200
        assert resp.json()["prompt_variants"][0]["prompt"] == "new prompt"

    def test_update_missing_product_returns_404(self, client):
        resp = client.put("/api/products/does-not-exist", json={
            "variants": [{"prompt": "p", "title": "T"}],
        })
        assert resp.status_code == 404


# ── DELETE /api/products/{name} ───────────────────────────────────────────────

class TestDeleteProduct:
    def test_delete_existing_product(self, client):
        client.post("/api/products", json={
            "name": "del-prod",
            "variants": [{"prompt": "p", "title": "T"}],
        })
        resp = client.delete("/api/products/del-prod")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == "del-prod"

    def test_delete_removes_product_from_list(self, client):
        client.post("/api/products", json={
            "name": "gone-prod",
            "variants": [{"prompt": "p", "title": "T"}],
        })
        client.delete("/api/products/gone-prod")
        resp = client.get("/api/products")
        names = [p["name"] for p in resp.json()]
        assert "gone-prod" not in names

    def test_delete_missing_product_returns_404(self, client):
        resp = client.delete("/api/products/phantom")
        assert resp.status_code == 404


# ── GET /api/tasks ────────────────────────────────────────────────────────────

class TestListTasks:
    def test_returns_pagination_keys(self, client):
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        body = resp.json()
        assert "tasks" in body
        assert "total" in body
        assert "limit" in body
        assert "offset" in body

    def test_empty_tasks_list(self, client):
        resp = client.get("/api/tasks")
        assert resp.json()["tasks"] == []
        assert resp.json()["total"] == 0

    def test_respects_limit_param(self, client):
        resp = client.get("/api/tasks?limit=50")
        assert resp.json()["limit"] == 50

    def test_respects_offset_param(self, client):
        resp = client.get("/api/tasks?offset=10")
        assert resp.json()["offset"] == 10


# ── POST /api/tasks/submit ────────────────────────────────────────────────────

class TestSubmitTasks:
    def test_submit_missing_product_returns_404(self, client):
        resp = client.post("/api/tasks/submit", json={
            "product_name": "no-such-product",
            "account_name": "test-account",
            "count": 1,
        })
        assert resp.status_code == 404

    def test_submit_creates_tasks(self, client):
        client.post("/api/products", json={
            "name": "submit-prod",
            "variants": [{"prompt": "make video", "title": "V1"}],
        })
        resp = client.post("/api/tasks/submit", json={
            "product_name": "submit-prod",
            "account_name": "test-account",
            "count": 2,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["created"] == 2
        assert len(body["task_ids"]) == 2

    def test_submitted_tasks_appear_in_list(self, client):
        client.post("/api/products", json={
            "name": "listed-prod",
            "variants": [{"prompt": "p", "title": "V1"}],
        })
        client.post("/api/tasks/submit", json={
            "product_name": "listed-prod",
            "account_name": "test-account",
            "count": 1,
        })
        tasks_resp = client.get("/api/tasks")
        assert tasks_resp.json()["total"] == 1


# ── POST /api/tasks/stop-batch ────────────────────────────────────────────────

class TestStopBatch:
    def test_stop_batch_validates_max_size(self, client):
        task_ids = [f"task-{i}" for i in range(501)]
        resp = client.post("/api/tasks/stop-batch", json={"task_ids": task_ids})
        assert resp.status_code == 422

    def test_stop_batch_empty_list_returns_200(self, client):
        resp = client.post("/api/tasks/stop-batch", json={"task_ids": []})
        assert resp.status_code == 200
        assert resp.json()["stopped"] == 0

    def test_stop_batch_rejects_long_task_id(self, client):
        long_id = "x" * 64
        resp = client.post("/api/tasks/stop-batch", json={"task_ids": [long_id]})
        assert resp.status_code == 422

    def test_stop_batch_stops_pending_tasks(self, client):
        # Create a product and submit a task to get real task IDs
        client.post("/api/products", json={
            "name": "stop-prod",
            "variants": [{"prompt": "p", "title": "V1"}],
        })
        submit_resp = client.post("/api/tasks/submit", json={
            "product_name": "stop-prod",
            "account_name": "test-account",
            "count": 1,
        })
        task_id = submit_resp.json()["task_ids"][0]
        stop_resp = client.post("/api/tasks/stop-batch", json={"task_ids": [task_id]})
        assert stop_resp.status_code == 200
        assert stop_resp.json()["stopped"] == 1


# ── GET /api/status ───────────────────────────────────────────────────────────

class TestSystemStatus:
    def test_returns_200(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200

    def test_has_tasks_key(self, client):
        resp = client.get("/api/status")
        assert "tasks" in resp.json()

    def test_has_accounts_key(self, client):
        resp = client.get("/api/status")
        assert "accounts" in resp.json()

    def test_tasks_contains_all_statuses(self, client):
        resp = client.get("/api/status")
        tasks = resp.json()["tasks"]
        expected_statuses = {"pending", "submitting", "generating", "downloading", "succeeded", "failed"}
        assert set(tasks.keys()) == expected_statuses

    def test_accounts_list_includes_synced_account(self, client):
        resp = client.get("/api/status")
        accounts = resp.json()["accounts"]
        names = [a["name"] for a in accounts]
        assert "test-account" in names
