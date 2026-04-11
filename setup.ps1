# setup.ps1 - 即梦内容工厂环境安装（只需运行一次）

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:NO_PROXY = "127.0.0.1,localhost"

Write-Host "=== 即梦内容工厂 — 环境安装 ===" -ForegroundColor Cyan

# 1. 检查 Python（排除 Windows Store 占位符）
Write-Host "`n[1/4] 检查 Python..." -ForegroundColor Yellow
$pyVer = (python --version 2>&1) | Out-String
$pyVer = $pyVer.Trim()
if (-not $pyVer -or $pyVer -notmatch '^Python \d') {
    Write-Host "  未找到 Python，尝试自动安装..." -ForegroundColor Yellow

    # 检查 winget 是否可用
    $wg = Get-Command winget -ErrorAction SilentlyContinue
    if ($wg) {
        Write-Host "  通过 winget 安装 Python 3.12..." -ForegroundColor Yellow
        winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  winget 安装失败，请手动安装" -ForegroundColor Red
            Write-Host "  下载地址: https://python.org/downloads/" -ForegroundColor Yellow
            Write-Host "  安装时务必勾选 'Add Python to PATH'" -ForegroundColor Yellow
            Read-Host "按回车键退出"
            exit 1
        }
        # 刷新 PATH（winget 安装后 PATH 不会立即生效）
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        # 再次检查
        $pyVer = (python --version 2>&1) | Out-String
        $pyVer = $pyVer.Trim()
        if (-not $pyVer -or $pyVer -notmatch '^Python \d') {
            Write-Host "  Python 已安装但需要重启终端才能生效" -ForegroundColor Yellow
            Write-Host "  请关闭此窗口，重新双击 setup.bat" -ForegroundColor Yellow
            Read-Host "按回车键退出"
            exit 1
        }
        Write-Host "  Python 安装成功" -ForegroundColor Green
    } else {
        Write-Host "  错误：winget 不可用，请手动安装 Python" -ForegroundColor Red
        Write-Host "  下载地址: https://python.org/downloads/" -ForegroundColor Yellow
        Write-Host "  安装时务必勾选 'Add Python to PATH'" -ForegroundColor Yellow
        Read-Host "按回车键退出"
        exit 1
    }
}
Write-Host "  $pyVer" -ForegroundColor Green

# 2. 安装 Python 依赖
Write-Host "`n[2/4] 安装 Python 依赖..." -ForegroundColor Yellow

# 检查 pip 是否可用，不可用则尝试 bootstrap
$pipCheck = (python -m pip --version 2>&1) | Out-String
if ($pipCheck -notmatch 'pip') {
    Write-Host "  pip 未安装，尝试自动 bootstrap..." -ForegroundColor Yellow
    python -m ensurepip --upgrade 2>&1 | Out-Null
    # ensurepip 失败时降级为下载 get-pip.py
    $pipCheck2 = (python -m pip --version 2>&1) | Out-String
    if ($pipCheck2 -notmatch 'pip') {
        Write-Host "  ensurepip 失败，下载 get-pip.py..." -ForegroundColor Yellow
        Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile "$env:TEMP\get-pip.py" -UseBasicParsing
        python "$env:TEMP\get-pip.py" --quiet
    }
}

python -m pip install -r "$ROOT\requirements.txt" --quiet 2>&1 | Out-Null
# 验证关键依赖
$uvCheck = (python -c "import uvicorn; print('ok')" 2>&1) | Out-String
if ($uvCheck.Trim() -ne "ok") {
    Write-Host "  依赖安装失败，重试（显示详细输出）..." -ForegroundColor Yellow
    python -m pip install -r "$ROOT\requirements.txt"
    $uvCheck2 = (python -c "import uvicorn; print('ok')" 2>&1) | Out-String
    if ($uvCheck2.Trim() -ne "ok") {
        Write-Host "  错误：Python 依赖安装失败" -ForegroundColor Red
        Read-Host "按回车键退出"
        exit 1
    }
}
Write-Host "  完成" -ForegroundColor Green

# 3. 安装 Playwright 浏览器内核
Write-Host "`n[3/4] 安装 Playwright Chromium..." -ForegroundColor Yellow
python -m playwright install chromium
Write-Host "  完成" -ForegroundColor Green

# 4. 创建 config.yaml（如果不存在）
Write-Host "`n[4/4] 检查配置文件..." -ForegroundColor Yellow
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
