from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from src.models.task import Task, TaskStatus

router = APIRouter(prefix="/api")


# ── Request / Response models ─────────────────────────────────────────────────

class SubmitRequest(BaseModel):
    product_name: str
    account_name: str
    count: int
    variant_ids: list[str] | None = None


class VariantInput(BaseModel):
    prompt: str
    title: str = ""  # auto-generated from prompt if empty


class CreateProductRequest(BaseModel):
    name: str
    variants: list[VariantInput]


# ── Products ──────────────────────────────────────────────────────────────────

@router.get("/products")
async def list_products(request: Request) -> list[dict[str, Any]]:
    from src.runtime.product_store import list_products as _list
    return _list(request.app.state.config.paths.data_dir)


@router.get("/products/{name}")
async def get_product(name: str, request: Request) -> dict[str, Any]:
    from src.runtime.product_store import get_product as _get
    try:
        return _get(request.app.state.config.paths.data_dir, name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Product '{name}' not found")


@router.post("/products")
async def create_product(body: CreateProductRequest, request: Request) -> dict[str, Any]:
    from src.runtime.product_store import create_product as _create
    from src.models.product import PromptVariant
    data_dir = request.app.state.config.paths.data_dir
    variants = [
        PromptVariant(id="", title=v.title or v.prompt[:20], prompt=v.prompt)
        for v in body.variants
    ]
    try:
        return _create(data_dir, body.name, variants, images=[])
    except FileExistsError:
        raise HTTPException(status_code=409, detail=f"Product '{body.name}' already exists")


@router.put("/products/{name}")
async def update_product_route(name: str, request: Request) -> dict[str, Any]:
    from src.runtime.product_store import update_product as _update

    body = await request.json()
    variants = body.get("variants", [])
    data_dir = request.app.state.config.paths.data_dir
    try:
        return _update(data_dir, name, variants)
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
    product_dir = data_dir / name
    if not product_dir.exists():
        raise HTTPException(status_code=404, detail=f"Product '{name}' not found")

    saved: list[str] = []
    allowed = {".jpg", ".jpeg", ".png", ".webp"}
    for f in files:
        suffix = Path(f.filename or "").suffix.lower()
        if suffix not in allowed:
            continue
        dest = product_dir / f.filename
        with dest.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        saved.append(f.filename)

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
    product_dir = data_dir / name
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
) -> list[dict[str, Any]]:
    storage = request.app.state.storage
    task_status = TaskStatus(status) if status else None
    tasks = storage.list_tasks(
        status=task_status,
        product_name=product_name,
        account_name=account_name,
    )
    return [t.model_dump(mode="json") for t in tasks]


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

    created: list[str] = []
    for i in range(body.count):
        variant = variants[i % len(variants)]
        task = Task(
            product_name=body.product_name,
            variant_id=variant["id"],
            prompt=variant["prompt"],
            account_name=body.account_name,
        )
        storage.create_task(task)
        created.append(task.task_id)

    return {"created": len(created), "task_ids": created}


@router.post("/tasks/retry-failed")
async def retry_failed_tasks(request: Request) -> dict[str, Any]:
    """Reset all FAILED tasks back to PENDING so the scheduler can retry them."""
    storage = request.app.state.storage
    count = storage.reset_failed_tasks()
    return {"reset": count}


@router.post("/tasks/stop-batch")
async def stop_tasks_batch(request: Request) -> dict[str, Any]:
    body = await request.json()
    task_ids = body.get("task_ids", [])
    if not isinstance(task_ids, list):
        return {"stopped": 0, "error": "task_ids must be a list"}
    storage = request.app.state.storage
    count = storage.stop_tasks_batch(task_ids)
    return {"stopped": count}


@router.post("/tasks/{task_id}/stop")
async def stop_task(task_id: str, request: Request) -> dict[str, Any]:
    storage = request.app.state.storage
    task = storage.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in (TaskStatus.PENDING, TaskStatus.SUBMITTING):
        raise HTTPException(status_code=409, detail=f"Cannot stop task in status '{task.status}'")
    if task.status == TaskStatus.SUBMITTING:
        updated = storage.mark_submit_failed(task_id, "stopped by user")
    else:
        updated = storage.update_task_status(
            task_id, TaskStatus.FAILED, error_message="stopped by user"
        )
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
        return {"ok": False, "error": str(exc)}


# ── System status ─────────────────────────────────────────────────────────────

@router.get("/status")
async def system_status(request: Request) -> dict[str, Any]:
    storage = request.app.state.storage
    accounts = storage.get_accounts()

    status_counts: dict[str, int] = {}
    for s in TaskStatus:
        status_counts[s.value] = len(storage.list_tasks(status=s))

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
        raise HTTPException(status_code=502, detail=f"Cannot reach multi-space browser: {exc}")

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
