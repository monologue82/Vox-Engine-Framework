@echo off
setlocal enabledelayedexpansion

title VoxEngine Framework - Stop Services

cls
echo.
echo  +==============================================================+
echo  ^|                                                              ^|
echo  ^|           VoxEngine Framework - Stop Services                ^|
echo  ^|                                                              ^|
echo  +==============================================================+
echo.

echo  [1/4] Stopping Flask application...
echo.

rem Find and kill Python processes running app.py
for /f "tokens=2" %%i in ('tasklist /FI "WINDOWTITLE eq VoxEngine*" /NH 2^>nul ^| findstr "python"') do (
    echo  [INFO] Found Python process: %%i
    taskkill /F /PID %%i >nul 2>&1
    if !errorlevel! equ 0 (
        echo  [OK] Process %%i terminated
    )
)

rem Try to kill by window title
taskkill /FI "WINDOWTITLE eq VoxEngine*" /F >nul 2>&1
if !errorlevel! equ 0 (
    echo  [OK] VoxEngine processes terminated
) else (
    echo  [INFO] No VoxEngine processes found
)

echo.
echo  [2/4] Stopping vLLM server...
echo.

rem Kill vLLM processes
taskkill /FI "WINDOWTITLE eq *vLLM*" /F >nul 2>&1
if !errorlevel! equ 0 (
    echo  [OK] vLLM server stopped
) else (
    echo  [INFO] No vLLM server running
)

rem Kill Python processes with vllm in command
for /f "tokens=2" %%i in ('wmic process where "commandline like '%%vllm%%'" get ProcessId 2^>nul ^| findstr "[0-9]"') do (
    echo  [INFO] Found vLLM process: %%i
    taskkill /F /PID %%i >nul 2>&1
)

echo.
echo  [3/4] Stopping llama.cpp server...
echo.

rem Kill llama.cpp processes
for /f "tokens=2" %%i in ('wmic process where "commandline like '%%llama%%'" get ProcessId 2^>nul ^| findstr "[0-9]"') do (
    echo  [INFO] Found llama.cpp process: %%i
    taskkill /F /PID %%i >nul 2>&1
)

for /f "tokens=2" %%i in ('wmic process where "commandline like '%%server.exe%%'" get ProcessId 2^>nul ^| findstr "[0-9]"') do (
    echo  [INFO] Found server process: %%i
    taskkill /F /PID %%i >nul 2>&1
)

echo  [OK] llama.cpp server stopped

echo.
echo  [4/4] Cleaning up...
echo.

rem Wait a moment for processes to fully terminate
timeout /t 2 /nobreak >nul

echo  [OK] All services stopped
echo.

echo  +==============================================================+
echo  ^|                                                              ^|
echo  ^|                  Services Stopped Successfully               ^|
echo  ^|                                                              ^|
echo  +==============================================================+
echo.
echo  Stopped services:
echo    - Flask application (app.py)
echo    - vLLM server (if running)
echo    - llama.cpp server (if running)
echo.
echo  You can now restart the services with start.bat
echo.

pause
