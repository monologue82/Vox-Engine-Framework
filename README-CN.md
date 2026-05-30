[English](README.md) | 中文

# Vox Engine Framework

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](#)
[![GPU](https://img.shields.io/badge/GPU-CUDA-green.svg)](#)

一个功能强大的实时语音识别与翻译系统，集成 FunASR/SenseVoice 高性能离线语音识别和多种 AI 翻译引擎，支持流式输出低延迟的识别和翻译体验。

## 核心功能

- **实时语音识别** — 基于 FunASR + SenseVoiceSmall，GPU 加速流式 ASR
- **多引擎翻译** — 支持 LPS（本地处理系统）、vLLM、Ollama、LM Studio
- **流式输出** — 识别和翻译结果实时流式展示
- **文本转语音** — 基于 GSV-TTS-Lite 的流式 TTS 播放
- **流式 TTS** — 翻译结果逐块到达时增量播放，支持自动朗读
- **麦克风管理** — 多设备选择和切换
- **智能翻译批处理** — 累积 ASR 文本，根据内容长度智能触发翻译
- **序列号有序翻译** — 服务端序列编号防止乱序翻译显示
- **持久 ASR 缓存** — 跨音频块的 FunASR 缓存维护流式上下文
- **实时监控** — 识别置信度、翻译延迟、音频电平、字符数等指标
- **Web 界面** — 现代化响应式 WebUI，支持深色/浅色主题

## 技术栈

### 后端

| 组件 | 技术 |
|------|------|
| Web 框架 | Flask + Flask-SocketIO |
| 语音识别 | FunASR + SenseVoiceSmall |
| 翻译引擎 | LPS (llama.cpp / OpenAI 兼容)、vLLM、Ollama、LM Studio |
| 语音合成 | GSV-TTS-Lite（基于 Embedding 的语音克隆） |
| 异步运行时 | eventlet + threading |
| 音频处理 | PyAudio + Web Audio API |
| 缓存系统 | LRU Cache（带 TTL） |

### 前端

| 组件 | 技术 |
|------|------|
| 核心 | HTML5 + CSS3 + JavaScript |
| 实时通信 | Socket.IO |
| 音频采集 | Web Audio API (MediaStream) |
| 音频处理 | AudioWorklet + ScriptProcessor |
| 设计系统 | 自定义编辑风格，温暖色调 |

## 系统要求

### 最低配置

- **操作系统**: Windows 10/11
- **Python**: 3.11+
- **内存**: 8GB
- **存储**: 10GB 可用空间
- **GPU**: 推荐（NVIDIA 带 CUDA）

### 推荐配置

- **操作系统**: Windows 11
- **Python**: 3.13
- **内存**: 16GB+
- **GPU**: NVIDIA GPU，CUDA 12+ 支持
- **存储**: 50GB+ SSD

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/monologue82/Vox-Engine-Framework.git
cd Vox-Engine-Framework
```

### 2. 安装依赖

#### 方式一：使用安装脚本（推荐）

```bash
setup.bat
```

#### 方式二：手动安装

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
.\venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

> **注意**: 如需 CUDA 12+ GPU 加速，请单独安装 PyTorch：
> ```bash
> pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu132
> ```

### 3. 启动系统

```bash
start.bat
```

或手动启动：

```bash
.\venv\Scripts\activate
python app.py
```

### 4. 访问界面

打开浏览器访问：

- **主页面**: [http://localhost:5000/app](http://localhost:5000/app)
- **设置页面**: [http://localhost:5000/settings](http://localhost:5000/settings)

## Web 界面

系统提供以下现代化 Web 页面：

| 路由 | 页面 | 说明 |
|------|------|------|
| `/app` | 主应用 | 实时 ASR、翻译、TTS 界面 |
| `/settings` | 设置 | 麦克风、翻译引擎、TTS、主题配置 |
| `/start` | 启动页 | 系统启动和状态概览 |
| `/loading` | 加载中 | 模型加载进度显示 |
| `/asr_debug` | ASR 调试 | ASR 原始输出检查器 |
| `/translation_debug` | 翻译调试 | 翻译流检查器 |
| `/tts_debug` | TTS 调试 | TTS 流检查器 |
| `/tts_only_debug` | 仅 TTS | 独立 TTS 测试页 |

## 翻译引擎配置

### LPS（本地处理系统）— 默认引擎

系统默认使用 LPS 翻译，支持两种后端：

**OpenAI 兼容**（推荐）：连接任意 OpenAI 兼容服务器
```json
{
  "lps": {
    "backend": "openai_compatible",
    "openai_url": "http://localhost:8080/v1"
  }
}
```

**llama.cpp**：直接使用本地 GGUF 模型
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
# 系统会自动启动 vLLM 服务
```

### Ollama

1. 下载安装 [Ollama](https://ollama.com/)
2. 启动服务：`ollama serve`
3. 拉取模型：`ollama pull qwen2.5:3b`

### LM Studio

1. 下载 [LM Studio](https://lmstudio.ai/)
2. 加载模型并启动本地推理服务
3. 在 Web 界面设置中配置 API 地址

## TTS 配置

系统支持流式 TTS，具有以下特性：

- **声音选择**: 多预设语音（Jenny、Xiaoxiao、Xiaoyi 等）
- **流式播放**: TTS 音频随翻译结果逐块到达增量播放
- **自动朗读**: 自动播放翻译后的文本
- **语速控制**: 可调语音速度

TTS 模型加载自 `models/tts/` 目录，包括嵌入模型（chinese-hubert-base、chinese-roberta-wwm-ext-large）、G2P 转换器和 SoVITS 模型。

## 项目结构

```
Vox-Engine-Framework/
├── app.py                         # 主应用入口 (Flask + SocketIO)
├── funasr_asr.py                  # FunASR 流式 ASR 接口
├── api_engine_routes.py           # API 引擎路由
├── config.json                    # 系统配置
├── settings.json                  # 用户设置（主题、TTS、翻译提供商）
├── requirements.txt               # Python 依赖
├── .gitignore                     # Git 忽略规则
├── LICENSE                        # MIT 许可证
├── DESIGN.md                      # 设计系统文档
├── README.md                      # 英文文档
├── README-CN.md                   # 中文文档
│
├── config/                        # 配置文件目录
│   ├── engines.json              # 翻译引擎定义
│   ├── languages.json            # 支持的语言
│   ├── translation_styles.json   # 翻译风格预设
│   ├── vllm_models.json          # vLLM 模型注册表
│   ├── frp_tunnels.json          # FRP 隧道配置
│   └── user_presets/             # 用户自定义预设
│
├── engines/                       # 引擎模块（旧版）
│   ├── __init__.py
│   ├── base_engine.py            # 基础引擎类
│   ├── engine_manager.py         # 引擎管理器
│   ├── streamspeech_engine.py    # StreamSpeech 引擎
│   └── traditional_engine.py     # 传统引擎
│
├── core/                          # 核心模块
│
├── models/                        # 模型文件（不在仓库中，单独下载）
│   ├── stt/                      # 语音识别模型
│   │   ├── SenseVoiceSmall/      # FunASR SenseVoice 模型
│   │   └── vosk-model-small-cn-0.22/
│   ├── translate/                # 翻译模型
│   │   └── tencent/              # 腾讯 Hy-MT2 模型
│   └── tts/                      # TTS 模型
│       ├── chinese-hubert-base/  # Hubert 嵌入模型
│       ├── chinese-roberta-wwm-ext-large/  # RoBERTa 模型
│       ├── g2p/                  # 音素转换
│       │   ├── en/               # 英文 G2P
│       │   └── zh/               # 中文 G2P
│       ├── gpt/                  # GPT 基 TTS
│       ├── sovits/               # SoVITS 模型
│       ├── s2Gv2ProPlus/         # SoVITS v2 Pro Plus
│       ├── sv/                   # 说话人验证
│       └── references/           # 参考音频样本
│
├── static/                        # 静态资源
│   ├── css/
│   │   └── style.css             # 主样式表
│   ├── js/
│   │   └── main.js               # 主应用 JavaScript
│   ├── audio-processor.js        # 音频处理管道
│   └── icons/                    # 提供商图标
│       ├── deepseek.ico
│       ├── gradio.png
│       ├── huggingface.ico
│       ├── lmstudio.ico
│       ├── modelscope.ico
│       ├── ollama.ico
│       ├── vllm.ico
│       └── vosk.ico
│
├── templates/                      # HTML 模板
│   ├── index.html                # 主应用页面
│   ├── settings.html             # 设置页面
│   ├── start.html                # 启动页面
│   ├── loading.html              # 加载页面
│   ├── engine_selector.html      # 引擎选择组件
│   ├── language_selector.html    # 语言选择组件
│   ├── asr_debug.html            # ASR 调试控制台
│   ├── translation_debug.html    # 翻译调试控制台
│   ├── tts_debug.html            # TTS 调试控制台
│   └── tts_only_debug.html       # 独立 TTS 测试
│
├── test/                          # 测试套件
│   ├── test_asr_baseline.py      # ASR 基线测试
│   ├── test_asr_quick.py         # 快速 ASR 测试
│   ├── test_encoding.py          # 编码测试
│   ├── test_full_pipeline.py     # 端到端流水线测试
│   ├── test_streaming_asr.py     # 流式 ASR 测试
│   ├── test_redirect.py          # 重定向测试
│   ├── test_strip.py             # 文本剥离测试
│   └── tts_output.wav            # TTS 样本输出
│
├── voice_samples/                 # 录制的语音样本
├── setup.bat                      # 安装脚本（虚拟环境 + 依赖）
├── start.bat                      # 启动脚本
├── stop.bat                       # 停止脚本
├── repair.bat                     # 修复脚本
└── test_streaming_asr.py          # 流式 ASR 测试（根目录）
```

## 故障排除

### 常见问题

**Q: "FunASR model not loaded"**
- A: 首次运行会自动下载 `SenseVoiceSmall` 模型，或手动放入 `models/stt/SenseVoiceSmall/`

**Q: 麦克风列表为空**
- A: 检查系统麦克风权限，确保没有其他应用占用麦克风

**Q: 翻译返回空结果**
- A: 确认翻译引擎正在运行且可访问。LPS 默认地址为 `http://localhost:8080/v1`

**Q: "Ollama 服务未运行"**
- A: 先运行 `ollama serve` 启动 Ollama 服务

**Q: 中文路径问题**
- A: 系统会自动将模型复制到临时目录处理中文路径问题

**Q: 端口 5000 已被占用**
- A: 修改 `config.json` 中的 `server.port` 配置项

### 调试页面

系统为每个流水线阶段提供了专用的调试页面：
- `/asr_debug` — 监控 ASR 原始输出
- `/translation_debug` — 检查翻译流数据块
- `/tts_debug` — 调试 TTS 音频块
- `/tts_only_debug` — 独立 TTS 测试

## 配置说明

### config.json

主配置文件控制系统全局设置：

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

用户持久化设置（主题、语言、TTS 偏好、翻译提供商）：

```json
{
  "theme": "dark",
  "language": "en-US",
  "translation": { "provider": "lmstudio" },
  "tts": { "voice": "en-US-JennyNeural", "streaming": true }
}
```

## 性能优化建议

1. **使用 SSD 存储** — 模型加载速度显著提升
2. **GPU 加速** — 使用 NVIDIA GPU 带 CUDA 12+ 加速 FunASR 和翻译
3. **调整数据块大小** — 较小数据块（2048）降低延迟，较大数据块（8192）提升 ASR 准确率
4. **本地翻译** — LPS 本地运行消除网络延迟
5. **线程池调优** — 调整 config.json 中的 `performance.max_threads`

## 许可证

本项目采用 MIT 许可证 — 详见 [LICENSE](LICENSE) 文件

## 致谢

- [FunASR](https://github.com/modelscope/FunASR) — 基础端到端语音识别工具包
- [SenseVoice](https://github.com/FunAudioLLM/SenseVoice) — 多语言语音理解模型
- [vLLM](https://github.com/vllm-project/vllm) — 高性能 LLM 推理引擎
- [Ollama](https://ollama.com/) — 本地 AI 模型运行平台
- [LM Studio](https://lmstudio.ai/) — 桌面端 LLM 推理
- [Flask](https://flask.palletsprojects.com/) — Python Web 框架
- [Socket.IO](https://socket.io/) — 实时双向通信
- [GSV-TTS-Lite](https://pypi.org/project/gsv-tts-lite/) — 轻量级 TTS 引擎
- [Vosk](https://alphacephei.com/vosk/) — 旧版 ASR 引擎支持

---

**注意**: 本项目仅供学习和研究使用。使用 AI 模型时请遵守相关模型的许可协议。