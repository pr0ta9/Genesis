@echo off
setlocal enabledelayedexpansion

REM Save the project root directory
set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

echo Starting Genesis (Development Mode)...
echo.

echo [1/3] Starting Docker services...
echo (First time may take 10-20 minutes to build)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
if errorlevel 1 (
    echo ERROR: Failed to start Docker services
    pause
    exit /b 1
)

echo.
echo [2/3] Waiting for backend to be ready...
echo Backend: http://localhost:8000 (hot reload enabled)

:wait_backend
timeout /t 3 /nobreak >nul
curl -f http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    <nul set /p ="."
    goto :wait_backend
)

echo.
echo Backend is ready!

echo.
echo [3/3] Starting GUI (DEV mode)...
cd gui

REM Run Flutter and capture exit regardless of error code
call flutter run -d windows
set FLUTTER_EXIT_CODE=!errorlevel!

cd /d "%PROJECT_ROOT%"

echo.
echo GUI closed (exit code: !FLUTTER_EXIT_CODE!).
echo.
echo Stopping Docker services...
docker-compose -f docker-compose.yml -f docker-compose.dev.yml down
if errorlevel 1 (
    echo WARNING: Failed to stop some services
    pause
    exit /b 1
) else (
    echo Docker services stopped successfully.
    echo Genesis stopped.
)