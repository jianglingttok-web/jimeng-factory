# setup.ps1 - 即梦内容工厂环境安装（只需运行一次）

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:NO_PROXY = "127.0.0.1,localhost"

Write-Host "=== 即梦内容工厂 — 环境安装 ===" -ForegroundColor Cyan

# 1. 检查 Python
Write-Host "`n[1/5] 检查 Python..." -ForegroundColor Yellow
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "  错误：未找到 Python，请先安装 Python 3.10+" -ForegroundColor Red
    exit 1
}
$pyVer = python --version 2>&1
Write-Host "  $pyVer" -ForegroundColor Green

# 2. 安装 Python 依赖
Write-Host "`n[2/5] 安装 Python 依赖..." -ForegroundColor Yellow
python -m pip install -r "$ROOT\requirements.txt" --quiet
Write-Host "  完成" -ForegroundColor Green

# 3. 安装 Playwright 浏览器内核
Write-Host "`n[3/5] 安装 Playwright Chromium..." -ForegroundColor Yellow
python -m playwright install chromium
Write-Host "  完成" -ForegroundColor Green

# 4. 检查 Node.js 并安装前端依赖 + 编译
Write-Host "`n[4/5] 安装前端依赖并编译..." -ForegroundColor Yellow
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
    Write-Host "  错误：未找到 Node.js，请先安装 Node.js 18+" -ForegroundColor Red
    exit 1
}
$nodeVer = node --version 2>&1
Write-Host "  Node $nodeVer"
Push-Location "$ROOT\frontend"
npm install --quiet
npm run build
Pop-Location
Write-Host "  完成" -ForegroundColor Green

# 5. 创建 config.yaml（如果不存在）
Write-Host "`n[5/5] 检查配置文件..." -ForegroundColor Yellow
if (-not (Test-Path "$ROOT\config.yaml")) {
    Copy-Item "$ROOT\config.yaml.example" "$ROOT\config.yaml"
    Write-Host "  已创建 config.yaml（从模板复制）" -ForegroundColor Green
    Write-Host "  请编辑 config.yaml 中的多空间浏览器路径" -ForegroundColor Yellow
} else {
    Write-Host "  config.yaml 已存在，跳过" -ForegroundColor Green
}

# 创建运行时目录
New-Item -ItemType Directory -Force -Path "$ROOT\runtime" | Out-Null
New-Item -ItemType Directory -Force -Path "$ROOT\outputs" | Out-Null
New-Item -ItemType Directory -Force -Path "$ROOT\data\products" | Out-Null

Write-Host "`n=== 安装完成 ===" -ForegroundColor Cyan
Write-Host "下一步：" -ForegroundColor White
Write-Host "  1. 编辑 config.yaml 中的 browser_executable_path（多空间浏览器路径）"
Write-Host "  2. 双击 start.bat 启动系统"
Write-Host "  3. 打开 http://localhost:5173 或 http://localhost:8001"
