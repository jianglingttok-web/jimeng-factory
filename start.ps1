# start.ps1 - 即梦内容工厂开发环境一键启动

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$BROWSER_EXE = "E:\多空间浏览器\mul-key-chrome\多空间浏览器.exe"
$CDP_PORT = 9222
$env:NO_PROXY = "127.0.0.1,localhost"

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

# 3. Vite 前端
if (Test-Port 5173) {
    Write-Host "Vite 前端已在运行 (port 5173)，跳过。"
} else {
    Write-Host "启动 Vite 前端 (port 5173)..."
    Start-Process cmd -ArgumentList "/k npm run dev" `
        -WorkingDirectory "$ROOT\frontend" -WindowStyle Normal
}

# 等待服务就绪后打开浏览器
Start-Sleep -Seconds 3
Write-Host "打开 http://localhost:5173 ..."
Start-Process "http://localhost:5173"

Write-Host "所有服务已启动。"
