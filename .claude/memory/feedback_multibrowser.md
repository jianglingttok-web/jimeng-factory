---
name: 多空间浏览器操作规范
description: 即梦内容工厂项目使用多空间浏览器，任何浏览器操作必须通过CDP连接已有账号，不能直接开新标签页导航
type: feedback
---

不能直接用 Chrome DevTools MCP 或 playwright 开新标签页导航到即梦。

**Why:** 项目使用多空间浏览器（每个账号有独立 space），账号登录态在已有的浏览器 space 里，直接开新标签会没有登录态。

**How to apply:** 所有即梦页面操作必须通过 JimengProvider 的 CDP 连接（`_open_session` → `reuse_existing_page=True`），连接到已经在跑的账号 space，不能绕过这一层直接操作浏览器。
