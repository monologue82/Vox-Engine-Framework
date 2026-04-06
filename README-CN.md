[English](README.md) | 中文

# Vox Engine Framework

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](#)
[![GitHub Stars](https://img.shields.io/github/stars/monologue82/Vox-Engine-Framework?style=social)](https://github.com/monologue82/Vox-Engine-Framework/stargazers)

## 项目简介

This is a powerful real-time speech recognition and translation system, integrating advanced speech recognition technology and multiple AI translation engines. The system supports streaming transmission, providing low-latency real-time recognition and translation experience, along with a beautiful web interface.

这是一个功能强大的实时语音识别与翻译系统，集成了先进的语音识别技术和多种AI翻译引擎。系统支持流式传输，能够提供低延迟的实时识别和翻译体验，同时具有美观的Web界面。

## 核心功能

- **实时语音识别** - 基于Vosk的高性能离线语音识别
- **智能翻译** - 支持vLLM、Ollama、LM Studio等多种翻译引擎
- **流式传输** - 识别和翻译结果实时流式输出
- **麦克风管理** - 支持多设备选择和切换
- **模型管理** - 灵活的AI模型选择和配置
- **实时监控** - 显示识别时长、翻译时长、字符数等关键指标
- **精美界面** - 现代化WebUI设计，支持响应式布局
- **自动服务启动** - 一键启动vLLM等后端服务

## 技术栈

### 后端技术

- **框架**: Flask + Flask-SocketIO
- **语音识别**: Vosk
- **AI翻译**: vLLM / Ollama / LM Studio
- **TTS**: GSV-TTS-Lite
- **异步处理**: threading + concurrent.futures
- **缓存系统**: LRU Cache

### 前端技术

- **核心**: HTML5 + CSS3 + JavaScript
- **实时通信**: Socket.IO
- **音频处理**: Web Audio API

### 开发工具

- **依赖管理**: pip + requirements.txt
- **虚拟环境**: venv
- **脚本管理**: Windows Batch (.bat)

## 系统要求

### 最低配置

- **操作系统**: Windows 10/11
- **Python**: 3.11 或更高版本
- **内存**: 8GB RAM
- **存储空间**: 10GB 可用空间

### 推荐配置

- **操作系统**: Windows 11
- **Python**: 3.13
- **内存**: 16GB+ RAM
- **GPU**: NVIDIA GPU (支持CUDA)
- **存储空间**: 50GB+ SSD

## 快速开始

### 1. 克隆或下载项目

```bash
git clone https://github.com/monologue82/Vox-Engine-Framework.git
cd Vox-Engine-Framework
```

### 2. 安装依赖

#### 方式一：使用批处理脚本（推荐）

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

### 3. 配置翻译引擎

#### 选项A：vLLM（推荐，性能最佳）

```bash
# 安装vLLM
pip install vllm

# 系统启动时会自动启动vLLM服务
```

#### 选项B：Ollama（备选方案）

1. 下载并安装 [Ollama](https://ollama.com/)
2. 启动Ollama服务：

```bash
ollama serve
```

3. 下载翻译模型：

```bash
ollama pull llama2
# 或
ollama pull qwen2.5:7b
```

### 4. 启动系统

#### 方式一：使用批处理文件（推荐）

```bash
start.bat
```

#### 方式二：手动启动

```bash
# 激活虚拟环境
.\venv\Scripts\activate

# 运行应用
python app.py
```

### 5. 访问界面

打开浏览器，访问：`http://localhost:5001`

## 项目结构

```
Vox-Engine-Framework/
├── app.py                      # 主应用入口
├── api_engine_routes.py        # API路由
├── requirements.txt            # Python依赖
├── config.json                 # 主配置文件
├── settings.json               # 用户设置
├── .gitignore                  # Git忽略文件
├── LICENSE                     # MIT许可证
├── README.md                   # 英文说明文档
├── README-CN.md                # 中文说明文档
│
├── config/                     # 配置文件目录
│   ├── engines.json           # 引擎配置
│   ├── frp_tunnels.json       # FRP隧道配置
│   ├── languages.json         # 语言配置
│   ├── translation_styles.json # 翻译风格配置
│   └── vllm_models.json       # vLLM模型配置
│
├── core/                       # 核心模块
│   └── llama.cpp/             # llama.cpp 相关（不包含在仓库中）
│
├── engines/                    # 引擎模块
│   ├── __init__.py
│   ├── base_engine.py         # 基础引擎类
│   ├── engine_manager.py      # 引擎管理器
│   ├── streamspeech_engine.py # StreamSpeech引擎
│   └── traditional_engine.py  # 传统引擎
│
├── models/                     # 模型目录
│   ├── stt/                   # 语音识别模型
│   │   └── vosk-model-small-cn-0.22/
│   └── tts/                   # 语音合成模型
│       ├── chinese-roberta-wwm-ext-large/  # RoBERTa 模型
│       ├── g2p/               # 音素转换
│       │   ├── en/            # 英文 G2P
│       │   └── zh/            # 中文 G2P
│       ├── s2Gv2ProPlus/     # SoVITS 模型
│       └── sv/                # 说话人验证模型
│
├── static/                     # 静态资源
│   ├── css/                   # 样式文件
│   │   └── style.css
│   ├── icons/                 # 图标资源
│   └── js/                    # JavaScript文件
│       └── main.js
│
├── templates/                  # HTML模板
│   ├── index.html             # 主页面
│   ├── engine_selector.html   # 引擎选择
│   ├── language_selector.html # 语言选择
│   ├── loading.html           # 加载页面
│   ├── settings.html          # 设置页面
│   └── start.html             # 开始页面
│
├── venv/                       # Python虚拟环境（不提交）
├── setup.bat                   # 安装脚本
├── start.bat                   # 启动脚本
├── stop.bat                    # 停止脚本
└── repair.bat                  # 修复脚本
```

## 使用指南

### 基础使用流程

1. **启动系统** - 运行 `start.bat` 或 `python app.py`
2. **选择设备** - 在Web界面中选择麦克风设备
3. **选择模型** - 选择语音识别模型和翻译模型
4. **开始识别** - 点击"开始识别"按钮
5. **实时翻译** - 开始说话，系统会实时显示识别和翻译结果
6. **停止识别** - 点击"停止识别"按钮结束

### 翻译引擎选择

| 引擎 | 特点 | 推荐场景 |
|------|------|----------|
| **vLLM** | 高性能、低延迟、支持连续批处理 | 生产环境、需要最佳性能 |
| **Ollama** | 简单易用、支持多种模型 | 开发测试、个人使用 |
| **LM Studio** | 图形化界面、模型管理方便 | 桌面应用场景 |

## 配置说明

### 主配置文件 (config.json)

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

### 环境变量

- `PYTORCH_CUDA_ALLOC_CONF`: PyTorch内存分配配置（默认：`expandable_segments:True`）

## 故障排除

### 常见问题

**Q: 提示 "Ollama 服务未运行"**
- A: 请先运行 `ollama serve` 启动Ollama服务

**Q: 无法加载语音识别模型**
- A: 检查 `models/stt/vosk-model-small-cn-0.22` 目录是否存在

**Q: 麦克风列表为空**
- A: 检查系统麦克风是否正常工作，并确保应用程序有麦克风权限

**Q: 翻译模型列表为空**
- A: 确保已下载对应模型（如 `ollama pull <模型名>`）

**Q: 中文路径问题**
- A: 系统会自动将模型复制到临时目录处理中文路径问题

### 日志和调试

应用运行时会在控制台输出详细的日志信息，包括：
- 模型加载状态
- 服务连接状态
- 识别和翻译进度
- 错误和警告信息

## 性能优化建议

1. **使用SSD存储** - 将模型和系统放在SSD上可以大幅提升加载速度
2. **GPU加速** - 使用支持CUDA的NVIDIA GPU运行vLLM
3. **合理配置模型** - 根据硬件选择合适大小的模型
4. **网络优化** - vLLM服务建议本地运行以减少网络延迟

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=monologue82/Vox-Engine-Framework&type=Date)](https://star-history.com/#monologue82/Vox-Engine-Framework&Date)

## 贡献指南

我们欢迎各种形式的贡献！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 致谢

- [Vosk](https://alphacephei.com/vosk/) - 开源语音识别引擎
- [vLLM](https://github.com/vllm-project/vllm) - 高性能LLM推理引擎
- [Ollama](https://ollama.com/) - 本地AI模型运行平台
- [Flask](https://flask.palletsprojects.com/) - Python Web框架
- [GSV-TTS-Lite](https://pypi.org/project/gsv-tts-lite/) - 轻量级TTS引擎

## 联系方式

如有问题或建议，欢迎通过以下方式联系：

- 提交 Issue
- 发送 Pull Request
- 在 [哔哩哔哩](https://space.bilibili.com/1741551557) 关注我

---

**注意**: 本项目仅供学习和研究使用。使用AI模型时请遵守相关模型的许可协议。
