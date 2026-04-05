@echo off
setlocal enabledelayedexpansion

title VoxEngine Framework - Environment Repair

cls
echo.
echo  +==============================================================+
echo  ^|                                                              ^|
echo  ^|           VoxEngine Framework - Repair Tool                  ^|
echo  ^|                                                              ^|
echo  +==============================================================+
echo.

echo  [Step 1/8] Checking virtual environment...
echo.

if not exist "venv\Scripts\python.exe" (
    echo  [ERROR] Virtual environment not found!
    echo.
    echo  Please run setup.bat to deploy environment
    echo.
    pause
    exit /b 1
)

echo  [OK] Virtual environment exists
echo.

echo  [Step 2/8] Checking Python version...
echo.

venv\Scripts\python.exe --version
for /f "tokens=2" %%i in ('venv\Scripts\python.exe --version 2^>^&1') do set PYTHON_VERSION=%%i
echo  Current Python version: %PYTHON_VERSION%
echo.

echo  [OK] Python environment is normal
echo.

echo  [Step 3/8] Checking PyTorch installation...
echo.

venv\Scripts\python.exe -c "import torch" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] PyTorch not installed!
    echo  Trying to install PyTorch (CUDA required)...
    echo.
    echo  Method 1: Using PyTorch official source (CUDA 12.8)...
    venv\Scripts\pip.exe install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
    if %errorlevel% neq 0 (
        echo.
        echo  Method 1 failed, trying Method 2: PyTorch official (CUDA 12.4)...
        venv\Scripts\pip.exe install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
    )
    if %errorlevel% neq 0 (
        echo.
        echo  Method 2 failed, trying Method 3: PyTorch official (CUDA 12.1)...
        venv\Scripts\pip.exe install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
    )
    if %errorlevel% neq 0 (
        echo.
        echo  Method 3 failed, trying Method 4: PyTorch official (CUDA 11.8)...
        venv\Scripts\pip.exe install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
    )
    if %errorlevel% neq 0 (
        echo.
        echo  [ERROR] PyTorch CUDA version installation failed!
        echo.
        echo  Please check if your GPU supports CUDA
        echo  Or manually run: venv\Scripts\pip.exe install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
        echo.
        pause
        exit /b 1
    )
)

:check_cuda
echo.
echo  Checking PyTorch CUDA support...
venv\Scripts\python.exe -c "import torch; exit(0 if torch.cuda.is_available() else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] PyTorch installed but CUDA not available!
    echo.
    echo  Reinstalling PyTorch CUDA version...
    echo  Uninstalling current version...
    venv\Scripts\pip.exe uninstall -y torch torchvision torchaudio >nul 2>&1
    echo.
    echo  Method 1: Using PyTorch official source (CUDA 12.8)...
    venv\Scripts\pip.exe install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
    if %errorlevel% neq 0 (
        echo.
        echo  Method 1 failed, trying Method 2: PyTorch official (CUDA 12.4)...
        venv\Scripts\pip.exe install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
    )
    if %errorlevel% neq 0 (
        echo.
        echo  Method 2 failed, trying Method 3: PyTorch official (CUDA 12.1)...
        venv\Scripts\pip.exe install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
    )
    if %errorlevel% neq 0 (
        echo.
        echo  Method 3 failed, trying Method 4: PyTorch official (CUDA 11.8)...
        venv\Scripts\pip.exe install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
    )
    if %errorlevel% neq 0 (
        echo.
        echo  [ERROR] PyTorch CUDA version installation failed!
        echo.
        echo  Please ensure your GPU supports CUDA
        echo  And NVIDIA graphics driver is installed
        echo.
        pause
        exit /b 1
    )
    goto :check_cuda
)

echo  [OK] PyTorch installed, CUDA support normal
venv\Scripts\python.exe -c "import torch; print('  Version:', torch.__version__); print('  CUDA:', 'Available'); print('  GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
echo.

echo  [Step 4/8] Checking vLLM installation (Default Translation Engine)...
echo.

venv\Scripts\python.exe -c "import vllm" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [WARN] vLLM not installed! Installing now...
    echo.
    echo  Installing vLLM (this may take a few minutes)...
    venv\Scripts\pip.exe install vllm -i https://pypi.tuna.tsinghua.edu.cn/simple
    if %errorlevel% neq 0 (
        echo.
        echo  [WARN] vLLM installation failed from Tsinghua mirror, trying official source...
        venv\Scripts\pip.exe install vllm
    )
    if %errorlevel% neq 0 (
        echo.
        echo  [ERROR] vLLM installation failed!
        echo.
        echo  Please install manually:
        echo    venv\Scripts\pip.exe install vllm
        echo.
        echo  Or use alternative translation engine (Ollama)
        echo.
    ) else (
        echo  [OK] vLLM installed successfully
        venv\Scripts\python.exe -c "import vllm; print('  Version:', vllm.__version__)"
    )
) else (
    echo  [OK] vLLM installed
    venv\Scripts\python.exe -c "import vllm; print('  Version:', vllm.__version__)"
)
echo.

echo  [Step 5/8] Checking core dependencies...
echo.

set "MISSING_DEPS="

venv\Scripts\python.exe -c "import flask" >nul 2>&1
if %errorlevel% neq 0 set "MISSING_DEPS=%MISSING_DEPS% flask"

venv\Scripts\python.exe -c "import vosk" >nul 2>&1
if %errorlevel% neq 0 set "MISSING_DEPS=%MISSING_DEPS% vosk"

venv\Scripts\python.exe -c "import pyaudio" >nul 2>&1
if %errorlevel% neq 0 set "MISSING_DEPS=%MISSING_DEPS% pyaudio"

venv\Scripts\python.exe -c "import flask_socketio" >nul 2>&1
if %errorlevel% neq 0 set "MISSING_DEPS=%MISSING_DEPS% flask-socketio"

venv\Scripts\python.exe -c "import requests" >nul 2>&1
if %errorlevel% neq 0 set "MISSING_DEPS=%MISSING_DEPS% requests"

venv\Scripts\python.exe -c "import numpy" >nul 2>&1
if %errorlevel% neq 0 set "MISSING_DEPS=%MISSING_DEPS% numpy"

venv\Scripts\python.exe -c "import gsv_tts" >nul 2>&1
if %errorlevel% neq 0 set "MISSING_DEPS=%MISSING_DEPS% gsv-tts-lite"

if not "%MISSING_DEPS%"=="" (
    echo  [WARN] Missing dependencies:%MISSING_DEPS%
    echo  Installing missing dependencies...
    if exist "requirements.txt" (
        venv\Scripts\pip.exe install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    ) else (
        echo  requirements.txt not found, trying individual install...
        for %%d in (%MISSING_DEPS%) do (
            echo  Installing: %%d
            venv\Scripts\pip.exe install %%d -i https://pypi.tuna.tsinghua.edu.cn/simple
        )
    )
) else (
    echo  [OK] All core dependencies installed
)
echo.

echo  [Step 6/8] Checking engine modules...
echo.

if exist "engines" (
    echo  [OK] Engine modules directory found
    venv\Scripts\python.exe -c "from engines import EngineManager; print('  [OK] Engine modules imported')" >nul 2>&1
    if %errorlevel% equ 0 (
        echo  [OK] Engine modules loaded successfully
    ) else (
        echo  [WARN] Engine modules import failed
        echo  Traditional engine will be used
    )
) else (
    echo  [INFO] Engine modules directory not found
    echo  Traditional engine will be used
)
echo.

echo  [Step 7/8] Checking StreamSpeech dependencies (Optional)...
echo.

if exist "StreamSpeech-main" (
    echo  [OK] StreamSpeech directory found
    venv\Scripts\python.exe -c "import fairseq; import simuleval" >nul 2>&1
    if %errorlevel% equ 0 (
        echo  [OK] fairseq and simuleval installed
        echo  StreamSpeech engine is available
    ) else (
        echo  [WARN] fairseq or simuleval not installed
        echo.
        echo  Installing StreamSpeech dependencies...
        venv\Scripts\pip.exe install fairseq simuleval -i https://pypi.tuna.tsinghua.edu.cn/simple
        if %errorlevel% equ 0 (
            echo  [OK] StreamSpeech dependencies installed
        ) else (
            echo  [WARN] StreamSpeech dependencies installation failed
            echo  Install manually: pip install fairseq simuleval
        )
    )
) else (
    echo  [INFO] StreamSpeech directory not found (optional)
)
echo.

echo  [Step 8/8] Checking monitoring modules...
echo.

echo  Checking psutil (system monitoring)...
venv\Scripts\python.exe -c "import psutil" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [INFO] psutil not installed, installing...
    venv\Scripts\pip.exe install psutil -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
    if %errorlevel% neq 0 (
        echo  [WARN] psutil installation failed
    ) else (
        echo  [OK] psutil installed
    )
) else (
    echo  [OK] psutil installed
)

echo  Checking pynvml (GPU monitoring)...
venv\Scripts\python.exe -c "import pynvml" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [INFO] pynvml not installed, installing...
    venv\Scripts\pip.exe install pynvml -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
    if %errorlevel% neq 0 (
        echo  [INFO] pynvml installation failed, GPU monitoring disabled
        echo  This is normal if you don't have an NVIDIA GPU
    ) else (
        echo  [OK] pynvml installed
    )
) else (
    echo  [OK] pynvml installed
)
echo.

echo  +==============================================================+
echo  ^|                                                              ^|
echo  ^|                  Environment Repair Complete!                ^|
echo  ^|                                                              ^|
echo  +==============================================================+
echo.
echo  Version: v0.3.0 Framework Edition
echo  Default Engine: Traditional (Vosk + vLLM/llama.cpp + TTS)
echo  Experimental Engine: StreamSpeech (End-to-End)
echo  System Monitor: Enabled (Memory, CPU, GPU)
echo.
echo  Now you can run start.bat to start the application
echo.

choice /c YN /m "  Start service now?"
if %errorlevel% equ 1 (
    echo.
    echo  Starting service...
    call start.bat
)

exit /b 0
