# 即梦内容工厂 — Project Status

## 当前阶段：Phase 7 — 产品化封装与分发

## 决策记录

| # | 决策 | 结论 | 日期 |
|---|------|------|------|
| 1 | 重开方式 | 新建仓库，按需迁移旧代码 | 2026-03-30 |
| 2 | 共享账号策略 | 简单模式，时间窗口过滤，不做 trace_token | 2026-03-30 |
| 3 | 并发模型 | 每账号保持10个 generating 任务 | 2026-03-30 |
| 4 | 技术栈 | 前后端推倒重来（FastAPI + Vue 3） | 2026-03-30 |
| 5 | 项目目录 | E:\即梦内容工厂 | 2026-03-30 |
| 6 | harvest 改走 Python 拦截 | 删除 _LIST_COMPLETED_JS，list_completed 改用 page.on("response") + get_asset_list | 2026-04-03 |
| 7 | 分发形态 | ZIP 压缩包，运营解压即用，不依赖 git | 2026-04-03 |

## 开发阶段

| Phase | 目标 | 状态 |
|-------|------|------|
| 0 | 项目初始化 + 架构文档 | **已完成** |
| 1 | 后端骨架 + 数据模型 + 产品管理 API | **已完成** |
| 2 | 迁移 jimeng provider（submit_job） | **已完成** |
| 3 | 提交调度器（保持10并发） | **已完成** |
| 4 | 收割器 + 下载 | **已完成** |
| 5 | 前端 Vue 3（Tasks/Submit/Products） | **已完成** |
| 6 | 端到端验收 | **已完成** |
| 7 | 产品化封装与分发 | **进行中** |

## 已完成切片

- Phase 0: 架构文档 + git init + config.example.yaml (2026-03-30)
- Phase 1 Slice 1: 数据模型 + config + storage + product_store (2026-03-30)
- Phase 2 Slice 1: jimeng provider（submit_job，CDP-only，无 trace_token）(2026-03-31)
- Phase 3: scheduler.py — 调度器，claim_pending + submit_job 循环 (2026-03-31)
- Phase 4: harvester.py — 收割器，list_completed + download_video 循环 (2026-03-31)
- Phase 5: Vue 3 前端 — Tasks/Submit/Products 三页面 + batch stop + accordion UI (2026-03-31)
- Phase 6: 端到端验收通过 — 完整链路跑通 (2026-04-02)
- Phase 7 Slice 1: 部署脚本 — setup.ps1 + config.yaml.example + start.ps1 检查 + GUIDE.md (2026-04-03)
- Phase 7 Slice 2: BOM 修复 — ps1 文件加 UTF-8 BOM，PowerShell 中文显示正常 (2026-04-03)

## 当前阻塞

无

- Phase 7 Slice 3: build-release.ps1 + production-first 启动 + 排除收紧 (2026-04-03)

## 下一个切片

**Phase 7 Slice 4**: Codex 验证打包结果 → 分发
