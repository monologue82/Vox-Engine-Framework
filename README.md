English | [中文](README-CN.md)

# Vox Engine Framework

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](#)

## 📖 Project Introduction

This is a powerful real-time speech recognition and translation system, integrating advanced speech recognition technology and multiple AI translation engines. The system supports streaming transmission, providing low-latency real-time recognition and translation experience, along with a beautiful web interface.

## ✨ Core Features

- 🎯 **Real-time Speech Recognition** - High-performance offline speech recognition based on Vosk
- 🔄 **Intelligent Translation** - Supports multiple translation engines including vLLM, Ollama, LM Studio
- ⚡ **Streaming Transmission** - Real-time streaming output of recognition and translation results
- 🎙️ **Microphone Management** - Supports multi-device selection and switching
- 🤖 **Model Management** - Flexible AI model selection and configuration
- 📊 **Real-time Monitoring** - Displays key metrics such as recognition duration, translation duration, character count
- 🎨 **Beautiful Interface** - Modern WebUI design with responsive layout
- 🔌 **Automatic Service Startup** - One-click startup of backend services like vLLM

## 🛠️ Technology Stack

### Backend Technologies
- **Framework**: Flask + Flask-SocketIO
- **Speech Recognition**: Vosk
- **AI Translation**: vLLM / Ollama / LM Studio
- **TTS**: GSV-TTS-Lite
- **Asynchronous Processing**: threading + concurrent.futures
- **Cache System**: LRU Cache

### Frontend Technologies
- **Core**: HTML5 + CSS3 + JavaScript
- **Real-time Communication**: Socket.IO
- **Audio Processing**: Web Audio API

### Development Tools
- **Dependency Management**: pip + requirements.txt
- **Virtual Environment**: venv
- **Script Management**: Windows Batch (.bat)

## 📋 System Requirements

### Minimum Requirements
- **Operating System**: Windows 10/11
- **Python**: 3.11 or higher
- **Memory**: 8GB RAM
- **Storage**: 10GB available space

### Recommended Requirements
- **Operating System**: Windows 11
- **Python**: 3.13
- **Memory**: 16GB+ RAM
- **GPU**: NVIDIA GPU (CUDA supported)
- **Storage**: 50GB+ SSD

## 🚀 Quick Start

### 1. Clone or Download the Project

```bash
git clone https://github.com/monologue82/Vox-Engine-Framework.git
cd Vox-Engine-Framework
```

### 2. Install Dependencies

#### Method 1: Using Batch Script (Recommended)
```bash
setup.bat
```

#### Method 2: Manual Installation
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Translation Engine

#### Option A: vLLM (Recommended, Best Performance)
```bash
# Install vLLM
pip install vllm

# The system will automatically start vLLM service when it starts
```

#### Option B: Ollama (Alternative)
1. Download and install [Ollama](https://ollama.com/)
2. Start Ollama service:
```bash
ollama serve
```
3. Download translation model:
```bash
ollama pull llama2
# or
ollama pull qwen2.5:7b
```

### 4. Start the System

#### Method 1: Using Batch File (Recommended)
```bash
start.bat
```

#### Method 2: Manual Startup
```bash
# Activate virtual environment
.\venv\Scripts\activate

# Run the application
python app.py
```

### 5. Access the Interface

Open your browser and visit: `http://localhost:5001`

## 📁 Project Structure

```
Vox-Engine-Framework/
├── app.py                      # Main application entry
├── api_engine_routes.py        # API routes
├── requirements.txt            # Python dependencies
├── config.json                 # Main configuration file
├── settings.json               # User settings
├── .gitignore                  # Git ignore file
├── LICENSE                     # MIT License
├── README.md                   # English documentation
├── README-CN.md                # Chinese documentation
│
├── config/                     # Configuration files directory
│   ├── engines.json           # Engine configuration
│   ├── frp_tunnels.json       # FRP tunnel configuration
│   ├── languages.json         # Language configuration
│   ├── translation_styles.json # Translation style configuration
│   └── vllm_models.json       # vLLM model configuration
│
├── core/                       # Core modules
│   └── llama.cpp/             # llama.cpp related (not included in repository)
│
├── engines/                    # Engine modules
│   ├── __init__.py
│   ├── base_engine.py         # Base engine class
│   ├── engine_manager.py      # Engine manager
│   ├── streamspeech_engine.py # StreamSpeech engine
│   └── traditional_engine.py  # Traditional engine
│
├── models/                     # Models directory
│   ├── stt/                   # Speech recognition models
│   │   └── vosk-model-small-cn-0.22/
│   └── tts/                   # Text-to-speech models
│       ├── chinese-roberta-wwm-ext-large/  # RoBERTa model
│       ├── g2p/               # Grapheme-to-phoneme
│       │   ├── en/            # English G2P
│       │   └── zh/            # Chinese G2P
│       ├── s2Gv2ProPlus/     # SoVITS model
│       └── sv/                # Speaker verification model
│
├── static/                     # Static resources
│   ├── css/                   # Style files
│   │   └── style.css
│   ├── icons/                 # Icon resources
│   └── js/                    # JavaScript files
│       └── main.js
│
├── templates/                  # HTML templates
│   ├── index.html             # Main page
│   ├── engine_selector.html   # Engine selector
│   ├── language_selector.html # Language selector
│   ├── loading.html           # Loading page
│   ├── settings.html          # Settings page
│   └── start.html             # Start page
│
├── venv/                       # Python virtual environment (not committed)
├── setup.bat                   # Installation script
├── start.bat                   # Startup script
├── stop.bat                    # Stop script
└── repair.bat                  # Repair script
```

## 💡 Usage Guide

### Basic Usage Flow

1. **Start the system** - Run `start.bat` or `python app.py`
2. **Select device** - Select microphone device in the web interface
3. **Select model** - Choose speech recognition model and translation model
4. **Start recognition** - Click "Start Recognition" button
5. **Real-time translation** - Start speaking, the system will display recognition and translation results in real-time
6. **Stop recognition** - Click "Stop Recognition" button to end

### Translation Engine Selection

| Engine | Features | Recommended Scenarios |
|--------|----------|------------------------|
| **vLLM** | High performance, low latency, continuous batching support | Production environments, best performance required |
| **Ollama** | Easy to use, supports multiple models | Development testing, personal use |
| **LM Studio** | Graphical interface, convenient model management | Desktop application scenarios |

## ⚙️ Configuration

### Main Configuration File (config.json)

```json
{
  "vllm": {
    "auto_start": true
  },
  "translation": {
    "auto_start_vllm": true
  },
  "llama_cpp": {
    "version": "auto",
    "model_path": ""
  }
}
```

### Environment Variables

- `PYTORCH_CUDA_ALLOC_CONF`: PyTorch memory allocation configuration (default: `expandable_segments:True`)

## 🔧 Troubleshooting

### Common Issues

**Q: Getting "Ollama service not running"**
- A: Please run `ollama serve` first to start Ollama service

**Q: Cannot load speech recognition model**
- A: Check if `models/stt/vosk-model-small-cn-0.22` directory exists

**Q: Microphone list is empty**
- A: Check if system microphone is working properly and ensure the application has microphone permissions

**Q: Translation model list is empty**
- A: Ensure you have downloaded the corresponding model (e.g., `ollama pull <model_name>`)

**Q: Chinese path issues**
- A: The system will automatically copy models to a temporary directory to handle Chinese path issues

### Logs and Debugging

The application outputs detailed log information in the console while running, including:
- Model loading status
- Service connection status
- Recognition and translation progress
- Error and warning messages

## 📈 Performance Optimization Tips

1. **Use SSD Storage** - Placing models and system on SSD can significantly improve loading speed
2. **GPU Acceleration** - Use NVIDIA GPU with CUDA support to run vLLM
3. **Proper Model Configuration** - Choose appropriate model size based on your hardware
4. **Network Optimization** - vLLM service is recommended to run locally to reduce network latency

## 🤝 Contributing

We welcome contributions of all kinds!

1. Fork this repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details

## 🙏 Acknowledgments

- [Vosk](https://alphacephei.com/vosk/) - Open source speech recognition engine
- [vLLM](https://github.com/vllm-project/vllm) - High performance LLM inference engine
- [Ollama](https://ollama.com/) - Local AI model running platform
- [Flask](https://flask.palletsprojects.com/) - Python Web framework
- [GSV-TTS-Lite](https://pypi.org/project/gsv-tts-lite/) - Lightweight TTS engine

## 📞 Contact

For questions or suggestions, please contact us through:

- Submit an Issue
- Send a Pull Request
- Follow me on [Bilibili](https://space.bilibili.com/1741551557)

---

**Note**: This project is for learning and research purposes only. Please comply with the license agreements of the respective AI models when using them.
