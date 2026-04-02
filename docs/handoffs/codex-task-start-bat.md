# Codex Task: 创建 start.bat

## 目标
在 E:\即梦内容工厂\ 根目录创建 start.bat，一条命令启动开发模式所需的所有服务。

## 当前运行模式（开发模式）
- 前端：Vite dev server，http://localhost:5173（代理 /api → FastAPI）
- 后端：FastAPI，http://127.0.0.1:8001（只提供 /api/*）
- 多空间浏览器：必须带 --remote-debugging-port=9222 启动，CDP 才可用

## 要创建的文件
E:\即梦内容工厂\start.bat

## start.bat 要做的事（顺序）

1. 检查多空间浏览器是否已在运行（检查 9222 端口）
   - 如果没运行，启动它：
     `start "" "E:\多空间浏览器\mul-key-chrome\多空间浏览器.exe" --remote-debugging-port=9222`
   - 如果已运行，跳过（不重复启动）

2. 切换到 E:\即梦内容工厂 目录

3. 在新窗口启动 FastAPI：
   `start "FastAPI" cmd /k "cd /d E:\即梦内容工厂 && python -m uvicorn src.web.app:app --host 0.0.0.0 --port 8001"`

4. 在新窗口启动 Vite：
   `start "Frontend" cmd /k "cd /d E:\即梦内容工厂\frontend && npm run dev"`

5. 等待 2 秒后，用默认浏览器打开前端入口：
   `timeout /t 2 /nobreak > nul`
   `start http://localhost:5173`

## 验收标准
- start.bat 存在于 E:\即梦内容工厂\start.bat
- 双击后打开 3 个窗口（多空间浏览器、FastAPI、Vite）
- 自动打开 http://localhost:5173

## 约束
- 只创建 start.bat，不修改其他文件
- 不运行 git 命令
- 完成后输出：[IMPORTANT] done:
- 阻塞时输出：[IMPORTANT] blocked: <原因>
