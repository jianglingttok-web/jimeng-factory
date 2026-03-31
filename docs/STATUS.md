# 即梦内容工厂 — Project Status

## 当前阶段：Phase 0 — 项目初始化

## 决策记录

| # | 决策 | 结论 | 日期 |
|---|------|------|------|
| 1 | 重开方式 | 新建仓库，按需迁移旧代码 | 2026-03-30 |
| 2 | 共享账号策略 | 简单模式，时间窗口过滤，不做 trace_token | 2026-03-30 |
| 3 | 并发模型 | 每账号保持10个 generating 任务 | 2026-03-30 |
| 4 | 技术栈 | 前后端推倒重来（FastAPI + Vue 3） | 2026-03-30 |
| 5 | 项目目录 | E:\即梦内容工厂 | 2026-03-30 |

## 开发阶段

| Phase | 目标 | 状态 |
|-------|------|------|
| 0 | 项目初始化 + 架构文档 | **已完成** |
| 1 | 后端骨架 + 数据模型 + 产品管理 API | **已完成** |
| 2 | 迁移 jimeng provider（submit_job） | **已完成** |
| 3 | 提交调度器（保持10并发） | 待开始 |
| 4 | 收割器 + 下载 | 待开始 |
| 5 | 前端 Vue 3 | 待开始 |
| 6 | 端到端验收 | 待开始 |

## 已完成切片

- Phase 0: 架构文档 + git init + config.example.yaml (2026-03-30)
- Phase 1 Slice 1: 数据模型 + config + storage + product_store (2026-03-30)
- Phase 2 Slice 1: jimeng provider（submit_job，CDP-only，无 trace_token）(2026-03-31)

## 当前阻塞

无

## 下一个切片

**Phase 3 Slice 1**: 提交调度器（保持10并发）
- 目标: 从 product_store 取任务，调用 JimengProvider.submit_job，维持每账号 max_concurrent 并发
