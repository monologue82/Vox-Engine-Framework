@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

for /F %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"

set "C_RESET=%ESC%[0m"
set "C_RED=%ESC%[31m"
set "C_GREEN=%ESC%[32m"
set "C_YELLOW=%ESC%[33m"
set "C_BLUE=%ESC%[34m"
set "C_MAGENTA=%ESC%[35m"
set "C_CYAN=%ESC%[36m"
set "C_WHITE=%ESC%[37m"
set "C_BOLD=%ESC%[1m"

set "APP_ROOT=%~dp0"

echo.
echo %C_BOLD%%C_CYAN%============================================%C_RESET%
echo %C_BOLD%%C_CYAN%       VoxEngine Setup Wizard%C_RESET%
echo %C_BOLD%%C_CYAN%============================================%C_RESET%
echo.

where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo %C_RED%[ERROR] Python is not installed or not found in PATH.%C_RESET%
    echo %C_YELLOW%Please install Python 3.10 or later from https://python.org%C_RESET%
    pause
    exit /b 1
)

python --version 2>&1 | find "3." >nul
if %ERRORLEVEL% NEQ 0 (
    echo %C_RED%[ERROR] Python 3.x is required.%C_RESET%
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYTHON_VER=%%v"
echo %C_GREEN%[OK] Python %PYTHON_VER% detected%C_RESET%
echo.

if not exist "%APP_ROOT%venv\Scripts\python.exe" (
    echo %C_YELLOW%[INFO] Creating virtual environment...%C_RESET%
    python -m venv "%APP_ROOT%venv"
    if !ERRORLEVEL! NEQ 0 (
        echo %C_RED%[ERROR] Failed to create virtual environment.%C_RESET%
        pause
        exit /b 1
    )
    echo %C_GREEN%[OK] Virtual environment created%C_RESET%
) else (
    echo %C_GREEN%[OK] Virtual environment already exists%C_RESET%
)
echo.

echo %C_BLUE%[INFO] Activating virtual environment...%C_RESET%
call "%APP_ROOT%venv\Scripts\activate.bat"

if "%VIRTUAL_ENV%"=="" (
    echo %C_RED%[ERROR] Failed to activate virtual environment.%C_RESET%
    pause
    exit /b 1
)
echo %C_GREEN%[OK] Virtual environment activated%C_RESET%
echo.

echo %C_BOLD%%C_YELLOW%[STEP] Installing core dependencies...%C_RESET%
echo %C_YELLOW%This may take a while. Please be patient...%C_RESET%
echo.

pip install --upgrade pip -q
if %ERRORLEVEL% NEQ 0 (
    echo %C_RED%[WARN] pip upgrade failed, continuing...%C_RESET%
)

echo %C_BLUE%[INFO] Installing editdistance-s (compatible editdistance replacement)...%C_RESET%
pip install editdistance-s>=1.0.0
if %ERRORLEVEL% NEQ 0 (
    echo %C_RED%[ERROR] Failed to install editdistance-s.%C_RESET%
    pause
    exit /b 1
)
echo %C_GREEN%[OK] editdistance-s installed%C_RESET%

echo %C_BLUE%[INFO] Installing funasr (without auto-dependencies)...%C_RESET%
pip install funasr>=1.1.0 --no-deps
if %ERRORLEVEL% NEQ 0 (
    echo %C_RED%[WARN] funasr --no-deps install had issues, continuing...%C_RESET%
)

echo %C_BLUE%[INFO] Installing remaining dependencies from requirements.txt...%C_RESET%
pip install -r "%APP_ROOT%requirements.txt"
if %ERRORLEVEL% NEQ 0 (
    echo %C_RED%[ERROR] Failed to install some dependencies.%C_RESET%
    echo %C_YELLOW%Check requirements.txt and try again.%C_RESET%
    pause
    exit /b 1
)
echo %C_GREEN%[OK] Dependencies installed successfully%C_RESET%
echo.

echo %C_BLUE%[INFO] Setting up editdistance compatibility layer...%C_RESET%
python -c "
import os, sys
venv_site = os.path.join(sys.prefix, 'Lib', 'site-packages', 'editdistance')
os.makedirs(venv_site, exist_ok=True)
init_py = os.path.join(venv_site, '__init__.py')
if not os.path.exists(init_py):
    with open(init_py, 'w') as f:
        f.write('from editdistance_s import distance\n\ndef eval(*args, **kwargs):\n    return distance(*args, **kwargs)\n\n__all__ = [\"eval\", \"distance\"]\n')
    print('[OK] editdistance compatibility shim created')
else:
    print('[OK] editdistance compatibility shim already exists')
"
echo %C_GREEN%[OK] editdistance compatibility ready%C_RESET%
echo.

if not exist "%APP_ROOT%models\stt\SenseVoiceSmall\model.pt" (
    echo %C_YELLOW%[INFO] ASR model not found locally.%C_RESET%
    echo %C_YELLOW%[INFO] The model will be downloaded automatically on first run.%C_RESET%
    echo.
) else (
    echo %C_GREEN%[OK] ASR model found%C_RESET%
)

if not exist "%APP_ROOT%models\tts\s2Gv2ProPlus.pth" (
    echo %C_YELLOW%[INFO] TTS model not found locally.%C_RESET%
    echo %C_YELLOW%[INFO] The model will be downloaded automatically on first run.%C_RESET%
    echo.
) else (
    echo %C_GREEN%[OK] TTS model found%C_RESET%
)

echo %C_BOLD%%C_GREEN%============================================%C_RESET%
echo %C_BOLD%%C_GREEN%      Setup Complete!%C_RESET%
echo %C_BOLD%%C_GREEN%============================================%C_RESET%
echo.
echo %C_CYAN%Run %C_BOLD%start.bat%C_RESET%%C_CYAN% to launch VoxEngine%C_RESET%
echo.
pause