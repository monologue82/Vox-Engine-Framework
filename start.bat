@echo off
setlocal enabledelayedexpansion

cls
echo.
echo  +==============================================================+
echo  ^|                                                              ^|
echo  ^|                     VoxEngine Framework                      ^|
echo  ^|              Multi-Engine Speech Processing                  ^|
echo  ^|                                                              ^|
echo  +==============================================================+
echo.

echo  [1/5] Checking virtual environment...
echo.

if not exist "venv\Scripts\python.exe" (
    echo  [ERROR] Virtual environment not found!
    echo.
    echo  Please run setup.bat to create and configure virtual environment
    echo.
    pause
    exit /b 1
)

rem Check Python version
venv\Scripts\python.exe --version | findstr "3.11" >nul
if %errorlevel% neq 0 (
    echo  [ERROR] Virtual environment is not using Python 3.11!
    echo.
    echo  Please run setup.bat to recreate virtual environment
    echo.
    pause
    exit /b 1
)

rem Check PyTorch installation
venv\Scripts\python.exe -c "import torch; print('  PyTorch version:', torch.__version__); print('  CUDA available:', torch.cuda.is_available())" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] PyTorch not installed or CUDA not available!
    echo.
    echo  Please run setup.bat to install PyTorch
    echo.
    pause
    exit /b 1
)

rem Check GSV-TTS-Lite installation
venv\Scripts\python.exe -c "import gsv_tts" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [WARN] GSV-TTS-Lite not installed, TTS will be unavailable
    echo  Installing GSV-TTS-Lite...
    venv\Scripts\pip.exe install gsv-tts-lite==0.3.5 -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
)

rem Check pynvml installation (GPU monitoring)
venv\Scripts\python.exe -c "import pynvml" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [INFO] pynvml not installed, GPU monitoring disabled
    echo  Installing pynvml for GPU monitoring...
    venv\Scripts\pip.exe install pynvml -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
)

rem Check psutil installation (system monitoring)
venv\Scripts\python.exe -c "import psutil" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [INFO] psutil not installed, system monitoring disabled
    echo  Installing psutil for system monitoring...
    venv\Scripts\pip.exe install psutil -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
)

rem Check engine modules
venv\Scripts\python.exe -c "from engines import EngineManager" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [INFO] Engine modules not fully loaded, traditional engine will be used
)

echo  [OK] Virtual environment check passed
echo.

echo  [2/5] Checking vLLM (Default Translation Engine)...
echo.

venv\Scripts\python.exe -c "import vllm" >nul 2>&1
if %errorlevel% equ 0 goto vllm_installed

echo  [WARN] vLLM not installed!
echo.
echo  vLLM is the default translation engine.
echo  Installing now ^(this may take a few minutes^)...
echo.
venv\Scripts\pip.exe install vllm -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% equ 0 goto vllm_install_success

echo.
echo  [ERROR] vLLM installation failed!
echo.
echo  Please install manually:
echo    venv\Scripts\pip.exe install vllm
echo.
echo  Or use Ollama as alternative translation engine.
echo.
pause
goto check_ollama

:vllm_install_success
echo  [OK] vLLM installed successfully
goto check_ollama

:vllm_installed
echo  [OK] vLLM installed
venv\Scripts\python.exe -c "import vllm; print('  Version:', vllm.__version__)"

:check_ollama
echo.
echo  [3/5] Checking Ollama service (Optional Fallback)...
echo.

venv\Scripts\python.exe -c "import requests; requests.get('http://localhost:11434/api/tags', timeout=5)" >nul 2>&1
if %errorlevel% equ 0 goto ollama_running

echo  [INFO] Ollama service not running (optional, vLLM is default)
echo.
echo  Ollama can be used as a fallback translation engine.
echo  To enable Ollama:
echo    1. Install Ollama: https://ollama.com/
echo    2. Run: ollama serve
echo    3. Run: ollama pull llama2
echo.
goto check_streamspeech

:ollama_running
echo  [OK] Ollama service running (optional fallback)
echo.

:check_streamspeech
echo.
echo  [4/5] Checking StreamSpeech Engine (Optional)...
echo.

if not exist "StreamSpeech-main" (
    echo  [INFO] StreamSpeech directory not found
    echo  StreamSpeech engine will be unavailable
    echo.
    echo  To enable StreamSpeech:
    echo    1. Clone or download StreamSpeech repository
    echo    2. Place in project root directory
    echo    3. Install fairseq and simuleval
    echo.
    goto start_server
)

echo  [OK] StreamSpeech directory found
echo  Checking fairseq and simuleval...

venv\Scripts\python.exe -c "import fairseq; import simuleval" >nul 2>&1
if %errorlevel% equ 0 (
    echo  [OK] fairseq and simuleval installed
    echo  StreamSpeech engine is available
) else (
    echo  [WARN] fairseq or simuleval not installed
    echo.
    echo  To enable StreamSpeech engine:
    echo    pip install fairseq simuleval
    echo.
    echo  StreamSpeech features:
    echo    - End-to-end ASR+S2TT+S2ST
    echo    - Low latency (320-640ms)
    echo    - SOTA quality
    echo.
)

:start_server
echo.
echo  [5/5] Starting speech recognition server...
echo.
echo  +==============================================================+
echo  ^|  Server URL: http://localhost:5001                           ^|
echo  ^|  Version: v0.3.0 Framework Edition                           ^|
echo  ^|  Active Engine: vLLM (Default)                               ^|
echo  ^|  Available Engines: Traditional, StreamSpeech (Experimental) ^|
echo  ^|  Press Ctrl+C to stop server                                 ^|
echo  +==============================================================+
echo.
echo  Engine Options:
echo    - Traditional Engine: Vosk ASR + vLLM/llama.cpp + TTS
echo    - StreamSpeech Engine: End-to-End ASR+S2TT+S2ST
echo.
echo  You can switch engines in the web interface.
echo.
echo  System Monitor: Enabled (Memory, CPU, GPU)
echo.

venv\Scripts\python.exe app.py

if %errorlevel% neq 0 (
    echo.
    echo  Server exited with error code: %errorlevel%
    echo.
)

pause
