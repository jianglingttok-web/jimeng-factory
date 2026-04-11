"""Tests for Scheduler — focus on error handling behavior."""
from __future__ import annotations

import asyncio
import os
import tempfile
from unittest.mock import MagicMock
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
        s.sync_accounts([
            Account(
                name="unknown-account",
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


class TestSchedulerValueError:
    def test_unknown_account_fails_immediately(self, storage):
        """ValueError from get_account should fail the task with max_retries=0."""
        from src.providers.jimeng import JimengProvider
        from src.runtime.scheduler import Scheduler

        # Create a task for an account that exists in DB but not in provider config
        task = Task(
            product_name="test",
            variant_id="v1",
            prompt="test",
            account_name="unknown-account",
        )
        storage.create_task(task)

        # Build a lightweight config stub (avoid spec= so nested attributes work)
        config = MagicMock()
        config.video.max_retries = 2
        config.paths.data_dir = "data/products"

        # Provider raises ValueError for any get_account call
        provider = MagicMock(spec=JimengProvider)
        provider.get_account.side_effect = ValueError("Unknown account: unknown-account")

        scheduler = Scheduler(storage, provider, config)
        asyncio.run(scheduler.run_once())

        updated = storage.get_task(task.task_id)
        # Should be FAILED immediately (max_retries=0 in the ValueError handler)
        assert updated.status == TaskStatus.FAILED
        assert updated.retry_count == 0
