from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from src.config import AppConfig
from src.models.account import AccountStatus
from src.providers.jimeng import JimengProvider
from src.runtime.storage import Storage

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, storage: Storage, provider: JimengProvider, config: AppConfig):
        self.storage = storage
        self.provider = provider
        self.config = config

    def _resolve_image_paths(self, product_name: str) -> list[str]:
        """Return absolute paths for all images under data_dir/{product_name}/."""
        data_dir = Path(self.config.paths.data_dir)
        product_dir = data_dir / product_name
        if not product_dir.exists():
            return []
        extensions = {".jpg", ".jpeg", ".png", ".webp"}
        return sorted(
            str(p.resolve())
            for p in product_dir.iterdir()
            if p.suffix.lower() in extensions
        )

    async def run_once(self) -> list[str]:
        accounts = await asyncio.to_thread(self.storage.get_accounts, status=AccountStatus.ACTIVE)
        # Submit across accounts concurrently — each account's tasks are
        # still sequential (shared browser page), but different accounts
        # run in parallel.
        results = await asyncio.gather(
            *[self._submit_for_account(account) for account in accounts],
            return_exceptions=True,
        )
        submitted: list[str] = []
        for result in results:
            if isinstance(result, Exception):
                logger.exception("Account-level submission error: %s", result)
            elif isinstance(result, list):
                submitted.extend(result)
        return submitted

    async def _submit_for_account(self, account) -> list[str]:
        submitted: list[str] = []
        max_retries = self.config.video.max_retries

        slots = max(0, account.max_concurrent - account.generating_count)
        if slots <= 0:
            return submitted

        tasks = await asyncio.to_thread(self.storage.claim_pending_tasks, account.name, slots)
        for task in tasks:

            try:
                acct_cfg = self.provider.get_account(account.name)
            except ValueError as exc:
                await asyncio.to_thread(
                    self.storage.mark_submit_failed,
                    task.task_id,
                    f"{type(exc).__name__}: {exc}",
                    max_retries=0,
                )
                logger.error(
                    "Account '%s' not in provider config — task %s failed permanently. "
                    "Run /api/accounts/discover to reload.",
                    account.name, task.task_id,
                )
                continue

            image_paths = self._resolve_image_paths(task.product_name)
            if not image_paths:
                await asyncio.to_thread(
                    self.storage.mark_submit_failed,
                    task.task_id,
                    f"No images found for product '{task.product_name}'",
                    max_retries=max_retries,
                )
                logger.warning(
                    "No images for product '%s', task %s failed",
                    task.product_name, task.task_id,
                )
                continue

            submit_start = time.time()
            try:
                receipt = await self.provider.submit_job(
                    account=acct_cfg,
                    prompt=task.prompt,
                    image_paths=image_paths,
                    duration_seconds=task.duration_seconds,
                )
            except asyncio.CancelledError:
                await asyncio.to_thread(
                    self.storage.mark_submit_failed,
                    task.task_id,
                    "cancelled",
                    max_retries=max_retries,
                )
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception("Submit failed for task %s", task.task_id)
                await asyncio.to_thread(
                    self.storage.mark_submit_failed,
                    task.task_id,
                    f"{type(exc).__name__}: {exc}",
                    max_retries=max_retries,
                )
                continue

            if receipt.ok:
                await asyncio.to_thread(self.storage.mark_submit_succeeded, task.task_id, submitted_at=submit_start)
                submitted.append(task.task_id)
                logger.info("Submitted task %s for account %s", task.task_id, account.name)
            else:
                await asyncio.to_thread(
                    self.storage.mark_submit_failed,
                    task.task_id,
                    receipt.error or "unknown error",
                    max_retries=max_retries,
                )
                logger.warning(
                    "Submit rejected for task %s: %s", task.task_id, receipt.error,
                )

        return submitted
