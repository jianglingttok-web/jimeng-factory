# 即梦内容工厂 — Architecture v1

## 1. 一句话定义

通过多空间浏览器并行多个即梦账号，批量生成电商带货视频，按产品维度自动下载落盘。

## 2. 核心模型

```
产品 (Product)
├── name: string
├── images: file[]              # 1-3 张参考图
└── prompt_variants: variant[]  # N 个脚本变体
    ├── id: string (8位短码)
    ├── title: string
    └── prompt: string

任务 (Task)
├── task_id: string (UUID)
├── product_name: string
├── variant_id: string          # 使用了哪个变体
├── prompt: string              # 实际发送的 prompt
├── account_name: string        # 指派的账号
├── status: enum                # 见状态机
├── result_video_path: string?
├── error_message: string?
├── created_at: timestamp
└── updated_at: timestamp

账号 (Account)
├── name: string
├── space_id: string            # 多空间浏览器 space
├── cdp_url: string
├── web_port: int
├── status: enum (active | disabled | error)
├── generating_count: int       # 当前远端生成中的数量
└── max_concurrent: int = 10    # 即梦系统限制
```

## 3. 任务状态机

```
pending → submitting → generating → downloading → succeeded
                │           │            │
                └→ failed   └→ failed    └→ failed
                    │           │            │
                    └→ pending  └→ pending   └→ generating
                    (自动重试)   (自动重试)    (重试下载)
```

状态说明：
- `pending`: 等待调度
- `submitting`: 浏览器正在提交（占浏览器资源，不占即梦并发）
- `generating`: 远端生成中（占即梦并发，不占浏览器资源）
- `downloading`: 正在下载完成的视频
- `succeeded`: 视频已落盘
- `failed`: 失败（含重试次数，可自动回退到 pending）

## 4. 调度逻辑

### 4.1 并发控制

每个账号维护 `generating_count`（远端正在生成的任务数）。

```
可提交数 = max_concurrent(10) - generating_count
```

当 `可提交数 > 0` 且有 pending 任务时，调度器提交任务。
一个任务提交成功 → `generating_count += 1`。
一个任务生成完成（成功或失败）→ `generating_count -= 1`。

### 4.2 提交与完成检测分离

- **提交器 (Submitter)**: 轮询 pending 任务，提交到即梦，标记为 generating
- **收割器 (Harvester)**: 轮询有 generating 任务的账号，检查远端完成状态，触发下载

两者独立运行，互不阻塞。

### 4.3 任务分配

运营在 Web 端手动指派：选择产品 + 选择账号 + 指定数量。
系统从 prompt_variants 中轮询分配变体，生成 N 个 pending 任务。

## 5. 下载策略（简单模式）

- 账号独占优先：运营尽量让每个账号只跑一个产品
- 下载按时间窗口过滤：只下载本批次提交后生成的视频
- 落盘目录：`outputs/{product_name}/`
- 下载清单：`outputs/{product_name}/.download_manifest.json`
- 接受少量误下风险，不做 trace_token 硬隔离

## 6. 即梦页面固定参数

提交任务时，Provider 必须在即梦页面上选择以下固定参数：

| 参数 | 固定值 |
|------|--------|
| 模式 | 视频生成 |
| 模型 | Seedance 2.0 Fast |
| 参考类型 | 全能参考 |
| 画幅 | 9:16 |
| 时长 | 可选（默认 10s，运营可在提交时调整） |

## 7. 本地路径配置原则

所有涉及本地环境的路径都通过 `config.yaml` 配置，不硬编码：

- 多空间浏览器可执行文件路径
- SpaceData 目录路径
- CDP URL / Web 控制端口
- 产品数据目录
- 输出目录
- 数据库路径

每台运营电脑首次使用时只需复制 `config.example.yaml` → `config.yaml` 并修改路径。

## 8. 技术栈

| 层 | 选型 | 说明 |
|----|------|------|
| 后端框架 | FastAPI | 轻量，async 原生支持 |
| 数据库 | SQLite | 本地运行，无需外部依赖 |
| 浏览器自动化 | Playwright | CDP 模式连接多空间浏览器 |
| 前端 | Vue 3 + Vite | 单页应用，替代旧版原生 JS |
| 包管理 | pip + requirements.txt | 保持简单 |

## 9. 目录结构

```
E:\即梦内容工厂\
├── docs/                          # 文档
│   ├── ARCHITECTURE.md
│   └── STATUS.md
├── src/
│   ├── models/                    # 数据模型
│   │   ├── product.py             # Product, PromptVariant
│   │   ├── task.py                # Task, TaskStatus
│   │   └── account.py             # Account, AccountStatus
│   ├── providers/
│   │   └── jimeng.py              # 即梦浏览器自动化（从旧仓迁移）
│   ├── runtime/
│   │   ├── storage.py             # SQLite 存储层
│   │   ├── submitter.py           # 提交调度器
│   │   ├── harvester.py           # 完成检测 + 下载
│   │   └── product_store.py       # 产品文件管理
│   ├── web/
│   │   ├── app.py                 # FastAPI 入口
│   │   └── routes.py              # API 路由
│   └── config.py                  # 配置加载
├── frontend/                      # Vue 3 前端
│   ├── src/
│   │   ├── App.vue
│   │   ├── views/
│   │   │   ├── Products.vue       # 产品管理
│   │   │   ├── Tasks.vue          # 任务列表 + 状态监控
│   │   │   └── Submit.vue         # 任务下单
│   │   └── components/
│   └── package.json
├── data/
│   └── products/                  # 产品数据（图片 + product.json）
├── outputs/                       # 下载的视频按产品目录存放
├── runtime/
│   └── app.db                     # SQLite 数据库
├── config.yaml
├── requirements.txt
└── start.bat                      # 一键启动
```

## 10. 从旧仓迁移清单

### 迁移（重构后复用）
- `providers/jimeng.py` — 核心 2100 行，submit_job / audit / download 逻辑
- `runtime/product_store.py` — 产品模型 + revision hash
- `runtime/storage.py` — SQLite schema（精简字段）
- `config.py` — 配置结构（精简）

### 不迁移
- `runtime/catalog.py` — 旧 YAML 加载，已被 product_store 替代
- `runtime/trace_token.py` — 简单模式不需要
- `runtime/cleanup.py`, `preview.py`, `run_ledger.py` — 未使用
- `web/static/` — 前端推倒重来
- 所有 `tmp_*` 临时文件

## 11. API 设计

### 产品
- `GET    /api/products`              — 产品列表
- `POST   /api/products`              — 创建产品
- `GET    /api/products/{name}`       — 产品详情
- `PUT    /api/products/{name}`       — 更新产品
- `DELETE /api/products/{name}`       — 删除产品

### 任务
- `GET    /api/tasks`                 — 任务列表（支持按产品/账号/状态过滤）
- `POST   /api/tasks/submit`         — 批量创建任务（产品 + 账号 + 数量）
- `POST   /api/tasks/{id}/stop`      — 停止单个任务
- `POST   /api/tasks/stop-batch`     — 批量停止

### 账号
- `GET    /api/accounts`              — 账号列表 + 实时状态
- `POST   /api/accounts/{name}/probe` — 健康检查

### 系统
- `GET    /api/status`                — 总览（各状态任务数、账号状态）

## 12. 验收标准（首个里程碑）

> 2 个账号、1 个产品、2 个脚本变体，在 Web 端完成：
> 创建产品 → 指派任务(每账号5个) → 每账号保持10并发提交 → 远端完成 → 自动下载 → 按产品目录落盘
> 链路可观察（Web 端实时看到状态流转）

## 13. 不做的事（本期）

- 用户认证 / 权限
- 多机部署 / 数据同步
- 自动选品 / 智能调度
- 成本统计 / 报表
- 通知集成（飞书/Slack）
- trace_token 产品级隔离
