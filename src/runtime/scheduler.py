from __future__ import annotations

import asyncio
import logging

from src.config import AppConfig
from src.models.account import AccountStatus
from src.models.task import Task, TaskStatus
from src.providers.jimeng import JimengProvider
from src.runtime.storage import Storage

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, storage: Storage, provider: JimengProvider, config: AppConfig):
        self.storage = storage
        self.provider = provider
        self.config = config

    async def run_once(self) -> list[str]:
        accounts = self.storage.get_accounts(status=AccountStatus.ACTIVE)
        slot_map = {
            account.name: max(0, account.max_concurrent - account.generating_count)
            for account in accounts
        }
        pending = self.storage.list_tasks(status=TaskStatus.PENDING)

        tasks_by_account: dict[str, list[Task]] = {}
        for task in pending:
            tasks_by_account.setdefault(task.account_name, []).append(task)

        submitted: list[str] = []

        for account_name, slots in slot_map.items():
            if slots <= 0:
                continue

            acct_tasks = tasks_by_account.get(account_name, [])
            for task in acct_tasks[:slots]:
                self.storage.update_task_status(task.task_id, TaskStatus.SUBMITTING)
                self.storage.update_generating_count(account_name, delta=+1)

                try:
                    acct_cfg = self.provider.get_account(account_name)
                except ValueError as exc:
                    self.storage.update_task_status(
                        task.task_id,
                        TaskStatus.FAILED,
                        error_message=str(exc),
                        increment_retry=True,
                    )
                    self.storage.update_generating_count(account_name, delta=-1)
                    logger.warning("Scheduler account lookup failed for %s: %s", account_name, exc)
                    continue

                try:
                    result = await self.provider.submit_job(
                        account=acct_cfg,
                        prompt=task.prompt,
                        image_paths=[],
                    )
                except asyncio.CancelledError:
                    self.storage.update_generating_count(account_name, delta=-1)
                    raise
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Scheduler submit failed for task %s", task.task_id)
                    self.storage.update_task_status(
                        task.task_id,
                        TaskStatus.FAILED,
                        error_message=str(exc),
                        increment_retry=True,
                    )
                    self.storage.update_generating_count(account_name, delta=-1)
                    submitted.append(task.task_id)
                    continue

                if result.get("ok"):
                    self.storage.update_task_status(task.task_id, TaskStatus.GENERATING)
                else:
                    self.storage.update_task_status(
                        task.task_id,
                        TaskStatus.FAILED,
                        error_message=result.get("error"),
                        increment_retry=True,
                    )
                    self.storage.update_generating_count(account_name, delta=-1)

                submitted.append(task.task_id)

        return submitted
