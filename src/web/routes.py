from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from src.models.task import Task, TaskStatus

router = APIRouter(prefix="/api")


# ── Request / Response models ─────────────────────────────────────────────────

class SubmitRequest(BaseModel):
    product_name: str
    account_name: str
    count: int
    variant_ids: list[str] | None = None
    duration_seconds: int | None = None


class VariantInput(BaseModel):
    prompt: str
    title: str = ""  # auto-generated from prompt if empty


class CreateProductRequest(BaseModel):
    name: str
    variants: list[VariantInput]


class UpdateProductRequest(BaseModel):
    variants: list[VariantInput]


class StopBatchRequest(BaseModel):
    task_ids: list[str]


def _safe_product_dir(data_dir: str | Path, name: str) -> Path:
    """Resolve product directory and guard against path traversal."""
    base = Path(data_dir).resolve()
    product_dir = (base / name).resolve()
    if not product_dir.is_relative_to(base):
        raise HTTPException(status_code=400, detail="Invalid product name")
    return product_dir


# ── Products ──────────────────────────────────────────────────────────────────

@router.get("/products")
async def list_products(request: Request) -> list[dict[str, Any]]:
    from src.runtime.product_store import list_products as _list
    return _list(request.app.state.config.paths.data_dir)


@router.get("/products/{name}")
async def get_product(name: str, request: Request) -> dict[str, Any]:
    from src.runtime.product_store import get_product as _get
    config = request.app.state.config
    _safe_product_dir(config.paths.data_dir, name)  # validate before delegating
    try:
        return _get(config.paths.data_dir, name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Product '{name}' not found")


@router.post("/products")
async def create_product(body: CreateProductRequest, request: Request) -> dict[str, Any]:
    from src.runtime.product_store import create_product as _create
    from src.models.product import PromptVariant
    data_dir = request.app.state.config.paths.data_dir
    _safe_product_dir(data_dir, body.name)  # validate before delegating
    variants = [
        PromptVariant(id="", title=v.title or v.prompt[:20], prompt=v.prompt)
        for v in body.variants
    ]
    try:
        return _create(data_dir, body.name, variants, images=[])
    except FileExistsError:
        raise HTTPException(status_code=409, detail=f"Product '{body.name}' already exists")


@router.put("/products/{name}")
async def update_product_route(name: str, body: UpdateProductRequest, request: Request) -> dict[str, Any]:
    from src.runtime.product_store import update_product as _update
    data_dir = request.app.state.config.paths.data_dir
    _safe_product_dir(data_dir, name)  # path traversal guard
    try:
        return _update(data_dir, name, [v.model_dump() for v in body.variants])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Product '{name}' not found")


@router.post("/products/{name}/images")
async def upload_product_images(
    name: str,
    request: Request,
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    """Upload images to a product directory."""
    from src.runtime.product_store import get_product as _get, _write_product_file
    from src.models.product import Product
    import json

    data_dir = Path(request.app.state.config.paths.data_dir)
    product_dir = _safe_product_dir(data_dir, name)
    if not product_dir.exists():
        raise HTTPException(status_code=404, detail=f"Product '{name}' not found")

    _MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
    saved: list[str] = []
    allowed = {".jpg", ".jpeg", ".png", ".webp"}
    for f in files:
        suffix = Path(f.filename or "").suffix.lower()
        if suffix not in allowed:
            continue
        safe_name = Path(f.filename or "").name
        if not safe_name or safe_name.startswith(".") or safe_name == "product.json":
            continue
        # Reject filenames that contain path separators or traversal sequences
        if "/" in safe_name or "\\" in safe_name or ".." in safe_name:
            continue
        # Enforce file size limit
        if f.size is not None:
            if f.size > _MAX_FILE_SIZE:
                continue
            dest = product_dir / safe_name
            file_obj = f.file

            def _write_file(path: Path, src: Any) -> None:
                with path.open("wb") as out:
                    shutil.copyfileobj(src, out)

            await asyncio.to_thread(_write_file, dest, file_obj)
        else:
            # f.size unavailable — read in chunks and enforce limit during write
            dest = product_dir / safe_name
            written = 0
            chunk_size = 65536
            with dest.open("wb") as out:
                while True:
                    chunk = await f.read(chunk_size)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > _MAX_FILE_SIZE:
                        break
                    out.write(chunk)
            if written > _MAX_FILE_SIZE:
                dest.unlink(missing_ok=True)
                continue
        saved.append(safe_name)

    if saved:
        # Update product.json images list
        product_file = product_dir / "product.json"
        data = json.loads(product_file.read_text(encoding="utf-8"))
        existing = set(data.get("images", []))
        existing.update(saved)
        data["images"] = sorted(existing)
        product_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return {"saved": saved}


@router.delete("/products/{name}")
async def delete_product(name: str, request: Request) -> dict[str, Any]:
    data_dir = Path(request.app.state.config.paths.data_dir)
    product_dir = _safe_product_dir(str(data_dir), name)
    if not product_dir.exists():
        raise HTTPException(status_code=404, detail=f"Product '{name}' not found")
    shutil.rmtree(product_dir)
    return {"deleted": name}


# ── Tasks ─────────────────────────────────────────────────────────────────────

@router.get("/tasks")
async def list_tasks(
    request: Request,
    status: str | None = None,
    product_name: str | None = None,
    account_name: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    storage = request.app.state.storage
    task_status = TaskStatus(status) if status else None
    tasks = storage.list_tasks(
        status=task_status,
        product_name=product_name,
        account_name=account_name,
        limit=limit,
        offset=offset,
    )
    return {
        "tasks": [t.model_dump(mode="json") for t in tasks],
        "total": len(tasks),
        "limit": limit,
        "offset": offset,
    }


@router.post("/tasks/submit")
async def submit_tasks(body: SubmitRequest, request: Request) -> dict[str, Any]:
    from src.models.task import Task
    from src.runtime.product_store import get_product as _get

    config = request.app.state.config
    storage = request.app.state.storage

    try:
        product = _get(config.paths.data_dir, body.product_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Product '{body.product_name}' not found")

    variants = product.get("prompt_variants", [])
    if not variants:
        raise HTTPException(status_code=422, detail="Product has no prompt variants")

    if body.variant_ids:
        variants = [v for v in variants if v["id"] in body.variant_ids]
        if not variants:
            raise HTTPException(status_code=422, detail="None of the requested variant_ids found")

    batch: list[Task] = []
    for i in range(body.count):
        variant = variants[i % len(variants)]
        batch.append(Task(
            product_name=body.product_name,
            variant_id=variant["id"],
            prompt=variant["prompt"],
            account_name=body.account_name,
            duration_seconds=body.duration_seconds,
        ))
    storage.create_tasks_batch(batch)

    return {"created": len(batch), "task_ids": [t.task_id for t in batch]}


@router.post("/tasks/retry-failed")
async def retry_failed_tasks(request: Request) -> dict[str, Any]:
    """Reset all FAILED tasks back to PENDING so the scheduler can retry them."""
    storage = request.app.state.storage
    count = storage.reset_failed_tasks()
    return {"reset": count}


@router.post("/tasks/stop-batch")
async def stop_tasks_batch(body: StopBatchRequest, request: Request) -> dict[str, Any]:
    _MAX_BATCH = 500
    if len(body.task_ids) > _MAX_BATCH:
        raise HTTPException(status_code=422, detail=f"Too many task_ids; max is {_MAX_BATCH}")
    for tid in body.task_ids:
        if not tid or not isinstance(tid, str) or len(tid) >= 64:
            raise HTTPException(status_code=422, detail="Invalid task_id in batch")
    storage = request.app.state.storage
    count = storage.stop_tasks_batch(body.task_ids)
    return {"stopped": count}


@router.post("/tasks/{task_id}/stop")
async def stop_task(task_id: str, request: Request) -> dict[str, Any]:
    storage = request.app.state.storage
    task = storage.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    cancellable = (
        TaskStatus.PENDING,
        TaskStatus.SUBMITTING,
        TaskStatus.GENERATING,
        TaskStatus.DOWNLOADING,
    )
    if task.status not in cancellable:
        raise HTTPException(status_code=409, detail=f"Cannot stop task in status '{task.status}'")
    stopped = storage.stop_tasks_batch([task_id])
    if not stopped:
        raise HTTPException(status_code=409, detail="Task could not be stopped")
    updated = storage.get_task(task_id)
    return updated.model_dump(mode="json") if updated else {}


# ── Accounts ──────────────────────────────────────────────────────────────────

@router.get("/accounts")
async def list_accounts(request: Request) -> list[dict[str, Any]]:
    accounts = request.app.state.storage.get_accounts()
    return [a.model_dump(mode="json") for a in accounts]


@router.post("/accounts/discover")
async def discover_accounts(request: Request) -> dict[str, Any]:
    """Pull account list from multi-space browser API and sync to DB."""
    synced = await _do_discover(request.app.state)
    return {"synced": len(synced), "accounts": [a.model_dump(mode="json") for a in synced]}


@router.post("/accounts/{name}/probe")
async def probe_account(name: str, request: Request) -> dict[str, Any]:
    provider = request.app.state.provider
    try:
        acct_cfg = provider.get_account(name)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Account '{name}' not found in config")
    try:
        targets = await provider._fetch_cdp_targets(acct_cfg)
        return {"ok": True, "cdp_targets": len(targets)}
    except Exception as exc:  # noqa: BLE001
        logger.error("CDP probe failed for account '%s': %s", name, exc)
        return {"ok": False, "error": "CDP probe failed"}


# ── System status ─────────────────────────────────────────────────────────────

@router.get("/status")
async def system_status(request: Request) -> dict[str, Any]:
    storage = request.app.state.storage
    accounts = storage.get_accounts()

    raw_counts = storage.count_tasks_by_status()
    status_counts = {s.value: raw_counts.get(s.value, 0) for s in TaskStatus}

    return {
        "tasks": status_counts,
        "accounts": [
            {
                "name": a.name,
                "status": a.status.value,
                "generating_count": a.generating_count,
                "max_concurrent": a.max_concurrent,
            }
            for a in accounts
        ],
    }


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


# ── Account discovery helper (shared with lifespan) ──────────────────────────

async def _do_discover(state: Any) -> list:
    """Fetch spaces from multi-space browser API and sync as accounts."""
    import asyncio
    from urllib import request as urllib_request
    import json as _json
    from src.models.account import Account, AccountStatus

    config = state.config
    storage = state.storage
    web_port = config.providers.jimeng.web_port
    cdp_url = config.providers.jimeng.cdp_url
    max_concurrent = config.providers.jimeng.default_concurrency

    for var in ("no_proxy", "NO_PROXY"):
        existing = os.environ.get(var, "")
        if "127.0.0.1" not in existing:
            os.environ[var] = (
                f"127.0.0.1,localhost,{existing}"
                if existing
                else "127.0.0.1,localhost"
            )

    url = f"http://127.0.0.1:{web_port}/api/sandbox/spaces"
    try:
        raw = await asyncio.to_thread(
            lambda: urllib_request.urlopen(  # noqa: S310
                urllib_request.Request(url, headers={"User-Agent": "jimeng-factory"}),
                timeout=5,
            ).read().decode("utf-8")
        )
        spaces = _json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        logger.error("Account discovery failed reaching multi-space browser: %s", exc)
        raise HTTPException(status_code=502, detail="Cannot reach multi-space browser")

    if not isinstance(spaces, list):
        raise HTTPException(status_code=502, detail="Unexpected response from multi-space browser")

    accounts = [
        Account(
            name=space.get("name") or space["id"],
            space_id=space["id"],
            cdp_url=cdp_url,
            web_port=web_port,
            status=AccountStatus.ACTIVE,
            max_concurrent=max_concurrent,
        )
        for space in spaces
        if space.get("id")
    ]
    if accounts:
        storage.sync_accounts(accounts)
        # Keep provider config in sync so get_account() works
        from src.config import JimengAccountConfig
        state.provider.provider_config.accounts = [
            JimengAccountConfig(
                name=a.name,
                space_id=a.space_id,
                cdp_url=a.cdp_url,
                web_port=a.web_port,
                max_concurrent=a.max_concurrent,
            )
            for a in accounts
        ]
    return accounts
