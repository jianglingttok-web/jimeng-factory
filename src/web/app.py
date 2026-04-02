from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
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

    scheduler = Scheduler(storage, provider, config)
    harvester = Harvester(storage, provider, config)

    app.state.config = config
    app.state.storage = storage
    app.state.provider = provider

    # Auto-discover accounts from multi-space browser on startup
    from src.web.routes import _do_discover
    try:
        discovered = await _do_discover(app.state)
        logger.info("Auto-discovered %d account(s) from multi-space browser", len(discovered))
    except Exception as exc:
        logger.warning("Account auto-discovery failed (will retry via /api/accounts/discover): %s", exc)

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
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8001",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    # Serve frontend static files in production (when dist/ exists).
    dist_dir = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if dist_dir.is_dir():
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            file_path = dist_dir / full_path
            if file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(dist_dir / "index.html")
    return app


app = create_app()
