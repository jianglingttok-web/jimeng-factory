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
        accounts = self.storage.get_accounts(status=AccountStatus.ACTIVE)
        submitted: list[str] = []
        max_retries = self.config.video.max_retries

        for account in accounts:
            slots = max(0, account.max_concurrent - account.generating_count)
            if slots <= 0:
                continue

            for _ in range(slots):
                # Claim one task at a time — if cancelled mid-loop, only the
                # current task needs rollback, not a pre-claimed batch.
                tasks = self.storage.claim_pending_tasks(account.name, limit=1)
                if not tasks:
                    break
                task = tasks[0]

                try:
                    acct_cfg = self.provider.get_account(account.name)
                except ValueError as exc:
                    self.storage.mark_submit_failed(
                        task.task_id,
                        f"{type(exc).__name__}: {exc}" or repr(exc),
                        max_retries=max_retries,
                    )
                    logger.warning("Account lookup failed for %s: %s", account.name, exc)
                    continue

                image_paths = self._resolve_image_paths(task.product_name)
                if not image_paths:
                    self.storage.mark_submit_failed(
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
                    self.storage.mark_submit_failed(
                        task.task_id,
                        "cancelled",
                        max_retries=max_retries,
                    )
                    raise
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Submit failed for task %s", task.task_id)
                    self.storage.mark_submit_failed(
                        task.task_id,
                        f"{type(exc).__name__}: {exc}" or repr(exc),
                        max_retries=max_retries,
                    )
                    continue

                if receipt.ok:
                    self.storage.mark_submit_succeeded(task.task_id, submitted_at=submit_start)
                    submitted.append(task.task_id)
                    logger.info("Submitted task %s for account %s", task.task_id, account.name)
                else:
                    self.storage.mark_submit_failed(
                        task.task_id,
                        receipt.error or "unknown error",
                        max_retries=max_retries,
                    )
                    logger.warning(
                        "Submit rejected for task %s: %s", task.task_id, receipt.error,
                    )

        return submitted
