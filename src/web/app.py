from __future__ import annotations

import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from src.auth.init_admin import ensure_admin_user
from src.config import load_config
from src.providers.jimeng import JimengProvider
from src.runtime.harvester import Harvester
from src.runtime.scheduler import Scheduler
from src.runtime.storage import Storage
from src.runtime.user_store import UserStore
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

    # ── Auth setup ────────────────────────────────────────────────────────────
    user_store = UserStore(config.paths.database_path)
    user_store.init_db()
    ensure_admin_user(user_store)

    if not config.auth.secret_key:
        env_key = os.environ.get("JIMENG_SECRET_KEY")
        if env_key:
            config.auth.secret_key = env_key
        else:
            config.auth.secret_key = secrets.token_hex(32)
            logger.warning(
                "JIMENG_SECRET_KEY not set — using ephemeral key. "
                "All tokens will be invalidated on next restart. "
                "Set JIMENG_SECRET_KEY in environment to persist sessions."
            )

    app.state.user_store = user_store

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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    config = load_config(Path("config.yaml"))
    app = FastAPI(title="即梦内容工厂", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.web.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    from src.web.auth_routes import auth_router
    app.include_router(auth_router)
    app.include_router(router)
    # Serve frontend static files in production (when dist/ exists).
    dist_dir = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if dist_dir.is_dir():
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            resolved = (dist_dir / full_path).resolve()
            if resolved.is_file() and resolved.is_relative_to(dist_dir.resolve()):
                return FileResponse(resolved)
            return FileResponse(dist_dir / "index.html")
    return app


app = create_app()
