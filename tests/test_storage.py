"""Tests for Storage — focus on rescue methods and aggregation."""
from __future__ import annotations

import tempfile
import os

import pytest

from src.models.account import Account, AccountStatus
from src.models.task import Task, TaskStatus
from src.runtime.storage import Storage


@pytest.fixture
def storage():
    # Use a temp file: Storage.connect() creates a new connection each call,
    # so :memory: would give each call an empty database.
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        s = Storage(db_path)
        s.init_db()
        # Seed a test account
        s.sync_accounts([
            Account(
                name="test-account",
                space_id="space-1",
                cdp_url="http://localhost:9222",
                web_port=3000,
                status=AccountStatus.ACTIVE,
            )
        ])
        yield s
    finally:
        # Windows may keep WAL/SHM files locked briefly; ignore cleanup errors.
        for path in [db_path, db_path + "-wal", db_path + "-shm"]:
            try:
                os.unlink(path)
            except OSError:
                pass


def _make_task(storage, status=TaskStatus.PENDING, **kwargs):
    defaults = dict(
        product_name="test-product",
        variant_id="v1",
        prompt="test prompt",
        account_name="test-account",
    )
    defaults.update(kwargs)
    task = Task(**defaults)
    storage.create_task(task)
    # Force status if not PENDING
    if status != TaskStatus.PENDING:
        with storage.connect() as conn:
            conn.execute(
                "UPDATE tasks SET status = ? WHERE task_id = ?",
                (status.value, task.task_id),
            )
            conn.commit()
    return task


class TestRescueStaleSubmitting:
    def test_submitting_tasks_reset_to_pending(self, storage):
        task = _make_task(storage, status=TaskStatus.SUBMITTING)
        storage.rescue_stale_submitting(stale_seconds=0)
        updated = storage.get_task(task.task_id)
        assert updated.status == TaskStatus.PENDING

    def test_other_statuses_unaffected(self, storage):
        generating = _make_task(storage, status=TaskStatus.GENERATING)
        pending = _make_task(storage, status=TaskStatus.PENDING)
        storage.rescue_stale_submitting()
        assert storage.get_task(generating.task_id).status == TaskStatus.GENERATING
        assert storage.get_task(pending.task_id).status == TaskStatus.PENDING


class TestCountTasksByStatus:
    def test_empty_db(self, storage):
        counts = storage.count_tasks_by_status()
        assert counts == {}

    def test_mixed_statuses(self, storage):
        _make_task(storage, status=TaskStatus.PENDING)
        _make_task(storage, status=TaskStatus.PENDING)
        _make_task(storage, status=TaskStatus.GENERATING)
        _make_task(storage, status=TaskStatus.FAILED)
        counts = storage.count_tasks_by_status()
        assert counts["pending"] == 2
        assert counts["generating"] == 1
        assert counts["failed"] == 1
