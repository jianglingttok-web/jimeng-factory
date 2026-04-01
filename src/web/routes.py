from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.models.task import Task, TaskStatus

router = APIRouter(prefix="/api")


# ── Request / Response models ─────────────────────────────────────────────────

class SubmitRequest(BaseModel):
    product_name: str
    account_name: str
    count: int
    variant_ids: list[str] | None = None  # None = round-robin all variants


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
    """Create pending tasks for a product + account combination."""
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

    # Filter to requested variant IDs if specified
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
            task_id,
            TaskStatus.FAILED,
            error_message="stopped by user",
        )
    return updated.model_dump(mode="json") if updated else {}


# ── Accounts ──────────────────────────────────────────────────────────────────

@router.get("/accounts")
async def list_accounts(request: Request) -> list[dict[str, Any]]:
    accounts = request.app.state.storage.get_accounts()
    return [a.model_dump(mode="json") for a in accounts]


@router.post("/accounts/{name}/probe")
async def probe_account(name: str, request: Request) -> dict[str, Any]:
    """Basic health check: verify CDP is reachable for the account."""
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
