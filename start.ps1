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
    if ($line -match "^\s*browser_executable_path:\s*[`"']?([^`"'#]+)[`"']?") {
        $BROWSER_EXE = $Matches[1].Trim()
    }
    if ($line -match "^\s*cdp_url:\s*[`"']?([^`"'#]+)[`"']?") {
        $CDP_URL = $Matches[1].Trim()
    }
}
$CDP_PORT = if ($CDP_URL -match ':(\d+)') { $Matches[1] } else { "9222" }

# 检查路径中的反斜杠问题（YAML 双引号里反斜杠会被当转义符）
$yamlPathBug = $configLines | Where-Object { $_ -match '_path:\s*[''"].*\\' }
if ($yamlPathBug) {
    Write-Host "警告：config.yaml 路径包含引号+反斜杠，可能导致 YAML 解析失败" -ForegroundColor Red
    Write-Host "  解决方法：把路径中的反斜杠 \ 全部改成正斜杠 /" -ForegroundColor Yellow
    Write-Host "  例如: browser_executable_path: C:/Users/.../mul-key-chrome.exe" -ForegroundColor Green
    Read-Host "按回车键退出"
    exit 1
}

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
$WEB_PORT = "3000"
foreach ($line in $configLines) {
    if ($line -match '^\s*web_port:\s*(\d+)') {
        $WEB_PORT = $Matches[1]
        break
    }
}

if (Test-Port $CDP_PORT) {
    Write-Host "多空间浏览器已在运行，跳过。"
} else {
    # 清理残留进程占用的 web port（上次崩溃残留）
    if (Test-Port $WEB_PORT) {
        Write-Host "检测到端口 $WEB_PORT 被占用，清理残留进程..." -ForegroundColor Yellow
        $pids = netstat -ano | Select-String "\s+\S+:${WEB_PORT}\s+\S+\s+LISTENING\s+(\d+)" | ForEach-Object {
            $_.Matches[0].Groups[1].Value
        } | Where-Object { [int]$_ -gt 4 -and [int]$_ -ne $PID } | Sort-Object -Unique
        foreach ($pid in $pids) {
            Write-Host "  终止进程 PID=$pid" -ForegroundColor Yellow
            Stop-Process -Id ([int]$pid) -Force -ErrorAction SilentlyContinue
        }
        if ($pids) { Start-Sleep -Seconds 1 }
        if (Test-Port $WEB_PORT) {
            Write-Host "  警告：端口 $WEB_PORT 仍被占用，浏览器可能启动失败" -ForegroundColor Red
        }
    }
    Write-Host "启动多空间浏览器 (--remote-debugging-port=$CDP_PORT)..."
    Start-Process -FilePath $BROWSER_EXE -ArgumentList "--remote-debugging-port=$CDP_PORT"
    Start-Sleep -Seconds 3
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

# 等待 FastAPI 就绪
Write-Host "等待 FastAPI 启动..." -NoNewline
$ready = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 1
    Write-Host "." -NoNewline
    if (Test-Port 8001) { $ready = $true; break }
}
Write-Host ""

if ($ready) {
    Write-Host "打开 $OPEN_URL ..."
    Start-Process $OPEN_URL
    Write-Host "所有服务已启动。"
} else {
    Write-Host "警告：FastAPI 未能在 20 秒内启动" -ForegroundColor Red
    Write-Host "  可能原因：" -ForegroundColor Yellow
    Write-Host "  1. 未运行 setup.bat 安装依赖" -ForegroundColor Yellow
    Write-Host "  2. 查看 FastAPI 窗口的错误信息" -ForegroundColor Yellow
    Write-Host "  手动测试: python -m uvicorn src.web.app:app --host 0.0.0.0 --port 8001" -ForegroundColor Yellow
    Read-Host "按回车键退出"
}
