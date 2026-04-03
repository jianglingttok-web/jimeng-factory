# start.ps1 - 即梦内容工厂开发环境一键启动

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:NO_PROXY = "127.0.0.1,localhost"

# 前置检查：config.yaml 是否存在
if (-not (Test-Path "$ROOT\config.yaml")) {
    Write-Host "错误：config.yaml 不存在。请先运行 setup.ps1" -ForegroundColor Red
    Write-Host "  powershell -ExecutionPolicy Bypass -File `"$ROOT\setup.ps1`""
    Read-Host "按回车键退出"
    exit 1
}

# 从 config.yaml 读取浏览器路径和 CDP 端口（纯 PowerShell，不依赖 Python）
$configLines = Get-Content "$ROOT\config.yaml" -Encoding UTF8
$BROWSER_EXE = ""
$CDP_URL = ""
foreach ($line in $configLines) {
    if ($line -match '^\s*browser_executable_path:\s*"?([^"#]+)"?') {
        $BROWSER_EXE = $Matches[1].Trim()
    }
    if ($line -match '^\s*cdp_url:\s*"?([^"#]+)"?') {
        $CDP_URL = $Matches[1].Trim()
    }
}
$CDP_PORT = if ($CDP_URL -match ':(\d+)') { $Matches[1] } else { "9222" }

if (-not $BROWSER_EXE -or -not (Test-Path $BROWSER_EXE)) {
    Write-Host "错误：多空间浏览器路径无效 — $BROWSER_EXE" -ForegroundColor Red
    Write-Host "  请检查 config.yaml 中的 browser_executable_path" -ForegroundColor Yellow
    Read-Host "按回车键退出"
    exit 1
}

# 前置检查：frontend/dist 是否存在
if (-not (Test-Path "$ROOT\frontend\dist\index.html")) {
    Write-Host "警告：前端未编译，将以开发模式运行（需要 Vite）" -ForegroundColor Yellow
}

function Test-Port($port) {
    try {
        $conn = [System.Net.Sockets.TcpClient]::new()
        $result = $conn.BeginConnect("127.0.0.1", $port, $null, $null)
        $success = $result.AsyncWaitHandle.WaitOne(500)
        $open = $success -and $conn.Connected
        $conn.Close()
        return $open
    } catch { return $false }
}

# 1. 多空间浏览器
if (Test-Port $CDP_PORT) {
    Write-Host "多空间浏览器已在运行，跳过。"
} else {
    Write-Host "启动多空间浏览器 (--remote-debugging-port=$CDP_PORT)..."
    Start-Process -FilePath $BROWSER_EXE -ArgumentList "--remote-debugging-port=$CDP_PORT"
    Start-Sleep -Seconds 2
}

# 2. FastAPI
if (Test-Port 8001) {
    Write-Host "FastAPI 已在运行 (port 8001)，跳过。"
} else {
    Write-Host "启动 FastAPI (port 8001)..."
    Start-Process cmd -ArgumentList "/k python -m uvicorn src.web.app:app --host 0.0.0.0 --port 8001" `
        -WorkingDirectory $ROOT -WindowStyle Normal
}

# 3. 前端：有 dist 走生产模式（FastAPI 直接 serve），否则 fallback Vite 开发模式
if (Test-Path "$ROOT\frontend\dist\index.html") {
    $OPEN_URL = "http://localhost:8001"
    Write-Host "前端使用生产模式（FastAPI 直接提供静态文件）"
} else {
    $OPEN_URL = "http://localhost:5173"
    if (Test-Port 5173) {
        Write-Host "Vite 前端已在运行 (port 5173)，跳过。"
    } else {
        Write-Host "启动 Vite 前端 (port 5173)..."
        Start-Process cmd -ArgumentList "/k npm run dev" `
            -WorkingDirectory "$ROOT\frontend" -WindowStyle Normal
    }
}

# 等待服务就绪后打开浏览器
Start-Sleep -Seconds 3
Write-Host "打开 $OPEN_URL ..."
Start-Process $OPEN_URL

Write-Host "所有服务已启动。"
