# Codex 审核交接单 — 2026-04-02

## 项目背景

即梦内容工厂：通过多空间浏览器并行多个即梦账号，批量生成电商带货视频。

- 后端：FastAPI + SQLite + Playwright（CDP 浏览器自动化）
- 前端：Vue 3 + Vite，代理到 FastAPI
- 仓库路径：`E:\即梦内容工厂`

---

## 当前运行环境状态

### ✅ 多空间浏览器（CDP）
- 进程：`E:\多空间浏览器\mul-key-chrome\多空间浏览器.exe --remote-debugging-port=9222`
- CDP 可用：`http://127.0.0.1:9222` → `ws://127.0.0.1:9222/devtools/browser/...`
- 控制 API：`http://127.0.0.1:3000`
- 关键 API 端点：
  - `GET  /api/sandbox/spaces` → 返回 space 列表（id, name, group）
  - `GET  /api/sandbox/status` → 返回各 sandbox 状态（token, spaceId, alive）
  - `POST /api/sandbox/open-space {"spaceId": "..."}` → 激活 space，在浏览器中打开即梦页面
- `open-space` 激活后 CDP targets 结构：
  ```
  type=page  url=https://jimeng.jianying.com/ai-tool/asset?workspace=0  ← 即梦内容页
  type=page  url=file://.../renderer/browser.html                        ← toolbar（含 space 信息）
  type=page  url=file://.../renderer/index.html                          ← app 主页
  ```

### ❌ FastAPI 服务（未运行）
- 应运行在：`http://127.0.0.1:8001`
- 启动命令：`python -m uvicorn src.web.app:app --host 0.0.0.0 --port 8001 --reload`
- **注意**：必须在 `E:\即梦内容工厂` 目录下执行

### ✅ 前端（Vite dev server）
- 运行在：`http://localhost:5173`
- 代理 `/api/*` → `http://127.0.0.1:8001`

### ✅ config.yaml（刚创建）
路径：`E:\即梦内容工厂\config.yaml`
```yaml
providers:
  jimeng:
    cdp_url: "http://127.0.0.1:9222"
    web_port: 3000
    default_concurrency: 10
    accounts: []      ← 从 spaces API 自动发现
```

---

## 代码现状审核

### `src/providers/jimeng.py`

#### 提交流程（正常路径）
```
submit_job(account, prompt, image_paths)
  └── _open_session(account, reuse_existing_page=True)
        └── connect_over_cdp("http://127.0.0.1:9222")   ← 现在可用 ✅
        └── _pick_existing_jimeng_page(browser)           ← 找已有即梦页
        └── 无则 _open_cdp_page(context)                  ← 开新页
  └── _ensure_work_page(session, account, "generate")
        └── _ensure_account_page(session, account)
              └── _resolve_account_page(browser, account)
                    └── _activate_space(account)          ← 调 open-space API
                    └── 轮询 toolbar pages → 找 space_id 匹配的即梦页
  └── _prepare_submission_page / _upload_images / _fill_prompt
  └── _click_generate → SubmitReceipt(ok=True)
```

#### 已知风险点

**1. `_pick_existing_jimeng_page` 包含 non-Jimeng 页**

```python
def _pick_existing_jimeng_page(self, browser: Browser) -> Optional[Page]:
    candidates = self._candidate_pages(browser)
    return candidates[0] if candidates else None
```

`_candidate_pages` 返回所有非空白页，包括 `browser.html`（toolbar）和 `index.html`（app主页）。
首次连接时第一个候选可能是这些 app 页，不是即梦页。
这会导致 `_ensure_work_page` 尝试在 toolbar 页上 `page.goto("jimeng...")` → 大概率失败或导航到错误 context。

**修复方向**：`_pick_existing_jimeng_page` 应只返回 `jimeng.jianying.com` 页。

**2. `_toolbar_page_probe` 的 `window.browserAPI.getSpaceInfo()` 可能不可用**

该函数在 `renderer/browser.html` 页内执行：
```js
const space = await window.browserAPI.getSpaceInfo().catch(() => null);
```

如果 `window.browserAPI` 未在该页面 preload 中暴露，则 space 返回 null，
导致 `toolbar_probes` 为空，`_resolve_account_page` 进入 fallback 分支。

Fallback 分支依赖 `_lookup_space_identity`（调 spaces API）和 `_page_identity`（在页内执行 fetch）。
如果 spaces API 的 `accountId/nickname` 字段都是 null（实测如此，见 `/api/sandbox/spaces` 响应），
则最终回退到：
```python
for page in candidates:
    if JIMENG_HOST_FRAGMENT in page.url:
        return page
```
这是最宽松的匹配，**会匹配任何即梦页，不区分哪个账号**。

**对单账号测试无影响，多账号并发时会造成账号串台。**

**3. `_resolve_account_page` 第一分支的 `_fetch_cdp_targets` 需要 CDP 支持**

```python
cdp_targets = await self._fetch_cdp_targets(account)  # hits {cdp_url}/json/list
```

实测 `http://127.0.0.1:9222/json/list` 可用 ✅

---

### `src/runtime/scheduler.py`
- 正常：单任务 claim 循环，CancelledError 有 rollback
- 图片路径解析：`data/products/{product_name}/*.{jpg,png,webp}` ✅
- 图片检查：无图片 → 直接 mark_submit_failed（不重试）⚠️ 注意产品创建后图片上传是分步的

### `src/runtime/storage.py`
- 新增：`reset_failed_tasks()` ✅
- `claim_pending_tasks` / `mark_submit_succeeded` / `mark_submit_failed` 均有 CAS ✅

### `src/web/routes.py`
- 新增：`POST /api/tasks/retry-failed` ✅
- `POST /api/accounts/discover` → 调 `/api/sandbox/spaces` 同步账号 ✅

### `frontend/src/views/Tasks.vue`
- 新增：橙色「重试失败」按钮 ✅
- 绿色「同步账号」按钮 ✅

---

## 需要 Codex 执行的修复

### Fix 1：`_pick_existing_jimeng_page` 只返回真实即梦页

**文件**：`E:\即梦内容工厂\src\providers\jimeng.py`

**问题行**（约 662-664）：
```python
def _pick_existing_jimeng_page(self, browser: Browser) -> Optional[Page]:
    candidates = self._candidate_pages(browser)
    return candidates[0] if candidates else None
```

**修复**：过滤只取 `jimeng.jianying.com` 页：
```python
def _pick_existing_jimeng_page(self, browser: Browser) -> Optional[Page]:
    for page in self._candidate_pages(browser):
        if JIMENG_HOST_FRAGMENT in page.url and not page.is_closed():
            return page
    return None
```

---

### Fix 2：`_open_session` 的 seed_page 传错

**文件**：`E:\即梦内容工厂\src\providers\jimeng.py`

**问题行**（约 369-371）：
```python
context = browser.contexts[0]
page = await self._open_cdp_page(context, seed_page=existing_page)
```

`existing_page` 是 `_pick_existing_jimeng_page` 返回的，修 Fix 1 后可能为 None。
但 `_open_cdp_page` 需要 seed_page 来 `window.open()`。
应改为从 context.pages 里找任意可用页作为 seed：

```python
context = browser.contexts[0]
seed = existing_page or (context.pages[0] if context.pages else None)
page = await self._open_cdp_page(context, seed_page=seed)
```

---

### Fix 3（可选，低优先级）：多账号时 fallback 匹配太宽松

暂不修，单账号测试阶段不影响。等多账号验证时再处理。

---

## 验收步骤（Codex 不需要执行，仅供参考）

1. 用户重启 FastAPI
2. 点「同步账号」→ 账号列表出现
3. 点「重试失败」→ 5 个任务重置为 pending
4. 观察 scheduler 日志：应看到 `_activate_space` 调用、页面导航、表单填写
5. 任务状态变为 generating → downloading → succeeded

---

## 文件路径速查

```
E:\即梦内容工厂\
├── config.yaml                          ← 刚创建，含 cdp_url/web_port
├── src\
│   ├── config.py                        ← AppConfig / JimengAccountConfig
│   ├── providers\jimeng.py              ← CDP 自动化核心（约 900 行）
│   ├── runtime\
│   │   ├── scheduler.py                 ← 提交调度
│   │   ├── harvester.py                 ← 结果收割
│   │   └── storage.py                   ← SQLite 原子操作
│   └── web\
│       ├── app.py                       ← FastAPI lifespan
│       └── routes.py                    ← API 路由
└── frontend\src\
    ├── api.js
    └── views\
        ├── Tasks.vue
        ├── Products.vue
        └── Submit.vue
```
