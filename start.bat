@echo off
chcp 65001 >nul
setlocal

set "APP_ROOT=%~dp0"

echo.
echo   __      __   _   _   __     __  __ _ _
echo   \ \    / /__^| ^|_^| ^|__\ \   / / / _(_) ^|
echo    \ \/\/ / -_)  _^| / -_) ^| ^| / _ \ _^| ^|_^| ^|
echo     \_/\_/\___^|\__^|_\___^| ^|_^| \___/_^| \__, ^|
echo                                    ^|___/
echo.
echo ============================================
echo        VoxEngine Launcher
echo ============================================
echo.

if not exist "%APP_ROOT%venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found!
    echo Please run setup.bat first to initialize the environment.
    echo.
    pause
    exit /b 1
)

echo [INFO] Activating virtual environment...
call "%APP_ROOT%venv\Scripts\activate.bat"

if "%VIRTUAL_ENV%"=="" (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)
echo [OK] Virtual environment activated
echo.

echo [INFO] Starting VoxEngine server...
echo.
echo ============================================
echo   Server will be available at:
echo     http://localhost:5000/app
echo     http://localhost:5000/settings
echo ============================================
echo.
echo Press Ctrl+C to stop the server
echo.

cd /d "%APP_ROOT%"

"%APP_ROOT%venv\Scripts\python.exe" app.py

echo.
echo [OK] VoxEngine has shut down.
echo.
pause