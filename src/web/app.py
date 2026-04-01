from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import load_config
from src.providers.jimeng import JimengProvider
from src.runtime.harvester import Harvester
from src.runtime.scheduler import Scheduler
from src.runtime.storage import Storage
from src.web.routes import router

logger = logging.getLogger(__name__)

_SCHEDULER_INTERVAL = 5   # seconds between scheduler ticks
_HARVESTER_INTERVAL = 10  # seconds between harvester ticks


async def _scheduler_loop(scheduler: Scheduler) -> None:
    while True:
        try:
            submitted = await scheduler.run_once()
            if submitted:
                logger.info("Scheduler submitted %d task(s)", len(submitted))
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Scheduler loop error")
        await asyncio.sleep(_SCHEDULER_INTERVAL)


async def _harvester_loop(harvester: Harvester) -> None:
    while True:
        try:
            downloaded = await harvester.run_once()
            if downloaded:
                logger.info("Harvester downloaded %d video(s)", downloaded)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Harvester loop error")
        await asyncio.sleep(_HARVESTER_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    config_path = Path("config.yaml")
    config = load_config(config_path)

    storage = Storage(config.paths.database_path)
    storage.init_db()
    storage.rescue_stale_downloads()
    storage.rebuild_generating_counts()

    provider = JimengProvider(config, config_path)

    # Sync accounts from config into DB
    from src.models.account import Account, AccountStatus
    accounts = [
        Account(
            name=acct.name,
            space_id=acct.space_id,
            cdp_url=acct.cdp_url or config.providers.jimeng.cdp_url,
            web_port=acct.web_port or config.providers.jimeng.web_port,
            status=AccountStatus.ACTIVE,
            max_concurrent=acct.max_concurrent or config.providers.jimeng.default_concurrency,
        )
        for acct in config.providers.jimeng.accounts
    ]
    if accounts:
        storage.sync_accounts(accounts)

    scheduler = Scheduler(storage, provider, config)
    harvester = Harvester(storage, provider, config)

    app.state.config = config
    app.state.storage = storage
    app.state.provider = provider

    tasks = [
        asyncio.create_task(_scheduler_loop(scheduler), name="scheduler"),
        asyncio.create_task(_harvester_loop(harvester), name="harvester"),
    ]
    logger.info("即梦内容工厂 started — scheduler every %ds, harvester every %ds",
                _SCHEDULER_INTERVAL, _HARVESTER_INTERVAL)

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Background loops stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="即梦内容工厂", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
