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


class Storage:
    def __init__(self, database_path: str | Path):
        self.database_path = database_path
        if database_path != ":memory:":
            Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def init_db(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA_SQL)
            connection.commit()

    def create_task(self, task: Task | dict) -> Task:
        record = task if isinstance(task, Task) else Task.model_validate(task)
        payload = record.model_dump(mode="json")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    task_id, product_name, variant_id, prompt, account_name,
                    status, result_video_path, error_message, retry_count,
                    max_retries, created_at, updated_at, duration_seconds
                ) VALUES (
                    :task_id, :product_name, :variant_id, :prompt, :account_name,
                    :status, :result_video_path, :error_message, :retry_count,
                    :max_retries, :created_at, :updated_at, :duration_seconds
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
            for account in normalized:
                connection.execute(
                    """
                    INSERT INTO accounts (
                        name, space_id, cdp_url, web_port, status,
                        generating_count, max_concurrent
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        space_id = excluded.space_id,
                        cdp_url = excluded.cdp_url,
                        web_port = excluded.web_port,
                        status = excluded.status,
                        generating_count = excluded.generating_count,
                        max_concurrent = excluded.max_concurrent
                    """,
                    (
                        account.name,
                        account.space_id,
                        account.cdp_url,
                        account.web_port,
                        account.status.value,
                        account.generating_count,
                        account.max_concurrent,
                    ),
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
