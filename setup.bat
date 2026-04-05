@echo off
setlocal enabledelayedexpansion

title VoxEngine Framework - Setup

cls
echo.
echo  +==============================================================+
echo  ^|                                                              ^|
echo  ^|           VoxEngine Framework - Setup Tool                   ^|
echo  ^|                                                              ^|
echo  +==============================================================+
echo.

set "REQUIREMENTS_FILE=requirements.txt"
set "VENV_DIR=venv"
set "VOSK_MODEL_DIR=models\stt\vosk-model-small-cn-0.22"
set "VLLM_URL=http://localhost:8000"
set "OLLAMA_URL=http://localhost:11434"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

echo  [Step 1/9] Checking Python environment...
echo.

where py >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python not found!
    echo.
    echo  Please install Python 3.11:
    echo    Download: https://www.python.org/downloads/
    echo    Check "Add Python to PATH" during installation
    echo.
    goto :error_exit
)

py -3.11 --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python 3.11 not found!
    echo.
    echo  Please install Python 3.11:
    echo    Download: https://www.python.org/downloads/
    echo    Check "Add Python to PATH" during installation
    echo.
    goto :error_exit
)

py -3.11 --version
echo  [OK] Python 3.11 installed
echo.

echo  [Step 2/9] Checking/Creating virtual environment...
echo.

set "NEED_CREATE_VENV=1"

if exist "%VENV_PYTHON%" (
    echo  Virtual environment exists, checking...
    "%VENV_PYTHON%" --version >nul 2>&1
    if !errorlevel! equ 0 (
        echo  [OK] Virtual environment is valid
        set "NEED_CREATE_VENV=0"
    ) else (
        echo  [WARN] Virtual environment is corrupted, recreating...
    )
)

if "%NEED_CREATE_VENV%"=="1" (
    if exist "%VENV_DIR%" (
        echo  Removing old virtual environment...
        rmdir /s /q "%VENV_DIR%" 2>nul
        if exist "%VENV_DIR%" (
            echo  [WARN] Cannot delete old directory, renaming...
            ren "%VENV_DIR%" "venv_old_%RANDOM%" 2>nul
        )
    )
    
    echo  Creating virtual environment with Python 3.11...
    py -3.11 -m venv "%VENV_DIR%"
    if %errorlevel% neq 0 (
        echo  [ERROR] Failed to create virtual environment!
        echo.
        echo  Please try manually:
        echo    py -3.11 -m venv venv
        echo.
        goto :error_exit
    )
    
    if not exist "%VENV_PYTHON%" (
        echo  [ERROR] Virtual environment created but python.exe not found
        goto :error_exit
    )
    
    echo  [OK] Virtual environment created
)
echo.

echo  [Step 3/9] Upgrading pip...
echo.

"%VENV_PYTHON%" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
if %errorlevel% neq 0 (
    echo  [WARN] pip upgrade failed, continuing...
) else (
    echo  [OK] pip upgraded to latest version
)
echo.

echo  [Step 4/9] Installing PyTorch 2.8.0+cu128 (for RTX 5060)...
echo.

echo  Installing PyTorch 2.8.0+cu128, please wait...
echo  This may take a few minutes...
"%VENV_PYTHON%" -m pip install torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128 >nul 2>&1
if %errorlevel% neq 0 (
    echo  [WARN] PyTorch installation failed, trying Tsinghua mirror...
    "%VENV_PYTHON%" -m pip install torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
)
echo  [OK] PyTorch installed
echo.

echo  [Step 5/9] Installing project dependencies...
echo.

if not exist "%REQUIREMENTS_FILE%" (
    echo  [ERROR] %REQUIREMENTS_FILE% not found!
    goto :error_exit
)

echo  Installing dependencies, please wait...
"%VENV_PYTHON%" -m pip install -r %REQUIREMENTS_FILE% -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
if %errorlevel% neq 0 (
    echo  [WARN] Dependencies installation failed, trying one by one...
    
    for /f "tokens=*" %%i in (%REQUIREMENTS_FILE%) do (
        echo    Installing: %%i
        "%VENV_PYTHON%" -m pip install "%%i" -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
    )
)
echo  [OK] Dependencies installed
echo.

echo  [Step 6/9] Installing vLLM (Default Translation Engine)...
echo.

echo  Installing vLLM, please wait...
echo  This may take several minutes depending on your network...
"%VENV_PYTHON%" -m pip install vllm -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
if %errorlevel% neq 0 (
    echo  [WARN] vLLM installation from Tsinghua mirror failed, trying official source...
    "%VENV_PYTHON%" -m pip install vllm >nul 2>&1
)

"%VENV_PYTHON%" -c "import vllm" >nul 2>&1
if %errorlevel% equ 0 (
    echo  [OK] vLLM installed successfully
    "%VENV_PYTHON%" -c "import vllm; print('  Version:', vllm.__version__)"
) else (
    echo  [WARN] vLLM installation failed!
    echo  You can install it later manually:
    echo    venv\Scripts\pip.exe install vllm
    echo.
    echo  Or use Ollama as alternative translation engine.
)
echo.

echo  [Step 6.5/9] Optional: StreamSpeech End-to-End Engine...
echo.

echo  StreamSpeech provides low-latency ASR+S2TT+S2ST with SOTA quality
echo.
choice /c YN /m "  Install fairseq and simuleval for StreamSpeech?"
if %errorlevel% equ 1 (
    echo.
    echo  Installing fairseq and simuleval...
    "%VENV_PYTHON%" -m pip install fairseq simuleval -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
    if %errorlevel% neq 0 (
        echo  [WARN] StreamSpeech dependencies installation failed
        echo  Install manually: venv\Scripts\pip.exe install fairseq simuleval
    ) else (
        echo  [OK] StreamSpeech dependencies installed
    )
) else (
    echo.
    echo  [INFO] Skipping StreamSpeech installation
    echo  You can install later: venv\Scripts\pip.exe install fairseq simuleval
)
echo.

echo  [Step 7/9] Checking Vosk speech model...
echo.

if exist "%VOSK_MODEL_DIR%\am\final.mdl" (
    echo  [OK] Vosk Chinese model exists
) else (
    echo  [WARN] Vosk Chinese model not found!
    echo.
    echo  Please download Vosk Chinese model:
    echo    Download: https://alphacephei.com/vosk/models
    echo    Recommended: vosk-model-small-cn-0.22 (~50MB)
    echo.
    echo  Extract to: %VOSK_MODEL_DIR%
    echo.
    choice /c YN /m "  Continue without model (can be downloaded later)?"
    if !errorlevel! equ 2 goto :error_exit
)
echo.

echo  [Step 8/9] Checking Ollama service (Optional Fallback)...
echo.

REM Check if vLLM is installed successfully
"%VENV_PYTHON%" -c "import vllm" >nul 2>&1
if %errorlevel% equ 0 (
    echo  [INFO] vLLM is installed and will be used as default engine
    echo  Skipping Ollama service check (vLLM is preferred)
    echo.
    echo  Note: Ollama can still be used as fallback if needed.
    echo  To enable Ollama manually:
    echo    1. Run: ollama serve
    echo    2. Configure in web interface
    echo.
    goto :skip_ollama_check
)

REM Only check Ollama if vLLM is not installed
where ollama >nul 2>&1
if %errorlevel% neq 0 (
    echo  [INFO] Ollama not found (optional, vLLM is the default)
    echo.
    echo  Ollama can be installed as a fallback translation engine:
    echo    Download: https://ollama.com/
    echo.
    echo  To use Ollama:
    echo    1. Install Ollama
    echo    2. Run: ollama serve
    echo    3. Run: ollama pull llama2
    echo.
) else (
    echo  [OK] Ollama installed (optional fallback)
    
    "%VENV_PYTHON%" -c "import requests; requests.get('%OLLAMA_URL%/api/tags', timeout=5)" >nul 2>&1
    if !errorlevel! neq 0 (
        echo  Starting Ollama service...
        start "" ollama serve >nul 2>&1
        timeout /t 5 /nobreak >nul
    )
    
    "%VENV_PYTHON%" -c "import requests; requests.get('%OLLAMA_URL%/api/tags', timeout=5)" >nul 2>&1
    if !errorlevel! equ 0 (
        echo  [OK] Ollama service running
        
        echo.
        echo  Checking available models...
        "%VENV_PYTHON%" -c "import requests, json; r=requests.get('%OLLAMA_URL%/api/tags'); models=[m['name'] for m in r.json().get('models',[])]; print('  Installed models: ' + (', '.join(models) if models else 'None')); exit(0 if models else 1)" >nul 2>&1
        if !errorlevel! neq 0 (
            echo  [INFO] No Ollama models found (optional, vLLM is default)
            echo.
            echo  To download Ollama models:
            echo    ollama pull llama2
            echo    ollama pull qwen2
            echo.
        )
    ) else (
        echo  [INFO] Ollama service not running (optional, vLLM is default)
    )
)

:skip_ollama_check
echo.

echo  [Step 9/9] Downloading NLTK data...
echo.

echo  Downloading NLTK cmudict (required for TTS)...
"%VENV_PYTHON%" -c "import nltk; nltk.download('cmudict', quiet=True)"
if %errorlevel% neq 0 (
    echo  [WARN] NLTK cmudict download failed, will retry on first use
) else (
    echo  [OK] NLTK cmudict downloaded
)
echo.

echo  [Step 10/10] Verifying installation...
echo.

echo  Checking core modules...
"%VENV_PYTHON%" -c "import flask; import vosk; import pyaudio; import requests; import flask_socketio; import numpy; print('  [OK] All core modules imported')" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Core modules import failed, check dependencies!
    goto :error_exit
)

echo  Checking GSV-TTS-Lite module...
"%VENV_PYTHON%" -c "import gsv_tts; print('  [OK] GSV-TTS-Lite module imported')" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [WARN] GSV-TTS-Lite import failed, TTS will be disabled
    echo  Installing GSV-TTS-Lite...
    "%VENV_PYTHON%" -m pip install gsv-tts-lite==0.3.5 -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
    if %errorlevel% neq 0 (
        echo  [WARN] GSV-TTS-Lite installation failed, install manually: pip install gsv-tts-lite==0.3.5
    ) else (
        echo  [OK] GSV-TTS-Lite installed
    )
)
echo.

echo  Checking vLLM module...
"%VENV_PYTHON%" -c "import vllm; print('  [OK] vLLM module imported')" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [WARN] vLLM not installed
    echo  Install manually: venv\Scripts\pip.exe install vllm
)
echo.

echo  Checking monitoring modules...
"%VENV_PYTHON%" -c "import psutil; print('  [OK] psutil module imported')" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [INFO] psutil not installed, installing for system monitoring...
    "%VENV_PYTHON%" -m pip install psutil -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
)

"%VENV_PYTHON%" -c "import pynvml; print('  [OK] pynvml module imported')" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [INFO] pynvml not installed, installing for GPU monitoring...
    "%VENV_PYTHON%" -m pip install pynvml -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
    if %errorlevel% neq 0 (
        echo  [INFO] pynvml installation failed, GPU monitoring will be disabled
        echo  This is normal if you don't have an NVIDIA GPU
    ) else (
        echo  [OK] pynvml installed
    )
)
echo.

echo.
echo  +==============================================================+
echo  ^|                                                              ^|
echo  ^|                    Setup Complete!                           ^|
echo  ^|                                                              ^|
echo  +==============================================================+
echo.
echo  Version: v0.3.0 Framework Edition
echo  Default Engine: Traditional (Vosk + vLLM/llama.cpp + TTS)
echo  Experimental Engine: StreamSpeech (End-to-End)
echo  System Monitor: Enabled (Memory, CPU, GPU)
echo.
echo  Next steps:
echo    1. Run start.bat to start the application
echo    2. Run repair.bat if you encounter any issues
echo.
echo  Available Engines:
echo    - Traditional Engine: Vosk ASR + vLLM/llama.cpp + TTS
echo    - StreamSpeech Engine: End-to-End ASR+S2TT+S2ST (if installed)
echo.

choice /c YN /m "  Start service now?"
if %errorlevel% equ 1 (
    echo.
    echo  Starting service...
    call start.bat
)

goto :end

:error_exit
echo.
echo  +==============================================================+
echo  ^|                                                              ^|
echo  ^|                    Setup Failed!                             ^|
echo  ^|                                                              ^|
echo  +==============================================================+
echo.
pause
exit /b 1

:end
pause
exit /b 0
