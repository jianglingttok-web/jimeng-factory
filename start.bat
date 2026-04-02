@echo off
setlocal
chcp 65001 > nul

set "ROOT=%~dp0"
set "FRONTEND=%ROOT%frontend"
set "BROWSER_EXE=E:\多空间浏览器\mul-key-chrome\多空间浏览器.exe"
set "CDP_PORT=9222"
set "API_PORT=8001"
set "FRONTEND_URL=http://localhost:5173"

echo Checking multi-space browser on port %CDP_PORT%...
netstat -ano | findstr ":%CDP_PORT% " | findstr /C:"LISTENING" /C:"侦听" > nul 2>&1
if errorlevel 1 (
    echo Starting multi-space browser...
    start "" "%BROWSER_EXE%" --remote-debugging-port=%CDP_PORT%
) else (
    echo Multi-space browser already running.
)

echo Starting FastAPI on port %API_PORT%...
start "FastAPI" cmd /k "cd /d ""%ROOT%"" && python -m uvicorn src.web.app:app --host 0.0.0.0 --port %API_PORT%"

echo Starting Vite dev server...
start "Frontend" cmd /k "cd /d ""%FRONTEND%"" && npm run dev"

echo Opening frontend...
timeout /t 2 /nobreak > nul
start "" "%FRONTEND_URL%"
