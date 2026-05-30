[中文](README-CN.md) | English

# Vox Engine Framework

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](#)
[![GPU](https://img.shields.io/badge/GPU-CUDA-green.svg)](#)

A real-time speech recognition and translation system with streaming output, powered by FunASR/SenseVoice for high-performance offline ASR and multiple AI translation engine backends.

## Features

- **Real-time Speech Recognition** — FunASR with SenseVoiceSmall model, GPU-accelerated streaming ASR
- **Multi-Engine Translation** — Supports LPS (Local Processing System), vLLM, Ollama, and LM Studio
- **Streaming Output** — Real-time streaming display of both recognition and translation results
- **Text-to-Speech** — GSV-TTS-Lite based TTS with streaming playback
- **Streaming TTS** — Incremental TTS that plays as translation chunks arrive, with auto-play support
- **Microphone Management** — Multi-device selection and switching
- **Smart Translation Batching** — Accumulates ASR text and batches translation requests based on content length
- **Sequence-Ordered Translation** — Server-side sequence numbering prevents out-of-order translation display
- **Persistent ASR Cache** — Cross-chunk FunASR cache maintains streaming context across audio segments
- **Real-time Monitoring** — Recognition confidence, translation latency, audio levels, and character counts
- **Web Interface** — Modern, responsive WebUI with dark/light theme support

## Tech Stack

### Backend

| Component | Technology |
|-----------|-----------|
| Web Framework | Flask + Flask-SocketIO |
| ASR Engine | FunASR + SenseVoiceSmall |
| Translation | LPS (llama.cpp / OpenAI-compatible), vLLM, Ollama, LM Studio |
| TTS Engine | GSV-TTS-Lite with embedding-based voice cloning |
| Async Runtime | eventlet + threading |
| Audio Processing | PyAudio + Web Audio API |
| Caching | LRU Cache with TTL |

### Frontend

| Component | Technology |
|-----------|-----------|
| Core | HTML5 + CSS3 + JavaScript |
| Real-time Communication | Socket.IO |
| Audio Capture | Web Audio API (MediaStream) |
| Audio Processing | AudioWorklet + ScriptProcessor |
| Design System | Custom editorial design with warm palette |

## System Requirements

### Minimum

- **OS**: Windows 10/11
- **Python**: 3.11+
- **RAM**: 8GB
- **Storage**: 10GB free
- **GPU**: Recommended (NVIDIA with CUDA)

### Recommended

- **OS**: Windows 11
- **Python**: 3.13
- **RAM**: 16GB+
- **GPU**: NVIDIA GPU with CUDA 12+
- **Storage**: 50GB+ SSD

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/monologue82/Vox-Engine-Framework.git
cd Vox-Engine-Framework
```

### 2. Install Dependencies

#### Option A: Using Setup Script (Recommended)

```bash
setup.bat
```

#### Option B: Manual Installation

```bash
# Create virtual environment
python -m venv venv

# Activate it
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

> **Note**: For CUDA 12+ GPU support, install PyTorch separately:
> ```bash
> pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu132
> ```

### 3. Start the System

```bash
start.bat
```

Or manually:

```bash
.\venv\Scripts\activate
python app.py
```

### 4. Access the Interface

Open your browser and visit:

- **Main page**: [http://localhost:5000/app](http://localhost:5000/app)
- **Settings**: [http://localhost:5000/settings](http://localhost:5000/settings)

## Web Interface

The system provides a modern web interface with the following pages:

| Route | Page | Description |
|-------|------|-------------|
| `/app` | Main Application | Real-time ASR, translation, and TTS interface |
| `/settings` | Settings | Microphone, translation engine, TTS, and theme configuration |
| `/start` | Launch Page | System startup and status overview |
| `/loading` | Loading | Model loading progress display |
| `/asr_debug` | ASR Debug | Raw ASR output inspector |
| `/translation_debug` | Translation Debug | Translation stream inspector |
| `/tts_debug` | TTS Debug | TTS stream inspector |
| `/tts_only_debug` | TTS Only | Standalone TTS test page |

## Translation Engine Setup

### LPS (Local Processing System) — Default

The system uses LPS as the default translation provider, which supports two backends:

**OpenAI-compatible** (recommended): Connect to any OpenAI-compatible server (LM Studio, llama-server, Ollama, vLLM)
```json
{
  "lps": {
    "backend": "openai_compatible",
    "openai_url": "http://localhost:8080/v1"
  }
}
```

**llama.cpp**: Use local GGUF models directly
```json
{
  "lps": {
    "backend": "llama_cpp",
    "models_dir": "models/translate",
    "default_model": "models/translate/your-model.gguf"
  }
}
```

### vLLM

```bash
pip install vllm
# System will auto-start vLLM service
```

### Ollama

1. Download and install [Ollama](https://ollama.com/)
2. Start the service: `ollama serve`
3. Pull a model: `ollama pull qwen2.5:3b`

### LM Studio

1. Download [LM Studio](https://lmstudio.ai/)
2. Load a model and start the local inference server
3. Set the API URL in the web interface settings

## TTS Configuration

The system supports streaming TTS with the following features:

- **Voice Selection**: Multiple preset voices (Jenny, Xiaoxiao, Xiaoyi, etc.)
- **Streaming Playback**: TTS audio plays incrementally as translation chunks arrive
- **Auto-play**: Automatically reads translated text aloud
- **Speed Control**: Adjustable speech rate

TTS models are loaded from the `models/tts/` directory, including embedding models (chinese-hubert-base, chinese-roberta-wwm-ext-large), G2P converters, and SoVITS models.

## Project Structure

```
Vox-Engine-Framework/
├── app.py                         # Main application entry (Flask + SocketIO)
├── funasr_asr.py                  # FunASR streaming ASR interface
├── api_engine_routes.py           # API engine routes
├── config.json                    # System configuration
├── settings.json                  # User settings (theme, TTS, translation provider)
├── requirements.txt               # Python dependencies
├── .gitignore                     # Git ignore rules
├── LICENSE                        # MIT License
├── DESIGN.md                      # Design system documentation
├── README.md                      # English documentation
├── README-CN.md                   # Chinese documentation
│
├── config/                        # Configuration files
│   ├── engines.json              # Translation engine definitions
│   ├── languages.json            # Supported languages
│   ├── translation_styles.json   # Translation style presets
│   ├── vllm_models.json          # vLLM model registry
│   ├── frp_tunnels.json          # FRP tunnel configuration
│   └── user_presets/             # User-defined presets
│
├── engines/                       # Engine module (legacy)
│   ├── __init__.py
│   ├── base_engine.py            # Base engine class
│   ├── engine_manager.py         # Engine manager
│   ├── streamspeech_engine.py    # StreamSpeech engine
│   └── traditional_engine.py     # Traditional engine
│
├── core/                          # Core modules
│
├── models/                        # Model files (not in repo, downloaded separately)
│   ├── stt/                      # Speech recognition models
│   │   ├── SenseVoiceSmall/      # FunASR SenseVoice model
│   │   └── vosk-model-small-cn-0.22/
│   ├── translate/                # Translation models
│   │   └── tencent/              # Tencent Hy-MT2 models
│   └── tts/                      # TTS models
│       ├── chinese-hubert-base/  # Hubert embedding model
│       ├── chinese-roberta-wwm-ext-large/  # RoBERTa model
│       ├── g2p/                  # Grapheme-to-phoneme
│       │   ├── en/               # English G2P
│       │   └── zh/               # Chinese G2P
│       ├── gpt/                  # GPT-based TTS
│       ├── sovits/               # SoVITS model
│       ├── s2Gv2ProPlus/         # SoVITS v2 Pro Plus
│       ├── sv/                   # Speaker verification
│       └── references/           # Reference audio samples
│
├── static/                        # Static assets
│   ├── css/
│   │   └── style.css             # Main stylesheet
│   ├── js/
│   │   └── main.js               # Main application JavaScript
│   ├── audio-processor.js        # Audio processing pipeline
│   └── icons/                    # Provider icons
│       ├── deepseek.ico
│       ├── gradio.png
│       ├── huggingface.ico
│       ├── lmstudio.ico
│       ├── modelscope.ico
│       ├── ollama.ico
│       ├── vllm.ico
│       └── vosk.ico
│
├── templates/                      # HTML templates
│   ├── index.html                # Main application page
│   ├── settings.html             # Settings page
│   ├── start.html                # Launch page
│   ├── loading.html              # Loading screen
│   ├── engine_selector.html      # Engine selector component
│   ├── language_selector.html    # Language selector component
│   ├── asr_debug.html            # ASR debug console
│   ├── translation_debug.html    # Translation debug console
│   ├── tts_debug.html            # TTS debug console
│   └── tts_only_debug.html       # Standalone TTS test
│
├── test/                          # Test suite
│   ├── test_asr_baseline.py      # ASR baseline test
│   ├── test_asr_quick.py         # Quick ASR test
│   ├── test_encoding.py          # Encoding test
│   ├── test_full_pipeline.py     # End-to-end pipeline test
│   ├── test_streaming_asr.py     # Streaming ASR test
│   ├── test_redirect.py          # Redirect test
│   ├── test_strip.py             # Text stripping test
│   └── tts_output.wav            # TTS sample output
│
├── voice_samples/                 # Recorded voice samples
├── setup.bat                      # Setup script (venv + dependencies)
├── start.bat                      # Launch script
├── stop.bat                       # Stop script
├── repair.bat                     # Repair script
└── test_streaming_asr.py          # Streaming ASR test (root level)
```

## Troubleshooting

### Common Issues

**Q: "FunASR model not loaded"**
- A: The model `SenseVoiceSmall` will be downloaded automatically on first run, or place it in `models/stt/SenseVoiceSmall/`

**Q: Microphone list is empty**
- A: Check system microphone permissions and ensure no other app is using the microphone

**Q: Translation returns empty results**
- A: Verify your translation engine is running and accessible. For LPS, check `http://localhost:8080/v1`

**Q: "Ollama service not running"**
- A: Run `ollama serve` first to start the Ollama service

**Q: Chinese path issues on Windows**
- A: The system automatically copies models to a temp directory to handle Chinese path issues

**Q: Port 5000 already in use**
- A: Change the port in `config.json` → `server.port`

### Debug Pages

The system includes dedicated debug pages for each pipeline stage:
- `/asr_debug` — Monitor raw ASR output
- `/translation_debug` — Inspect translation stream chunks
- `/tts_debug` — Debug TTS audio chunks
- `/tts_only_debug` — Standalone TTS testing

## Configuration

### config.json

The main configuration file controls system-wide settings:

```json
{
  "server": { "port": 5000 },
  "audio": { "sample_rate": 16000, "chunk_size": 4096 },
  "translation": { "default_provider": "lps" },
  "lps": {
    "backend": "openai_compatible",
    "openai_url": "http://localhost:8080/v1"
  },
  "tts": { "enabled": true, "default_model": "s2Gv2ProPlus" }
}
```

### settings.json

User-persisted settings (theme, language, TTS preferences, translation provider):

```json
{
  "theme": "dark",
  "language": "en-US",
  "translation": { "provider": "lmstudio" },
  "tts": { "voice": "en-US-JennyNeural", "streaming": true }
}
```

## Performance Optimization

1. **Use SSD storage** — Model loading is significantly faster from SSD
2. **GPU acceleration** — NVIDIA GPU with CUDA 12+ for FunASR and translation
3. **Adjust chunk size** — Smaller chunk size (2048) reduces latency, larger (8192) improves ASR accuracy
4. **Local translation** — Run LPS locally to eliminate network latency
5. **Thread pool tuning** — Adjust `performance.max_threads` in config.json

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [FunASR](https://github.com/modelscope/FunASR) — Fundamental End-to-End Speech Recognition Toolkit
- [SenseVoice](https://github.com/FunAudioLLM/SenseVoice) — Multilingual voice understanding model
- [vLLM](https://github.com/vllm-project/vllm) — High performance LLM inference engine
- [Ollama](https://ollama.com/) — Local AI model running platform
- [LM Studio](https://lmstudio.ai/) — Desktop LLM inference
- [Flask](https://flask.palletsprojects.com/) — Python web framework
- [Socket.IO](https://socket.io/) — Real-time bidirectional communication
- [GSV-TTS-Lite](https://pypi.org/project/gsv-tts-lite/) — Lightweight TTS engine
- [Vosk](https://alphacephei.com/vosk/) — Legacy ASR engine support

---

**Note**: This project is for learning and research purposes. Please comply with the license agreements of the respective AI models when using them.