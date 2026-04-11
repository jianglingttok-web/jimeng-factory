from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from src.config import AppConfig
from src.models.account import AccountStatus
from src.models.task import TaskStatus
from src.providers.jimeng import JimengProvider, RemoteResult
from src.runtime.storage import Storage

logger = logging.getLogger(__name__)


class Harvester:
    def __init__(self, storage: Storage, provider: JimengProvider, config: AppConfig):
        self.storage = storage
        self.provider = provider
        self.config = config

    def _output_dir(self, product_name: str) -> Path:
        return Path(self.config.paths.output_dir) / product_name

    async def run_once(self) -> int:
        """Check all GENERATING tasks for completion and download finished videos.

        Returns the number of tasks that were downloaded this cycle.
        """
        max_retries = self.config.video.max_retries
        generating_tasks = await asyncio.to_thread(self.storage.list_tasks, status=TaskStatus.GENERATING)
        if not generating_tasks:
            return 0

        # Group by account to minimise CDP connections
        by_account: dict[str, list] = {}
        for task in generating_tasks:
            by_account.setdefault(task.account_name, []).append(task)

        downloaded = 0

        for account_name, tasks in by_account.items():
            try:
                acct_cfg = self.provider.get_account(account_name)
            except ValueError:
                logger.error("Account '%s' not in provider config — skipping harvest", account_name)
                continue

            # Split into: tasks that already have a result_url (retry download)
            # and tasks that still need to be matched to a remote result.
            retry_download = sorted(
                [task for task in tasks if task.result_url],
                key=lambda task: task.submitted_at or 0.0,
            )
            needs_match = sorted(
                [task for task in tasks if task.result_url is None],
                key=lambda task: task.submitted_at or 0.0,
            )

            # Consumed URLs: all result_urls already claimed for this account
            # (across all statuses, not just GENERATING) to prevent re-binding.
            account_tasks = await asyncio.to_thread(self.storage.list_tasks, account_name=account_name)
            consumed_urls = {
                task.result_url
                for task in account_tasks
                if task.result_url
            }

            # Build the download work list starting with retry tasks
            downloads: list[tuple] = [
                (
                    task,
                    RemoteResult(
                        url=task.result_url,
                        created_at=task.submitted_at or 0.0,
                    ),
                )
                for task in retry_download
                if task.result_url
            ]

            # Match unmatched tasks to fresh remote results
            if needs_match:
                submitted_ats = [task.submitted_at for task in needs_match if task.submitted_at is not None]
                since_ts = min(submitted_ats) if submitted_ats else 0.0

                try:
                    completed = await self.provider.list_completed(acct_cfg, since_ts=since_ts)
                except Exception:  # noqa: BLE001
                    logger.exception("Harvester list_completed failed for account %s", account_name)
                    completed = []

                # Deduplicate and filter consumed URLs; sort by created_at for stable ordering
                fresh_results: list[RemoteResult] = []
                seen_urls = set(consumed_urls)
                for remote_result in sorted(completed, key=lambda r: r.created_at):
                    if not remote_result.url or remote_result.url in seen_urls:
                        continue
                    fresh_results.append(remote_result)
                    seen_urls.add(remote_result.url)

                for task, remote_result in zip(needs_match, fresh_results):
                    if not await asyncio.to_thread(self.storage.claim_result_url, task.task_id, remote_result.url):
                        continue  # another process already claimed it
                    downloads.append((task, remote_result))

            # Execute downloads
            for task, remote_result in downloads:
                dest_dir = self._output_dir(task.product_name)
                dest_dir.mkdir(parents=True, exist_ok=True)

                # Mark as downloading before actual download
                await asyncio.to_thread(self.storage.update_task_status, task.task_id, TaskStatus.DOWNLOADING)

                try:
                    receipt = await self.provider.download_video(
                        acct_cfg, remote_result, dest_dir
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Harvester download failed for task %s", task.task_id)
                    await asyncio.to_thread(
                        self.storage.mark_download_failed,
                        task.task_id,
                        str(exc),
                        max_retries=max_retries,
                    )
                    continue

                if receipt.ok and receipt.path:
                    await asyncio.to_thread(self.storage.mark_download_succeeded, task.task_id, receipt.path)
                    downloaded += 1
                    logger.info("Downloaded task %s → %s", task.task_id, receipt.path)
                else:
                    await asyncio.to_thread(
                        self.storage.mark_download_failed,
                        task.task_id,
                        receipt.error or "download returned no path",
                        max_retries=max_retries,
                    )

        return downloaded
