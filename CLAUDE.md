# CLAUDE.md - 即梦内容工厂

## 项目概述

即梦内容工厂是一个**视频批量生成自动化系统**，通过 Playwright + CDP 协议操控"多空间浏览器"，在即梦（jimeng.jianying.com）平台上全自动批量生成商品短视频。面向 TikTok Shop 泰区/印尼区内容生产。

## 技术栈

- **后端**: Python FastAPI + SQLite + Playwright (CDP browser automation)
- **前端**: Vue 3 + Vite (单页应用)
- **进程管理**: PM2
- **多空间浏览器**: Chromium-based, CDP port 9222, web API port 3000

## 架构与数据流

```
用户 → 前端 UI → POST /api/tasks/submit → Storage 写入 pending 任务
                                                    ↓ (每5s)
                                     Scheduler.run_once()
                                       ├─ 读 data/products/{name}/ 下的图片
                                       ├─ JimengProvider.submit_job()
                                       │   └─ Playwright 控制多空间浏览器：上传图片 → 填 prompt → 点击生成
                                       └─ 任务状态 → generating
                                                    ↓ (每10s)
                                     Harvester.run_once()
                                       ├─ 从即梦页面抓取完成的视频 URL
                                       ├─ 下载视频到 outputs/{product}/{task_id}.mp4
                                       └─ 任务状态 → succeeded
```

**任务状态机**: `pending → submitting → generating → downloading → succeeded / failed`

**多账号并发**: Scheduler 对每个 ACTIVE 账号并行提交（asyncio.gather），每账号受 max_concurrent 限制（默认 10）。失败自动重试（最多 max_retries 次，默认 2 次）。

## 核心模块

| 模块 | 职责 |
|------|------|
| `src/web/app.py` | FastAPI 入口；lifespan 中启动 Scheduler + Harvester 后台循环 |
| `src/web/routes.py` | REST API（任务 CRUD、账号发现、产品管理） |
| `src/runtime/scheduler.py` | 每 5s 轮询 pending 任务 → 调用 Provider 提交到即梦 |
| `src/runtime/harvester.py` | 每 10s 轮询 generating 任务 → 抓取结果 → 下载视频 |
| `src/runtime/storage.py` | SQLite 封装，管理 Task / Account 状态 |
| `src/runtime/product_store.py` | 产品目录读写（data/products/{name}/product.json + 图片） |
| `src/providers/jimeng.py` | Playwright 自动化核心：CDP 连接多空间浏览器，操作即梦页面 |
| `src/models/task.py` | Task 数据模型与状态枚举 |
| `src/models/account.py` | 多空间浏览器账号模型 |
| `src/config.py` | YAML 配置加载 |

## 目录结构

```
data/products/     # 产品数据（图片 + product.json）
outputs/           # 生成的视频文件
runtime/           # SQLite 数据库 (app.db)
frontend/dist/     # 前端构建产物（后端 serve）
frontend/src/      # Vue 3 源码
tests/             # pytest 测试
```

## PM2 Services

| Port | Name | Type |
|------|------|------|
| 8001 | jimeng-backend-8001 | FastAPI (uvicorn) |
| 5173 | jimeng-frontend-5173 | Vite (Vue 3) |

```bash
pm2 start ecosystem.config.cjs   # 首次启动
pm2 start all                    # 后续启动
pm2 stop all / pm2 restart all
pm2 logs / pm2 status / pm2 monit
```

## 配置 (config.yaml)

参考 `config.yaml.example`，关键配置：
- `web`: 后端 host/port、CORS
- `paths`: 产品目录、输出目录、数据库路径
- `video`: 时长、重试次数、超时、生成参数（模型 Seedance 2.0 Fast、比例 9:16）
- `providers.jimeng`: 多空间浏览器路径、CDP 端口、每账号并发数

## 部署（运营使用）

1. 解压 zip 到任意目录
2. 运行 `setup.bat` 安装依赖
3. 编辑 `config.yaml` 配置多空间浏览器路径
4. 运行 `start.bat` 启动服务
5. 浏览器打开 `http://localhost:8001`

## 开发注意事项

- 本项目是本地部署工具，**不需要登录/认证模块**
- 浏览器操作必须通过 CDP 连接已有的多空间浏览器账号 space
- 前端构建后需要重启 PM2 才生效
- 打包发布用 `build-release.ps1`（自动排除开发文件）
