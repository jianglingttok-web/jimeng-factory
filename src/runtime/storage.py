from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Iterable

from src.models.account import Account, AccountStatus
from src.models.task import Task, TaskStatus


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    variant_id TEXT NOT NULL,
    prompt TEXT NOT NULL,
    account_name TEXT NOT NULL,
    status TEXT NOT NULL,
    result_video_path TEXT,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 2,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    submitted_at REAL,
    result_url TEXT,
    duration_seconds INTEGER
);

CREATE TABLE IF NOT EXISTS accounts (
    name TEXT PRIMARY KEY,
    space_id TEXT NOT NULL,
    cdp_url TEXT NOT NULL,
    web_port INTEGER NOT NULL,
    status TEXT NOT NULL,
    generating_count INTEGER NOT NULL DEFAULT 0,
    max_concurrent INTEGER NOT NULL DEFAULT 10
);
"""

# Migration: add new columns to existing databases
_MIGRATIONS = [
    "ALTER TABLE tasks ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE tasks ADD COLUMN max_retries INTEGER NOT NULL DEFAULT 2",
    "ALTER TABLE tasks ADD COLUMN submitted_at REAL",
    "ALTER TABLE tasks ADD COLUMN result_url TEXT",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_space_id ON accounts(space_id)",
]


class Storage:
    def __init__(self, database_path: str | Path):
        self.database_path = database_path
        if database_path != ":memory:":
            Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def init_db(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA_SQL)
            connection.commit()
        self._run_migrations()

    def _run_migrations(self) -> None:
        for statement in _MIGRATIONS:
            with self.connect() as connection:
                try:
                    connection.execute(statement)
                    connection.commit()
                except sqlite3.Error:
                    pass  # column/index already exists or existing duplicate data blocks the index

    def create_task(self, task: Task | dict) -> Task:
        record = task if isinstance(task, Task) else Task.model_validate(task)
        payload = record.model_dump(mode="json")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    task_id, product_name, variant_id, prompt, account_name,
                    status, result_video_path, error_message, retry_count,
                    max_retries, created_at, updated_at, submitted_at,
                    result_url, duration_seconds
                ) VALUES (
                    :task_id, :product_name, :variant_id, :prompt, :account_name,
                    :status, :result_video_path, :error_message, :retry_count,
                    :max_retries, :created_at, :updated_at, :submitted_at,
                    :result_url, :duration_seconds
                )
                """,
                payload,
            )
            connection.commit()
        return record

    def get_task(self, task_id: str) -> Task | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return Task.model_validate(dict(row)) if row else None

    def list_tasks(
        self,
        *,
        status: TaskStatus | None = None,
        product_name: str | None = None,
        account_name: str | None = None,
    ) -> list[Task]:
        query = "SELECT * FROM tasks WHERE 1=1"
        params: list[object] = []
        if status is not None:
            query += " AND status = ?"
            params.append(status.value)
        if product_name is not None:
            query += " AND product_name = ?"
            params.append(product_name)
        if account_name is not None:
            query += " AND account_name = ?"
            params.append(account_name)
        query += " ORDER BY created_at ASC"

        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [Task.model_validate(dict(row)) for row in rows]

    # ── Atomic state transitions ───────────────────────────────────────────────

    def claim_pending_tasks(self, account_name: str, limit: int) -> list[Task]:
        """Atomically claim up to `limit` pending tasks for an account.

        Sets status to SUBMITTING and increments generating_count in a single
        transaction. Returns the claimed tasks.
        """
        now = time.time()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM tasks
                WHERE account_name = ? AND status = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (account_name, TaskStatus.PENDING.value, limit),
            ).fetchall()

            claimed: list[Task] = []
            for row in rows:
                task_id = row["task_id"]
                updated = connection.execute(
                    """
                    UPDATE tasks
                    SET status = ?, updated_at = ?
                    WHERE task_id = ? AND status = ?
                    """,
                    (TaskStatus.SUBMITTING.value, now, task_id, TaskStatus.PENDING.value),
                ).rowcount
                if updated:
                    claimed.append(Task.model_validate(dict(row)))

            if claimed:
                connection.execute(
                    """
                    UPDATE accounts
                    SET generating_count = MAX(generating_count + ?, 0)
                    WHERE name = ?
                    """,
                    (len(claimed), account_name),
                )
            connection.commit()
        return claimed

    def mark_submit_succeeded(self, task_id: str, submitted_at: float) -> Task | None:
        """Mark a task as GENERATING after successful submission."""
        now = time.time()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = ?, submitted_at = ?, updated_at = ?
                WHERE task_id = ? AND status = ?
                """,
                (
                    TaskStatus.GENERATING.value,
                    submitted_at,
                    now,
                    task_id,
                    TaskStatus.SUBMITTING.value,
                ),
            )
            connection.commit()
        return self.get_task(task_id)

    def mark_submit_failed(
        self,
        task_id: str,
        error: str,
        *,
        max_retries: int = 0,
    ) -> Task | None:
        """Retry a failed submission until retry budget is exhausted."""
        now = time.time()
        with self.connect() as connection:
            task_row = connection.execute(
                """
                SELECT account_name, retry_count, max_retries
                FROM tasks
                WHERE task_id = ? AND status = ?
                """,
                (task_id, TaskStatus.SUBMITTING.value),
            ).fetchone()

            if task_row:
                retry_count = int(task_row["retry_count"] or 0)
                retry_limit = max(0, max_retries)
                next_status = (
                    TaskStatus.PENDING.value
                    if retry_count < retry_limit
                    else TaskStatus.FAILED.value
                )
                next_error = None if next_status == TaskStatus.PENDING.value else error
                next_retry_count = retry_count + 1 if next_status == TaskStatus.PENDING.value else retry_count
                connection.execute(
                    """
                    UPDATE tasks
                    SET status = ?, error_message = ?, retry_count = ?,
                        updated_at = ?
                    WHERE task_id = ? AND status = ?
                    """,
                    (
                        next_status,
                        next_error,
                        next_retry_count,
                        now,
                        task_id,
                        TaskStatus.SUBMITTING.value,
                    ),
                )
                connection.execute(
                    """
                    UPDATE accounts
                    SET generating_count = MAX(generating_count - 1, 0)
                    WHERE name = ?
                    """,
                    (task_row["account_name"],),
                )
            connection.commit()
        return self.get_task(task_id)

    def reset_failed_tasks(self) -> int:
        """Reset all FAILED tasks back to PENDING. Returns count of tasks reset."""
        now = time.time()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE tasks
                SET status = ?, error_message = NULL, updated_at = ?
                WHERE status = ?
                """,
                (TaskStatus.PENDING.value, now, TaskStatus.FAILED.value),
            )
            connection.commit()
        return cursor.rowcount

    def stop_tasks_batch(self, task_ids: list[str]) -> int:
        """Stop multiple tasks at once. Only tasks in cancellable states are affected."""
        if not task_ids:
            return 0

        now = time.time()
        cancellable = (
            TaskStatus.PENDING.value,
            TaskStatus.SUBMITTING.value,
            TaskStatus.GENERATING.value,
            TaskStatus.DOWNLOADING.value,
        )
        countable = {
            TaskStatus.SUBMITTING.value,
            TaskStatus.GENERATING.value,
            TaskStatus.DOWNLOADING.value,
        }
        placeholders = ",".join("?" for _ in task_ids)
        status_placeholders = ",".join("?" for _ in cancellable)

        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT task_id, account_name, status
                FROM tasks
                WHERE task_id IN ({placeholders}) AND status IN ({status_placeholders})
                """,
                [*task_ids, *cancellable],
            ).fetchall()
            if not rows:
                return 0

            cursor = connection.execute(
                f"""
                UPDATE tasks
                SET status = ?, error_message = ?, updated_at = ?
                WHERE task_id IN ({placeholders}) AND status IN ({status_placeholders})
                """,
                [TaskStatus.FAILED.value, "stopped by user", now, *task_ids, *cancellable],
            )

            decrements: dict[str, int] = {}
            for row in rows:
                if row["status"] in countable:
                    decrements[row["account_name"]] = decrements.get(row["account_name"], 0) + 1

            for account_name, delta in decrements.items():
                connection.execute(
                    """
                    UPDATE accounts
                    SET generating_count = MAX(generating_count - ?, 0)
                    WHERE name = ?
                    """,
                    (delta, account_name),
                )

            connection.commit()
        return cursor.rowcount

    def claim_result_url(self, task_id: str, result_url: str) -> bool:
        """Atomically claim a remote result URL for a task that is still unmatched."""
        now = time.time()
        with self.connect() as connection:
            updated = connection.execute(
                """
                UPDATE tasks
                SET result_url = ?, updated_at = ?
                WHERE task_id = ? AND result_url IS NULL
                """,
                (result_url, now, task_id),
            ).rowcount
            connection.commit()
        return updated == 1

    def mark_download_succeeded(self, task_id: str, video_path: str) -> Task | None:
        """Mark a task as SUCCEEDED with the local video path; decrement generating_count."""
        now = time.time()
        with self.connect() as connection:
            task_row = connection.execute(
                "SELECT account_name FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()

            connection.execute(
                """
                UPDATE tasks
                SET status = ?, result_video_path = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (TaskStatus.SUCCEEDED.value, video_path, now, task_id),
            )
            if task_row:
                connection.execute(
                    """
                    UPDATE accounts
                    SET generating_count = MAX(generating_count - 1, 0)
                    WHERE name = ?
                    """,
                    (task_row["account_name"],),
                )
            connection.commit()
        return self.get_task(task_id)

    def mark_download_failed(
        self,
        task_id: str,
        error: str,
        *,
        max_retries: int = 0,
    ) -> Task | None:
        """Retry a failed download until retry budget is exhausted."""
        now = time.time()
        with self.connect() as connection:
            task_row = connection.execute(
                """
                SELECT account_name, retry_count
                FROM tasks
                WHERE task_id = ? AND status = ?
                """,
                (task_id, TaskStatus.DOWNLOADING.value),
            ).fetchone()

            if task_row:
                retry_count = int(task_row["retry_count"] or 0)
                retry_limit = max(0, max_retries)
                next_status = (
                    TaskStatus.GENERATING.value
                    if retry_count < retry_limit
                    else TaskStatus.FAILED.value
                )
                next_error = None if next_status == TaskStatus.GENERATING.value else error
                next_retry_count = retry_count + 1 if next_status == TaskStatus.GENERATING.value else retry_count
                connection.execute(
                    """
                    UPDATE tasks
                    SET status = ?, error_message = ?, retry_count = ?,
                        updated_at = ?
                    WHERE task_id = ? AND status = ?
                    """,
                    (
                        next_status,
                        next_error,
                        next_retry_count,
                        now,
                        task_id,
                        TaskStatus.DOWNLOADING.value,
                    ),
                )
            if task_row and next_status == TaskStatus.FAILED.value:
                connection.execute(
                    """
                    UPDATE accounts
                    SET generating_count = MAX(generating_count - 1, 0)
                    WHERE name = ?
                    """,
                    (task_row["account_name"],),
                )
            connection.commit()
        return self.get_task(task_id)

    def rescue_stale_downloads(self) -> None:
        """Reset stale DOWNLOADING tasks to GENERATING before startup recount."""
        now = time.time()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = ?, updated_at = ?
                WHERE status = ?
                """,
                (
                    TaskStatus.GENERATING.value,
                    now,
                    TaskStatus.DOWNLOADING.value,
                ),
            )
            connection.commit()

    def rebuild_generating_counts(self) -> None:
        """Recount generating tasks per account from task table.

        Call on startup to repair generating_count after unclean shutdown.
        """
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT account_name, COUNT(*) as cnt
                FROM tasks
                WHERE status IN (?, ?)
                GROUP BY account_name
                """,
                (TaskStatus.SUBMITTING.value, TaskStatus.GENERATING.value),
            ).fetchall()

            connection.execute("UPDATE accounts SET generating_count = 0")
            for row in rows:
                connection.execute(
                    "UPDATE accounts SET generating_count = ? WHERE name = ?",
                    (row["cnt"], row["account_name"]),
                )
            connection.commit()

    # ── Legacy update methods (kept for compatibility) ────────────────────────

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        result_video_path: str | None = None,
        error_message: str | None = None,
        increment_retry: bool = False,
    ) -> Task | None:
        now = time.time()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = ?,
                    result_video_path = COALESCE(?, result_video_path),
                    error_message = ?,
                    retry_count = retry_count + ?,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (
                    status.value,
                    result_video_path,
                    error_message,
                    1 if increment_retry else 0,
                    now,
                    task_id,
                ),
            )
            connection.commit()
        return self.get_task(task_id)

    def sync_accounts(self, accounts: Iterable[Account | dict]) -> list[Account]:
        normalized = [
            account if isinstance(account, Account) else Account.model_validate(account)
            for account in accounts
        ]
        with self.connect() as connection:
            duplicate_space_rows = connection.execute(
                """
                SELECT space_id
                FROM accounts
                WHERE space_id != ''
                GROUP BY space_id
                HAVING COUNT(*) > 1
                """
            ).fetchall()
            for row in duplicate_space_rows:
                space_id = row["space_id"]
                existing_rows = connection.execute(
                    """
                    SELECT name, generating_count
                    FROM accounts
                    WHERE space_id = ?
                    ORDER BY rowid ASC
                    """,
                    (space_id,),
                ).fetchall()
                if not existing_rows:
                    continue

                canonical_name = existing_rows[0]["name"]
                old_names = [existing_row["name"] for existing_row in existing_rows]
                preserved_generating = max(
                    int(existing_row["generating_count"] or 0)
                    for existing_row in existing_rows
                )
                placeholders = ",".join("?" for _ in old_names)
                connection.execute(
                    f"UPDATE tasks SET account_name = ? WHERE account_name IN ({placeholders})",
                    [canonical_name, *old_names],
                )
                connection.execute("DELETE FROM accounts WHERE space_id = ?", (space_id,))
                connection.execute(
                    """
                    INSERT INTO accounts (
                        name, space_id, cdp_url, web_port, status,
                        generating_count, max_concurrent
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        canonical_name,
                        space_id,
                        "",
                        0,
                        AccountStatus.ACTIVE.value,
                        preserved_generating,
                        10,
                    ),
                )

            for account in normalized:
                status_value = getattr(account.status, "value", account.status)
                existing_rows = connection.execute(
                    """
                    SELECT name, generating_count
                    FROM accounts
                    WHERE space_id = ?
                    ORDER BY rowid ASC
                    """,
                    (account.space_id,),
                ).fetchall()

                if existing_rows:
                    old_names = [row["name"] for row in existing_rows]
                    preserved_generating = max(
                        int(row["generating_count"] or 0)
                        for row in existing_rows
                    )
                    placeholders = ",".join("?" for _ in old_names)
                    connection.execute(
                        f"UPDATE tasks SET account_name = ? WHERE account_name IN ({placeholders})",
                        [account.name, *old_names],
                    )
                    connection.execute("DELETE FROM accounts WHERE space_id = ?", (account.space_id,))
                    connection.execute(
                        """
                        INSERT INTO accounts (
                            name, space_id, cdp_url, web_port, status,
                            generating_count, max_concurrent
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            account.name,
                            account.space_id,
                            account.cdp_url,
                            account.web_port,
                            status_value,
                            preserved_generating,
                            account.max_concurrent,
                        ),
                    )
                else:
                    connection.execute(
                        """
                        INSERT INTO accounts (
                            name, space_id, cdp_url, web_port, status,
                            generating_count, max_concurrent
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            account.name,
                            account.space_id,
                            account.cdp_url,
                            account.web_port,
                            status_value,
                            account.generating_count,
                            account.max_concurrent,
                        ),
                    )

            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_space_id ON accounts(space_id)"
            )
            connection.commit()
        return normalized

    def get_accounts(
        self,
        *,
        status: AccountStatus | None = None,
    ) -> list[Account]:
        query = "SELECT * FROM accounts"
        params: list[object] = []
        if status is not None:
            query += " WHERE status = ?"
            params.append(status.value)
        query += " ORDER BY name ASC"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [Account.model_validate(dict(row)) for row in rows]

    def update_generating_count(
        self,
        account_name: str,
        *,
        delta: int | None = None,
        value: int | None = None,
    ) -> Account | None:
        if (delta is None) == (value is None):
            raise ValueError("Provide exactly one of delta or value.")

        with self.connect() as connection:
            if value is not None:
                connection.execute(
                    """
                    UPDATE accounts
                    SET generating_count = ?
                    WHERE name = ?
                    """,
                    (max(0, value), account_name),
                )
            else:
                connection.execute(
                    """
                    UPDATE accounts
                    SET generating_count = MAX(generating_count + ?, 0)
                    WHERE name = ?
                    """,
                    (delta, account_name),
                )
            connection.commit()

            row = connection.execute(
                "SELECT * FROM accounts WHERE name = ?",
                (account_name,),
            ).fetchone()
        return Account.model_validate(dict(row)) if row else None
