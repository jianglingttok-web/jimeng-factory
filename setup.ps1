# setup.ps1 - 即梦内容工厂环境安装（只需运行一次）

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:NO_PROXY = "127.0.0.1,localhost"

Write-Host "=== 即梦内容工厂 — 环境安装 ===" -ForegroundColor Cyan

# 1. 检查 Python（排除 Windows Store 占位符）
Write-Host "`n[1/5] 检查 Python..." -ForegroundColor Yellow
$pyVer = (python --version 2>&1) | Out-String
$pyVer = $pyVer.Trim()
if (-not $pyVer -or $pyVer -notmatch '^Python \d') {
    Write-Host "  错误：未找到 Python（或仅有 Windows Store 占位符）" -ForegroundColor Red
    Write-Host "  请从 https://python.org/downloads/ 安装 Python 3.10+" -ForegroundColor Yellow
    Write-Host "  安装时务必勾选 'Add Python to PATH'" -ForegroundColor Yellow
    Read-Host "按回车键退出"
    exit 1
}
Write-Host "  $pyVer" -ForegroundColor Green

# 2. 安装 Python 依赖
Write-Host "`n[2/5] 安装 Python 依赖..." -ForegroundColor Yellow
python -m pip install -r "$ROOT\requirements.txt" --quiet
Write-Host "  完成" -ForegroundColor Green

# 3. 安装 Playwright 浏览器内核
Write-Host "`n[3/5] 安装 Playwright Chromium..." -ForegroundColor Yellow
python -m playwright install chromium
Write-Host "  完成" -ForegroundColor Green

# 4. 前端编译（已有 dist 则跳过）
Write-Host "`n[4/5] 检查前端..." -ForegroundColor Yellow
if (Test-Path "$ROOT\frontend\dist\index.html") {
    Write-Host "  前端已编译，跳过" -ForegroundColor Green
} else {
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
}

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
