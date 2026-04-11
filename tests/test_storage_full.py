"""Comprehensive tests for Storage — covers CRUD, state transitions, and aggregation."""
from __future__ import annotations

import os
import tempfile
import time

import pytest

from src.models.account import Account, AccountStatus
from src.models.task import Task, TaskStatus
from src.runtime.storage import Storage


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def storage(tmp_path):
    s = Storage(str(tmp_path / "test.db"))
    s.init_db()
    s.sync_accounts([
        Account(
            name="test-account",
            space_id="space-1",
            cdp_url="http://localhost:9222",
            web_port=3000,
            status=AccountStatus.ACTIVE,
        )
    ])
    return s


def _make_task(storage: Storage, status: TaskStatus = TaskStatus.PENDING, **kwargs) -> Task:
    defaults = dict(
        product_name="test-product",
        variant_id="v1",
        prompt="test prompt",
        account_name="test-account",
    )
    defaults.update(kwargs)
    task = Task(**defaults)
    storage.create_task(task)
    if status != TaskStatus.PENDING:
        with storage.connect() as conn:
            conn.execute(
                "UPDATE tasks SET status = ? WHERE task_id = ?",
                (status.value, task.task_id),
            )
            conn.commit()
    return task


def _force_status(storage: Storage, task_id: str, status: TaskStatus) -> None:
    with storage.connect() as conn:
        conn.execute(
            "UPDATE tasks SET status = ? WHERE task_id = ?",
            (status.value, task_id),
        )
        conn.commit()


# ── create_task / create_tasks_batch ─────────────────────────────────────────

class TestCreateTask:
    def test_create_returns_task(self, storage):
        task = Task(
            product_name="prod-a",
            variant_id="v1",
            prompt="hello",
            account_name="test-account",
        )
        result = storage.create_task(task)
        assert result.task_id == task.task_id
        assert result.status == TaskStatus.PENDING

    def test_created_task_is_retrievable(self, storage):
        task = Task(
            product_name="prod-b",
            variant_id="v2",
            prompt="world",
            account_name="test-account",
        )
        storage.create_task(task)
        retrieved = storage.get_task(task.task_id)
        assert retrieved is not None
        assert retrieved.task_id == task.task_id
        assert retrieved.product_name == "prod-b"
        assert retrieved.prompt == "world"

    def test_create_accepts_dict(self, storage):
        task = Task(
            product_name="prod-dict",
            variant_id="v1",
            prompt="from dict",
            account_name="test-account",
        )
        result = storage.create_task(task.model_dump(mode="json"))
        assert result.task_id == task.task_id

    def test_create_tasks_batch_inserts_all(self, storage):
        tasks = [
            Task(product_name="p", variant_id="v1", prompt=f"prompt-{i}", account_name="test-account")
            for i in range(5)
        ]
        created = storage.create_tasks_batch(tasks)
        assert len(created) == 5
        for task in tasks:
            assert storage.get_task(task.task_id) is not None

    def test_create_tasks_batch_empty_list(self, storage):
        result = storage.create_tasks_batch([])
        assert result == []

    def test_create_tasks_batch_returns_in_order(self, storage):
        tasks = [
            Task(product_name="p", variant_id="v1", prompt=f"prompt-{i}", account_name="test-account")
            for i in range(3)
        ]
        created = storage.create_tasks_batch(tasks)
        for original, returned in zip(tasks, created):
            assert original.task_id == returned.task_id


# ── get_task ──────────────────────────────────────────────────────────────────

class TestGetTask:
    def test_returns_none_for_missing(self, storage):
        assert storage.get_task("nonexistent-id") is None

    def test_returns_task_for_existing(self, storage):
        task = _make_task(storage)
        result = storage.get_task(task.task_id)
        assert result is not None
        assert result.task_id == task.task_id

    def test_fields_preserved_correctly(self, storage):
        task = Task(
            product_name="detailed-product",
            variant_id="variant-abc",
            prompt="detailed prompt text",
            account_name="test-account",
            max_retries=3,
        )
        storage.create_task(task)
        retrieved = storage.get_task(task.task_id)
        assert retrieved.product_name == "detailed-product"
        assert retrieved.variant_id == "variant-abc"
        assert retrieved.prompt == "detailed prompt text"
        assert retrieved.max_retries == 3


# ── list_tasks ────────────────────────────────────────────────────────────────

class TestListTasks:
    def test_empty_db_returns_empty_list(self, storage):
        assert storage.list_tasks() == []

    def test_returns_all_tasks_unfiltered(self, storage):
        _make_task(storage, status=TaskStatus.PENDING)
        _make_task(storage, status=TaskStatus.GENERATING)
        _make_task(storage, status=TaskStatus.FAILED)
        result = storage.list_tasks()
        assert len(result) == 3

    def test_filter_by_status(self, storage):
        _make_task(storage, status=TaskStatus.PENDING)
        _make_task(storage, status=TaskStatus.PENDING)
        _make_task(storage, status=TaskStatus.GENERATING)
        pending = storage.list_tasks(status=TaskStatus.PENDING)
        assert len(pending) == 2
        assert all(t.status == TaskStatus.PENDING for t in pending)

    def test_filter_by_product_name(self, storage):
        _make_task(storage, product_name="product-alpha")
        _make_task(storage, product_name="product-alpha")
        _make_task(storage, product_name="product-beta")
        result = storage.list_tasks(product_name="product-alpha")
        assert len(result) == 2
        assert all(t.product_name == "product-alpha" for t in result)

    def test_filter_by_account_name(self, storage):
        storage.sync_accounts([
            Account(name="acct-2", space_id="space-2", cdp_url="http://localhost:9222", web_port=3000)
        ])
        _make_task(storage, account_name="test-account")
        _make_task(storage, account_name="acct-2")
        result = storage.list_tasks(account_name="acct-2")
        assert len(result) == 1
        assert result[0].account_name == "acct-2"

    def test_filter_product_not_found(self, storage):
        _make_task(storage, product_name="some-product")
        result = storage.list_tasks(product_name="no-such-product")
        assert result == []

    def test_pagination_limit(self, storage):
        for _ in range(10):
            _make_task(storage)
        result = storage.list_tasks(limit=3)
        assert len(result) == 3

    def test_pagination_offset(self, storage):
        tasks = [_make_task(storage) for _ in range(5)]
        first_two = storage.list_tasks(limit=2, offset=0)
        next_two = storage.list_tasks(limit=2, offset=2)
        ids_first = {t.task_id for t in first_two}
        ids_next = {t.task_id for t in next_two}
        assert ids_first.isdisjoint(ids_next)

    def test_offset_beyond_count_returns_empty(self, storage):
        _make_task(storage)
        result = storage.list_tasks(offset=100)
        assert result == []

    def test_combined_filters(self, storage):
        _make_task(storage, status=TaskStatus.PENDING, product_name="prod-a")
        _make_task(storage, status=TaskStatus.GENERATING, product_name="prod-a")
        _make_task(storage, status=TaskStatus.PENDING, product_name="prod-b")
        result = storage.list_tasks(status=TaskStatus.PENDING, product_name="prod-a")
        assert len(result) == 1
        assert result[0].product_name == "prod-a"
        assert result[0].status == TaskStatus.PENDING


# ── claim_pending_tasks ───────────────────────────────────────────────────────

class TestClaimPendingTasks:
    def test_claims_correct_number(self, storage):
        for _ in range(5):
            _make_task(storage)
        claimed = storage.claim_pending_tasks("test-account", 3)
        assert len(claimed) == 3

    def test_claimed_tasks_have_submitting_status(self, storage):
        for _ in range(3):
            _make_task(storage)
        storage.claim_pending_tasks("test-account", 3)
        # Verify in DB
        submitting = storage.list_tasks(status=TaskStatus.SUBMITTING)
        assert len(submitting) == 3

    def test_returns_empty_when_no_pending(self, storage):
        claimed = storage.claim_pending_tasks("test-account", 5)
        assert claimed == []

    def test_does_not_claim_other_statuses(self, storage):
        _make_task(storage, status=TaskStatus.GENERATING)
        _make_task(storage, status=TaskStatus.FAILED)
        claimed = storage.claim_pending_tasks("test-account", 10)
        assert claimed == []

    def test_respects_account_name(self, storage):
        storage.sync_accounts([
            Account(name="other-account", space_id="space-other", cdp_url="http://localhost:9222", web_port=3000)
        ])
        _make_task(storage, account_name="other-account")
        claimed = storage.claim_pending_tasks("test-account", 5)
        assert claimed == []

    def test_does_not_claim_more_than_limit(self, storage):
        for _ in range(10):
            _make_task(storage)
        claimed = storage.claim_pending_tasks("test-account", 2)
        assert len(claimed) == 2
        # Remaining should still be PENDING
        pending = storage.list_tasks(status=TaskStatus.PENDING)
        assert len(pending) == 8


# ── mark_submit_succeeded ─────────────────────────────────────────────────────

class TestMarkSubmitSucceeded:
    def test_changes_status_to_generating(self, storage):
        task = _make_task(storage, status=TaskStatus.SUBMITTING)
        result = storage.mark_submit_succeeded(task.task_id, submitted_at=time.time())
        assert result is not None
        assert result.status == TaskStatus.GENERATING

    def test_sets_submitted_at(self, storage):
        task = _make_task(storage, status=TaskStatus.SUBMITTING)
        ts = time.time()
        result = storage.mark_submit_succeeded(task.task_id, submitted_at=ts)
        assert result.submitted_at == pytest.approx(ts, abs=0.01)

    def test_no_op_if_not_submitting(self, storage):
        task = _make_task(storage, status=TaskStatus.PENDING)
        result = storage.mark_submit_succeeded(task.task_id, submitted_at=time.time())
        # task still exists but status should not change
        assert result is not None
        assert result.status == TaskStatus.PENDING

    def test_returns_none_for_unknown_task(self, storage):
        # mark_submit_succeeded calls get_task after update; unknown task returns None
        result = storage.mark_submit_succeeded("unknown-id", submitted_at=time.time())
        assert result is None


# ── mark_submit_failed ────────────────────────────────────────────────────────

class TestMarkSubmitFailed:
    def test_retries_back_to_pending_when_budget_remains(self, storage):
        task = _make_task(storage, status=TaskStatus.SUBMITTING)
        result = storage.mark_submit_failed(task.task_id, error="boom", max_retries=2)
        assert result is not None
        assert result.status == TaskStatus.PENDING

    def test_increments_retry_count_on_retry(self, storage):
        task = _make_task(storage, status=TaskStatus.SUBMITTING)
        result = storage.mark_submit_failed(task.task_id, error="boom", max_retries=2)
        assert result.retry_count == 1

    def test_marks_failed_when_retries_exhausted(self, storage):
        task = _make_task(storage, status=TaskStatus.SUBMITTING)
        # No retries allowed
        result = storage.mark_submit_failed(task.task_id, error="final error", max_retries=0)
        assert result.status == TaskStatus.FAILED
        assert result.error_message == "final error"

    def test_clears_error_message_on_retry(self, storage):
        task = _make_task(storage, status=TaskStatus.SUBMITTING)
        result = storage.mark_submit_failed(task.task_id, error="temp error", max_retries=2)
        assert result.error_message is None

    def test_no_op_if_not_submitting(self, storage):
        task = _make_task(storage, status=TaskStatus.PENDING)
        result = storage.mark_submit_failed(task.task_id, error="oops", max_retries=2)
        # Task not in SUBMITTING state — update won't apply, but get_task still returns
        assert result is not None
        assert result.status == TaskStatus.PENDING


# ── stop_tasks_batch ──────────────────────────────────────────────────────────

class TestStopTasksBatch:
    def test_stops_pending_tasks(self, storage):
        t1 = _make_task(storage, status=TaskStatus.PENDING)
        t2 = _make_task(storage, status=TaskStatus.PENDING)
        count = storage.stop_tasks_batch([t1.task_id, t2.task_id])
        assert count == 2
        assert storage.get_task(t1.task_id).status == TaskStatus.FAILED
        assert storage.get_task(t2.task_id).status == TaskStatus.FAILED

    def test_stops_submitting_tasks(self, storage):
        task = _make_task(storage, status=TaskStatus.SUBMITTING)
        count = storage.stop_tasks_batch([task.task_id])
        assert count == 1
        assert storage.get_task(task.task_id).status == TaskStatus.FAILED

    def test_skips_succeeded_tasks(self, storage):
        task = _make_task(storage, status=TaskStatus.SUCCEEDED)
        count = storage.stop_tasks_batch([task.task_id])
        assert count == 0
        assert storage.get_task(task.task_id).status == TaskStatus.SUCCEEDED

    def test_skips_already_failed_tasks(self, storage):
        task = _make_task(storage, status=TaskStatus.FAILED)
        count = storage.stop_tasks_batch([task.task_id])
        assert count == 0

    def test_sets_stopped_by_user_error_message(self, storage):
        task = _make_task(storage, status=TaskStatus.PENDING)
        storage.stop_tasks_batch([task.task_id])
        stopped = storage.get_task(task.task_id)
        assert stopped.error_message == "stopped by user"

    def test_empty_list_returns_zero(self, storage):
        count = storage.stop_tasks_batch([])
        assert count == 0

    def test_partial_stop_when_mixed_statuses(self, storage):
        pending = _make_task(storage, status=TaskStatus.PENDING)
        succeeded = _make_task(storage, status=TaskStatus.SUCCEEDED)
        count = storage.stop_tasks_batch([pending.task_id, succeeded.task_id])
        assert count == 1
        assert storage.get_task(pending.task_id).status == TaskStatus.FAILED
        assert storage.get_task(succeeded.task_id).status == TaskStatus.SUCCEEDED


# ── mark_download_succeeded ───────────────────────────────────────────────────

class TestMarkDownloadSucceeded:
    def test_changes_status_to_succeeded(self, storage):
        task = _make_task(storage, status=TaskStatus.DOWNLOADING)
        result = storage.mark_download_succeeded(task.task_id, video_path="/tmp/video.mp4")
        assert result.status == TaskStatus.SUCCEEDED

    def test_sets_video_path(self, storage):
        task = _make_task(storage, status=TaskStatus.DOWNLOADING)
        result = storage.mark_download_succeeded(task.task_id, video_path="/tmp/video.mp4")
        assert result.result_video_path == "/tmp/video.mp4"

    def test_returns_none_for_unknown_task(self, storage):
        result = storage.mark_download_succeeded("unknown-id", video_path="/tmp/x.mp4")
        assert result is None


# ── mark_download_failed ──────────────────────────────────────────────────────

class TestMarkDownloadFailed:
    def test_retries_back_to_generating_when_budget_remains(self, storage):
        task = _make_task(storage, status=TaskStatus.DOWNLOADING)
        result = storage.mark_download_failed(task.task_id, error="network error", max_retries=2)
        assert result.status == TaskStatus.GENERATING

    def test_marks_failed_when_retries_exhausted(self, storage):
        task = _make_task(storage, status=TaskStatus.DOWNLOADING)
        result = storage.mark_download_failed(task.task_id, error="permanent failure", max_retries=0)
        assert result.status == TaskStatus.FAILED
        assert result.error_message == "permanent failure"

    def test_increments_retry_count_on_retry(self, storage):
        task = _make_task(storage, status=TaskStatus.DOWNLOADING)
        result = storage.mark_download_failed(task.task_id, error="err", max_retries=3)
        assert result.retry_count == 1

    def test_no_op_if_not_downloading(self, storage):
        task = _make_task(storage, status=TaskStatus.GENERATING)
        result = storage.mark_download_failed(task.task_id, error="err", max_retries=2)
        assert result.status == TaskStatus.GENERATING


# ── sync_accounts ─────────────────────────────────────────────────────────────

class TestSyncAccounts:
    def test_adds_new_accounts(self, storage):
        storage.sync_accounts([
            Account(name="new-account", space_id="space-new", cdp_url="http://localhost:9222", web_port=3000)
        ])
        accounts = storage.get_accounts()
        names = {a.name for a in accounts}
        assert "new-account" in names

    def test_handles_duplicate_call_idempotently(self, storage):
        acct = Account(name="idm-account", space_id="space-idm", cdp_url="http://localhost:9222", web_port=3000)
        storage.sync_accounts([acct])
        storage.sync_accounts([acct])
        accounts = storage.get_accounts()
        names = [a.name for a in accounts if a.name == "idm-account"]
        assert len(names) == 1

    def test_existing_account_updated_by_space_id(self, storage):
        storage.sync_accounts([
            Account(name="renamed", space_id="space-1", cdp_url="http://localhost:9222", web_port=3000)
        ])
        accounts = storage.get_accounts()
        names = {a.name for a in accounts}
        # test-account (space-1) should be replaced/updated to "renamed"
        assert "renamed" in names

    def test_returns_list_of_accounts(self, storage):
        result = storage.sync_accounts([
            Account(name="acct-x", space_id="space-x", cdp_url="http://localhost:9222", web_port=3000)
        ])
        assert isinstance(result, list)
        assert len(result) == 1


# ── count_tasks_by_status ─────────────────────────────────────────────────────

class TestCountTasksByStatus:
    def test_empty_db_returns_empty_dict(self, storage):
        counts = storage.count_tasks_by_status()
        assert counts == {}

    def test_counts_single_status(self, storage):
        _make_task(storage, status=TaskStatus.PENDING)
        counts = storage.count_tasks_by_status()
        assert counts.get("pending") == 1

    def test_counts_multiple_statuses(self, storage):
        _make_task(storage, status=TaskStatus.PENDING)
        _make_task(storage, status=TaskStatus.PENDING)
        _make_task(storage, status=TaskStatus.GENERATING)
        _make_task(storage, status=TaskStatus.FAILED)
        _make_task(storage, status=TaskStatus.SUCCEEDED)
        counts = storage.count_tasks_by_status()
        assert counts["pending"] == 2
        assert counts["generating"] == 1
        assert counts["failed"] == 1
        assert counts["succeeded"] == 1

    def test_count_updates_after_status_change(self, storage):
        task = _make_task(storage, status=TaskStatus.PENDING)
        assert storage.count_tasks_by_status().get("pending") == 1
        _force_status(storage, task.task_id, TaskStatus.SUCCEEDED)
        counts = storage.count_tasks_by_status()
        assert counts.get("pending", 0) == 0
        assert counts.get("succeeded") == 1
