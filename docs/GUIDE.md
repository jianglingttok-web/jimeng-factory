# 即梦内容工厂 — 安装与使用指南

## 系统要求

- Windows 10/11
- Python 3.10+（推荐 3.12+）
- 多空间浏览器（mul-key-chrome）

## 快速安装

### 1. 安装前置软件

- Python: https://python.org/downloads/ （安装时勾选 "Add to PATH"）
- 多空间浏览器: 联系技术获取安装包

### 2. 运行安装脚本

双击 `setup.bat`

脚本会自动：

- 安装 Python 依赖
- 安装 Playwright 浏览器内核
- 创建配置文件

### 3. 修改配置

编辑 `config.yaml`，主要修改：

- `browser_executable_path`: 多空间浏览器的实际安装路径
- `default_concurrency`: 每账号并发任务数（默认 10）

### 4. 启动

双击 `start.bat`

系统会自动启动：

- 多空间浏览器（如未运行）
- 后端服务（端口 8001）
- 自动打开浏览器 `http://localhost:8001`

前端已预编译，无需额外安装 Node.js 开发环境。

## 日常使用

### 同步账号

1. 在多空间浏览器中打开需要使用的 space（每个 space = 一个即梦账号）
2. 在网页中点击“同步账号”按钮
3. 账号列表自动更新

### 创建产品

1. 进入“产品列表”页面
2. 点击“新建产品”
3. 输入产品名称
4. 上传 1-3 张商品图片
5. 添加视频生成 prompt（可多条）
6. 保存

### 提交任务

1. 进入“提交”页面
2. 选择产品和账号
3. 点击“提交”
4. 系统自动分配任务到各账号并行生成

### 监控任务

- “任务列表”页面实时显示所有任务状态
- 点击“详情”查看错误信息、重试次数
- 失败任务自动重试（最多 2 次）
- 全部失败后可手动点击“重试失败”

### 批量操作

- 勾选任务 → “批量停止”：停止选中的任务
- “重试失败”：重置所有失败任务

## 常见问题

### Q: 启动后提示 “config.yaml 不存在”

双击 `setup.bat` 运行安装脚本。

### Q: 任务全部失败，错误 “BrowserType.connect_over_cdp”

多空间浏览器未启动或未带 `--remote-debugging-port=9222` 参数。关闭所有窗口，重新双击 `start.bat`。

### Q: 任务卡在 “generating” 不动

Harvester 每 10 秒检查一次。如果长时间不动：

1. 检查即梦页面上视频是否已生成完成
2. 重启 FastAPI 服务

### Q: 端口被占用

关闭占用端口的旧进程，重新启动。`start.bat` 会自动跳过已运行的服务。

### Q: 前端页面打不开

访问 `http://localhost:8001`，确认后端服务已启动。

## 目录结构

```text
即梦内容工厂/
├── setup.bat           ← 双击安装（只需一次）
├── start.bat           ← 双击启动
├── setup.ps1           ← 安装脚本（实际逻辑）
├── start.ps1           ← 启动脚本（实际逻辑）
├── config.yaml         ← 本地配置（不入库）
├── config.yaml.example ← 配置模板
├── requirements.txt    ← Python 依赖
├── src/                ← 后端代码
├── frontend/           ← 前端代码
├── data/products/      ← 产品数据（图片+prompt）
├── outputs/            ← 生成的视频
└── runtime/            ← SQLite 数据库
```
