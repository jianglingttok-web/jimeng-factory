from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from urllib import request as urllib_request

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import Browser, BrowserContext, Locator, Page, Playwright, async_playwright

from src.config import AppConfig, JimengAccountConfig

# ── Selectors ────────────────────────────────────────────────────────────────

PROMPT_SELECTORS = [
    "div.prompt-editor-ZsQbxJ [contenteditable='true'][role='textbox']",
    "div.prompt-editor-sizer-uoJfkU [contenteditable='true'][role='textbox']",
    "textarea",
    "div[contenteditable='true'][role='textbox']",
    "[role='textbox']",
]

UPLOAD_SELECTORS = [
    "input.file-input-tdRCSu",
    "input[type='file']",
]

REFERENCE_REMOVE_SELECTORS = [
    "div.remove-button-I6lF9g",
    "div.remove-button-container-h9rAPn div.remove-button-I6lF9g",
    "div[class*='remove-button']",
    "div[class*='remove-button-container'] div[class*='remove-button']",
    "button[class*='remove-button']",
]

GENERATE_TEXT_CANDIDATES = [
    "\u751f\u6210\u89c6\u9891",
    "\u7acb\u5373\u751f\u6210",
    "\u5f00\u59cb\u751f\u6210",
    "\u751f\u6210",
]

GENERATE_BUTTON_SELECTORS = [
    "div.toolbar-actions-KjbR4x button.submit-button-xdhu0e",
    "div.toolbar-actions-KjbR4x button.submit-button-s4a7XV",
    "div.collapsed-submit-button-container-H2gPUd button.submit-button-xdhu0e",
    "button.submit-button-xdhu0e.submit-button-s4a7XV",
    "button.submit-button-xdhu0e.collapsed-submit-button-jLdVvV",
    "button.lv-btn-primary.lv-btn-icon-only.button-Kn5fSj[type='button']",
]

LOGIN_BLOCK_SELECTORS = [
    "text=\u540c\u610f\u534f\u8bae\u4ee5\u540e\u524d\u5f80\u767b\u5f55",
    "button:has-text('\u767b\u5f55')",
]

PROGRESS_SELECTORS = [
    "span.progress-Rrdm29",
    "div.inside-content-generator-UYAdvw span.progress-Rrdm29",
]

TOOLBAR_READY_SELECTORS = [
    "div.toolbar-CO0C5P",
    "div[class*='toolbar-']",
    "div[class*='toolbar-'] div[role='combobox']",
    "div[role='combobox']",
    "button[class*='toolbar-button-']",
]

SUBMISSION_SURFACE_SELECTORS = [
    "div.toolbar-CO0C5P",
    "div[class*='toolbar-']",
    "div.prompt-editor-container-VmNauw",
    "div[class*='prompt-editor-container-']",
    "div.prompt-editor-ZsQbxJ [contenteditable='true'][role='textbox']",
    "div[class*='prompt-editor-'] [contenteditable='true'][role='textbox']",
    "input.file-input-tdRCSu",
    "input[type='file']",
]

JIMENG_HOST_FRAGMENT = "jimeng.jianying.com"
TOOLBAR_PAGE_FRAGMENT = "renderer/browser.html"

_CDP_ACTIVATION_LOCKS: dict[str, asyncio.Lock] = {}

logger = logging.getLogger(__name__)
_TRANSCODE_QUALITIES = ("720p", "480p", "360p", "origin")

# ── Harvest helpers ───────────────────────────────────────────────────────────

def _download_url_sync(url: str, dest_path: str) -> None:
    """Synchronous download helper (run via asyncio.to_thread)."""
    req = urllib_request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 jimeng-factory/1.0"},
    )
    with urllib_request.urlopen(req, timeout=120) as response:  # noqa: S310
        data = response.read()
    Path(dest_path).write_bytes(data)


@dataclass
class SessionHandle:
    playwright: Playwright
    browser: Optional[Browser]
    context: BrowserContext
    page: Page
    created_page: bool


# ── Public API return types ───────────────────────────────────────────────────

@dataclass
class SubmitReceipt:
    ok: bool
    error: Optional[str] = None


@dataclass
class RemoteResult:
    """A completed video available for download on the Jimeng platform."""
    url: str
    created_at: float  # unix timestamp when generation completed
    title: str = ""


@dataclass
class DownloadReceipt:
    ok: bool
    path: Optional[str] = None  # absolute local path if ok
    error: Optional[str] = None


class JimengProvider:
    def __init__(self, config: AppConfig, config_path: str | Path):
        self.config = config
        self.config_path = Path(config_path).resolve()
        self.provider_config = config.providers.jimeng
        self._sticky_generate_pages: dict[str, Page] = {}
        self._configured_generate_pages: dict[str, int] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def get_account(self, account_name: str) -> JimengAccountConfig:
        for account in self.provider_config.accounts:
            if account.name == account_name:
                return account
        raise ValueError(f"Unknown account: {account_name}")

    def _effective_cdp_url(self, account: JimengAccountConfig) -> str:
        return account.cdp_url or self.provider_config.cdp_url

    def _effective_max_concurrent(self, account: JimengAccountConfig) -> int:
        return account.max_concurrent or self.provider_config.default_concurrency

    async def submit_job(
        self,
        account: JimengAccountConfig,
        prompt: str,
        image_paths: Iterable[str | Path],
    ) -> SubmitReceipt:
        """Submit a generation job to Jimeng via CDP browser automation."""
        resolved_images = [str(Path(item).resolve()) for item in image_paths]

        if not resolved_images:
            return SubmitReceipt(ok=False, error="at least one image is required")

        timeout_ms = self.config.video.task_timeout_seconds * 1000

        session: SessionHandle | None = None
        try:
            session = await self._open_session(account=account, reuse_existing_page=True)
            page = await self._ensure_work_page(session, account, "generate", timeout_ms)
            await self._prepare_submission_page(page, account=account)
            await self._upload_images(page, resolved_images)
            await self._fill_prompt(page, prompt)
            await self._wait_for_available_generation_slot(
                page=page,
                target_limit=self._effective_max_concurrent(account),
                timeout_ms=timeout_ms,
            )
            await self._click_generate(page)
            await page.wait_for_timeout(1500)
            return SubmitReceipt(ok=True)

        except PlaywrightTimeoutError as exc:
            if any(token in str(exc) for token in ("Toolbar combobox index", "Toolbar controls were not ready")):
                self._forget_sticky_generate_page(account)
            return SubmitReceipt(ok=False, error=f"timeout: {exc}")
        except Exception as exc:  # noqa: BLE001
            if any(token in str(exc) for token in ("Toolbar combobox index", "Toolbar controls were not ready")):
                self._forget_sticky_generate_page(account)
            return SubmitReceipt(ok=False, error=f"{type(exc).__name__}: {exc}" or repr(exc))
        finally:
            if session is not None:
                await self._close_session(session)

    def _pick_transcoded_video_url(self, transcoded: Any) -> Optional[str]:
        if not isinstance(transcoded, dict):
            return None
        for quality in _TRANSCODE_QUALITIES:
            candidate = transcoded.get(quality)
            if not isinstance(candidate, dict):
                continue
            url = str(candidate.get("video_url") or "").strip()
            if url:
                return url
        return None

    def _extract_remote_results_from_asset_payload(
        self,
        payload: Any,
        since_ts: float,
    ) -> list[RemoteResult]:
        data = payload.get("data") if isinstance(payload, dict) else None
        asset_list = data.get("asset_list") if isinstance(data, dict) else None
        if not isinstance(asset_list, list):
            return []

        results: list[RemoteResult] = []
        for asset in asset_list:
            if not isinstance(asset, dict) or asset.get("type") != 2:
                continue

            video = asset.get("video")
            if not isinstance(video, dict):
                continue

            created_at = float(video.get("created_time") or 0)
            if created_at > 1e12:
                created_at = created_at / 1000
            if created_at < since_ts:
                continue

            item_list = video.get("item_list")
            if not isinstance(item_list, list) or not item_list:
                continue

            first_item = item_list[0]
            item_video = first_item.get("video") if isinstance(first_item, dict) else None
            transcoded = item_video.get("transcoded_video") if isinstance(item_video, dict) else None
            url = self._pick_transcoded_video_url(transcoded)
            if not url:
                continue

            results.append(
                RemoteResult(
                    url=url,
                    created_at=created_at,
                    title=str(asset.get("id") or ""),
                )
            )
        return results

    async def list_completed(
        self,
        account: JimengAccountConfig,
        since_ts: float,
    ) -> list[RemoteResult]:
        """Poll the Jimeng generate page for videos completed after since_ts."""
        timeout_ms = self.config.video.task_timeout_seconds * 1000
        session: SessionHandle | None = None
        page: Optional[Page] = None
        captured_responses: list[Any] = []

        def capture_response(response: Any) -> None:
            if "get_asset_list" in response.url:
                captured_responses.append(response)

        try:
            session = await self._open_session(account=account, reuse_existing_page=True)
            page = await self._ensure_work_page(session, account, "generate", timeout_ms)
            page.on("response", capture_response)

            with contextlib.suppress(Exception):
                await page.reload(wait_until="domcontentloaded", timeout=min(timeout_ms, 20_000))
            with contextlib.suppress(Exception):
                await page.wait_for_timeout(3000)

            items_by_url: dict[str, RemoteResult] = {}
            for response in captured_responses:
                try:
                    payload = await response.json()
                except Exception:
                    continue
                for item in self._extract_remote_results_from_asset_payload(payload, since_ts):
                    if item.url not in items_by_url:
                        items_by_url[item.url] = item

            items = sorted(items_by_url.values(), key=lambda item: item.created_at)
            logger.info(
                "list_completed: account=%s since=%.0f found=%d",
                account.name, since_ts, len(items),
            )
            return items

        except Exception as exc:  # noqa: BLE001
            logger.exception("list_completed failed for account %s", account.name)
            return []
        finally:
            if page is not None:
                with contextlib.suppress(Exception):
                    page.remove_listener("response", capture_response)
            if session is not None:
                await self._close_session(session)

    async def download_video(
        self,
        account: JimengAccountConfig,
        result: RemoteResult,
        dest_dir: str | Path,
    ) -> DownloadReceipt:
        """Download a completed video to dest_dir.

        Uses a direct HTTP request (CDN URLs don't need auth).
        Falls back to page.evaluate-based download if direct fails.
        """
        import uuid as _uuid
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        filename = f"{_uuid.uuid4().hex}.mp4"
        target = dest / filename

        try:
            await asyncio.to_thread(
                _download_url_sync,
                result.url,
                str(target),
            )
            return DownloadReceipt(ok=True, path=str(target))
        except Exception as exc:  # noqa: BLE001
            logger.error("Direct download failed for %s: %s", result.url, exc)
            return DownloadReceipt(ok=False, error=f"{type(exc).__name__}: {exc}" or repr(exc))

    # ── Session management ────────────────────────────────────────────────────

    async def _open_session(
        self,
        account: JimengAccountConfig,
        reuse_existing_page: bool,
    ) -> SessionHandle:
        cdp_url = self._effective_cdp_url(account)
        # Ensure local CDP connections bypass any HTTP proxy.
        for var in ("no_proxy", "NO_PROXY"):
            existing = os.environ.get(var, "")
            if "127.0.0.1" not in existing:
                os.environ[var] = (
                    f"127.0.0.1,localhost,{existing}"
                    if existing
                    else "127.0.0.1,localhost"
                )
        playwright = await async_playwright().start()
        browser = await playwright.chromium.connect_over_cdp(cdp_url)
        if not browser.contexts:
            await playwright.stop()
            raise RuntimeError("CDP connected, but no browser contexts are available.")

        existing_page = self._pick_existing_jimeng_page(browser) if reuse_existing_page else None
        if existing_page is not None:
            return SessionHandle(playwright, browser, existing_page.context, existing_page, False)

        context = browser.contexts[0]
        page = await self._open_cdp_page(context, seed_page=existing_page)
        return SessionHandle(playwright, browser, page.context, page, True)

    async def _close_session(self, session: SessionHandle) -> None:
        if session.created_page:
            with contextlib.suppress(Exception):
                await session.page.close()
        await session.playwright.stop()

    async def _open_cdp_page(self, context: BrowserContext, seed_page: Optional[Page] = None) -> Page:
        with contextlib.suppress(Exception):
            return await context.new_page()

        if seed_page is None:
            if context.pages:
                seed_page = context.pages[0]
            else:
                raise RuntimeError("CDP context has no reusable page to spawn a new tab.")

        existing_pages = set(context.pages)
        await seed_page.evaluate("(url) => window.open(url, '_blank')", self.provider_config.base_url)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            for page in context.pages:
                if page not in existing_pages:
                    return page
            await seed_page.wait_for_timeout(200)
        raise RuntimeError("CDP session could not open a new tab; window.open fallback did not create a page.")

    # ── Page resolution ───────────────────────────────────────────────────────

    def _page_url_for(self, kind: str) -> str:
        if kind == "generate":
            return "https://jimeng.jianying.com/ai-tool/generate?workspace=0&type=video"
        return self.provider_config.base_url

    def _shared_browser_key(self, account: JimengAccountConfig) -> str:
        return f"{account.cdp_url or ''}|{account.web_port or ''}"

    def _activation_lock_for(self, account: JimengAccountConfig) -> asyncio.Lock:
        key = self._shared_browser_key(account)
        lock = _CDP_ACTIVATION_LOCKS.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _CDP_ACTIVATION_LOCKS[key] = lock
        return lock

    # ── Sticky page cache ─────────────────────────────────────────────────────

    def _sticky_generate_page_key(self, account: JimengAccountConfig) -> str:
        return f"{self._shared_browser_key(account)}|{account.space_id or account.name}|generate"

    def _remember_sticky_generate_page(self, account: JimengAccountConfig, page: Page) -> None:
        key = self._sticky_generate_page_key(account)
        existing = self._sticky_generate_pages.get(key)
        if existing is not None and existing is not page:
            self._configured_generate_pages.pop(key, None)
        self._sticky_generate_pages[key] = page

    def _forget_sticky_generate_page(self, account: JimengAccountConfig) -> None:
        key = self._sticky_generate_page_key(account)
        self._sticky_generate_pages.pop(key, None)
        self._configured_generate_pages.pop(key, None)

    def _mark_generate_page_configured(self, account: JimengAccountConfig, page: Page) -> None:
        self._configured_generate_pages[self._sticky_generate_page_key(account)] = id(page)

    def _is_generate_page_configured(self, account: JimengAccountConfig, page: Page) -> bool:
        return self._configured_generate_pages.get(self._sticky_generate_page_key(account)) == id(page)

    async def _get_sticky_generate_page(self, account: JimengAccountConfig) -> Optional[Page]:
        page = self._sticky_generate_pages.get(self._sticky_generate_page_key(account))
        if page is None:
            return None
        if page.is_closed():
            self._forget_sticky_generate_page(account)
            return None
        try:
            await page.title()
        except Exception:
            self._forget_sticky_generate_page(account)
            return None
        return page

    # ── CDP control API (for space activation) ─────────────────────────────────

    def _control_base_url(self, account: JimengAccountConfig) -> Optional[str]:
        if account.web_port is None:
            return None
        return f"http://127.0.0.1:{account.web_port}"

    def _control_request_json_sync(
        self,
        account: JimengAccountConfig,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Any:
        base_url = self._control_base_url(account)
        if not base_url:
            raise RuntimeError(f"Account '{account.name}' does not define web_port.")
        url = base_url.rstrip("/") + path
        data = None
        headers: Dict[str, str] = {}
        method = "GET"
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
            method = "POST"
        req = urllib_request.Request(url, data=data, headers=headers, method=method)
        with urllib_request.urlopen(req, timeout=5) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}

    async def _control_request_json(
        self,
        account: JimengAccountConfig,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Any:
        return await asyncio.to_thread(self._control_request_json_sync, account, path, payload)

    def _fetch_cdp_targets_sync(self, account: JimengAccountConfig) -> list[dict[str, Any]]:
        cdp_url = self._effective_cdp_url(account).rstrip("/")
        if not cdp_url:
            return []
        url = f"{cdp_url}/json/list"
        req = urllib_request.Request(url, headers={"User-Agent": "jimeng-factory"})
        with urllib_request.urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            value = payload.get("value")
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    async def _fetch_cdp_targets(self, account: JimengAccountConfig) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._fetch_cdp_targets_sync, account)

    async def _activate_space(self, account: JimengAccountConfig) -> Any:
        if not account.space_id or not account.web_port:
            return None
        return await self._control_request_json(account, "/api/sandbox/open-space", {"spaceId": account.space_id})

    async def _lookup_space_identity(self, account: JimengAccountConfig) -> Dict[str, Optional[str]]:
        identity: Dict[str, Optional[str]] = {
            "space_id": account.space_id,
            "account_id": None,
            "nickname": None,
        }
        if not account.space_id or not account.web_port:
            return identity
        payload = await self._control_request_json(account, "/api/sandbox/spaces")
        spaces = payload if isinstance(payload, list) else []
        for item in spaces:
            if not isinstance(item, dict) or item.get("id") != account.space_id:
                continue
            identity["account_id"] = self._normalize_identity(item.get("accountId"))
            identity["nickname"] = self._normalize_identity(item.get("nickname"))
            break
        return identity

    # ── Page identity helpers ──────────────────────────────────────────────────

    @staticmethod
    def _normalize_identity(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text.casefold() if text else None

    def _iter_browser_pages(self, browser: Browser) -> list[Page]:
        pages: list[Page] = []
        for context in browser.contexts:
            pages.extend(page for page in context.pages if not page.is_closed())
        return pages

    async def _page_target_info(self, page: Page) -> Optional[Dict[str, Any]]:
        try:
            cdp_session = await page.context.new_cdp_session(page)
        except Exception:
            return None
        try:
            result = await cdp_session.send("Target.getTargetInfo")
            info = result.get("targetInfo")
            return info if isinstance(info, dict) else None
        except Exception:
            return None
        finally:
            with contextlib.suppress(Exception):
                await cdp_session.detach()

    async def _toolbar_page_probe(self, page: Page) -> Optional[Dict[str, Any]]:
        if page.is_closed() or TOOLBAR_PAGE_FRAGMENT not in page.url:
            return None
        target_info = await self._page_target_info(page)
        target_id = target_info.get("targetId") if isinstance(target_info, dict) else None
        try:
            payload = await page.evaluate(
                """async () => {
                    const bar = document.getElementById('url-bar');
                    const space = await window.browserAPI.getSpaceInfo().catch(() => null);
                    return {
                        space,
                        urlBar: bar ? bar.value : null,
                        title: document.title,
                    };
                }"""
            )
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        space = payload.get("space")
        if not isinstance(space, dict):
            return None
        space_id = str(space.get("id") or "").strip()
        if not space_id:
            return None
        return {
            "space_id": space_id,
            "url_bar": str(payload.get("urlBar") or "").strip() or None,
            "target_id": str(target_id or "").strip() or None,
            "page": page,
        }

    def _resolve_toolbar_content_target_id(
        self,
        toolbar_probe: Dict[str, Any],
        cdp_targets: list[dict[str, Any]],
    ) -> Optional[str]:
        toolbar_target_ids = [
            str(item.get("id") or "")
            for item in cdp_targets
            if item.get("type") == "page" and TOOLBAR_PAGE_FRAGMENT in str(item.get("url") or "")
        ]
        jimeng_target_ids = [
            str(item.get("id") or "")
            for item in cdp_targets
            if item.get("type") == "page" and JIMENG_HOST_FRAGMENT in str(item.get("url") or "")
        ]

        fallback_target_id: Optional[str] = None
        toolbar_target_id = str(toolbar_probe.get("target_id") or "")
        if toolbar_target_id and toolbar_target_id in toolbar_target_ids:
            toolbar_index = toolbar_target_ids.index(toolbar_target_id)
            if toolbar_index < len(jimeng_target_ids):
                fallback_target_id = jimeng_target_ids[toolbar_index]

        url_bar = str(toolbar_probe.get("url_bar") or "").strip()
        if not url_bar:
            return fallback_target_id

        resolved_matches: list[str] = []
        for item in cdp_targets:
            if str(item.get("url") or "") != url_bar:
                continue
            target_id = str(item.get("id") or "").strip()
            if not target_id:
                continue
            if item.get("type") == "iframe":
                target_id = str(item.get("parentId") or "").strip()
            if target_id and target_id not in resolved_matches:
                resolved_matches.append(target_id)

        if len(resolved_matches) == 1:
            return resolved_matches[0]
        if fallback_target_id and fallback_target_id in resolved_matches:
            return fallback_target_id
        return fallback_target_id

    def _candidate_pages(self, browser: Browser, preferred_page: Optional[Page] = None) -> list[Page]:
        candidates: list[Page] = []
        seen: set[int] = set()
        if preferred_page is not None and not preferred_page.is_closed():
            candidates.append(preferred_page)
            seen.add(id(preferred_page))
        for page in self._iter_browser_pages(browser):
            if id(page) in seen:
                continue
            if JIMENG_HOST_FRAGMENT in page.url:
                candidates.append(page)
                seen.add(id(page))
        for page in self._iter_browser_pages(browser):
            if id(page) in seen:
                continue
            if page.url not in ("about:blank", ""):
                candidates.append(page)
                seen.add(id(page))
        return candidates

    def _pick_existing_jimeng_page(self, browser: Browser) -> Optional[Page]:
        for page in self._candidate_pages(browser):
            if not page.is_closed() and JIMENG_HOST_FRAGMENT in page.url:
                return page
        return None

    async def _page_identity(self, page: Page) -> Optional[Dict[str, Optional[str]]]:
        if page.is_closed() or JIMENG_HOST_FRAGMENT not in page.url:
            return None
        try:
            payload = await page.evaluate(
                """async () => {
                    try {
                        const response = await fetch('https://jimeng.jianying.com/mweb/v1/get_user_info', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            credentials: 'include',
                            body: '{}',
                        });
                        const data = await response.json().catch(() => null);
                        const info = data?.data;
                        if (!info?.uid) return null;
                        return { accountId: String(info.uid), nickname: info.name || null };
                    } catch {
                        return null;
                    }
                }"""
            )
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        account_id = self._normalize_identity(payload.get("accountId"))
        nickname = self._normalize_identity(payload.get("nickname"))
        if not account_id and not nickname:
            return None
        return {"account_id": account_id, "nickname": nickname}

    async def _resolve_account_page(
        self,
        browser: Browser,
        account: JimengAccountConfig,
        preferred_page: Optional[Page],
        timeout_ms: int,
    ) -> Page:
        if account.space_id and account.web_port:
            await self._activate_space(account)
            deadline = time.monotonic() + min(timeout_ms / 1000, 15)
            while time.monotonic() < deadline:
                await asyncio.sleep(0.5)
                cdp_targets = await self._fetch_cdp_targets(account)
                pages = self._iter_browser_pages(browser)
                target_to_page: dict[str, Page] = {}
                toolbar_probes: list[dict[str, Any]] = []
                for page in pages:
                    target_info = await self._page_target_info(page)
                    target_id = str((target_info or {}).get("targetId") or "").strip()
                    if target_id:
                        target_to_page[target_id] = page
                    probe = await self._toolbar_page_probe(page)
                    if probe is not None:
                        if not probe.get("target_id") and target_id:
                            probe["target_id"] = target_id
                        toolbar_probes.append(probe)

                for probe in toolbar_probes:
                    if probe.get("space_id") != account.space_id:
                        continue
                    content_target_id = self._resolve_toolbar_content_target_id(probe, cdp_targets)
                    if content_target_id and content_target_id in target_to_page:
                        return target_to_page[content_target_id]

        target_identity = await self._lookup_space_identity(account)
        if account.space_id and account.web_port:
            await self._activate_space(account)
            identity_deadline = time.monotonic() + 5
            while time.monotonic() < identity_deadline:
                if target_identity.get("account_id") or target_identity.get("nickname"):
                    break
                target_identity = await self._lookup_space_identity(account)
                await asyncio.sleep(0.25)

        deadline = time.monotonic() + max(timeout_ms / 1000, 5)
        while time.monotonic() < deadline:
            candidates = self._candidate_pages(browser, preferred_page=preferred_page)
            if target_identity.get("account_id") or target_identity.get("nickname"):
                for page in candidates:
                    identity = await self._page_identity(page)
                    if identity is None:
                        continue
                    account_match = bool(target_identity.get("account_id")) and identity.get("account_id") == target_identity.get("account_id")
                    nickname_match = bool(target_identity.get("nickname")) and identity.get("nickname") == target_identity.get("nickname")
                    if account_match or nickname_match:
                        return page
            else:
                for page in candidates:
                    if JIMENG_HOST_FRAGMENT in page.url:
                        return page
            await asyncio.sleep(0.5)

        if target_identity.get("account_id") or target_identity.get("nickname"):
            raise RuntimeError(
                f"Could not resolve an open Jimeng page for account '{account.name}' "
                f"(space_id={account.space_id})."
            )
        raise RuntimeError(
            f"Could not find any Jimeng page for account '{account.name}'. "
            "Open the target space manually before running the script."
        )

    async def _ensure_account_page(
        self,
        session: SessionHandle,
        account: JimengAccountConfig,
        timeout_ms: int,
    ) -> Page:
        page = session.page
        if session.browser is None:
            raise RuntimeError("CDP session has no browser handle.")

        original_page = page
        async with self._activation_lock_for(account):
            page = await self._resolve_account_page(
                session.browser,
                account,
                preferred_page=original_page,
                timeout_ms=timeout_ms,
            )

        if session.created_page and page is not original_page:
            with contextlib.suppress(Exception):
                await original_page.close()
            session.created_page = False

        session.page = page
        session.context = page.context
        return page

    async def _ensure_work_page(
        self,
        session: SessionHandle,
        account: JimengAccountConfig,
        kind: str,
        timeout_ms: int,
    ) -> Page:
        if kind == "generate":
            sticky_page = await self._get_sticky_generate_page(account)
            if sticky_page is not None:
                session.page = sticky_page
                session.context = sticky_page.context
                sticky_page.set_default_timeout(min(timeout_ms, 60_000))
                if await self._has_ready_generate_surface(sticky_page):
                    return sticky_page
                with contextlib.suppress(Exception):
                    await sticky_page.goto(self._page_url_for("generate"), wait_until="domcontentloaded")
                    await self._wait_for_submission_surface(sticky_page)
                    if await self._has_ready_generate_surface(sticky_page):
                        self._remember_sticky_generate_page(account, sticky_page)
                        return sticky_page
                self._forget_sticky_generate_page(account)

        page = await self._ensure_account_page(session, account, timeout_ms)
        page.set_default_timeout(min(timeout_ms, 60_000))

        if kind == "generate":
            if await self._has_ready_generate_surface(page):
                self._remember_sticky_generate_page(account, page)
                return page
            await page.goto(self._page_url_for("generate"), wait_until="domcontentloaded")
            await self._wait_for_submission_surface(page)
            if await self._has_ready_generate_surface(page):
                self._remember_sticky_generate_page(account, page)
            return page

        raise ValueError(f"Unsupported Jimeng page kind: {kind}")

    # ── Page readiness checks ──────────────────────────────────────────────────

    async def _has_submission_surface(self, page: Page) -> bool:
        for selector in SUBMISSION_SURFACE_SELECTORS:
            with contextlib.suppress(Exception):
                if await page.locator(selector).count() > 0:
                    return True
        return False

    async def _wait_for_submission_surface(self, page: Page) -> None:
        deadline = time.monotonic() + 20
        nudged = False
        while time.monotonic() < deadline:
            if await self._has_submission_surface(page):
                await page.wait_for_timeout(200)
                return
            if not nudged:
                await self._bring_composer_into_view(page)
                nudged = True
            await page.wait_for_timeout(500)
        raise RuntimeError("Current page is not ready for submission.")

    async def _toolbar_combobox_count(self, page: Page) -> int:
        selectors = [
            "div[class*='toolbar-'] div[role='combobox']",
            "div.toolbar-CO0C5P div[role='combobox']",
            "div[role='combobox']",
        ]
        for selector in selectors:
            with contextlib.suppress(Exception):
                count = await page.locator(selector).count()
                if count > 0:
                    return count
        return 0

    async def _has_ready_generate_surface(self, page: Page) -> bool:
        if not await self._has_submission_surface(page):
            return False
        if await self._toolbar_combobox_count(page) >= 1:
            return True
        for selector in PROMPT_SELECTORS:
            with contextlib.suppress(Exception):
                if await page.locator(selector).count() > 0:
                    return True
        return False

    async def _detect_login_problem(self, page: Page) -> Optional[str]:
        for selector in LOGIN_BLOCK_SELECTORS:
            with contextlib.suppress(Exception):
                if await page.locator(selector).count() > 0:
                    return "Current browser session is not logged in to Jimeng."
        return None

    # ── Submission preparation ─────────────────────────────────────────────────

    async def _prepare_submission_page(
        self,
        page: Page,
        account: JimengAccountConfig,
    ) -> Dict[str, Any]:
        await self._wait_for_submission_surface(page)

        login_error = await self._detect_login_problem(page)
        if login_error:
            raise RuntimeError(login_error)

        toolbar_defaults_applied = False
        if not self._is_generate_page_configured(account, page):
            await self._apply_toolbar_defaults(page)
            self._mark_generate_page_configured(account, page)
            toolbar_defaults_applied = True

        reference_images_cleared = await self._clear_reference_images(page)
        return {
            "toolbar_defaults_applied": toolbar_defaults_applied,
            "reference_images_cleared": reference_images_cleared,
        }

    # ── Toolbar configuration ─────────────────────────────────────────────────

    def _toolbar_desired_values(self) -> tuple[str, str, str, str, str]:
        d = self.config.video.jimeng_defaults
        mode = d.mode
        model = d.model
        reference = d.reference_type
        aspect = d.aspect_ratio
        duration = f"{self.config.video.default_duration_seconds}s"
        return mode, model, reference, aspect, duration

    async def _apply_toolbar_defaults(self, page: Page) -> None:
        mode, model, reference, aspect, duration = self._toolbar_desired_values()
        await self._wait_for_toolbar_ready(page)
        count = await self._toolbar_combobox_count(page)
        if count >= 4:
            with contextlib.suppress(Exception):
                await self._select_toolbar_combobox_value(page, 0, mode)
            with contextlib.suppress(Exception):
                await self._select_toolbar_combobox_value(page, 1, model)
            with contextlib.suppress(Exception):
                await self._select_toolbar_combobox_value(page, 2, reference)
            with contextlib.suppress(Exception):
                await self._set_aspect_ratio(page, aspect)
            with contextlib.suppress(Exception):
                await self._select_toolbar_combobox_value(page, 3, duration)
        else:
            logger.info(
                "Toolbar has %d comboboxes (< 4); switching to text-based enforcement.", count
            )
        await self._enforce_standard_generate_defaults(page)
        await page.wait_for_timeout(500)

    async def _enforce_standard_generate_defaults(self, page: Page) -> None:
        mode, model, reference, aspect, duration = self._toolbar_desired_values()
        await self._ensure_control_value(page, mode, [mode, "Agent \u6a21\u5f0f", "\u521b\u4f5c\u6a21\u5f0f"])
        await self._ensure_control_value(page, model, [model, "Seedance \u89c6\u9891\u521b\u4f5c", "Seedance"])
        await self._ensure_control_value(page, reference, [reference, "\u81ea\u52a8", "\u7075\u611f\u641c\u7d22", "\u521b\u610f\u8bbe\u8ba1", "\u53c2\u8003"])
        await self._ensure_control_value(page, aspect, [aspect, "\u6bd4\u4f8b"])
        await self._ensure_control_value(page, duration, [duration, "\u65f6\u957f"])

    async def _wait_for_toolbar_ready(self, page: Page) -> None:
        deadline = time.monotonic() + 20
        nudged = False
        escaped = False
        while time.monotonic() < deadline:
            for selector in TOOLBAR_READY_SELECTORS:
                with contextlib.suppress(Exception):
                    locator = page.locator(selector)
                    if await locator.count() == 0:
                        continue
                    await locator.first.wait_for(state="visible", timeout=1000)
            if await self._toolbar_combobox_count(page) >= 1:
                return
            for selector in PROMPT_SELECTORS:
                with contextlib.suppress(Exception):
                    if await page.locator(selector).count() > 0:
                        return
            if not escaped:
                with contextlib.suppress(Exception):
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(100)
                escaped = True
            if not nudged:
                await self._bring_composer_into_view(page)
                nudged = True
            await page.wait_for_timeout(600)
        raise RuntimeError("Toolbar controls were not ready before timeout.")

    async def _bring_composer_into_view(self, page: Page) -> None:
        with contextlib.suppress(Exception):
            go_bottom = page.get_by_text("\u56de\u5230\u5e95\u90e8", exact=False)
            if await go_bottom.count() > 0:
                await go_bottom.last.click()
                await page.wait_for_timeout(400)
                return
        with contextlib.suppress(Exception):
            await page.keyboard.press("End")
            await page.wait_for_timeout(200)
        with contextlib.suppress(Exception):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(200)
        with contextlib.suppress(Exception):
            toolbar = page.locator("div[class*='toolbar-']").last
            if await toolbar.count() > 0:
                await toolbar.scroll_into_view_if_needed()
                await page.wait_for_timeout(200)

    async def _select_toolbar_combobox_value(self, page: Page, toolbar_index: int, expected_value: str) -> None:
        last_error = f"Could not select toolbar option: {expected_value}"
        for _attempt in range(3):
            toolbar_comboboxes = page.locator("div[class*='toolbar-'] div[role='combobox']")
            count = await toolbar_comboboxes.count()
            if count <= toolbar_index:
                raise RuntimeError(f"Toolbar combobox index {toolbar_index} not found for {expected_value}")

            combo = toolbar_comboboxes.nth(toolbar_index)
            current_value = await self._read_combobox_value(combo)
            if expected_value in current_value:
                return

            with contextlib.suppress(Exception):
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(150)

            await combo.scroll_into_view_if_needed()
            await combo.click()
            await page.wait_for_timeout(600)

            clicked = await self._click_toolbar_option(page, expected_value)
            if not clicked:
                last_error = f"Could not select toolbar option: {expected_value}"
                with contextlib.suppress(Exception):
                    await page.keyboard.press("Escape")
                await page.wait_for_timeout(250)
                continue

            await page.wait_for_timeout(350)
            current_value = await self._read_combobox_value(combo)
            if expected_value in current_value:
                return

            last_error = f"Toolbar option click did not stick: expected {expected_value}, got {current_value or '<empty>'}"
            with contextlib.suppress(Exception):
                await page.keyboard.press("Escape")
            await page.wait_for_timeout(250)

        raise RuntimeError(last_error)

    async def _click_toolbar_option(self, page: Page, expected_value: str) -> bool:
        click_kwargs: Dict[str, Any] = {"force": True, "timeout": 10000}

        option = page.get_by_role("option", name=expected_value)
        if await option.count() > 0:
            with contextlib.suppress(Exception):
                await option.first.click(**click_kwargs)
                return True

        exact_text = page.get_by_text(expected_value, exact=True)
        if await exact_text.count() > 0:
            with contextlib.suppress(Exception):
                await exact_text.last.click(**click_kwargs)
                return True

        popup_exact = page.locator(f"[role='listbox'] >> text=\"{expected_value}\"")
        if await popup_exact.count() > 0:
            with contextlib.suppress(Exception):
                await popup_exact.last.click(**click_kwargs)
                return True

        loose_text = page.locator(f"text={expected_value}")
        if await loose_text.count() > 0:
            with contextlib.suppress(Exception):
                await loose_text.last.click(**click_kwargs)
                return True

        return False

    async def _read_combobox_value(self, combo: Locator) -> str:
        with contextlib.suppress(Exception):
            value_locator = combo.locator("span.lv-select-view-value")
            if await value_locator.count() > 0:
                return re.sub(r"\s+", " ", (await value_locator.first.inner_text()).strip())
        with contextlib.suppress(Exception):
            return re.sub(r"\s+", " ", (await combo.inner_text()).strip())
        return ""

    async def _set_aspect_ratio(self, page: Page, expected_value: str) -> None:
        aspect_buttons = page.locator("div[class*='toolbar-'] button[class*='toolbar-button-']")
        count = await aspect_buttons.count()
        for index in range(count):
            button = aspect_buttons.nth(index)
            text = re.sub(r"\s+", " ", (await button.inner_text()).strip())
            if re.fullmatch(r"\d+:\d+", text):
                if text == expected_value:
                    return
                await button.click()
                await page.wait_for_timeout(300)
                option = page.get_by_text(expected_value, exact=True)
                if await option.count() > 0:
                    await option.last.click()
                    await page.wait_for_timeout(300)
                    return
                fallback = page.locator(f"text={expected_value}")
                if await fallback.count() > 0:
                    await fallback.last.click()
                    await page.wait_for_timeout(300)
                    return
                await page.keyboard.press("Escape")
        raise RuntimeError(f"Could not set aspect ratio: {expected_value}")

    async def _has_visible_exact_text(self, page: Page, expected_value: str) -> bool:
        candidates = [
            page.get_by_role("button", name=expected_value),
            page.get_by_role("option", name=expected_value),
            page.locator(f"[role='listbox'] >> text=\"{expected_value}\""),
            page.get_by_text(expected_value, exact=True),
        ]
        for locator in candidates:
            with contextlib.suppress(Exception):
                count = await locator.count()
                for index in range(min(count, 8)):
                    if await locator.nth(index).is_visible():
                        return True
        return False

    async def _click_visible_exact_text(self, page: Page, expected_value: str) -> bool:
        candidates = [
            page.get_by_role("button", name=expected_value),
            page.get_by_role("option", name=expected_value),
            page.locator(f"[role='listbox'] >> text=\"{expected_value}\""),
            page.get_by_text(expected_value, exact=True),
        ]
        for locator in candidates:
            with contextlib.suppress(Exception):
                count = await locator.count()
                for index in range(min(count, 8)):
                    item = locator.nth(index)
                    if not await item.is_visible():
                        continue
                    await item.scroll_into_view_if_needed()
                    await item.click(force=True, timeout=5000)
                    await page.wait_for_timeout(250)
                    return True
        return False

    async def _open_control_by_candidates(self, page: Page, trigger_candidates: list[str]) -> bool:
        controls = page.locator("button, [role='button'], [role='combobox']")
        with contextlib.suppress(Exception):
            total = await controls.count()
        if "total" not in locals():
            return False
        for index in range(min(total, 40)):
            item = controls.nth(index)
            try:
                if not await item.is_visible():
                    continue
                text = re.sub(r"\s+", " ", (await item.inner_text()).strip())
            except Exception:
                continue
            if not text:
                continue
            if not any(candidate in text for candidate in trigger_candidates):
                continue
            try:
                await item.scroll_into_view_if_needed()
            except Exception:
                pass
            try:
                await item.click(force=True, timeout=5000)
                await page.wait_for_timeout(300)
                return True
            except Exception:
                continue
        return False

    async def _ensure_control_value(
        self,
        page: Page,
        expected_value: str,
        trigger_candidates: list[str],
    ) -> None:
        if await self._has_visible_exact_text(page, expected_value):
            return
        with contextlib.suppress(Exception):
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(100)
        opened = await self._open_control_by_candidates(page, trigger_candidates)
        if opened:
            with contextlib.suppress(Exception):
                if await self._click_toolbar_option(page, expected_value):
                    await page.wait_for_timeout(250)
            if await self._has_visible_exact_text(page, expected_value):
                return
            with contextlib.suppress(Exception):
                if await self._click_visible_exact_text(page, expected_value):
                    await page.wait_for_timeout(250)
            if await self._has_visible_exact_text(page, expected_value):
                return
        if await self._click_visible_exact_text(page, expected_value):
            if await self._has_visible_exact_text(page, expected_value):
                return
        raise RuntimeError(f"Could not enforce generate setting: {expected_value}")

    # ── Image upload ──────────────────────────────────────────────────────────

    async def _clear_reference_images(self, page: Page) -> int:
        removed = 0
        for selector in UPLOAD_SELECTORS:
            locator = page.locator(selector)
            with contextlib.suppress(Exception):
                count = await locator.count()
                for index in range(min(count, 4)):
                    with contextlib.suppress(Exception):
                        await locator.nth(index).set_input_files([])

        for _ in range(24):
            clicked = False
            for selector in REFERENCE_REMOVE_SELECTORS:
                locator = page.locator(selector)
                count = 0
                with contextlib.suppress(Exception):
                    count = await locator.count()
                if count == 0:
                    continue
                button = locator.first
                try:
                    await button.scroll_into_view_if_needed()
                except Exception:
                    pass
                try:
                    await button.click(force=True, timeout=1500)
                    await page.wait_for_timeout(180)
                    removed += 1
                    clicked = True
                    break
                except Exception:
                    continue
            if not clicked:
                break

        if removed:
            for selector in UPLOAD_SELECTORS:
                locator = page.locator(selector)
                with contextlib.suppress(Exception):
                    count = await locator.count()
                    for index in range(min(count, 4)):
                        with contextlib.suppress(Exception):
                            await locator.nth(index).set_input_files([])
            await page.wait_for_timeout(300)
        return removed

    async def _pick_upload_input(self, page: Page, require_multiple: bool) -> Optional[Locator]:
        fallback: Optional[Locator] = None
        for selector in UPLOAD_SELECTORS:
            locator = page.locator(selector)
            count = await locator.count()
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    is_multiple = await candidate.evaluate("(node) => Boolean(node.multiple)")
                except Exception:
                    is_multiple = False
                if fallback is None:
                    fallback = candidate
                if not require_multiple or is_multiple:
                    return candidate
        return fallback

    async def _upload_images(self, page: Page, image_paths: list[str]) -> None:
        require_multiple = len(image_paths) > 1
        await self._clear_reference_images(page)
        locator = await self._pick_upload_input(page, require_multiple=require_multiple)
        if locator is None:
            raise RuntimeError("Could not find upload input on Jimeng page.")
        is_multiple = False
        with contextlib.suppress(Exception):
            is_multiple = await locator.evaluate("(node) => Boolean(node.multiple)")
        if require_multiple and not is_multiple:
            await self._apply_toolbar_defaults(page)
            await self._clear_reference_images(page)
            locator = await self._pick_upload_input(page, require_multiple=True)
            if locator is None:
                raise RuntimeError("Could not find multi-image upload input on Jimeng page.")
            with contextlib.suppress(Exception):
                is_multiple = await locator.evaluate("(node) => Boolean(node.multiple)")
            if not is_multiple:
                raise RuntimeError("Generate page upload input is single-file only after toolbar reset.")
        await locator.set_input_files(image_paths if is_multiple else image_paths[:1])
        await page.wait_for_timeout(1500)

    # ── Prompt fill ───────────────────────────────────────────────────────────

    async def _fill_prompt(self, page: Page, prompt: str) -> str:
        locator = await self._first_locator(page, PROMPT_SELECTORS)
        if locator is None:
            raise RuntimeError("Could not find prompt input on Jimeng page.")
        tag_name = await locator.evaluate("(node) => node.tagName.toLowerCase()")
        strategy = "textarea_fill"
        if tag_name == "textarea":
            await locator.fill(prompt)
        else:
            strategy = "contenteditable_fill"
            with contextlib.suppress(Exception):
                await locator.evaluate(
                    """(node) => {
                        node.focus();
                        if (node.isContentEditable) {
                            const selection = window.getSelection();
                            if (selection) {
                                selection.removeAllRanges();
                                const range = document.createRange();
                                range.selectNodeContents(node);
                                selection.addRange(range);
                            }
                        }
                    }"""
                )
            try:
                await locator.fill(prompt)
            except Exception:
                strategy = "contenteditable_dom_set"
                await locator.evaluate(
                    """(node, value) => {
                        node.focus();
                        if (node.isContentEditable) {
                            node.innerHTML = '';
                            node.textContent = value;
                            node.dispatchEvent(new InputEvent('input', { bubbles: true, data: value, inputType: 'insertText' }));
                            node.dispatchEvent(new Event('change', { bubbles: true }));
                            return;
                        }
                        node.value = value;
                        node.dispatchEvent(new Event('input', { bubbles: true }));
                        node.dispatchEvent(new Event('change', { bubbles: true }));
                    }""",
                    prompt,
                )
        await page.wait_for_timeout(800)
        return strategy

    # ── Generation slot + submit ───────────────────────────────────────────────

    async def _read_generation_progress(self, page: Page) -> Optional[tuple[int, int]]:
        for selector in PROGRESS_SELECTORS:
            locator = page.locator(selector)
            with contextlib.suppress(Exception):
                if await locator.count() == 0:
                    continue
                progress = locator.first
                nums = progress.locator("span.num-BZaUkE")
                if await nums.count() >= 2:
                    current_text = (await nums.nth(0).inner_text()).strip()
                    limit_text = (await nums.nth(1).inner_text()).strip()
                    if current_text.isdigit() and limit_text.isdigit():
                        return int(current_text), int(limit_text)
                text = re.sub(r"\s+", "", (await progress.inner_text()).strip())
                match = re.search(r"(\d+)/(\d+)", text)
                if match:
                    return int(match.group(1)), int(match.group(2))
        return None

    async def _wait_for_available_generation_slot(
        self,
        page: Page,
        target_limit: int,
        timeout_ms: int,
    ) -> Dict[str, Optional[int]]:
        deadline = time.monotonic() + (timeout_ms / 1000)
        last_snapshot: Dict[str, Optional[int]] = {
            "running_count": None,
            "page_limit": None,
            "effective_limit": target_limit,
        }
        while time.monotonic() < deadline:
            snapshot = await self._read_generation_progress(page)
            if snapshot is None:
                return {"running_count": None, "page_limit": None, "effective_limit": target_limit}
            running_count, page_limit = snapshot
            effective_limit = min(target_limit, page_limit)
            last_snapshot = {
                "running_count": running_count,
                "page_limit": page_limit,
                "effective_limit": effective_limit,
            }
            if running_count < effective_limit:
                return last_snapshot
            await page.wait_for_timeout(2000)
        raise RuntimeError(
            "No available generation slot before timeout. "
            f"Last snapshot: {last_snapshot['running_count']}/{last_snapshot['page_limit']}"
        )

    async def _click_generate(self, page: Page) -> None:
        for label in GENERATE_TEXT_CANDIDATES:
            with contextlib.suppress(Exception):
                button = page.get_by_role("button", name=label)
                if await button.count() > 0:
                    await button.first.scroll_into_view_if_needed()
                    await button.first.click(force=True)
                    return
        for selector in GENERATE_BUTTON_SELECTORS:
            with contextlib.suppress(Exception):
                button = page.locator(selector).last
                if await button.count() > 0:
                    await button.scroll_into_view_if_needed()
                    await button.click(force=True)
                    return
        raise RuntimeError("Could not find generate button on Jimeng page.")

    # ── Misc helpers ──────────────────────────────────────────────────────────

    async def _first_locator(self, page: Page, selectors: Iterable[str]) -> Optional[Locator]:
        for selector in selectors:
            locator = page.locator(selector)
            with contextlib.suppress(Exception):
                if await locator.count() > 0:
                    return locator.first
        return None
