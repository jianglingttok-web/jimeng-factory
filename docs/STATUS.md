# 即梦内容工厂 — Project Status

## 当前阶段：Phase 8 — 多机运行适配与稳定性

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
| 8 | 多账号并行调度 | asyncio.gather 按账号并发，账号内串行 | 2026-04-03 |
| 9 | scheduler/harvester 互斥 | per-account asyncio.Lock，防止 harvester reload 摧毁 submit 工具栏状态 | 2026-04-04 |
| 10 | 工具栏设置顺序 | reference → model（全能参考触发 VIP 自动切换，模型最后设覆盖） | 2026-04-04 |
| 11 | duration 单次设置 | 只在 _enforce_final_duration 设一次，不在 toolbar defaults 里重复设 | 2026-04-04 |
| 12 | Dreamina CLI 评估搁置 | CLI 需扫码登录，多空间浏览器账号无密码/手机，暂用浏览器方案 | 2026-04-04 |

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
| 7 | 产品化封装与分发 | **已完成** (v1.0-browser-automation) |
| 8 | 多机运行适配与稳定性 | **进行中** |

## 已完成切片

- Phase 0: 架构文档 + git init + config.example.yaml (2026-03-30)
- Phase 1 Slice 1: 数据模型 + config + storage + product_store (2026-03-30)
- Phase 2 Slice 1: jimeng provider（submit_job，CDP-only，无 trace_token）(2026-03-31)
- Phase 3: scheduler.py — 调度器，claim_pending + submit_job 循环 (2026-03-31)
- Phase 4: harvester.py — 收割器，list_completed + download_video 循环 (2026-03-31)
- Phase 5: Vue 3 前端 — Tasks/Submit/Products 三页面 + batch stop + accordion UI (2026-03-31)
- Phase 6: 端到端验收通过 — 完整链路跑通 (2026-04-02)
- Phase 7 Slice 1: 部署脚本 — setup.ps1 + config template + start checks + GUIDE.md (2026-04-03)
- Phase 7 Slice 2: BOM + 编码修复 (2026-04-03)
- Phase 7 Slice 3: build-release.ps1 + production-first 启动 + 排除收紧 (2026-04-03)
- Phase 7 Slice 4: Codex 验证 + 分发 → v1.0-browser-automation tag (2026-04-03)
- Phase 8 Slice 1: 应用日志配置 (logging.basicConfig) (2026-04-04)
- Phase 8 Slice 2: 多账号并行 + VIP 自动切换对抗 + 精确模型匹配 (2026-04-04)
- Phase 8 Slice 3: scheduler/harvester 页面锁 + duration 单次设置 (2026-04-04)

## 当前阻塞

无

## 已知技术债

- 浏览器自动化依赖 UI 选择器，即梦改版会坏（Dreamina CLI 是战略替代方案，待登录问题解决）
- harvester 仍用 page.reload 获取结果，锁只是串行化，未根除侵入性
- 零自动化测试覆盖

## 下一个切片

**Phase 8 Slice 4**: 运营实测反馈收集 → 修复剩余问题
