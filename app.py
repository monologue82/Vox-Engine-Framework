import warnings
# Filter out FutureWarning about pynvml deprecation
warnings.filterwarnings("ignore", category=FutureWarning, message="The pynvml package is deprecated")

import os
os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'
import sys
import json
import time
import threading
import queue
import wave
import io
import socket
import struct
import asyncio
import tempfile
import numpy as np
import re
from datetime import datetime
from collections import OrderedDict
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, session, redirect
from flask_socketio import SocketIO, emit
import pyaudio
import vosk
import requests

# Auto-download NLTK cmudict for TTS
try:
    import nltk
    try:
        nltk.data.find('corpora/cmudict')
    except LookupError:
        print("Downloading NLTK cmudict (required for TTS)...")
        nltk.download('cmudict', quiet=True)
        print("NLTK cmudict downloaded successfully.")
except Exception as e:
    print(f"Warning: Could not download NLTK cmudict: {e}")
    print("TTS may not work properly until cmudict is downloaded.")

# 彩色控制台输出类
class ConsoleColor:
    # ANSI颜色代码
    RESET = '\033[0m'
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # 背景色
    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_WHITE = '\033[47m'
    
    # 样式
    BOLD = '\033[1m'
    ITALIC = '\033[3m'
    UNDERLINE = '\033[4m'
    
    @classmethod
    def colorize(cls, text, color, bold=False, underline=False):
        """为文本添加颜色"""
        # 检查是否为Windows系统
        if sys.platform == 'win32':
            # Windows 10+ 支持ANSI颜色
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        
        style = ''
        if bold:
            style += cls.BOLD
        if underline:
            style += cls.UNDERLINE
        
        return f"{style}{color}{text}{cls.RESET}"
    
    @classmethod
    def success(cls, text):
        """成功信息"""
        return cls.colorize(f"[SUCCESS] {text}", cls.GREEN, bold=True)
    
    @classmethod
    def error(cls, text):
        """错误信息"""
        return cls.colorize(f"[ERROR] {text}", cls.RED, bold=True)
    
    @classmethod
    def warning(cls, text):
        """警告信息"""
        return cls.colorize(f"[WARNING] {text}", cls.YELLOW, bold=True)
    
    @classmethod
    def info(cls, text):
        """信息"""
        return cls.colorize(text, cls.BLUE)
    
    @classmethod
    def highlight(cls, text):
        """高亮信息"""
        return cls.colorize(text, cls.MAGENTA, bold=True)
    
    @classmethod
    def debug(cls, text):
        """调试信息"""
        return cls.colorize(text, cls.CYAN)
    
    @classmethod
    def title(cls, text):
        """标题"""
        return cls.colorize(text, cls.WHITE, bold=True, underline=True)

# edge-tts is removed, only GSV-TTS-Lite is used
TTS_AVAILABLE = False
print(ConsoleColor.warning("edge-tts is disabled. Only GSV-TTS-Lite is available."))

# TTS (Coqui) is not compatible with Python 3.13
# Using edge-tts and gsv-tts-lite as alternatives
VOICE_CLONE_AVAILABLE = False
voice_clone_tts = None
print(ConsoleColor.warning("TTS (Coqui) not available for Python 3.13. Using edge-tts and gsv-tts-lite as alternatives."))

try:
    from gsv_tts import TTS as GSVTTS
    GSV_TTS_AVAILABLE = True
    gsv_tts = None
except ImportError:
    GSV_TTS_AVAILABLE = False
    print(ConsoleColor.warning("gsv-tts-lite not installed. GSV-TTS-Lite features will be disabled."))

# Windows 适配：设置控制台编码
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key'
# Windows 适配：使用 threading 模式，更稳定
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode='threading', 
    ping_timeout=60, 
    ping_interval=25,
    max_http_buffer_size=10 * 1024 * 1024,  # 10MB buffer
    async_handlers=True,  # Enable async handlers
    logger=False,  # Disable logging for performance
    engineio_logger=False  # Disable engine.io logging
)

# Configuration
# Windows adaptation: Use absolute paths to avoid encoding issues
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
VOSK_MODELS_DIR = os.path.abspath(os.path.join(BASE_DIR, 'models', 'stt'))
DEFAULT_MODEL_PATH = os.path.abspath(os.path.join(BASE_DIR, 'models', 'stt', 'vosk-model-small-cn-0.22'))

# Load main config.json
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
def load_config():
    """Load main configuration from config.json"""
    default_config = {
        'vllm': {'auto_start': True},
        'translation': {'auto_start_vllm': True},
        'llama_cpp': {
            'version': 'auto',
            'model_path': ''
        }
    }
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                print(ConsoleColor.success(f"✓ Loaded config from {CONFIG_FILE}"))
                return config
        else:
            print(ConsoleColor.warning(f"Config file not found: {CONFIG_FILE}, using defaults"))
            return default_config
    except Exception as e:
        print(ConsoleColor.error(f"Failed to load config: {e}, using defaults"))
        return default_config

APP_CONFIG = load_config()

def save_config(config):
    """Save configuration to config.json"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(ConsoleColor.success(f"✓ Saved config to {CONFIG_FILE}"))
        return True
    except Exception as e:
        print(ConsoleColor.error(f"Failed to save config: {e}"))
        return False

# Language configuration
LANGUAGES_FILE = os.path.join(BASE_DIR, 'config', 'languages.json')
default_language = 'zh-CN'

# Load languages
def load_languages():
    try:
        with open(LANGUAGES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(ConsoleColor.error(f"Failed to load languages: {e}"))
        return {}

languages = load_languages()

# Get text function for i18n
def get_text(key, lang=None):
    if not lang:
        lang = session.get('language', default_language)
    
    try:
        keys = key.split('.')
        value = languages.get(lang, {})
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return key
        return value
    except Exception as e:
        print(ConsoleColor.error(f"Error getting text: {e}"))
        return key

# TTS模型目录配置 - 所有模型文件存放在项目目录下
TTS_MODELS_DIR = os.path.abspath(os.path.join(BASE_DIR, 'models', 'tts'))
TTS_GPT_DIR = os.path.join(TTS_MODELS_DIR, 'gpt')
TTS_SOVITS_DIR = os.path.join(TTS_MODELS_DIR, 'sovits')
TTS_REFERENCES_DIR = os.path.join(TTS_MODELS_DIR, 'references')

# 创建TTS模型目录
for tts_dir in [TTS_MODELS_DIR, TTS_GPT_DIR, TTS_SOVITS_DIR, TTS_REFERENCES_DIR]:
    if not os.path.exists(tts_dir):
        os.makedirs(tts_dir)
        print(ConsoleColor.info(f"Created TTS directory: {tts_dir}"))

OLLAMA_URL = 'http://localhost:11434'
VLLM_URL = 'http://localhost:8000'  # vLLM default port

# Global flags for service availability
VLLM_AVAILABLE = False
GSV_TTS_AVAILABLE = False

SAMPLE_RATE = 16000
CHUNK_SIZE = 8192  # Increased for better throughput
AUDIO_LEVEL_INTERVAL = 100  # Reduced from 60 for less overhead
PARTIAL_UPDATE_INTERVAL = 0.1  # Reduced from 0.15 for faster response
MIN_TRANSLATION_INTERVAL = 0.2  # Reduced from 0.3 for faster translations
MIN_CHARS_FOR_TRANSLATION = 4  # Reduced from 5 for faster trigger

# Optimized HTTP session for connection pooling
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
http_session = requests.Session()
http_adapter = requests.adapters.HTTPAdapter(
    pool_connections=10,
    pool_maxsize=20,
    max_retries=0,
    pool_block=False
)
http_session.mount('http://', http_adapter)
http_session.mount('https://', http_adapter)

VOICE_CLONE_DIR = os.path.join(BASE_DIR, 'voice_samples')
if not os.path.exists(VOICE_CLONE_DIR):
    os.makedirs(VOICE_CLONE_DIR)

ALLOWED_AUDIO_EXTENSIONS = {'.wav', '.mp3', '.ogg', '.flac', '.m4a'}
MAX_AUDIO_SIZE = 10 * 1024 * 1024

# LRU Cache implementation with OrderedDict for O(1) operations
class LRUCache:
    def __init__(self, capacity, max_memory_mb=None, default_ttl=None):
        """
        Initialize LRU Cache with memory and TTL support
        
        Args:
            capacity: Maximum number of entries
            max_memory_mb: Maximum memory usage in MB (optional)
            default_ttl: Default time-to-live in seconds (optional)
        """
        self.capacity = capacity
        self.cache = OrderedDict()  # key: (value, timestamp, size)
        self.max_memory = max_memory_mb * 1024 * 1024 if max_memory_mb else None
        self.default_ttl = default_ttl
        self.current_memory = 0
        self.last_cleanup = time.time()
        self.cleanup_interval = 3600  # Cleanup every hour
        self.access_count = 0
        self.hit_count = 0
    
    def get(self, key):
        """Get value from cache with O(1) complexity"""
        self.access_count += 1
        
        if key not in self.cache:
            return None
        
        value, timestamp, size = self.cache[key]
        
        # Check TTL
        if self.default_ttl and time.time() - timestamp > self.default_ttl:
            self.current_memory -= size
            del self.cache[key]
            return None
        
        # Move to end (most recently used) - O(1) with OrderedDict
        self.cache.move_to_end(key)
        self.hit_count += 1
        return value
    
    def put(self, key, value):
        """Put value into cache with O(1) complexity"""
        self._periodic_cleanup()
        
        # Calculate size for memory tracking
        try:
            size = len(value) if isinstance(value, (bytes, bytearray, str)) else sys.getsizeof(value)
        except:
            size = 0
        
        # Remove old entry if exists
        if key in self.cache:
            old_size = self.cache[key][2]
            self.current_memory -= old_size
        
        # Add new entry with timestamp
        self.cache[key] = (value, time.time(), size)
        self.current_memory += size
        self.cache.move_to_end(key)
        
        # Evict by count
        while len(self.cache) > self.capacity:
            self._evict_lru()
        
        # Evict by memory if needed
        if self.max_memory:
            while self.current_memory > self.max_memory and len(self.cache) > 1:
                self._evict_lru()
    
    def _evict_lru(self):
        """Evict least recently used entry - O(1) with OrderedDict"""
        if not self.cache:
            return
        key, (value, _, size) = self.cache.popitem(last=False)
        self.current_memory -= size
    
    def _periodic_cleanup(self):
        """Periodic cleanup to remove expired entries"""
        current_time = time.time()
        if current_time - self.last_cleanup > self.cleanup_interval:
            if self.default_ttl:
                # Remove expired entries
                expired = [
                    k for k, (v, ts, _) in self.cache.items()
                    if current_time - ts > self.default_ttl
                ]
                for k in expired:
                    self.current_memory -= self.cache[k][2]
                    del self.cache[k]
            
            self.last_cleanup = current_time
    
    def clear(self):
        """Clear all cache entries"""
        self.cache.clear()
        self.current_memory = 0
        self.hit_count = 0
        self.access_count = 0
    
    def __contains__(self, key):
        """Check if key exists in cache"""
        return key in self.cache
    
    def get_stats(self):
        """Get cache statistics"""
        hit_rate = (self.hit_count / self.access_count * 100) if self.access_count > 0 else 0
        return {
            'entries': len(self.cache),
            'memory_mb': round(self.current_memory / (1024 * 1024), 2),
            'memory_limit_mb': round(self.max_memory / (1024 * 1024), 2) if self.max_memory else None,
            'hit_rate': round(hit_rate, 2),
            'access_count': self.access_count,
            'hit_count': self.hit_count
        }

# Configuration paths
CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'config')
TRANSLATION_STYLES_FILE = os.path.join(CONFIG_DIR, 'translation_styles.json')
USER_PRESETS_DIR = os.path.join(CONFIG_DIR, 'user_presets')

# Global variables
model = None
current_model_path = None
is_processing = False
audio_queue = queue.Queue()
processing_thread = None
pyaudio_instance = None
translation_cache = LRUCache(150)  # Further reduced for faster lookup
MAX_CACHE_SIZE = 150
current_translation_style = ''  # Global variable to store current translation style
current_translation_prompt = ''  # Store optimized translation prompt
OLLAMA_AVAILABLE = True  # Global flag for Ollama availability
pending_translations = set()  # Track pending translations to avoid duplicates

# Load translation styles
translation_styles = {"presets": []}
try:
    if os.path.exists(TRANSLATION_STYLES_FILE):
        with open(TRANSLATION_STYLES_FILE, 'r', encoding='utf-8') as f:
            translation_styles = json.load(f)
    else:
        print(f"Translation styles file not found at: {TRANSLATION_STYLES_FILE}")
except Exception as e:
    print(f"Error loading translation styles: {e}")

# Windows 适配：检查端口是否被占用
def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def detect_llama_cpp_version():
    """自动检测适合的llama.cpp版本"""
    import platform
    import subprocess
    
    system = platform.system().lower()
    
    # 检查是否有CUDA支持
    has_cuda = False
    try:
        # 尝试运行nvidia-smi命令检查CUDA
        result = subprocess.run(['nvidia-smi'], capture_output=True, text=True, timeout=5)
        has_cuda = result.returncode == 0
    except:
        pass
    
    # 检查是否有Metal支持 (Mac)
    has_metal = False
    if system == 'darwin':
        has_metal = True
    
    # 根据环境推荐版本
    if has_cuda:
        return 'cuda'
    elif has_metal:
        return 'metal'
    else:
        return 'cpu'

def get_llama_cpp_version():
    """获取当前配置的llama.cpp版本"""
    global APP_CONFIG
    version = APP_CONFIG.get('llama_cpp', {}).get('version', 'auto')
    if version == 'auto':
        return detect_llama_cpp_version()
    return version

# Check if path contains non-ASCII characters
def has_non_ascii(path):
    try:
        path.encode('ascii')
        return False
    except UnicodeEncodeError:
        return True

# Copy model to temp directory to avoid Chinese path issues
def copy_model_to_temp(source_path):
    import shutil
    temp_base = os.path.join(os.environ.get('TEMP', '/tmp'), 'vosk_models')
    if not os.path.exists(temp_base):
        os.makedirs(temp_base)
    
    model_name = os.path.basename(source_path)
    dest_path = os.path.join(temp_base, model_name)
    
    if os.path.exists(dest_path):
        print(ConsoleColor.info(f"Using cached model in: {dest_path}"))
        return dest_path
    
    print(ConsoleColor.info(f"Copying model from {source_path} to {dest_path}"))
    try:
        shutil.copytree(source_path, dest_path)
        print(ConsoleColor.success("Model copied successfully"))
        return dest_path
    except Exception as e:
        print(ConsoleColor.error(f"Failed to copy model: {e}"))
        return None

# Get available vosk models
def get_vosk_models():
    models = []
    try:
        if os.path.exists(VOSK_MODELS_DIR):
            for item in os.listdir(VOSK_MODELS_DIR):
                model_path = os.path.join(VOSK_MODELS_DIR, item)
                if os.path.isdir(model_path):
                    # Check if it's a valid vosk model (contains am/conf/graph folders)
                    required_dirs = ['am', 'conf', 'graph']
                    if all(os.path.exists(os.path.join(model_path, d)) for d in required_dirs):
                        # Check for Chinese path issue
                        final_path = os.path.abspath(model_path)
                        if has_non_ascii(final_path):
                            # Note: We'll handle Chinese paths when loading the model
                            pass
                        
                        models.append({
                            'name': item,
                            'path': final_path
                        })
            print(ConsoleColor.success(f"Found {len(models)} Vosk models"))
        else:
            print(ConsoleColor.error(f"Vosk models directory does not exist: {VOSK_MODELS_DIR}"))
    except Exception as e:
        print(ConsoleColor.error(f"Failed to get Vosk models: {e}"))
    return models

# Initialize vosk model
def load_model(model_path=None):
    global model, current_model_path
    try:
        if model_path is None:
            model_path = DEFAULT_MODEL_PATH
        
        # Convert to absolute path to avoid encoding issues
        model_path = os.path.abspath(model_path)
        
        # Verify model directory exists
        if not os.path.exists(model_path):
            print(ConsoleColor.error(f"Vosk model path does not exist: {model_path}"))
            return False
        
        # Verify it's a valid model directory
        required_files = ['am/final.mdl', 'conf/mfcc.conf']
        for req_file in required_files:
            if not os.path.exists(os.path.join(model_path, req_file)):
                print(ConsoleColor.error(f"Invalid model directory: missing {req_file}"))
                return False
        
        # Check for Chinese path issue
        if has_non_ascii(model_path):
            print(ConsoleColor.warning(f"Model path contains non-ASCII characters: {model_path}"))
            print(ConsoleColor.info("Vosk library does not support Chinese paths. Copying model to temp directory..."))
            model_path = copy_model_to_temp(model_path)
            if model_path is None:
                return False
        
        # Try to load the model
        print(ConsoleColor.info(f"Loading Vosk model from: {model_path}"))
        model = vosk.Model(model_path)
        current_model_path = model_path
        print(ConsoleColor.success("Vosk model loaded successfully"))
        return True
        
    except Exception as e:
        print(ConsoleColor.error(f"Failed to load Vosk model: {e}"))
        print(ConsoleColor.info(f"  Model path: {model_path}"))
        return False

# Get microphone list (Windows optimized version)
def get_microphones():
    global pyaudio_instance
    mics = []
    try:
        p = pyaudio.PyAudio()
        pyaudio_instance = p
        
        for i in range(p.get_device_count()):
            try:
                info = p.get_device_info_by_index(i)
                # Windows adaptation: Check if it's an input device
                if info['maxInputChannels'] > 0:
                    mics.append({
                        'index': i,
                        'name': info['name'],
                        'channels': info['maxInputChannels'],
                        'sample_rate': int(info['defaultSampleRate'])
                    })
            except Exception as e:
                print(ConsoleColor.warning(f"Cannot get device {i} info: {e}"))
                continue
        
        print(ConsoleColor.success(f"Found {len(mics)} microphone devices"))
        return mics
    except Exception as e:
        print(ConsoleColor.error(f"Failed to get microphone list: {e}"))
        return []

# Get Ollama model list
def get_ollama_models():
    try:
        response = requests.get(f'{OLLAMA_URL}/api/tags', timeout=5)
        if response.status_code == 200:
            data = response.json()
            return [model['name'] for model in data.get('models', [])]
    except Exception as e:
        print(ConsoleColor.error(f"Failed to get Ollama models: {e}"))
    return []

# Get vLLM model list
def get_vllm_models():
    """Get available models from vLLM server"""
    try:
        response = requests.get(f'{VLLM_URL}/v1/models', timeout=5)
        if response.status_code == 200:
            data = response.json()
            models = [model['id'] for model in data.get('data', [])]
            if models:
                return models
    except Exception as e:
        print(ConsoleColor.warning(f"vLLM not available: {e}"))
    return []


# vLLM Model Management
VLLM_MODELS_DIR = os.path.join(BASE_DIR, 'models', 'llm')
VLLM_DOWNLOAD_PROGRESS = {}  # Track download progress

# Ensure directory exists
if not os.path.exists(VLLM_MODELS_DIR):
    os.makedirs(VLLM_MODELS_DIR)
    print(ConsoleColor.info(f"Created vLLM models directory: {VLLM_MODELS_DIR}"))


def get_local_vllm_models(models_dir=None):
    """
    Get list of locally available vLLM models.
    
    Scans the models/llm directory for downloaded models.
    Returns list of model info dicts with name and path.
    """
    if models_dir is None:
        models_dir = VLLM_MODELS_DIR
    
    models = []
    if not os.path.exists(models_dir):
        return models
    
    # Scan directory for model folders
    for item in os.listdir(models_dir):
        item_path = os.path.join(models_dir, item)
        if os.path.isdir(item_path):
            # Check if it looks like a valid model directory
            # (contains config.json or similar)
            if os.path.exists(os.path.join(item_path, 'config.json')) or \
               os.path.exists(os.path.join(item_path, 'model.safetensors')) or \
               os.path.exists(os.path.join(item_path, 'pytorch_model.bin')):
                models.append({
                    'name': item,
                    'path': item_path,
                    'size': get_dir_size(item_path),
                    'modified': datetime.fromtimestamp(os.path.getmtime(item_path)).isoformat()
                })
    
    return sorted(models, key=lambda x: x['name'])

def get_gguf_models():
    """
    Get list of locally available GGUF models for llama.cpp.
    
    Recursively scans the models directory for GGUF model files.
    Returns list of model info dicts with name and path.
    """
    MODELS_DIR = os.path.join(BASE_DIR, 'models')
    models = []
    
    if not os.path.exists(MODELS_DIR):
        return models
    
    # Recursively walk through models directory to find GGUF files
    for root, dirs, files in os.walk(MODELS_DIR):
        for item in files:
            if item.endswith('.gguf'):
                item_path = os.path.join(root, item)
                # Get relative path from models directory for display
                relative_path = os.path.relpath(item_path, MODELS_DIR)
                models.append({
                    'name': item,
                    'path': item_path,
                    'relative_path': relative_path,
                    'size': get_dir_size(item_path),
                    'modified': datetime.fromtimestamp(os.path.getmtime(item_path)).isoformat()
                })
    
    return sorted(models, key=lambda x: x['name'])


def get_dir_size(path):
    """Get directory or file size in human readable format."""
    total = 0
    if os.path.isfile(path):
        total = os.path.getsize(path)
    else:
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.exists(fp):
                    total += os.path.getsize(fp)
    
    # Convert to human readable
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if total < 1024.0:
            return f"{total:.2f} {unit}"
        total /= 1024.0
    return f"{total:.2f} PB"


def get_recommended_vllm_models():
    """Get list of recommended vLLM models for translation, organized by vendor.
    
    Reads model configuration from config/vllm_models.json file.
    Falls back to empty dict if file not found.
    """
    config_path = os.path.join(BASE_DIR, 'config', 'vllm_models.json')
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get('vendors', {})
    except Exception as e:
        print(ConsoleColor.warning(f"Failed to load vLLM models config: {e}"))
    
    return {}


# Get GPU information
def get_gpu_info():
    """Get GPU memory and utilization info using pynvml or fallback methods"""
    try:
        import pynvml
        try:
            pynvml.nvmlInit()
            device_count = pynvml.nvmlDeviceGetCount()
            
            if device_count > 0:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                
                # Get memory info
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                vram_total_gb = round(mem_info.total / (1024 ** 3), 2)
                vram_used_gb = round(mem_info.used / (1024 ** 3), 2)
                vram_percent = round((mem_info.used / mem_info.total) * 100, 1)
                
                # Get utilization
                try:
                    utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    gpu_util = utilization.gpu
                except:
                    gpu_util = 0
                
                pynvml.nvmlShutdown()
                
                return {
                    'available': True,
                    'vram_total_gb': vram_total_gb,
                    'vram_used_gb': vram_used_gb,
                    'vram_percent': vram_percent,
                    'gpu_util_percent': gpu_util
                }
            else:
                return {'available': False}
        except Exception as e:
            return {'available': False, 'error': str(e)}
    except ImportError:
        # Try using torch.cuda if pynvml is not available
        try:
            import torch
            if torch.cuda.is_available():
                mem_allocated = round(torch.cuda.memory_allocated(0) / (1024 ** 3), 2)
                mem_reserved = round(torch.cuda.memory_reserved(0) / (1024 ** 3), 2)
                mem_total_gb = round(torch.cuda.get_device_properties(0).total_memory / (1024 ** 3), 2)
                vram_percent = round((mem_allocated / mem_total_gb) * 100, 1)
                
                return {
                    'available': True,
                    'vram_total_gb': mem_total_gb,
                    'vram_used_gb': mem_allocated,
                    'vram_reserved_gb': mem_reserved,
                    'vram_percent': vram_percent,
                    'gpu_util_percent': 0  # torch doesn't provide utilization
                }
            else:
                return {'available': False}
        except:
            return {'available': False}


# Check vLLM health
def check_vllm_health():
    """Check if vLLM server is running"""
    try:
        response = requests.get(f'{VLLM_URL}/health', timeout=2)
        return response.status_code == 200
    except:
        return False

# Speech recognition processing thread (Windows optimized version)
def process_audio_stream(mic_index, model_name, provider='ollama', translation_style='', preset_id=None):
    global is_processing, model
    
    p = None
    stream = None
    
    try:
        # Windows adaptation: Create new PyAudio instance
        p = pyaudio.PyAudio()
        
        # Windows adaptation: Ultra-low latency audio stream with better stability
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            input_device_index=mic_index,
            frames_per_buffer=CHUNK_SIZE,
            input_host_api_specific_stream_info=None,
            stream_callback=None
        )
        
        # Start the stream
        stream.start_stream()
        
        # Create recognizer with optimized parameters for ultra-fast recognition
        rec = vosk.KaldiRecognizer(model, SAMPLE_RATE)
        rec.SetWords(True)  # Enable word-level recognition for faster results
        rec.SetPartialWords(True)  # Enable partial word results
        
        socketio.emit('status', {'status': 'listening', 'message': 'Listening...'})
        
        start_time = time.time()
        all_text = ""
        segment_count = 0
        last_emit_time = time.time()
        last_translation_text = ""
        partial_text = ""
        accumulated_partial = ""
        last_translation_time = 0
        accumulated_recognition = ""  # Accumulate recognition text for smarter batching
        last_partial_emit = 0
        
        # Store translation style for use in translation
        global current_translation_style
        current_translation_style = translation_style
        
        print(f"✓ Starting speech recognition using microphone: {mic_index}")
        if translation_style:
            print(ConsoleColor.info(f"Using translation style: {translation_style}"))
        if preset_id:
            print(ConsoleColor.info(f"Using translation preset: {preset_id}"))
        
        audio_level = 0
        audio_data_count = 0
        
        # Fast audio level calculation without numpy
        def calculate_audio_level_fast(audio_data):
            max_sample = 0
            for i in range(0, len(audio_data), 2):
                if i + 1 < len(audio_data):
                    sample = int.from_bytes(audio_data[i:i+2], byteorder='little', signed=True)
                    abs_sample = abs(sample)
                    if abs_sample > max_sample:
                        max_sample = abs_sample
            return min(max_sample / 32768.0, 1.0)
        
        while is_processing:
            try:
                data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                audio_data_count += 1
                
                # Optimized audio level - faster calculation without numpy
                if audio_data_count % AUDIO_LEVEL_INTERVAL == 0:
                    audio_level = calculate_audio_level_fast(data)
                    socketio.emit('audio_level', {'level': audio_level})
                
                if rec.AcceptWaveform(data):
                    result = json.loads(rec.Result())
                    text = result.get('text', '').strip()
                    
                    if text:
                        segment_count += 1
                        segment_time = time.time() - start_time
                        
                        print(ConsoleColor.success(f"Segment {segment_count}: {text[:50]}..."))  # Debug log
                        
                        socketio.emit('recognition_result', {
                            'text': text,
                            'segment': segment_count,
                            'time': f"{segment_time:.2f}s",
                            'is_final': False
                        })
                        
                        all_text += text + " "
                        accumulated_recognition += text + " "
                        
                        # Smart batching: translate immediately if we have enough content
                        if len(accumulated_recognition.strip()) >= MIN_CHARS_FOR_TRANSLATION:
                            socketio.emit('status', {'status': 'translating', 'message': 'Translating...'})
                            if provider == 'vllm':
                                translate_stream_vllm(accumulated_recognition.strip(), model_name, preset_id)
                            else:
                                translate_stream(accumulated_recognition.strip(), model_name, provider, preset_id)
                            accumulated_recognition = ""
                            last_translation_time = time.time()
                        
                else:
                    # Get partial results for faster response
                    partial = json.loads(rec.PartialResult())
                    partial_text = partial.get('partial', '')
                    
                    # Emit partial results more frequently for better UX
                    current_time = time.time()
                    if partial_text and (current_time - last_partial_emit > PARTIAL_UPDATE_INTERVAL):
                        socketio.emit('recognition_partial', {
                            'text': partial_text
                        })
                        last_partial_emit = current_time
                        
                        # Try to translate partial text if it's long enough and enough time has passed
                        if (len(partial_text) >= 8 and 
                            (current_time - last_translation_time) > MIN_TRANSLATION_INTERVAL):
                            socketio.emit('status', {'status': 'translating', 'message': 'Translating...'})
                            if provider == 'vllm':
                                translate_stream_vllm(partial_text, model_name, preset_id)
                            else:
                                translate_stream(partial_text, model_name, provider, preset_id)
                            last_translation_time = current_time
                        
            except IOError as e:
                if is_processing:
                    print(ConsoleColor.warning(f"Audio read error: {e}"))
                    print(ConsoleColor.info(f"Audio data count: {audio_data_count}"))
                    continue
                break
            except Exception as e:
                if is_processing:
                    print(ConsoleColor.error(f"Failed to process audio data: {e}"))
                    import traceback
                    traceback.print_exc()
                break
        
        print(ConsoleColor.success(f"Audio processing loop ended. Total segments: {segment_count}"))
        
        # Get final result
        try:
            final_result = json.loads(rec.FinalResult())
            final_text = final_result.get('text', '').strip()
            
            if final_text:
                all_text += final_text
        except Exception as e:
            print(ConsoleColor.warning(f"Failed to get final result: {e}"))
            
        total_time = time.time() - start_time
        
        socketio.emit('recognition_complete', {
            'text': all_text.strip(),
            'total_time': f"{total_time:.2f}s",
            'segments': segment_count
        })
        
        print(ConsoleColor.success(f"Speech recognition completed, total {segment_count} segments, took {total_time:.2f}s"))
        
    except Exception as e:
        error_msg = f'Audio processing error: {str(e)}'
        socketio.emit('error', {'message': error_msg})
        print(ConsoleColor.error(error_msg))
    finally:
        # Windows adaptation: Ensure resources are properly released
        if stream:
            try:
                stream.stop_stream()
                stream.close()
            except Exception as e:
                print(ConsoleColor.warning(f"Failed to close audio stream: {e}"))
        
        if p:
            try:
                p.terminate()
            except Exception as e:
                print(ConsoleColor.warning(f"Failed to terminate PyAudio: {e}"))

import concurrent.futures

# Streaming translation with provider support
def translate_stream(text, model_name, provider='llama.cpp', preset_id=None):
    global translation_cache, current_translation_style, current_translation_prompt, pending_translations
    
    # Determine API URL based on provider
    if provider == 'llama.cpp':
        API_URL = 'http://localhost:8080'  # llama.cpp default port
        service_name = 'llama.cpp'
    elif provider == 'lmstudio':
        API_URL = 'http://localhost:11434'
        service_name = 'LM Studio'
    else:
        API_URL = OLLAMA_URL
        service_name = 'Ollama'
    
    # Set default model if not provided
    if not model_name:
        model_name = 'llama2'  # Default Ollama model
    
    # Build clear translation prompt
    prompt = f"Translate this Chinese text to English. Output only the translation, no explanations: {text}"
    style_key = 'fast'
    
    # Store the optimized prompt
    current_translation_prompt = prompt
    
    # Create cache key with hash for faster lookup
    import hashlib
    text_hash = hashlib.md5(text.encode()).hexdigest()[:12]
    cache_key = f"{provider}:{model_name}:{style_key}:{text_hash}"
    
    # Check for duplicate pending translation
    if cache_key in pending_translations:
        print(ConsoleColor.debug(f"Skipping duplicate translation: '{text[:20]}...'"))
        return
    pending_translations.add(cache_key)
    
    # Check cache first
    if cache_key in translation_cache:
        cached_result = translation_cache.get(cache_key)
        print(ConsoleColor.highlight(f"⚡ CACHE HIT for: '{text[:20]}...'"))
        pending_translations.discard(cache_key)
        
        # Stream cached result
        for i, char in enumerate(cached_result):
            socketio.emit('translation_chunk', {
                'chunk': char,
                'translation': cached_result[:i+1],
                'char_count': i+1
            })
            time.sleep(0.01)  # Simulate streaming
        
        socketio.emit('translation_complete', {
            'translation': cached_result,
            'total_time': '0.00s',
            'chars': len(cached_result),
            'first_chunk_time': '0.001s'
        })
        return
    
    # Use thread pool for asynchronous processing
    def fetch_translation():
        try:
            start_time = time.time()
            
            # Check if Ollama is available
            try:
                # Test Ollama connection first
                test_response = requests.get(f'{API_URL}/api/tags', timeout=2)
                if test_response.status_code != 200:
                    raise Exception(f"Ollama service not responding: {test_response.status_code}")
            except Exception as e:
                print(ConsoleColor.error(f"Ollama service not available: {e}"))
                # Try to start Ollama service
                try:
                    import subprocess
                    print(ConsoleColor.info("Attempting to start Ollama service..."))
                    subprocess.Popen(['ollama', 'serve'], creationflags=subprocess.CREATE_NEW_CONSOLE)
                    # Wait for Ollama to start
                    time.sleep(3)
                except Exception as start_error:
                    print(ConsoleColor.error(f"Failed to start Ollama: {start_error}"))
                    raise
            
            # Ollama API call with balanced parameters for speed and quality
            response = requests.post(
                f'{API_URL}/api/generate',
                json={
                    'model': model_name,
                    'prompt': prompt,
                    'stream': True,
                    'options': {
                        'temperature': 0.3,  # Low temperature for consistency
                        'top_p': 0.8,        # Moderate sampling
                        'top_k': 20,         # Reasonable candidates
                        'num_predict': 200,  # Limit output for speed
                        'num_ctx': 512,      # Balanced context
                        'num_keep': 0,
                        'repeat_penalty': 1.0,
                        'repeat_last_n': 0,
                        'seed': 42,
                        'num_thread': 4,
                        'f16_kv': True
                    }
                },
                stream=True,
                timeout=60
            )
            
            translation = ""
            char_count = 0
            first_chunk_time = None
            
            for line in response.iter_lines(decode_unicode=True):
                if line:
                    try:
                        data = json.loads(line)
                        chunk = data.get('response', '')
                        
                        if chunk:
                            # Record time of first chunk for latency measurement
                            if first_chunk_time is None:
                                first_chunk_time = time.time() - start_time
                                print(ConsoleColor.highlight(f"⚡ FIRST CHUNK in {first_chunk_time:.3f}s"))
                            
                            translation += chunk
                            char_count += len(chunk)
                            
                            socketio.emit('translation_chunk', {
                                'chunk': chunk,
                                'translation': translation,
                                'char_count': char_count
                            })
                    
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        print(ConsoleColor.warning(f"Failed to parse translation data: {e}"))
                        continue
            
            total_time = time.time() - start_time
            
            # Cache the result
            if translation:
                translation_cache.put(cache_key, translation)
            
            socketio.emit('translation_complete', {
                'translation': translation,
                'total_time': f"{total_time:.2f}s",
                'chars': char_count,
                'first_chunk_time': f"{first_chunk_time:.3f}s" if first_chunk_time else "N/A"
            })
            
            print(ConsoleColor.highlight(f"⚡ DONE: {char_count} chars, total {total_time:.3f}s, first {first_chunk_time:.3f}s"))
            
        except requests.exceptions.Timeout:
            error_msg = f'Translation timeout, please check if {service_name} service is running normally'
            socketio.emit('error', {'message': error_msg})
            print(ConsoleColor.error(error_msg))
        except requests.exceptions.ConnectionError:
            error_msg = f'Unable to connect to {service_name} service, please ensure the service is running'
            socketio.emit('error', {'message': error_msg})
            print(ConsoleColor.error(error_msg))
        except Exception as e:
            error_msg = f'Translation error: {str(e)}'
            socketio.emit('error', {'message': error_msg})
            print(ConsoleColor.error(error_msg))
        finally:
            # Remove from pending translations
            try:
                pending_translations.discard(cache_key)
            except:
                pass
    
    # Run translation in a thread pool
    with concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix='translator') as executor:
        executor.submit(fetch_translation)

# vLLM translation with OpenAI-compatible API and batching support
def translate_stream_vllm(text, model_name=None, preset_id=None):
    """
    Translate using vLLM with OpenAI-compatible API
    vLLM provides 10-20x throughput improvement with continuous batching
    
    Features:
    - Stream translation chunks in real-time
    - Detect complete sentences and emit for TTS
    - Compatible with existing frontend streaming TTS system
    """
    global translation_cache, pending_translations
    
    service_name = 'vLLM'
    API_URL = VLLM_URL
    
    # Build translation prompt - optimized for Chinese to English translation
    prompt = f"Translate the following Chinese text to English. Provide only the translation without any explanations or notes:\n\n{text}"
    
    # Create cache key
    import hashlib
    text_hash = hashlib.blake2b(text.encode(), digest_size=8).hexdigest()
    cache_key = f"vllm:{text_hash}"
    
    # Check for duplicate pending translation
    if cache_key in pending_translations:
        print(ConsoleColor.debug(f"Skipping duplicate translation: '{text[:20]}...'"))
        return
    pending_translations.add(cache_key)
    
    # Check cache first
    if cache_key in translation_cache:
        cached_result = translation_cache.get(cache_key)
        print(ConsoleColor.highlight(f"⚡ vLLM CACHE HIT for: '{text[:20]}...'"))
        pending_translations.discard(cache_key)
        
        # Stream cached result with sentence detection for TTS
        accumulated = ""
        emitted_sentences = set()  # 跟踪已发送的句子
        for i, char in enumerate(cached_result):
            accumulated += char
            socketio.emit('translation_chunk', {
                'chunk': char,
                'translation': accumulated,
                'char_count': i+1
            })
            
            # 使用智能断句检测完整句子
            current_sentences = split_into_sentences(accumulated)
            for sentence in current_sentences:
                sentence = sentence.strip()
                if (sentence not in emitted_sentences and 
                    is_complete_sentence(sentence) and 
                    len(sentence) >= 5):
                    confidence = get_sentence_confidence(sentence)
                    socketio.emit('translation_sentence_complete', {
                        'sentence': sentence,
                        'translation': accumulated,
                        'is_complete': True,
                        'provider': 'vllm',
                        'confidence': round(confidence, 2),
                        'from_cache': True
                    })
                    emitted_sentences.add(sentence)
            
            time.sleep(0.005)
        
        socketio.emit('translation_complete', {
            'translation': cached_result,
            'total_time': '0.00s',
            'chars': len(cached_result),
            'first_chunk_time': '0.001s',
            'provider': 'vllm'
        })
        return
    
    def fetch_translation_vllm():
        try:
            start_time = time.time()
            
            # vLLM OpenAI-compatible API with optimized parameters for translation
            response = http_session.post(
                f'{API_URL}/v1/completions',
                json={
                    'model': model_name or 'default',
                    'prompt': prompt,
                    'max_tokens': 200,  # Increased for longer translations
                    'temperature': 0.1,  # Low temperature for accurate translation
                    'top_p': 0.9,
                    'stream': True,
                    'best_of': 1,
                    'use_beam_search': False,
                    'skip_special_tokens': True,
                    'spaces_between_special_tokens': False
                },
                stream=True,
                timeout=30,
                headers={'Content-Type': 'application/json'}
            )
            
            translation = ""
            char_count = 0
            first_chunk_time = None
            chunk_buffer = ""
            last_emit_time = 0
            EMIT_INTERVAL = 0.03  # Slightly longer interval for better batching
            sentence_buffer = ""  # Buffer for sentence detection
            completed_sentences = set()  # Track completed sentences to avoid duplicates
            
            for line in response.iter_lines(decode_unicode=True):
                if line:
                    line = line.strip()
                    if line.startswith('data: '):
                        line = line[6:]  # Remove 'data: ' prefix
                    
                    if line == '[DONE]':
                        break
                    
                    try:
                        data = json.loads(line)
                        choices = data.get('choices', [])
                        if choices:
                            chunk = choices[0].get('text', '')
                            
                            if chunk:
                                if first_chunk_time is None:
                                    first_chunk_time = time.time() - start_time
                                    print(ConsoleColor.highlight(f"⚡ vLLM FIRST CHUNK in {first_chunk_time:.3f}s"))
                                
                                chunk_buffer += chunk
                                translation += chunk
                                char_count += len(chunk)
                                
                                current_time = time.time()
                                
                                # Emit regular chunks for UI display
                                if len(chunk_buffer) >= 3 or (current_time - last_emit_time) > EMIT_INTERVAL:
                                    socketio.emit('translation_chunk', {
                                        'chunk': chunk_buffer,
                                        'translation': translation,
                                        'char_count': char_count
                                    })
                                    chunk_buffer = ""
                                    last_emit_time = current_time
                                
                                # 使用智能句子缓冲管理
                                sentence_buffer, sentences_to_emit, has_confident = smart_sentence_buffer(
                                    sentence_buffer, chunk, completed_sentences
                                )
                                
                                # 发送检测到的完整句子
                                for sentence in sentences_to_emit:
                                    if sentence not in completed_sentences:
                                        confidence = get_sentence_confidence(sentence)
                                        print(ConsoleColor.info(
                                            f"🎯 vLLM Sentence (confidence: {confidence:.2f}): '{sentence[:60]}{'...' if len(sentence) > 60 else ''}'"
                                        ))
                                        socketio.emit('translation_sentence_complete', {
                                            'sentence': sentence,
                                            'translation': translation,
                                            'is_complete': True,
                                            'provider': 'vllm',
                                            'confidence': round(confidence, 2)
                                        })
                                        completed_sentences.add(sentence)
                    
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        print(ConsoleColor.warning(f"Failed to parse vLLM data: {e}"))
                        continue
            
            # Emit remaining buffer
            if chunk_buffer:
                socketio.emit('translation_chunk', {
                    'chunk': chunk_buffer,
                    'translation': translation,
                    'char_count': char_count
                })
            
            # Emit any remaining incomplete sentence
            remaining = sentence_buffer.strip()
            if remaining and len(remaining) > 3 and remaining not in completed_sentences:
                socketio.emit('translation_sentence_complete', {
                    'sentence': remaining,
                    'translation': translation,
                    'is_complete': False,  # Mark as incomplete
                    'provider': 'vllm'
                })
            
            total_time = time.time() - start_time
            
            # Cache result
            if translation:
                translation_cache.put(cache_key, translation)
            
            socketio.emit('translation_complete', {
                'translation': translation,
                'total_time': f"{total_time:.2f}s",
                'chars': char_count,
                'first_chunk_time': f"{first_chunk_time:.3f}s" if first_chunk_time else "N/A",
                'provider': 'vllm',
                'sentences': len(completed_sentences)
            })
            
            print(ConsoleColor.highlight(f"⚡ vLLM DONE: {char_count} chars, {len(completed_sentences)} sentences, total {total_time:.3f}s"))
            
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            error_msg = f'vLLM service is not available, switching to Ollama'
            print(ConsoleColor.warning(error_msg))
            
            # Switch to Ollama automatically
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(translate_stream, text, model_name, 'ollama', preset_id)
        except Exception as e:
            error_msg = f'vLLM translation error: {str(e)}'
            socketio.emit('error', {'message': error_msg})
            print(ConsoleColor.error(error_msg))
        finally:
            try:
                pending_translations.discard(cache_key)
            except:
                pass
    
    # Run in thread pool
    with concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix='vllm_translator') as executor:
        executor.submit(fetch_translation_vllm)


def split_into_sentences(text):
    """
    智能分句 - 将文本分割成完整的句子用于TTS处理。
    
    特性：
    - 支持中英文标点符号
    - 智能处理缩写（Mr., Dr., etc.）
    - 处理小数点和数字
    - 处理引号内的句子
    - 最小长度保护，避免过短片段
    - 智能合并连续标点
    
    Args:
        text: 输入文本
        
    Returns:
        list: 句子列表
    """
    import re
    
    if not text or not text.strip():
        return []
    
    # 常见英文缩写列表（避免误判为句子结尾）
    abbreviations = {
        'mr.', 'mrs.', 'ms.', 'dr.', 'prof.', 'sr.', 'jr.', 'st.',
        'ave.', 'blvd.', 'rd.', 'no.', 'vol.', 'vols.', 'inc.',
        'ltd.', 'jr.', 'sr.', 'co.', 'corp.', 'plc.', 'llc.',
        'jan.', 'feb.', 'mar.', 'apr.', 'jun.', 'jul.', 'aug.',
        'sep.', 'oct.', 'nov.', 'dec.',
        'mon.', 'tue.', 'wed.', 'thu.', 'fri.', 'sat.', 'sun.',
        'a.m.', 'p.m.', 'e.g.', 'i.e.', 'etc.', 'vs.', 'vol.',
        'fig.', 'et al.', 'ph.d.', 'b.a.', 'm.a.', 'm.d.', 'd.d.s.',
        'u.s.', 'u.k.', 'u.n.', 'n.a.t.o.', 'e.u.',
        'a.d.', 'b.c.', 'c.e.', 'b.c.e.'
    }
    
    # 清理文本
    text = text.strip()
    
    # 保护缩写：将缩写中的点替换为特殊标记
    protected_text = text
    for abbr in sorted(abbreviations, key=len, reverse=True):  # 长的先处理
        pattern = re.escape(abbr)
        protected_text = re.sub(
            rf'\b{pattern}',
            abbr.replace('.', '\x00'),
            protected_text,
            flags=re.IGNORECASE
        )
    
    # 保护小数点（数字.数字）
    protected_text = re.sub(r'(\d)\.(\d)', r'\1\x01\2', protected_text)
    
    # 保护网址和邮箱
    protected_text = re.sub(
        r'(https?://[^\s]+|www\.[^\s]+|[\w.-]+@[\w.-]+\.\w+)',
        lambda m: m.group(0).replace('.', '\x02'),
        protected_text
    )
    
    # 定义句子分隔符模式
    # 匹配：.!?。！？后跟空格或结束，或换行符
    sentence_end_pattern = r'[.!?。！？]+(?:\s+|$|\n)'
    
    # 分割句子
    parts = re.split(f'({sentence_end_pattern})', protected_text)
    
    # 合并句子及其结束标点
    sentences = []
    i = 0
    while i < len(parts):
        part = parts[i].strip()
        if not part:
            i += 1
            continue
            
        # 如果这部分是结束标点，合并到前一个句子
        if re.match(r'^[.!?。！？]+$', part) and sentences:
            sentences[-1] += part
            i += 1
            continue
        
        # 检查下一块是否是结束标点
        if i + 1 < len(parts) and re.match(r'^[.!?。！？]+(?:\s+|$|\n)?$', parts[i + 1]):
            sentence = part + parts[i + 1].strip()
            i += 2
        else:
            sentence = part
            i += 1
        
        # 恢复被保护的字符
        sentence = sentence.replace('\x00', '.').replace('\x01', '.').replace('\x02', '.')
        
        # 清理并验证句子
        sentence = sentence.strip()
        if len(sentence) >= 3:  # 最小长度限制
            sentences.append(sentence)
    
    return sentences


def is_complete_sentence(text):
    """
    检查文本是否是一个完整的句子。
    
    判断标准：
    - 以句子结束标点结尾
    - 不是常见缩写
    - 长度合理
    - 有实际内容（不只是标点）
    
    Args:
        text: 输入文本
        
    Returns:
        bool: 是否是完整句子
    """
    import re
    
    text = text.strip()
    if not text or len(text) < 3:
        return False
    
    # 常见缩写列表
    abbreviations = {
        'mr.', 'mrs.', 'ms.', 'dr.', 'prof.', 'sr.', 'jr.', 'st.',
        'ave.', 'blvd.', 'rd.', 'no.', 'vol.', 'inc.', 'ltd.',
        'co.', 'corp.', 'jan.', 'feb.', 'mar.', 'apr.', 'jun.',
        'jul.', 'aug.', 'sep.', 'oct.', 'nov.', 'dec.',
        'a.m.', 'p.m.', 'e.g.', 'i.e.', 'etc.', 'vs.', 'fig.',
        'ph.d.', 'u.s.', 'u.k.', 'u.n.', 'a.d.', 'b.c.'
    }
    
    # 检查是否是缩写（不区分大小写）
    text_lower = text.lower()
    for abbr in abbreviations:
        if text_lower.endswith(abbr):
            return False
    
    # 检查是否以句子结束标点结尾
    if not re.search(r'[.!?。！？]$', text):
        return False
    
    # 检查是否包含实际内容（不只是标点）
    content = re.sub(r'[.!?。！？\s]', '', text)
    if len(content) < 2:
        return False
    
    # 检查是否是小数（如 "3.14"）
    if re.match(r'^\d+\.\d+$', text):
        return False
    
    return True


def get_sentence_confidence(text, next_chars=''):
    """
    评估句子完整性的置信度。
    
    用于在流式输出中判断是否足够确定一个句子已经完成。
    
    Args:
        text: 当前句子文本
        next_chars: 后续字符（用于判断上下文）
        
    Returns:
        float: 置信度 (0.0 - 1.0)
    """
    import re
    
    if not text or len(text.strip()) < 3:
        return 0.0
    
    text = text.strip()
    confidence = 0.0
    
    # 基础：以结束标点结尾
    if re.search(r'[.!?。！？]$', text):
        confidence += 0.4
        
        # 不是缩写
        if is_complete_sentence(text):
            confidence += 0.3
        else:
            confidence -= 0.2  # 可能是缩写，降低置信度
    
    # 长度因素（适中长度的句子更可能是完整的）
    content_len = len(re.sub(r'[.!?。！？\s]', '', text))
    if 10 <= content_len <= 200:
        confidence += 0.15
    elif content_len > 200:
        confidence += 0.1  # 长句子也可能需要分割
    
    # 后续字符提示
    if next_chars:
        next_stripped = next_chars.lstrip()
        if next_stripped:
            first_char = next_stripped[0]
            # 后续是大写字母或中文，说明当前句子很可能结束
            if first_char.isupper() or '\u4e00' <= first_char <= '\u9fff':
                confidence += 0.15
            # 后续是引号结束
            elif first_char in '"""\'\'':
                confidence += 0.1
    else:
        # 没有后续字符，可能是文本结束
        confidence += 0.1
    
    return min(confidence, 1.0)


def smart_sentence_buffer(buffer_text, new_chunk, completed_sentences, force_threshold=350):
    """
    智能句子缓冲管理 - 主动断句策略。
    
    用于流式翻译中管理句子缓冲区，决定何时发送完整句子。
    
    主动断句策略：
    1. 优先检测完整句子（高置信度立即发送）
    2. 中等置信度时根据缓冲区长度决策
    3. 缓冲区过长时主动强制断句
    4. 支持多级断句标点（句号 > 逗号 > 分号）
    
    Args:
        buffer_text: 当前缓冲区文本
        new_chunk: 新接收的文本块
        completed_sentences: 已完成的句子集合（用于去重）
        force_threshold: 强制断句阈值（默认 350 字符）
        
    Returns:
        tuple: (new_buffer, sentences_to_emit, is_confident)
    """
    import re
    
    # 添加新内容到缓冲区
    combined = buffer_text + new_chunk
    
    # 提取所有可能的句子
    sentences = split_into_sentences(combined)
    
    sentences_to_emit = []
    remaining_buffer = combined
    
    # 第一遍：高置信度句子立即发送
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence or sentence in completed_sentences:
            continue
        
        # 检查句子完整性置信度
        pos = combined.find(sentence)
        next_chars = combined[pos + len(sentence):pos + len(sentence) + 10] if pos >= 0 else ''
        
        confidence = get_sentence_confidence(sentence, next_chars)
        
        # 高置信度（>=0.7）立即发送
        if confidence >= 0.7:
            sentences_to_emit.append(sentence)
            if pos >= 0:
                remaining_buffer = combined[pos + len(sentence):]
                combined = remaining_buffer  # 更新 combined 用于后续处理
    
    # 第二遍：中等置信度根据缓冲区长度决策
    if len(remaining_buffer) > 200:  # 缓冲区达到中等长度
        sentences = split_into_sentences(remaining_buffer)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence or sentence in completed_sentences:
                continue
            
            pos = remaining_buffer.find(sentence)
            next_chars = remaining_buffer[pos + len(sentence):pos + len(sentence) + 10] if pos >= 0 else ''
            confidence = get_sentence_confidence(sentence, next_chars)
            
            # 中等置信度（>=0.5）且缓冲区较长时发送
            if confidence >= 0.5:
                sentences_to_emit.append(sentence)
                if pos >= 0:
                    remaining_buffer = remaining_buffer[pos + len(sentence):]
    
    # 清理剩余缓冲区
    remaining_buffer = remaining_buffer.strip()
    
    # 第三遍：主动强制断句（缓冲区过长时）
    if len(remaining_buffer) > force_threshold and not sentences_to_emit:
        # 优先找句子结束标点
        end_punctuations = ['.', '!', '?', '。', '！', '？']
        forced_pos = -1
        
        for punct in end_punctuations:
            pos = remaining_buffer.rfind(punct)
            if pos > forced_pos:
                forced_pos = pos
        
        # 如果没有句子结束标点，找逗号等次要标点
        if forced_pos < 50:
            comma_punctuations = [',', '，', ';', '；', ':', '：']
            for punct in comma_punctuations:
                pos = remaining_buffer.rfind(punct)
                if pos > forced_pos:
                    forced_pos = pos
        
        # 执行强制断句
        if forced_pos > 30:  # 确保有足够的上下文
            forced_sentence = remaining_buffer[:forced_pos + 1].strip()
            if forced_sentence and forced_sentence not in completed_sentences:
                sentences_to_emit.append(forced_sentence)
                remaining_buffer = remaining_buffer[forced_pos + 1:].strip()
    
    # 第四遍：极端情况，按空格或最大长度强制分割
    if len(remaining_buffer) > 500 and not sentences_to_emit:
        # 找最后一个空格分割（英文优化）
        last_space = remaining_buffer.rfind(' ')
        if last_space > 100 and last_space < len(remaining_buffer) - 50:
            forced_sentence = remaining_buffer[:last_space].strip()
            if forced_sentence and forced_sentence not in completed_sentences:
                sentences_to_emit.append(forced_sentence)
                remaining_buffer = remaining_buffer[last_space + 1:].strip()
    
    return remaining_buffer, sentences_to_emit, len(sentences_to_emit) > 0


# Batch translation with vLLM for multiple texts
def translate_batch_vllm(texts: list, model_name=None) -> list:
    """
    Batch translate multiple texts using vLLM
    Much more efficient than individual requests
    """
    if not texts:
        return []
    
    API_URL = VLLM_URL
    
    # Check cache for each text
    import hashlib
    results = []
    uncached_texts = []
    uncached_indices = []
    
    for i, text in enumerate(texts):
        text_hash = hashlib.blake2b(text.encode(), digest_size=8).hexdigest()
        cache_key = f"vllm:{text_hash}"
        
        if cache_key in translation_cache:
            results.append((i, translation_cache.get(cache_key)))
        else:
            results.append((i, None))
            uncached_texts.append(text)
            uncached_indices.append(i)
    
    if not uncached_texts:
        # All cached
        return [r[1] for r in sorted(results, key=lambda x: x[0])]
    
    # Build prompts for uncached texts
    prompts = [f"Translate to English: {text}" for text in uncached_texts]
    
    try:
        # vLLM batch API
        response = http_session.post(
            f'{API_URL}/v1/completions',
            json={
                'model': model_name or 'default',
                'prompt': prompts,
                'max_tokens': 100,
                'temperature': 0.1,
                'top_p': 0.9,
                'stream': False
            },
            timeout=60,
            headers={'Content-Type': 'application/json'}
        )
        
        data = response.json()
        choices = data.get('choices', [])
        
        # Update results and cache
        for idx, choice in zip(uncached_indices, choices):
            translation = choice.get('text', '').strip()
            results[idx] = (idx, translation)
            
            # Cache result
            text_hash = hashlib.blake2b(uncached_texts[uncached_indices.index(idx)].encode(), digest_size=8).hexdigest()
            cache_key = f"vllm:{text_hash}"
            translation_cache.put(cache_key, translation)
        
        print(ConsoleColor.success(f"Batch translated {len(uncached_texts)} texts with vLLM"))
        
    except Exception as e:
        print(ConsoleColor.error(f"vLLM batch translation error: {e}"))
        # Return original texts on error
        for idx in uncached_indices:
            results[idx] = (idx, texts[idx])
    
    return [r[1] for r in sorted(results, key=lambda x: x[0])]

# GSV-TTS-Lite audio cache with memory limit (500MB) and TTL (2 hours)
gsv_tts_cache = LRUCache(capacity=100, max_memory_mb=500, default_ttl=7200)

# Cache key generation helper for GSV-TTS
def generate_gsv_tts_cache_key(speaker_wav, text, speed=1.0):
    """
    Generate optimized cache key for GSV-TTS
    Uses xxhash if available (faster), falls back to blake2b
    """
    try:
        import xxhash
        text_hash = xxhash.xxh64(text.encode()).hexdigest()
    except ImportError:
        # Use blake2b for faster hashing than md5
        text_hash = hashlib.blake2b(text.encode(), digest_size=8).hexdigest()
    
    # Normalize speaker_wav to handle path variations
    speaker_name = os.path.splitext(os.path.basename(speaker_wav))[0]
    return f"gsv:{speaker_name}:{text_hash}:{speed:.2f}"

# Preload GSV-TTS-Lite model if available
def preload_gsv_tts():
    global gsv_tts
    if GSV_TTS_AVAILABLE:
        try:
            print(ConsoleColor.info(f"Preloading GSV-TTS-Lite model from {TTS_MODELS_DIR}..."))
            print(ConsoleColor.info("  Loading all models into memory for faster inference..."))
            
            # Send loading status to frontend
            socketio.emit('gsv_tts_status', {
                'status': 'loading',
                'message': f'Preloading GSV-TTS-Lite model from project directory...'
            })
            
            # Use flash attention if available for better performance
            # Use is_half=True for FP16 to reduce VRAM usage by ~50%
            # Set always_load_cnhubert and always_load_sv to False to save VRAM
            try:
                gsv_tts = GSVTTS(
                    models_dir=TTS_MODELS_DIR,
                    is_half=True,
                    use_flash_attn=True,
                    use_bert=True,
                    always_load_cnhubert=False,
                    always_load_sv=False
                )
                
                # Send GPT model loading status
                socketio.emit('gsv_tts_status', {
                    'status': 'loading_gpt',
                    'message': 'Loading GPT model...'
                })
                print(ConsoleColor.info("  Loading GPT model (s1v3)..."))
                gsv_tts.load_gpt_model()
                print(ConsoleColor.success("  GPT model loaded successfully"))
                
                # Send SoVITS model loading status
                socketio.emit('gsv_tts_status', {
                    'status': 'loading_sovits',
                    'message': 'Loading SoVITS model...'
                })
                print(ConsoleColor.info("  Loading SoVITS model (s2Gv2ProPlus)..."))
                gsv_tts.load_sovits_model()
                print(ConsoleColor.success("  SoVITS model loaded successfully"))
                
            except Exception as e:
                # Fallback to non-flash attention if flash attention fails
                print(ConsoleColor.warning(f"Flash attention failed: {e}. Falling back to non-flash attention..."))
                gsv_tts = GSVTTS(
                    models_dir=TTS_MODELS_DIR,
                    is_half=True,
                    use_flash_attn=False,
                    use_bert=True,
                    always_load_cnhubert=False,
                    always_load_sv=False
                )
                
                # Send GPT model loading status
                socketio.emit('gsv_tts_status', {
                    'status': 'loading_gpt',
                    'message': 'Loading GPT model (non-flash attention)...'
                })
                print(ConsoleColor.info("  Loading GPT model (s1v3)..."))
                gsv_tts.load_gpt_model()
                print(ConsoleColor.success("  GPT model loaded successfully"))
                
                # Send SoVITS model loading status
                socketio.emit('gsv_tts_status', {
                    'status': 'loading_sovits',
                    'message': 'Loading SoVITS model...'
                })
                print(ConsoleColor.info("  Loading SoVITS model (s2Gv2ProPlus)..."))
                gsv_tts.load_sovits_model()
                print(ConsoleColor.success("  SoVITS model loaded successfully"))
            
            print(ConsoleColor.success("GSV-TTS-Lite model preloaded successfully"))
            print(ConsoleColor.info("  All models loaded: Chinese HuBERT, Chinese RoBERTa, G2P, SV, GPT, SoVITS"))
            
            # Send success status to frontend
            socketio.emit('gsv_tts_status', {
                'status': 'loaded',
                'message': 'GSV-TTS-Lite model preloaded successfully'
            })
        except Exception as e:
            print(ConsoleColor.error(f"Failed to preload GSV-TTS-Lite model: {e}"))
            import traceback
            traceback.print_exc()
            
            # Send error status to frontend
            socketio.emit('gsv_tts_status', {
                'status': 'error',
                'message': f'Failed to preload GSV-TTS-Lite model: {str(e)}'
            })

# 路由
@app.route('/')
def index():
    """Main application page with start screen"""
    # Show start page first
    return render_template('start.html')

@app.route('/start')
def start():
    """System start page"""
    return render_template('start.html')

@app.route('/loading')
def loading():
    """System loading page"""
    return render_template('loading.html')

@app.route('/app')
def main_app():
    """Direct access to main application (skip loading)"""
    global components_loaded
    
    # Check if components are loaded
    if not components_loaded:
        # Redirect to start page if components not loaded
        return redirect('/start')
    
    current_language = session.get('language', default_language)
    # Add a random parameter to force browser to reload the template
    import random
    
    # Read the index.html file
    with open('templates/index.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Add language selector to the HTML content
    language_selector = '''
    <!-- Language Selector -->
    <div style="position: fixed; top: 20px; right: 80px; z-index: 99999; display: block !important;">
        <form action="/api/set-language" method="post" style="margin: 0;">
            <input type="hidden" name="language" id="language-input">
            <button type="button" onclick="document.getElementById('language-input').value='zh-CN'; this.form.submit();" style="background: red; color: white; width: 40px; height: 40px; border-radius: 50%; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center;">
                <i class="fas fa-language"></i>
            </button>
            <div style="position: absolute; top: 50px; right: 0; background: white; border: 1px solid #ddd; border-radius: 8px; padding: 10px; display: block;">
                <div style="font-size: 12px; font-weight: 600; color: #666; margin-bottom: 8px;">Language</div>
                <div style="display: flex; flex-direction: column; gap: 5px;">
                    <button type="button" onclick="document.getElementById('language-input').value='zh-CN'; this.form.submit();" style="padding: 8px 12px; border-radius: 6px; cursor: pointer; border: none; background: none; text-align: left;">中文</button>
                    <button type="button" onclick="document.getElementById('language-input').value='en-US'; this.form.submit();" style="padding: 8px 12px; border-radius: 6px; cursor: pointer; border: none; background: none; text-align: left;">English</button>
                </div>
            </div>
        </form>
    </div>
    '''
    
    # Insert the language selector after the settings button
    settings_button = '<a href="/settings" class="settings-button" title="Settings">'
    settings_button_end = '</a>'
    # Find the position of the settings button
    pos = html_content.find(settings_button)
    if pos != -1:
        # Find the end of the settings button
        end_pos = html_content.find(settings_button_end, pos)
        if end_pos != -1:
            # Insert the language selector after the settings button
            html_content = html_content[:end_pos + len(settings_button_end)] + language_selector + html_content[end_pos + len(settings_button_end):]
    
    # Return the modified HTML content
    return html_content

@app.route('/settings')
def settings():
    """System settings page"""
    current_language = session.get('language', default_language)
    return render_template('settings.html', current_language=current_language, get_text=get_text)

@app.route('/language-selector')
def language_selector():
    """Language selector page"""
    return render_template('language_selector.html')

@app.route('/api/set-language', methods=['POST'])
def set_language():
    """Set user language preference"""
    # Check if data is form data or JSON
    if request.form:
        language = request.form.get('language', default_language)
    else:
        data = request.json
        language = data.get('language', default_language)
    
    if language in languages:
        session['language'] = language
        # Redirect back to app page
        return redirect('/app')
    else:
        return jsonify({'error': 'Invalid language'}), 400

@app.route('/api/translations')
def get_translations():
    """Get translations for current language"""
    current_language = session.get('language', default_language)
    return jsonify({'translations': languages.get(current_language, {}), 'current_language': current_language})

@app.route('/api/language')
def get_current_language():
    """Get current language"""
    current_language = session.get('language', default_language)
    return jsonify({'language': current_language})

@app.route('/api/microphones')
def get_mics():
    mics = get_microphones()
    return jsonify(mics)

# Get LM Studio model list
def get_lmstudio_models():
    try:
        # LM Studio API endpoint is the same as Ollama
        LMSTUDIO_URL = 'http://localhost:11434'
        response = requests.get(f'{LMSTUDIO_URL}/api/tags', timeout=5)
        if response.status_code == 200:
            data = response.json()
            return [model['name'] for model in data.get('models', [])]
    except Exception as e:
        print(ConsoleColor.error(f"Failed to get LM Studio models: {e}"))
    return []

@app.route('/api/models')
def get_models():
    provider = request.args.get('provider', 'vllm')
    if provider == 'lmstudio':
        models = get_lmstudio_models()
    elif provider == 'ollama':
        models = get_ollama_models()
    else:
        models = get_vllm_models()
    return jsonify(models)

@app.route('/api/providers')
def get_providers():
    """Get available translation providers and their status"""
    providers = {
        'ollama': {
            'name': 'Ollama',
            'available': len(get_ollama_models()) > 0,
            'url': OLLAMA_URL,
            'description': 'Local LLM inference'
        },
        'lmstudio': {
            'name': 'LM Studio',
            'available': len(get_lmstudio_models()) > 0,
            'url': 'http://localhost:11434',
            'description': 'LM Studio local server'
        },
        'vllm': {
            'name': 'vLLM',
            'available': check_vllm_health(),
            'url': VLLM_URL,
            'description': 'High-throughput LLM inference with continuous batching'
        }
    }
    return jsonify(providers)

@app.route('/api/vosk-models')
def get_vosk_models_api():
    models = get_vosk_models()
    return jsonify(models)

@app.route('/api/gsv-tts-info')
def get_gsv_tts_info():
    """Get GSV-TTS-Lite model download link and information"""
    gsv_tts_info = {
        'download_url': 'https://github.com/chinokikiss/GSV-TTS-Lite',
        'description': 'GSV-TTS-Lite: Lightweight Text-to-Speech system with voice cloning capabilities',
        'required_models': [
            {
                'name': 'Chinese HuBERT model',
                'download_url': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/cnhubert.zip',
                'description': 'Chinese HuBERT model for phoneme extraction'
            },
            {
                'name': 'G2P model',
                'download_url': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/g2p.zip',
                'description': 'Grapheme-to-Phoneme conversion model'
            },
            {
                'name': 'Speaker Verification model',
                'download_url': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/sv.zip',
                'description': 'Speaker verification model for voice cloning'
            },
            {
                'name': 'GPT model (s1v3)',
                'download_url': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/s1v3.zip',
                'description': 'GPT model for prosody prediction'
            },
            {
                'name': 'SoVITS model (s2Gv2ProPlus)',
                'download_url': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/s2Gv2ProPlus.zip',
                'description': 'SoVITS model for speech synthesis'
            }
        ],
        'installation_instructions': '1. Download the models from the links below\n2. Upload the zip files using the file uploader\n3. The system will automatically extract them to the correct directory'
    }
    return jsonify(gsv_tts_info)

@app.route('/api/gsv-tts/recommended-models')
def get_gsv_tts_recommended_models():
    """Get recommended GSV-TTS-Lite models with direct download links"""
    recommended_models = {
        'base_models': [
            {
                'id': 'chinese-hubert',
                'name': 'Chinese HuBERT',
                'type': 'base',
                'size': '约 400MB',
                'description': '中文语音特征提取模型（必需）',
                'download_urls': {
                    'github': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/cnhubert.zip',
                    'ghproxy': 'https://ghproxy.com/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/cnhubert.zip',
                    'ghapi': 'https://ghapi.cn/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/cnhubert.zip'
                },
                'download_url': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/cnhubert.zip',
                'required': True
            },
            {
                'id': 'chinese-roberta',
                'name': 'Chinese RoBERTa',
                'type': 'base',
                'size': '约 400MB',
                'description': '中文文本理解模型（必需）',
                'download_urls': {
                    'github': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/cnroberta.zip',
                    'ghproxy': 'https://ghproxy.com/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/cnroberta.zip',
                    'ghapi': 'https://ghapi.cn/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/cnroberta.zip'
                },
                'download_url': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/cnroberta.zip',
                'required': True
            },
            {
                'id': 'g2p',
                'name': 'G2P Model',
                'type': 'base',
                'size': '约 100MB',
                'description': '文字转音素转换模型（必需）',
                'download_urls': {
                    'github': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/g2p.zip',
                    'ghproxy': 'https://ghproxy.com/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/g2p.zip',
                    'ghapi': 'https://ghapi.cn/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/g2p.zip'
                },
                'download_url': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/g2p.zip',
                'required': True
            },
            {
                'id': 'speaker-verification',
                'name': 'Speaker Verification',
                'type': 'base',
                'size': '约 50MB',
                'description': '说话人验证模型（必需，音色克隆）',
                'download_urls': {
                    'github': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/sv.zip',
                    'ghproxy': 'https://ghproxy.com/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/sv.zip',
                    'ghapi': 'https://ghapi.cn/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/sv.zip'
                },
                'download_url': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/sv.zip',
                'required': True
            }
        ],
        'gpt_models': [
            {
                'id': 's1v3',
                'name': 'GPT s1v3',
                'type': 'gpt',
                'size': '约 800MB',
                'description': 'GPT韵律预测模型（必需）',
                'download_urls': {
                    'github': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/s1v3.zip',
                    'ghproxy': 'https://ghproxy.com/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/s1v3.zip',
                    'ghapi': 'https://ghapi.cn/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/s1v3.zip'
                },
                'download_url': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/s1v3.zip',
                'required': True
            }
        ],
        'sovits_models': [
            {
                'id': 's2Gv2ProPlus',
                'name': 'SoVITS s2Gv2ProPlus',
                'type': 'sovits',
                'size': '约 1.2GB',
                'description': 'SoVITS语音合成模型（必需）',
                'download_urls': {
                    'github': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/s2Gv2ProPlus.zip',
                    'ghproxy': 'https://ghproxy.com/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/s2Gv2ProPlus.zip',
                    'ghapi': 'https://ghapi.cn/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/s2Gv2ProPlus.zip'
                },
                'download_url': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/s2Gv2ProPlus.zip',
                'required': True
            }
        ]
    }
    return jsonify(recommended_models)

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get current system settings"""
    global APP_CONFIG
    settings = {
        # llama.cpp 配置
        'llama_cpp_version': APP_CONFIG.get('llama_cpp', {}).get('version', 'auto'),
        'gguf_model_path': APP_CONFIG.get('llama_cpp', {}).get('model_path', ''),
        
        # 服务设置
        'vllm': APP_CONFIG.get('vllm', {'auto_start': True}),
        'translation': APP_CONFIG.get('translation', {'auto_start_vllm': True, 'default_provider': 'llama.cpp', 'default_model': ''}),
        'llama_cpp': APP_CONFIG.get('llama_cpp', {'auto_start': True, 'version': 'auto', 'model_path': ''}),
        
        # 系统设置
        'system': APP_CONFIG.get('system', {'enable_monitor': False}),
        
        # 语音识别设置
        'speech': APP_CONFIG.get('speech', {'default_microphone': 'auto', 'model': 'vosk-model-small-cn-0.22', 'sample_rate': '16000'}),
        
        # TTS 设置
        'tts': APP_CONFIG.get('tts', {'enabled': False, 'default_model': 's2Gv2ProPlus'}),
        
        # 网络设置
        'server': APP_CONFIG.get('server', {'port': '5001', 'enable_cors': True})
    }
    return jsonify(settings)

@app.route('/api/settings', methods=['POST'])
def save_settings():
    """Save system settings"""
    global APP_CONFIG
    data = request.json
    
    try:
        # Update configuration
        # llama.cpp 配置
        if 'llama_cpp_version' in data:
            if 'llama_cpp' not in APP_CONFIG:
                APP_CONFIG['llama_cpp'] = {}
            APP_CONFIG['llama_cpp']['version'] = data['llama_cpp_version']
        
        if 'gguf_model_path' in data:
            if 'llama_cpp' not in APP_CONFIG:
                APP_CONFIG['llama_cpp'] = {}
            APP_CONFIG['llama_cpp']['model_path'] = data['gguf_model_path']
        
        # 服务设置
        if 'vllm' in data:
            APP_CONFIG['vllm'] = data['vllm']
        
        if 'translation' in data:
            APP_CONFIG['translation'] = data['translation']
        
        if 'llama_cpp' in data:
            APP_CONFIG['llama_cpp'] = data['llama_cpp']
        
        # 系统设置
        if 'system' in data:
            APP_CONFIG['system'] = data['system']
        
        # 语音识别设置
        if 'speech' in data:
            APP_CONFIG['speech'] = data['speech']
        
        # TTS 设置
        if 'tts' in data:
            APP_CONFIG['tts'] = data['tts']
        
        # 网络设置
        if 'server' in data:
            APP_CONFIG['server'] = data['server']
        
        # Save to file
        if save_config(APP_CONFIG):
            return jsonify({'success': True, 'message': '设置保存成功'})
        else:
            return jsonify({'success': False, 'error': '保存配置文件失败'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/restart')
def restart_system():
    """Restart the system"""
    global components_loaded, vllm_process, llama_cpp_process
    
    try:
        # Stop all services
        if vllm_process and vllm_process.poll() is None:
            vllm_process.terminate()
            vllm_process.wait(timeout=10)
        
        if llama_cpp_process and llama_cpp_process.poll() is None:
            llama_cpp_process.terminate()
            llama_cpp_process.wait(timeout=10)
        
        # Reset components loaded flag
        components_loaded = False
        
        # Redirect to start page
        return redirect('/start')
    except Exception as e:
        print(f"重启系统失败: {e}")
        return redirect('/start')

# GSV-TTS model download progress tracking
gsv_tts_download_progress = {}

# Model ID to target directory mapping
MODEL_TARGET_DIRS = {
    'chinese-hubert': 'chinese-hubert-base',
    'chinese-roberta': 'chinese-roberta-wwm-ext-large',
    'g2p': 'g2p',
    'speaker-verification': 'sv',
    's1v3': 's1v3',
    's2Gv2ProPlus': 's2Gv2ProPlus'
}

@app.route('/api/gsv-tts/download-model', methods=['POST'])
def download_gsv_tts_model():
    """Download a GSV-TTS-Lite model and extract to correct location"""
    data = request.json
    model_id = data.get('model_id')
    download_source = data.get('source', 'github')
    
    if not model_id:
        return jsonify({'error': 'Model ID is required'}), 400
    
    # Define all recommended models data directly
    recommended_models_data = {
        'base_models': [
            {
                'id': 'chinese-hubert',
                'name': 'Chinese HuBERT',
                'download_urls': {
                    'github': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/cnhubert.zip',
                    'ghproxy': 'https://ghproxy.com/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/cnhubert.zip',
                    'ghapi': 'https://ghapi.cn/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/cnhubert.zip'
                },
                'download_url': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/cnhubert.zip'
            },
            {
                'id': 'chinese-roberta',
                'name': 'Chinese RoBERTa',
                'download_urls': {
                    'github': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/cnroberta.zip',
                    'ghproxy': 'https://ghproxy.com/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/cnroberta.zip',
                    'ghapi': 'https://ghapi.cn/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/cnroberta.zip'
                },
                'download_url': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/cnroberta.zip'
            },
            {
                'id': 'g2p',
                'name': 'G2P Model',
                'download_urls': {
                    'github': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/g2p.zip',
                    'ghproxy': 'https://ghproxy.com/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/g2p.zip',
                    'ghapi': 'https://ghapi.cn/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/g2p.zip'
                },
                'download_url': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/g2p.zip'
            },
            {
                'id': 'speaker-verification',
                'name': 'Speaker Verification',
                'download_urls': {
                    'github': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/sv.zip',
                    'ghproxy': 'https://ghproxy.com/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/sv.zip',
                    'ghapi': 'https://ghapi.cn/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/sv.zip'
                },
                'download_url': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/sv.zip'
            }
        ],
        'gpt_models': [
            {
                'id': 's1v3',
                'name': 'GPT s1v3',
                'download_urls': {
                    'github': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/s1v3.zip',
                    'ghproxy': 'https://ghproxy.com/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/s1v3.zip',
                    'ghapi': 'https://ghapi.cn/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/s1v3.zip'
                },
                'download_url': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/s1v3.zip'
            }
        ],
        'sovits_models': [
            {
                'id': 's2Gv2ProPlus',
                'name': 'SoVITS s2Gv2ProPlus',
                'download_urls': {
                    'github': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/s2Gv2ProPlus.zip',
                    'ghproxy': 'https://ghproxy.com/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/s2Gv2ProPlus.zip',
                    'ghapi': 'https://ghapi.cn/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/s2Gv2ProPlus.zip'
                },
                'download_url': 'https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/s2Gv2ProPlus.zip'
            }
        ]
    }
    
    # Find the model in recommended models
    model_info = None
    for model_type in ['base_models', 'gpt_models', 'sovits_models']:
        if model_type in recommended_models_data:
            for model in recommended_models_data[model_type]:
                if model.get('id') == model_id:
                    model_info = model
                    break
            if model_info:
                break
    
    if not model_info:
        return jsonify({'error': f'Model {model_id} not found'}), 404
    
    # Get download URL
    if 'download_urls' in model_info and download_source in model_info['download_urls']:
        download_url = model_info['download_urls'][download_source]
    else:
        download_url = model_info.get('download_url')
    
    if not download_url:
        return jsonify({'error': 'No download URL available'}), 400
    
    # Check if already downloading
    if model_id in gsv_tts_download_progress:
        return jsonify({'error': 'Model is already being downloaded', 'progress': gsv_tts_download_progress[model_id]}), 400
    
    # Initialize download progress
    gsv_tts_download_progress[model_id] = {
        'status': 'starting',
        'progress': 0,
        'downloaded': 0,
        'total': 0,
        'speed': 0,
        'error': None,
        'model_name': model_info.get('name', model_id)
    }
    
    # Get target directory
    target_dir_name = MODEL_TARGET_DIRS.get(model_id, model_id)
    target_dir = os.path.join(TTS_MODELS_DIR, target_dir_name)
    
    # Start download in background thread
    def download_worker():
        import zipfile
        import tempfile
        import shutil
        
        try:
            gsv_tts_download_progress[model_id]['status'] = 'downloading'
            
            # Create temporary directory for download
            temp_dir = tempfile.mkdtemp()
            zip_path = os.path.join(temp_dir, f'{model_id}.zip')
            
            # Download file with progress tracking
            print(ConsoleColor.info(f"Starting download of {model_info.get('name', model_id)} from {download_url}"))
            response = requests.get(download_url, stream=True, timeout=600)
            total_size = int(response.headers.get('content-length', 0))
            gsv_tts_download_progress[model_id]['total'] = total_size
            
            downloaded = 0
            chunk_size = 8192
            start_time = time.time()
            
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        gsv_tts_download_progress[model_id]['downloaded'] = downloaded
                        gsv_tts_download_progress[model_id]['progress'] = (downloaded / total_size * 100) if total_size > 0 else 0
                        
                        # Calculate download speed
                        elapsed = time.time() - start_time
                        if elapsed > 0:
                            gsv_tts_download_progress[model_id]['speed'] = downloaded / elapsed / (1024 * 1024)  # MB/s
            
            # Extract zip file
            print(ConsoleColor.info(f"Extracting {model_info.get('name', model_id)}..."))
            gsv_tts_download_progress[model_id]['status'] = 'extracting'
            gsv_tts_download_progress[model_id]['progress'] = 90
            
            # Remove existing directory if it exists
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            
            # Extract to temporary location first
            extract_temp = os.path.join(temp_dir, 'extract')
            os.makedirs(extract_temp, exist_ok=True)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_temp)
            
            # Find the extracted content and move to target location
            extracted_items = os.listdir(extract_temp)
            if len(extracted_items) == 1 and os.path.isdir(os.path.join(extract_temp, extracted_items[0])):
                # If zip contains a single directory, move its contents
                src_dir = os.path.join(extract_temp, extracted_items[0])
                shutil.move(src_dir, target_dir)
            else:
                # Otherwise move all contents
                os.makedirs(target_dir, exist_ok=True)
                for item in extracted_items:
                    src_path = os.path.join(extract_temp, item)
                    dst_path = os.path.join(target_dir, item)
                    if os.path.isdir(src_path):
                        shutil.move(src_path, dst_path)
                    else:
                        shutil.move(src_path, dst_path)
            
            # Clean up
            os.remove(zip_path)
            try:
                os.rmdir(extract_temp)
                os.rmdir(temp_dir)
            except:
                pass
            
            # Update progress
            gsv_tts_download_progress[model_id]['status'] = 'completed'
            gsv_tts_download_progress[model_id]['progress'] = 100
            
            print(ConsoleColor.success(f"Successfully downloaded and extracted {model_info.get('name', model_id)}"))
            
        except Exception as e:
            print(ConsoleColor.error(f"Failed to download {model_id}: {e}"))
            gsv_tts_download_progress[model_id]['status'] = 'error'
            gsv_tts_download_progress[model_id]['error'] = str(e)
            
            # Clean up on error
            try:
                if 'zip_path' in locals() and os.path.exists(zip_path):
                    os.remove(zip_path)
                if 'temp_dir' in locals() and os.path.exists(temp_dir):
                    import shutil
                    shutil.rmtree(temp_dir)
                # Clean up partially extracted model
                if os.path.exists(target_dir):
                    shutil.rmtree(target_dir)
            except Exception as cleanup_error:
                print(ConsoleColor.warning(f"Failed to clean up after error: {cleanup_error}"))
            
        finally:
            # Remove from download progress after 10 seconds
            time.sleep(10)
            if model_id in gsv_tts_download_progress:
                del gsv_tts_download_progress[model_id]
    
    # Start download thread
    download_thread = threading.Thread(target=download_worker, daemon=True)
    download_thread.start()
    
    return jsonify({
        'status': 'started',
        'message': f'Download started for {model_info.get("name", model_id)}'
    })

@app.route('/api/gsv-tts/download-progress/<model_id>')
def get_gsv_tts_download_progress(model_id):
    """Get download progress for a GSV-TTS model"""
    if model_id not in gsv_tts_download_progress:
        return jsonify({'error': 'No active download for this model'}), 404
    
    return jsonify(gsv_tts_download_progress[model_id])

@app.route('/api/gsv-tts/model-status/<model_id>')
def get_gsv_tts_model_status(model_id):
    """Check if a GSV-TTS model is installed"""
    target_dir_name = MODEL_TARGET_DIRS.get(model_id, model_id)
    target_dir = os.path.join(TTS_MODELS_DIR, target_dir_name)
    
    is_installed = os.path.exists(target_dir)
    
    # Check if directory has content
    has_content = False
    if is_installed:
        has_content = len(os.listdir(target_dir)) > 0
    
    return jsonify({
        'model_id': model_id,
        'installed': is_installed and has_content,
        'path': os.path.abspath(target_dir) if is_installed else None
    })

@app.route('/api/gsv-tts/upload-model', methods=['POST'])
def upload_gsv_tts_model():
    """Upload and extract GSV-TTS-Lite model files to project directory"""
    import zipfile
    import tempfile
    import shutil
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Use project directory for models
    models_dir = TTS_MODELS_DIR
    
    try:
        # Create a temporary directory for the upload
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save the uploaded file
            file_path = os.path.join(temp_dir, file.filename)
            file.save(file_path)
            
            # Check if it's a zip file
            if not file_path.endswith('.zip'):
                return jsonify({'error': 'Only zip files are supported'}), 400
            
            # Extract the zip file to a temporary location first
            extract_dir = os.path.join(temp_dir, 'extracted')
            os.makedirs(extract_dir, exist_ok=True)
            
            print(ConsoleColor.info(f"Extracting {file.filename}..."))
            
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Move extracted files to appropriate directories
            extracted_items = os.listdir(extract_dir)
            moved_files = []
            
            for item in extracted_items:
                src_path = os.path.join(extract_dir, item)
                
                # Determine target directory based on model type
                if 'gpt' in item.lower() or 's1' in item.lower():
                    dst_path = os.path.join(TTS_GPT_DIR, item)
                elif 'sovits' in item.lower() or 's2' in item.lower():
                    dst_path = os.path.join(TTS_SOVITS_DIR, item)
                elif 'hubert' in item.lower():
                    dst_path = os.path.join(models_dir, item)
                elif 'g2p' in item.lower():
                    dst_path = os.path.join(models_dir, item)
                elif 'sv' in item.lower() or 'speaker' in item.lower():
                    dst_path = os.path.join(models_dir, item)
                else:
                    dst_path = os.path.join(models_dir, item)
                
                # Remove existing directory if it exists
                if os.path.exists(dst_path):
                    if os.path.isdir(dst_path):
                        shutil.rmtree(dst_path)
                    else:
                        os.remove(dst_path)
                
                # Move the file/directory
                shutil.move(src_path, dst_path)
                moved_files.append({
                    'name': item,
                    'path': dst_path,
                    'type': 'directory' if os.path.isdir(dst_path) else 'file'
                })
            
            print(ConsoleColor.success(f"Successfully uploaded {file.filename} to project models directory"))
            
            return jsonify({
                'status': 'success',
                'message': f'Model {file.filename} uploaded and extracted successfully',
                'models_dir': models_dir,
                'moved_files': moved_files
            })
    except Exception as e:
        print(ConsoleColor.error(f"Failed to upload model: {e}"))
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/gsv-tts/available-models')
def get_gsv_tts_available_models():
    """Get available GSV-TTS-Lite models from project directory"""
    # Use project directory for models
    models_dir = TTS_MODELS_DIR
    
    # Check for available models
    available_models = {
        'chinese_hubert': {
            'available': os.path.exists(os.path.join(models_dir, 'chinese-hubert-base')),
            'path': os.path.join(models_dir, 'chinese-hubert-base')
        },
        'chinese_roberta': {
            'available': os.path.exists(os.path.join(models_dir, 'chinese-roberta-wwm-ext-large')),
            'path': os.path.join(models_dir, 'chinese-roberta-wwm-ext-large')
        },
        'g2p': {
            'available': os.path.exists(os.path.join(models_dir, 'g2p')),
            'path': os.path.join(models_dir, 'g2p')
        },
        'speaker_verification': {
            'available': os.path.exists(os.path.join(models_dir, 'sv')),
            'path': os.path.join(models_dir, 'sv')
        },
        'gpt': {
            'available': len(os.listdir(TTS_GPT_DIR)) > 0 if os.path.exists(TTS_GPT_DIR) else False,
            'path': TTS_GPT_DIR,
            'models': os.listdir(TTS_GPT_DIR) if os.path.exists(TTS_GPT_DIR) else []
        },
        'sovits': {
            'available': len(os.listdir(TTS_SOVITS_DIR)) > 0 if os.path.exists(TTS_SOVITS_DIR) else False,
            'path': TTS_SOVITS_DIR,
            'models': os.listdir(TTS_SOVITS_DIR) if os.path.exists(TTS_SOVITS_DIR) else []
        }
    }
    
    # Get reference audio files
    reference_audios = []
    if os.path.exists(TTS_REFERENCES_DIR):
        for file in os.listdir(TTS_REFERENCES_DIR):
            if file.lower().endswith(('.wav', '.mp3', '.ogg', '.flac', '.m4a')):
                reference_audios.append({
                    'name': file,
                    'path': os.path.join(TTS_REFERENCES_DIR, file),
                    'size': os.path.getsize(os.path.join(TTS_REFERENCES_DIR, file))
                })
    
    return jsonify({
        'models_dir': models_dir,
        'available_models': available_models,
        'reference_audios': reference_audios,
        'total_size_mb': sum(os.path.getsize(os.path.join(root, file)) / (1024 * 1024) 
                            for root, dirs, files in os.walk(models_dir) 
                            for file in files) if os.path.exists(models_dir) else 0
    })

@app.route('/api/translation/styles', methods=['GET'])
def get_translation_styles():
    """Get available translation styles"""
    global translation_styles
    
    # Load user presets
    user_presets = []
    try:
        if os.path.exists(USER_PRESETS_DIR):
            for file in os.listdir(USER_PRESETS_DIR):
                if file.endswith('.json'):
                    try:
                        with open(os.path.join(USER_PRESETS_DIR, file), 'r', encoding='utf-8') as f:
                            preset = json.load(f)
                            user_presets.append(preset)
                    except Exception as e:
                        print(f"Error loading user preset {file}: {e}")
    except Exception as e:
        print(f"Error loading user presets: {e}")
    
    return jsonify({
        'system_presets': translation_styles.get('presets', []),
        'user_presets': user_presets
    })

@app.route('/api/translation/style/optimize', methods=['POST'])
def optimize_translation_style():
    """Optimize translation style using AI"""
    data = request.json
    user_input = data.get('input', '')
    
    if not user_input:
        return jsonify({'error': 'Input is required'}), 400
    
    # Determine API URL based on provider
    API_URL = OLLAMA_URL
    service_name = 'Ollama'
    
    # Check if service is available
    try:
        response = requests.get(f'{API_URL}/api/tags', timeout=5)
        if response.status_code != 200:
            return jsonify({'error': f'Translation service is unavailable. Please start {service_name} service'}), 503
    except Exception as e:
        return jsonify({'error': f'Unable to connect to {service_name} service: {str(e)}'}), 503
    
    # Prompt to optimize user input
    optimization_prompt = f"Analyze the following user input and optimize it to create a clear, concise translation style instruction. The input may describe a style, occasion, or context for translation.\n\nUser input: {user_input}\n\nOptimized style instruction:"
    
    try:
        response = requests.post(
            f'{API_URL}/api/generate',
            json={
                'model': 'llama2',
                'prompt': optimization_prompt,
                'options': {
                    'temperature': 0.7,
                    'top_p': 0.9,
                    'num_predict': 100
                }
            },
            timeout=15
        )
        
        if response.status_code == 200:
            result = response.json()
            optimized_style = result.get('response', '').strip()
            
            # Generate prompt template
            prompt_template = f"Translate the following text to English with a {optimized_style} style. Maintain the original meaning while adapting the tone and expression to match the requested style.\n\nText: {{text}}\n\nTranslation:"
            
            return jsonify({
                'original_input': user_input,
                'optimized_style': optimized_style,
                'prompt_template': prompt_template
            })
        else:
            return jsonify({'error': 'Failed to optimize style'}), 500
    except Exception as e:
        return jsonify({'error': f'Error optimizing style: {str(e)}'}), 500

@app.route('/api/translation/preset/save', methods=['POST'])
def save_user_preset():
    """Save user custom preset"""
    data = request.json
    name = data.get('name', '')
    description = data.get('description', '')
    prompt_template = data.get('prompt_template', '')
    
    if not name or not prompt_template:
        return jsonify({'error': 'Name and prompt template are required'}), 400
    
    # Generate safe filename
    safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())
    preset_id = f"user_{safe_name}_{int(time.time())}"
    
    preset = {
        'id': preset_id,
        'name': name,
        'description': description,
        'type': 'custom',
        'prompt_template': prompt_template,
        'created_at': datetime.now().isoformat()
    }
    
    try:
        if not os.path.exists(USER_PRESETS_DIR):
            os.makedirs(USER_PRESETS_DIR)
        
        file_path = os.path.join(USER_PRESETS_DIR, f'{preset_id}.json')
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(preset, f, ensure_ascii=False, indent=2)
        
        return jsonify({
            'status': 'success',
            'message': 'Preset saved successfully',
            'preset': preset
        })
    except Exception as e:
        return jsonify({'error': f'Error saving preset: {str(e)}'}), 500

@app.route('/api/gsv-tts/delete-model', methods=['POST'])
def delete_gsv_tts_model():
    """Delete a GSV-TTS-Lite model from project directory"""
    import shutil
    data = request.json
    model_name = data.get('model_name')
    model_type = data.get('type', 'base')  # 'base', 'gpt', 'sovits', 'reference'
    
    if not model_name:
        return jsonify({'error': 'Model name is required'}), 400
    
    models_dir = TTS_MODELS_DIR
    
    # Determine model path based on type
    if model_type == 'gpt':
        model_path = os.path.join(TTS_GPT_DIR, model_name)
    elif model_type == 'sovits':
        model_path = os.path.join(TTS_SOVITS_DIR, model_name)
    elif model_type == 'reference':
        model_path = os.path.join(TTS_REFERENCES_DIR, model_name)
    else:
        # Base models
        model_paths = {
            'chinese_hubert': os.path.join(models_dir, 'chinese-hubert-base'),
            'chinese_roberta': os.path.join(models_dir, 'chinese-roberta-wwm-ext-large'),
            'g2p': os.path.join(models_dir, 'g2p'),
            'speaker_verification': os.path.join(models_dir, 'sv')
        }
        if model_name not in model_paths:
            return jsonify({'error': 'Invalid model name'}), 400
        model_path = model_paths[model_name]
    
    if not os.path.exists(model_path):
        return jsonify({'error': 'Model not found'}), 404
    
    try:
        if os.path.isdir(model_path):
            shutil.rmtree(model_path)
        else:
            os.remove(model_path)
        print(ConsoleColor.success(f"Successfully deleted GSV-TTS-Lite model: {model_name}"))
        return jsonify({
            'status': 'success',
            'message': f'Model {model_name} deleted successfully',
            'type': model_type
        })
    except Exception as e:
        print(ConsoleColor.error(f"Failed to delete GSV-TTS-Lite model {model_name}: {e}"))
        return jsonify({'error': str(e)}), 500

@app.route('/api/gsv-tts/upload-reference', methods=['POST'])
def upload_gsv_tts_reference():
    """Upload reference audio file for voice cloning"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Check file extension
    allowed_extensions = {'.wav', '.mp3', '.ogg', '.flac', '.m4a'}
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_extensions:
        return jsonify({'error': f'Invalid file type. Allowed: {", ".join(allowed_extensions)}'}), 400
    
    try:
        # Save to references directory
        file_path = os.path.join(TTS_REFERENCES_DIR, file.filename)
        file.save(file_path)
        
        print(ConsoleColor.success(f"Successfully uploaded reference audio: {file.filename}"))
        return jsonify({
            'status': 'success',
            'message': f'Reference audio {file.filename} uploaded successfully',
            'file': {
                'name': file.filename,
                'path': file_path,
                'size': os.path.getsize(file_path)
            }
        })
    except Exception as e:
        print(ConsoleColor.error(f"Failed to upload reference audio: {e}"))
        return jsonify({'error': str(e)}), 500

@app.route('/api/gsv-tts/references')
def get_gsv_tts_references():
    """Get all reference audio files"""
    references = []
    if os.path.exists(TTS_REFERENCES_DIR):
        for file in os.listdir(TTS_REFERENCES_DIR):
            if file.lower().endswith(('.wav', '.mp3', '.ogg', '.flac', '.m4a')):
                file_path = os.path.join(TTS_REFERENCES_DIR, file)
                references.append({
                    'name': file,
                    'path': file_path,
                    'size': os.path.getsize(file_path),
                    'modified': os.path.getmtime(file_path)
                })
    
    return jsonify({
        'references_dir': TTS_REFERENCES_DIR,
        'references': references
    })

# Available Vosk models for download
AVAILABLE_VOSK_MODELS = [
    # Chinese Models
    {
        'name': 'vosk-model-small-cn-0.22',
        'description': 'Small Chinese model (50MB) - Fast and lightweight',
        'language': 'Chinese',
        'size': '50MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip'
    },
    {
        'name': 'vosk-model-cn-0.22',
        'description': 'Medium Chinese model (1.2GB) - Better accuracy',
        'language': 'Chinese',
        'size': '1.2GB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-cn-0.22.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-cn-0.22.zip'
    },
    # English Models
    {
        'name': 'vosk-model-small-en-us-0.15',
        'description': 'Small English US model (40MB) - Fast and lightweight',
        'language': 'English (US)',
        'size': '40MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip'
    },
    {
        'name': 'vosk-model-en-us-0.22',
        'description': 'Medium English US model (1.8GB) - Better accuracy',
        'language': 'English (US)',
        'size': '1.8GB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip'
    },
    {
        'name': 'vosk-model-small-en-0.15',
        'description': 'Small English UK model (40MB) - Fast and lightweight',
        'language': 'English (UK)',
        'size': '40MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-en-0.15.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-en-0.15.zip'
    },
    {
        'name': 'vosk-model-en-0.22',
        'description': 'Medium English UK model (1.8GB) - Better accuracy',
        'language': 'English (UK)',
        'size': '1.8GB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-en-0.22.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-en-0.22.zip'
    },
    {
        'name': 'vosk-model-small-en-in-0.4',
        'description': 'Small English Indian model (40MB) - Fast and lightweight',
        'language': 'English (India)',
        'size': '40MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-en-in-0.4.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-en-in-0.4.zip'
    },
    # Japanese Models
    {
        'name': 'vosk-model-small-ja-0.22',
        'description': 'Small Japanese model (45MB) - Fast and lightweight',
        'language': 'Japanese',
        'size': '45MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-ja-0.22.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-ja-0.22.zip'
    },
    {
        'name': 'vosk-model-ja-0.22',
        'description': 'Medium Japanese model (2.4GB) - Better accuracy',
        'language': 'Japanese',
        'size': '2.4GB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-ja-0.22.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-ja-0.22.zip'
    },
    # Russian Models
    {
        'name': 'vosk-model-small-ru-0.22',
        'description': 'Small Russian model (45MB) - Fast and lightweight',
        'language': 'Russian',
        'size': '45MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip'
    },
    {
        'name': 'vosk-model-ru-0.22',
        'description': 'Medium Russian model (1.8GB) - Better accuracy',
        'language': 'Russian',
        'size': '1.8GB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-ru-0.22.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-ru-0.22.zip'
    },
    # French Models
    {
        'name': 'vosk-model-small-fr-0.22',
        'description': 'Small French model (40MB) - Fast and lightweight',
        'language': 'French',
        'size': '40MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip'
    },
    {
        'name': 'vosk-model-fr-0.22',
        'description': 'Medium French model (1.3GB) - Better accuracy',
        'language': 'French',
        'size': '1.3GB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-fr-0.22.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-fr-0.22.zip'
    },
    # German Models
    {
        'name': 'vosk-model-small-de-0.15',
        'description': 'Small German model (45MB) - Fast and lightweight',
        'language': 'German',
        'size': '45MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-de-0.15.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-de-0.15.zip'
    },
    {
        'name': 'vosk-model-de-0.21',
        'description': 'Medium German model (2.0GB) - Better accuracy',
        'language': 'German',
        'size': '2.0GB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-de-0.21.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-de-0.21.zip'
    },
    # Spanish Models
    {
        'name': 'vosk-model-small-es-0.42',
        'description': 'Small Spanish model (45MB) - Fast and lightweight',
        'language': 'Spanish',
        'size': '45MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip'
    },
    {
        'name': 'vosk-model-es-0.42',
        'description': 'Medium Spanish model (1.5GB) - Better accuracy',
        'language': 'Spanish',
        'size': '1.5GB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-es-0.42.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-es-0.42.zip'
    },
    # Portuguese Models
    {
        'name': 'vosk-model-small-pt-0.3',
        'description': 'Small Portuguese model (40MB) - Fast and lightweight',
        'language': 'Portuguese',
        'size': '40MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip'
    },
    # Italian Models
    {
        'name': 'vosk-model-small-it-0.22',
        'description': 'Small Italian model (45MB) - Fast and lightweight',
        'language': 'Italian',
        'size': '45MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-it-0.22.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-it-0.22.zip'
    },
    # Korean Models
    {
        'name': 'vosk-model-small-ko-0.22',
        'description': 'Small Korean model (50MB) - Fast and lightweight',
        'language': 'Korean',
        'size': '50MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-ko-0.22.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-ko-0.22.zip'
    },
    # Dutch Models
    {
        'name': 'vosk-model-small-nl-0.22',
        'description': 'Small Dutch model (45MB) - Fast and lightweight',
        'language': 'Dutch',
        'size': '45MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-nl-0.22.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-nl-0.22.zip'
    },
    # Turkish Models
    {
        'name': 'vosk-model-small-tr-0.3',
        'description': 'Small Turkish model (45MB) - Fast and lightweight',
        'language': 'Turkish',
        'size': '45MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-tr-0.3.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-tr-0.3.zip'
    },
    # Vietnamese Models
    {
        'name': 'vosk-model-small-vi-0.4',
        'description': 'Small Vietnamese model (40MB) - Fast and lightweight',
        'language': 'Vietnamese',
        'size': '40MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-vi-0.4.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-vi-0.4.zip'
    },
    # Polish Models
    {
        'name': 'vosk-model-small-pl-0.22',
        'description': 'Small Polish model (45MB) - Fast and lightweight',
        'language': 'Polish',
        'size': '45MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-pl-0.22.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-pl-0.22.zip'
    },
    # Czech Models
    {
        'name': 'vosk-model-small-cs-0.4',
        'description': 'Small Czech model (45MB) - Fast and lightweight',
        'language': 'Czech',
        'size': '45MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-cs-0.4.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-cs-0.4.zip'
    },
    # Ukrainian Models
    {
        'name': 'vosk-model-small-uk-0.4',
        'description': 'Small Ukrainian model (45MB) - Fast and lightweight',
        'language': 'Ukrainian',
        'size': '45MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-uk-0.4.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-uk-0.4.zip'
    },
    # Farsi (Persian) Models
    {
        'name': 'vosk-model-small-fa-0.5',
        'description': 'Small Farsi model (45MB) - Fast and lightweight',
        'language': 'Farsi (Persian)',
        'size': '45MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-fa-0.5.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-fa-0.5.zip'
    },
    # Hindi Models
    {
        'name': 'vosk-model-small-hi-0.22',
        'description': 'Small Hindi model (50MB) - Fast and lightweight',
        'language': 'Hindi',
        'size': '50MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-hi-0.22.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-hi-0.22.zip'
    },
    # Indonesian Models
    {
        'name': 'vosk-model-small-id-0.3',
        'description': 'Small Indonesian model (40MB) - Fast and lightweight',
        'language': 'Indonesian',
        'size': '40MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-id-0.3.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-id-0.3.zip'
    },
    # Swedish Models
    {
        'name': 'vosk-model-small-sv-0.15',
        'description': 'Small Swedish model (45MB) - Fast and lightweight',
        'language': 'Swedish',
        'size': '45MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-sv-0.15.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-sv-0.15.zip'
    },
    # Romanian Models
    {
        'name': 'vosk-model-small-ro-0.4',
        'description': 'Small Romanian model (45MB) - Fast and lightweight',
        'language': 'Romanian',
        'size': '45MB',
        'url': 'https://alphacephei.com/vosk/models/vosk-model-small-ro-0.4.zip',
        'download_url': 'https://alphacephei.com/vosk/models/vosk-model-small-ro-0.4.zip'
    }
]

# Model download progress tracking
download_progress = {}

@app.route('/api/available-vosk-models')
def get_available_vosk_models():
    """Get list of available Vosk models for download"""
    installed_models = get_vosk_models()
    installed_names = {m['name'] for m in installed_models}
    
    # Mark which models are already installed
    for model in AVAILABLE_VOSK_MODELS:
        model['installed'] = model['name'] in installed_names
        model['downloading'] = model['name'] in download_progress
    
    return jsonify(AVAILABLE_VOSK_MODELS)

@app.route('/api/download-model', methods=['POST'])
def download_model():
    """Download a Vosk model"""
    data = request.json
    model_name = data.get('model_name')
    
    if not model_name:
        return jsonify({'error': 'Model name is required'}), 400
    
    # Find model in available models
    model_info = None
    for model in AVAILABLE_VOSK_MODELS:
        if model['name'] == model_name:
            model_info = model
            break
    
    if not model_info:
        return jsonify({'error': 'Model not found in available models'}), 404
    
    # Check if already downloading
    if model_name in download_progress:
        return jsonify({'error': 'Model is already being downloaded', 'progress': download_progress[model_name]}), 400
    
    # Initialize download progress
    download_progress[model_name] = {
        'status': 'starting',
        'progress': 0,
        'downloaded': 0,
        'total': 0,
        'speed': 0,
        'error': None
    }
    
    # Start download in background thread
    def download_worker():
        import zipfile
        import tempfile
        
        try:
            download_progress[model_name]['status'] = 'downloading'
            
            # Create temporary directory for download
            temp_dir = tempfile.mkdtemp()
            zip_path = os.path.join(temp_dir, f'{model_name}.zip')
            
            # Download file with progress tracking
            print(ConsoleColor.info(f"Starting download of {model_name} from {model_info['download_url']}"))
            response = requests.get(model_info['download_url'], stream=True, timeout=300)
            total_size = int(response.headers.get('content-length', 0))
            download_progress[model_name]['total'] = total_size
            
            downloaded = 0
            chunk_size = 8192
            start_time = time.time()
            
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        download_progress[model_name]['downloaded'] = downloaded
                        download_progress[model_name]['progress'] = (downloaded / total_size * 100) if total_size > 0 else 0
                        
                        # Calculate download speed
                        elapsed = time.time() - start_time
                        if elapsed > 0:
                            download_progress[model_name]['speed'] = downloaded / elapsed / (1024 * 1024)  # MB/s
            
            # Extract zip file
            print(ConsoleColor.info(f"Extracting {model_name}..."))
            download_progress[model_name]['status'] = 'extracting'
            download_progress[model_name]['progress'] = 90
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(VOSK_MODELS_DIR)
            
            # Verify extraction
            extracted_path = os.path.join(VOSK_MODELS_DIR, model_name)
            if not os.path.exists(extracted_path):
                raise Exception(f'Failed to extract model to {extracted_path}')
            
            # Check for required directories
            required_dirs = ['am', 'conf', 'graph']
            for req_dir in required_dirs:
                if not os.path.exists(os.path.join(extracted_path, req_dir)):
                    raise Exception(f'Extracted model is missing required directory: {req_dir}')
            
            # Clean up
            os.remove(zip_path)
            os.rmdir(temp_dir)
            
            # Update progress
            download_progress[model_name]['status'] = 'completed'
            download_progress[model_name]['progress'] = 100
            
            print(ConsoleColor.success(f"Successfully downloaded and extracted {model_name}"))
            
        except Exception as e:
            print(ConsoleColor.error(f"Failed to download {model_name}: {e}"))
            download_progress[model_name]['status'] = 'error'
            download_progress[model_name]['error'] = str(e)
            
            # Clean up on error
            try:
                if 'zip_path' in locals() and os.path.exists(zip_path):
                    os.remove(zip_path)
                if 'temp_dir' in locals() and os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
                # Clean up partially extracted model
                extracted_path = os.path.join(VOSK_MODELS_DIR, model_name)
                if os.path.exists(extracted_path):
                    import shutil
                    shutil.rmtree(extracted_path)
            except Exception as cleanup_error:
                print(ConsoleColor.warning(f"Failed to clean up after error: {cleanup_error}"))
            
        finally:
            # Remove from download progress after 5 seconds
            time.sleep(5)
            if model_name in download_progress:
                del download_progress[model_name]
    
    # Start download thread
    download_thread = threading.Thread(target=download_worker, daemon=True)
    download_thread.start()
    
    return jsonify({
        'status': 'started',
        'message': f'Download started for {model_name}'
    })

@app.route('/api/download-progress/<model_name>')
def get_download_progress(model_name):
    """Get download progress for a model"""
    if model_name not in download_progress:
        return jsonify({'error': 'No active download for this model'}), 404
    
    return jsonify(download_progress[model_name])

@app.route('/api/delete-model', methods=['DELETE'])
def delete_model():
    """Delete a Vosk model"""
    data = request.json
    model_name = data.get('model_name')
    
    if not model_name:
        return jsonify({'error': 'Model name is required'}), 400
    
    # Find model path
    model_path = os.path.join(VOSK_MODELS_DIR, model_name)
    
    if not os.path.exists(model_path):
        return jsonify({'error': 'Model not found'}), 404
    
    # Check if it's the default model
    if os.path.abspath(model_path) == os.path.abspath(DEFAULT_MODEL_PATH):
        return jsonify({'error': 'Cannot delete the default model'}), 400
    
    try:
        import shutil
        shutil.rmtree(model_path)
        print(ConsoleColor.success(f"Successfully deleted model: {model_name}"))
        return jsonify({
            'status': 'success',
            'message': f'Model {model_name} deleted successfully'
        })
    except Exception as e:
        print(ConsoleColor.error(f"Failed to delete model {model_name}: {e}"))
        return jsonify({'error': str(e)}), 500

@app.route('/api/model-status/<model_name>')
def get_model_status(model_name):
    """Get status of a specific model"""
    model_path = os.path.join(VOSK_MODELS_DIR, model_name)
    
    if not os.path.exists(model_path):
        return jsonify({
            'installed': False,
            'status': 'not_installed'
        })
    
    # Check if model is valid
    required_dirs = ['am', 'conf', 'graph']
    is_valid = all(os.path.exists(os.path.join(model_path, d)) for d in required_dirs)
    
    # Calculate model size
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(model_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                total_size += os.path.getsize(fp)
            except:
                pass
    
    size_mb = total_size / (1024 * 1024)
    
    return jsonify({
        'installed': True,
        'valid': is_valid,
        'status': 'installed' if is_valid else 'invalid',
        'size_mb': round(size_mb, 2),
        'path': os.path.abspath(model_path)
    })

@app.route('/api/models-directory-size')
def get_models_directory_size():
    """Get total size of models directory"""
    total_size = 0
    if os.path.exists(VOSK_MODELS_DIR):
        for dirpath, dirnames, filenames in os.walk(VOSK_MODELS_DIR):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total_size += os.path.getsize(fp)
                except:
                    pass
    
    size_gb = total_size / (1024 * 1024 * 1024)
    return jsonify({
        'total_size_gb': round(size_gb, 2),
        'total_size_mb': round(total_size / (1024 * 1024), 2)
    })


# vLLM Model Management APIs
@app.route('/api/vllm-models')
def get_vllm_models_api():
    """Get list of locally installed vLLM models"""
    models = get_local_vllm_models()
    return jsonify({
        'models': models,
        'count': len(models),
        'models_dir': VLLM_MODELS_DIR
    })


@app.route('/api/vllm-models/loaded')
def get_loaded_vllm_models():
    """Get list of currently loaded vLLM models (in GPU/CPU)"""
    
    # Get vLLM loaded models
    vllm_loaded = []
    if check_vllm_health():
        try:
            response = requests.get(f'{VLLM_URL}/api/loaded_models', timeout=2)
            if response.ok:
                vllm_loaded = response.json().get('models', [])
        except:
            pass
    
    # Get GSV-TTS loaded models
    gsv_loaded = []
    try:
        # Check if GPT models are loaded (in gpt_models dict)
        if hasattr(gsv_tts, 'gpt_models') and gsv_tts.gpt_models:
            for model_name in gsv_tts.gpt_models.keys():
                gsv_loaded.append({
                    'name': f'GPT Model ({os.path.basename(model_name)})',
                    'type': 'gsv-tts',
                    'location': 'GPU' if torch.cuda.is_available() else 'CPU',
                    'status': 'loaded'
                })
        # Check if SoVITS models are loaded (in sovits_models dict)
        if hasattr(gsv_tts, 'sovits_models') and gsv_tts.sovits_models:
            for model_name in gsv_tts.sovits_models.keys():
                gsv_loaded.append({
                    'name': f'SoVITS Model ({os.path.basename(model_name)})',
                    'type': 'gsv-tts',
                    'location': 'GPU' if torch.cuda.is_available() else 'CPU',
                    'status': 'loaded'
                })
    except:
        pass
    
    # Get Vosk loaded models
    vosk_loaded = []
    if 'model' in globals() and 'current_model_path' in globals() and current_model_path:
        vosk_loaded.append({
            'name': os.path.basename(current_model_path),
            'type': 'vosk',
            'location': 'CPU',  # Vosk runs on CPU
            'status': 'loaded'
        })
    
    return jsonify({
        'vllm': vllm_loaded,
        'gsv_tts': gsv_loaded,
        'vosk': vosk_loaded,
        'total': len(vllm_loaded) + len(gsv_loaded) + len(vosk_loaded)
    })


@app.route('/api/vllm-models/unload-all', methods=['POST'])
def unload_all_models():
    """Unload all loaded models to free GPU memory"""
    try:
        # Unload vLLM models
        if check_vllm_health():
            try:
                response = requests.post(f'{VLLM_URL}/api/unload_all', timeout=5)
                if response.ok:
                    print(ConsoleColor.success('vLLM models unloaded successfully'))
            except Exception as e:
                print(ConsoleColor.warning(f'Failed to unload vLLM models: {e}'))
        
        # Unload GSV-TTS models
        global gsv_tts
        try:
            # Clear GPT models dict
            if hasattr(gsv_tts, 'gpt_models'):
                gsv_tts.gpt_models.clear()
            # Clear SoVITS models dict
            if hasattr(gsv_tts, 'sovits_models'):
                gsv_tts.sovits_models.clear()
            # Clear cnhubert if loaded
            if hasattr(gsv_tts, 'cnhubert_model'):
                gsv_tts.cnhubert_model = None
            # Clear speaker encoder if loaded
            if hasattr(gsv_tts, 'sv_model'):
                gsv_tts.sv_model = None
            # Clear CUDA cache if available
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            print(ConsoleColor.success('GSV-TTS models unloaded successfully'))
        except Exception as e:
            print(ConsoleColor.warning(f'Failed to unload GSV-TTS models: {e}'))
        
        # Vosk models are loaded on demand and don't need explicit unloading
        
        return jsonify({
            'status': 'success',
            'message': 'All models unloaded successfully'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to unload models: {str(e)}'
        }), 500


@app.route('/api/vllm-models/recommended')
def get_vllm_recommended_models():
    """Get list of recommended vLLM models organized by vendor"""
    recommended = get_recommended_vllm_models()
    installed = get_local_vllm_models()
    installed_ids = {m['name'] for m in installed}
    
    # Mark installed models for each vendor
    for vendor_key, vendor_data in recommended.items():
        for model in vendor_data['models']:
            model['installed'] = model['id'] in installed_ids
            if model['id'] in VLLM_DOWNLOAD_PROGRESS:
                model['download_progress'] = VLLM_DOWNLOAD_PROGRESS[model['id']]
    
    return jsonify({
        'vendors': recommended
    })


@app.route('/api/vllm-models/download', methods=['POST'])
def download_vllm_model():
    """Download a vLLM model from HuggingFace or ModelScope with speed optimization"""
    data = request.json
    model_id = data.get('model_id')
    source = data.get('source', 'huggingface')  # 'huggingface', 'huggingface-official', or 'modelscope'
    use_official = data.get('use_official', False)  # Whether to use official HF (not mirror)
    
    if not model_id:
        return jsonify({'error': 'Model ID is required'}), 400
    
    # Check if already downloading
    if model_id in VLLM_DOWNLOAD_PROGRESS and VLLM_DOWNLOAD_PROGRESS[model_id].get('status') == 'downloading':
        return jsonify({
            'error': 'Model is already being downloaded',
            'progress': VLLM_DOWNLOAD_PROGRESS[model_id]
        }), 400
    
    # Check if already installed
    local_models = get_local_vllm_models()
    if any(m['name'] == model_id for m in local_models):
        return jsonify({'error': 'Model is already installed'}), 400
    
    # Initialize progress tracking
    VLLM_DOWNLOAD_PROGRESS[model_id] = {
        'status': 'preparing',
        'progress': 0,
        'downloaded': 0,
        'total': 0,
        'speed': 0,
        'start_time': time.time()
    }
    
    # Start download in background thread
    def download_model_thread():
        try:
            import subprocess
            import sys
            
            # Ensure models directory exists in project folder
            target_dir = os.path.join(VLLM_MODELS_DIR, model_id.replace('/', '--'))
            os.makedirs(target_dir, exist_ok=True)
            
            VLLM_DOWNLOAD_PROGRESS[model_id]['status'] = 'downloading'
            VLLM_DOWNLOAD_PROGRESS[model_id]['target_dir'] = target_dir
            
            print(ConsoleColor.info(f"Starting download of {model_id} from {source} (official={use_official})..."))
            print(ConsoleColor.info(f"Target directory: {target_dir}"))
            
            # Check if aria2c is available
            def is_aria2c_available():
                try:
                    subprocess.run(['aria2c', '--version'], capture_output=True, timeout=2)
                    return True
                except:
                    return False
            
            aria2c_available = is_aria2c_available()
            
            if aria2c_available:
                print(ConsoleColor.success("✓ aria2c detected, using for faster downloads"))
                
                # Use aria2c for faster downloads
                import tempfile
                import json
                
                # For HuggingFace, use aria2c directly
                if source != 'modelscope':
                    # First get the download URLs using huggingface_hub
                    url_cmd = [
                        sys.executable, '-c',
                        f'''
import os
import sys
import json
from huggingface_hub import HfApi

# Set HF endpoint
if "{use_official}" == "True":
    os.environ['HF_ENDPOINT'] = 'https://huggingface.co'
else:
    os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

api = HfApi()
files = api.list_files_info("{model_id}")
download_urls = []
for file_info in files:
    if hasattr(file_info, 'download_url') and file_info.download_url:
        download_urls.append({
            'url': file_info.download_url,
            'path': file_info.path,
            'size': file_info.size if hasattr(file_info, 'size') else 0
        })
print(json.dumps(download_urls))
                        '''
                    ]
                    
                    # Get download URLs
                    url_process = subprocess.run(url_cmd, capture_output=True, text=True, env=env)
                    
                    try:
                        download_urls = json.loads(url_process.stdout)
                        
                        # Create aria2c input file
                        aria2c_input_file = os.path.join(tempfile.gettempdir(), f"aria2c_input_{model_id.replace('/', '_')}.txt")
                        with open(aria2c_input_file, 'w', encoding='utf-8') as f:
                            for item in download_urls:
                                url = item['url']
                                path = os.path.join(target_dir, item['path'])
                                f.write(f"{url}\n  out={path}\n  dir={target_dir}\n")
                        
                        # Build aria2c command
                        cmd = [
                            'aria2c',
                            '--input-file', aria2c_input_file,
                            '--dir', target_dir,
                            '--continue',
                            '--max-concurrent-downloads', '16',
                            '--split', '16',
                            '--max-connection-per-server', '16',
                            '--min-split-size', '1M',
                            '--file-allocation', 'none',
                            '--async-dns', 'true',
                            '--remote-time',
                            '--summary-interval', '1',
                            '--console-log-level', 'info'
                        ]
                    except:
                        # Fall back to original method if aria2c fails
                        aria2c_available = False
            
            if not aria2c_available:
                print(ConsoleColor.info("aria2c not available, using original download method"))
                
                # Use original download method
                
            if source == 'modelscope':
                # ModelScope download with optimizations
                env = os.environ.copy()
                env['MODELSCOPE_CACHE'] = VLLM_MODELS_DIR
                # Enable ModelScope multi-thread download
                env['MODELSCOPE_DOWNLOAD_THREADS'] = '8'
                env['MODELSCOPE_DOWNLOAD_TIMEOUT'] = '300'
                
                cmd = [
                    sys.executable, '-c',
                    f'''
import os
import sys
os.environ['MODELSCOPE_CACHE'] = "{VLLM_MODELS_DIR}"
os.environ['MODELSCOPE_DOWNLOAD_THREADS'] = '8'
os.environ['MODELSCOPE_DOWNLOAD_TIMEOUT'] = '300'
from modelscope import snapshot_download
snapshot_download("{model_id}", cache_dir="{VLLM_MODELS_DIR}", local_files_only=False)
                    '''
                ]
            else:
                # HuggingFace download with speed optimizations
                env = os.environ.copy()
                
                # Set HF cache to project directory
                env['HF_HOME'] = os.path.join(BASE_DIR, '.cache', 'huggingface')
                env['HF_HUB_CACHE'] = os.path.join(BASE_DIR, '.cache', 'huggingface', 'hub')
                env['TRANSFORMERS_CACHE'] = os.path.join(BASE_DIR, '.cache', 'transformers')
                
                # Determine HF endpoint based on source selection
                if use_official:
                    # Use official HuggingFace (no mirror)
                    env['HF_ENDPOINT'] = 'https://huggingface.co'
                    print(ConsoleColor.info(f"Using HuggingFace Official (huggingface.co)"))
                else:
                    # Use mirror for China (default) - try multiple mirrors
                    hf_endpoints = [
                        'https://hf-mirror.com',
                        'https://huggingface.co',
                        'https://hf-api.gitee.com',
                    ]
                    # Use provided endpoint or default to mirror
                    if 'HF_ENDPOINT' not in env:
                        env['HF_ENDPOINT'] = hf_endpoints[0]
                    print(ConsoleColor.info(f"Using HF-Mirror ({env.get('HF_ENDPOINT', 'hf-mirror.com')})"))
                
                # Enable multi-thread download
                env['HF_HUB_ENABLE_HF_TRANSFER'] = '1'
                
                cmd = [
                    sys.executable, '-c',
                    f'''
import os
import sys

# Set all cache directories to project folder
base_dir = r"{BASE_DIR}"
os.environ['HF_HOME'] = os.path.join(base_dir, '.cache', 'huggingface')
os.environ['HF_HUB_CACHE'] = os.path.join(base_dir, '.cache', 'huggingface', 'hub')
os.environ['TRANSFORMERS_CACHE'] = os.path.join(base_dir, '.cache', 'transformers')

# Set HF endpoint based on user selection
if "{use_official}" == "True":
    os.environ['HF_ENDPOINT'] = 'https://huggingface.co'
else:
    os.environ['HF_ENDPOINT'] = os.environ.get('HF_ENDPOINT', 'https://hf-mirror.com')

# Enable faster downloads
os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '1'

from huggingface_hub import snapshot_download
from huggingface_hub.constants import HUGGINGFACE_HUB_CACHE

print(f"Downloading to: {r"{target_dir}"}")
print(f"HF Endpoint: {{os.environ.get('HF_ENDPOINT', 'default')}}")

# Download with optimized settings
snapshot_download(
    "{model_id}",
    local_dir=r"{target_dir}",
    local_dir_use_symlinks=False,
    resume_download=True,
    max_workers=8,
    tqdm_class=None
)
                    '''
                ]
            
            # Run download process with optimized buffer
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                bufsize=1024*1024  # 1MB buffer for better performance
            )
            
            # Monitor progress with improved accuracy
            last_size = 0
            last_time = time.time()
            check_interval = 1.0  # Check every second for more responsive updates
            
            while process.poll() is None:
                time.sleep(check_interval)
                if os.path.exists(target_dir):
                    try:
                        current_size = sum(
                            os.path.getsize(os.path.join(dirpath, f))
                            for dirpath, dirnames, filenames in os.walk(target_dir)
                            for f in filenames
                            if os.path.exists(os.path.join(dirpath, f))
                        )
                        
                        # Get model size from config if available
                        config_path = os.path.join(target_dir, 'config.json')
                        estimated_total = 16 * 1024 * 1024 * 1024  # Default 16GB for 7B model
                        
                        # Try to get actual size from model info
                        if '7b' in model_id.lower() or '7B' in model_id:
                            estimated_total = 14 * 1024 * 1024 * 1024  # ~14GB
                        elif '13b' in model_id.lower() or '13B' in model_id:
                            estimated_total = 26 * 1024 * 1024 * 1024  # ~26GB
                        elif '70b' in model_id.lower() or '70B' in model_id:
                            estimated_total = 140 * 1024 * 1024 * 1024  # ~140GB
                        
                        progress = min((current_size / estimated_total) * 100, 99)
                        
                        VLLM_DOWNLOAD_PROGRESS[model_id]['downloaded'] = current_size
                        VLLM_DOWNLOAD_PROGRESS[model_id]['total'] = estimated_total
                        VLLM_DOWNLOAD_PROGRESS[model_id]['progress'] = round(progress, 2)
                        
                        # Calculate speed with smoothing
                        current_time = time.time()
                        time_delta = current_time - last_time
                        if time_delta > 0:
                            size_delta = current_size - last_size
                            speed = (size_delta / time_delta) / (1024 * 1024)  # MB/s
                            # Smooth the speed reading
                            old_speed = VLLM_DOWNLOAD_PROGRESS[model_id].get('speed', 0)
                            VLLM_DOWNLOAD_PROGRESS[model_id]['speed'] = round((old_speed * 0.7 + speed * 0.3), 2)
                        
                        last_size = current_size
                        last_time = current_time
                    except Exception as e:
                        pass  # Ignore errors during size calculation
            
            # Check result
            stdout, stderr = process.communicate()
            stdout_str = stdout.decode('utf-8', errors='ignore')
            stderr_str = stderr.decode('utf-8', errors='ignore')
            
            if process.returncode != 0:
                error_msg = stderr_str[:500] if stderr_str else stdout_str[:500]
                print(ConsoleColor.error(f"Failed to download {model_id}: {error_msg}"))
                VLLM_DOWNLOAD_PROGRESS[model_id]['status'] = 'error'
                VLLM_DOWNLOAD_PROGRESS[model_id]['error'] = error_msg
                return
            
            # Success
            VLLM_DOWNLOAD_PROGRESS[model_id]['status'] = 'completed'
            VLLM_DOWNLOAD_PROGRESS[model_id]['progress'] = 100
            print(ConsoleColor.success(f"Successfully downloaded {model_id} to {target_dir}"))
            
            # Emit socket event
            socketio.emit('vllm_model_download_complete', {
                'model_id': model_id,
                'target_dir': target_dir
            })
            
        except Exception as e:
            print(ConsoleColor.error(f"Error downloading {model_id}: {e}"))
            VLLM_DOWNLOAD_PROGRESS[model_id]['status'] = 'error'
            VLLM_DOWNLOAD_PROGRESS[model_id]['error'] = str(e)
    
    # Start download thread
    download_thread = threading.Thread(target=download_model_thread, name=f'download_{model_id}')
    download_thread.daemon = True
    download_thread.start()
    
    return jsonify({
        'message': f'Download started for {model_id}',
        'model_id': model_id,
        'status': 'downloading',
        'target_dir': os.path.join(VLLM_MODELS_DIR, model_id.replace('/', '--'))
    })


@app.route('/api/vllm-models/download-progress/<model_id>')
def get_vllm_download_progress(model_id):
    """Get download progress for a vLLM model"""
    if model_id not in VLLM_DOWNLOAD_PROGRESS:
        return jsonify({'error': 'No active download for this model'}), 404
    
    return jsonify(VLLM_DOWNLOAD_PROGRESS[model_id])


@app.route('/api/vllm-models/delete', methods=['POST'])
def delete_vllm_model():
    """Delete a locally installed vLLM model"""
    data = request.json
    model_name = data.get('model_name')
    
    if not model_name:
        return jsonify({'error': 'Model name is required'}), 400
    
    # Security check: prevent directory traversal
    if '..' in model_name or model_name.startswith('/'):
        return jsonify({'error': 'Invalid model name'}), 400
    
    model_path = os.path.join(VLLM_MODELS_DIR, model_name)
    
    if not os.path.exists(model_path):
        return jsonify({'error': 'Model not found'}), 404
    
    try:
        import shutil
        shutil.rmtree(model_path)
        print(ConsoleColor.success(f"Deleted model: {model_name}"))
        return jsonify({
            'message': f'Model {model_name} deleted successfully',
            'model_name': model_name
        })
    except Exception as e:
        return jsonify({'error': f'Failed to delete model: {str(e)}'}), 500


@app.route('/api/vllm-models/cancel-download', methods=['POST'])
def cancel_vllm_download():
    """Cancel an ongoing model download"""
    data = request.json
    model_id = data.get('model_id')
    
    if not model_id or model_id not in VLLM_DOWNLOAD_PROGRESS:
        return jsonify({'error': 'No active download found'}), 404
    
    # Mark as cancelled
    VLLM_DOWNLOAD_PROGRESS[model_id]['status'] = 'cancelled'
    
    # Note: Actual process termination would require storing the process object
    # For now, we'll just mark it as cancelled and clean up partial files
    
    # Clean up partial download
    target_dir = VLLM_DOWNLOAD_PROGRESS[model_id].get('target_dir')
    if target_dir and os.path.exists(target_dir):
        try:
            import shutil
            shutil.rmtree(target_dir)
        except:
            pass
    
    return jsonify({
        'message': f'Download cancelled for {model_id}',
        'model_id': model_id
    })


@app.route('/api/vllm-models/test-sources', methods=['GET'])
def test_vllm_download_sources():
    """Test download speed for different HuggingFace mirror sources"""
    import concurrent.futures
    import requests
    
    # List of HF mirror sources to test
    sources = [
        {'name': 'hf-mirror', 'endpoint': 'https://hf-mirror.com', 'description': 'HF Mirror (China)'},
        {'name': 'huggingface', 'endpoint': 'https://huggingface.co', 'description': 'HuggingFace Official'},
        {'name': 'gitee', 'endpoint': 'https://hf-api.gitee.com', 'description': 'Gitee Mirror (China)'},
    ]
    
    # Test model - using a small file for quick testing
    test_model = 'bert-base-uncased'
    test_file = 'config.json'
    
    results = []
    
    def test_source(source):
        """Test a single source"""
        start_time = time.time()
        try:
            endpoint = source['endpoint']
            url = f"{endpoint}/{test_model}/resolve/main/{test_file}"
            
            # Try to download a small file with timeout
            response = requests.get(url, timeout=10, stream=True)
            
            if response.status_code == 200:
                # Download first 10KB to measure speed
                downloaded = 0
                chunk_size = 1024
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        downloaded += len(chunk)
                        if downloaded >= 10 * 1024:  # 10KB
                            break
                
                elapsed = time.time() - start_time
                speed = (downloaded / elapsed) / 1024  # KB/s
                
                return {
                    'name': source['name'],
                    'endpoint': source['endpoint'],
                    'description': source['description'],
                    'status': 'available',
                    'speed_kbps': round(speed, 2),
                    'response_time_ms': round(elapsed * 1000, 2)
                }
            else:
                return {
                    'name': source['name'],
                    'endpoint': source['endpoint'],
                    'description': source['description'],
                    'status': 'unavailable',
                    'error': f'HTTP {response.status_code}'
                }
        except requests.exceptions.Timeout:
            return {
                'name': source['name'],
                'endpoint': source['endpoint'],
                'description': source['description'],
                'status': 'timeout',
                'error': 'Connection timeout'
            }
        except Exception as e:
            return {
                'name': source['name'],
                'endpoint': source['endpoint'],
                'description': source['description'],
                'status': 'error',
                'error': str(e)[:100]
            }
    
    # Test all sources in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_to_source = {executor.submit(test_source, source): source for source in sources}
        for future in concurrent.futures.as_completed(future_to_source):
            result = future.result()
            results.append(result)
    
    # Sort by speed (available sources first, then by speed)
    results.sort(key=lambda x: (
        0 if x['status'] == 'available' else 1,
        -x.get('speed_kbps', 0)
    ))
    
    # Get recommended source
    recommended = next((r for r in results if r['status'] == 'available'), None)
    
    return jsonify({
        'sources': results,
        'recommended': recommended['name'] if recommended else None,
        'test_model': test_model,
        'test_file': test_file
    })


TTS_VOICES = {
    'english': [
        {'id': 'en-US-JennyNeural', 'name': 'Jenny (US Female)', 'gender': 'Female', 'language': 'English (US)'},
        {'id': 'en-US-GuyNeural', 'name': 'Guy (US Male)', 'gender': 'Male', 'language': 'English (US)'},
        {'id': 'en-US-AriaNeural', 'name': 'Aria (US Female)', 'gender': 'Female', 'language': 'English (US)'},
        {'id': 'en-US-DavisNeural', 'name': 'Davis (US Male)', 'gender': 'Male', 'language': 'English (US)'},
        {'id': 'en-US-AmberNeural', 'name': 'Amber (US Female)', 'gender': 'Female', 'language': 'English (US)'},
        {'id': 'en-US-AnaNeural', 'name': 'Ana (US Female)', 'gender': 'Female', 'language': 'English (US)'},
        {'id': 'en-US-BrandonNeural', 'name': 'Brandon (US Male)', 'gender': 'Male', 'language': 'English (US)'},
        {'id': 'en-US-ChristopherNeural', 'name': 'Christopher (US Male)', 'gender': 'Male', 'language': 'English (US)'},
        {'id': 'en-US-EmmaNeural', 'name': 'Emma (US Female)', 'gender': 'Female', 'language': 'English (US)'},
        {'id': 'en-US-EricNeural', 'name': 'Eric (US Male)', 'gender': 'Male', 'language': 'English (US)'},
        {'id': 'en-GB-SoniaNeural', 'name': 'Sonia (UK Female)', 'gender': 'Female', 'language': 'English (UK)'},
        {'id': 'en-GB-RyanNeural', 'name': 'Ryan (UK Male)', 'gender': 'Male', 'language': 'English (UK)'},
        {'id': 'en-GB-MiaNeural', 'name': 'Mia (UK Female)', 'gender': 'Female', 'language': 'English (UK)'},
    ],
    'chinese': [
        {'id': 'zh-CN-XiaoxiaoNeural', 'name': '晓晓 (女声)', 'gender': 'Female', 'language': 'Chinese (CN)'},
        {'id': 'zh-CN-YunxiNeural', 'name': '云希 (男声)', 'gender': 'Male', 'language': 'Chinese (CN)'},
        {'id': 'zh-CN-YunjianNeural', 'name': '云健 (男声)', 'gender': 'Male', 'language': 'Chinese (CN)'},
        {'id': 'zh-CN-XiaoyiNeural', 'name': '晓伊 (女声)', 'gender': 'Female', 'language': 'Chinese (CN)'},
        {'id': 'zh-CN-YunyangNeural', 'name': '云扬 (男声)', 'gender': 'Male', 'language': 'Chinese (CN)'},
        {'id': 'zh-CN-XiaochenNeural', 'name': '晓辰 (女声)', 'gender': 'Female', 'language': 'Chinese (CN)'},
        {'id': 'zh-CN-XiaohanNeural', 'name': '晓涵 (女声)', 'gender': 'Female', 'language': 'Chinese (CN)'},
        {'id': 'zh-CN-XiaomengNeural', 'name': '晓梦 (女声)', 'gender': 'Female', 'language': 'Chinese (CN)'},
        {'id': 'zh-CN-XiaomoNeural', 'name': '晓墨 (女声)', 'gender': 'Female', 'language': 'Chinese (CN)'},
        {'id': 'zh-CN-XiaoruiNeural', 'name': '晓睿 (女声)', 'gender': 'Female', 'language': 'Chinese (CN)'},
        {'id': 'zh-CN-XiaoshuangNeural', 'name': '晓双 (女声)', 'gender': 'Female', 'language': 'Chinese (CN)'},
        {'id': 'zh-CN-XiaoxuanNeural', 'name': '晓萱 (女声)', 'gender': 'Female', 'language': 'Chinese (CN)'},
        {'id': 'zh-CN-XiaoyanNeural', 'name': '晓妍 (女声)', 'gender': 'Female', 'language': 'Chinese (CN)'},
        {'id': 'zh-CN-XiaoyouNeural', 'name': '晓悠 (女声)', 'gender': 'Female', 'language': 'Chinese (CN)'},
        {'id': 'zh-CN-YunfengNeural', 'name': '云枫 (男声)', 'gender': 'Male', 'language': 'Chinese (CN)'},
        {'id': 'zh-CN-YunhaoNeural', 'name': '云皓 (男声)', 'gender': 'Male', 'language': 'Chinese (CN)'},
        {'id': 'zh-CN-YunxiaNeural', 'name': '云夏 (男声)', 'gender': 'Male', 'language': 'Chinese (CN)'},
        {'id': 'zh-CN-YunyeNeural', 'name': '云野 (男声)', 'gender': 'Male', 'language': 'Chinese (CN)'},
        {'id': 'zh-CN-YunzeNeural', 'name': '云泽 (男声)', 'gender': 'Male', 'language': 'Chinese (CN)'},
        {'id': 'zh-HK-HiuGaaiNeural', 'name': '曉佳 (粤语女声)', 'gender': 'Female', 'language': 'Chinese (HK)'},
        {'id': 'zh-HK-WanLungNeural', 'name': '雲龍 (粤语男声)', 'gender': 'Male', 'language': 'Chinese (HK)'},
        {'id': 'zh-TW-HsiaoChenNeural', 'name': '曉臻 (台湾女声)', 'gender': 'Female', 'language': 'Chinese (TW)'},
        {'id': 'zh-TW-YunJheNeural', 'name': '雲哲 (台湾男声)', 'gender': 'Male', 'language': 'Chinese (TW)'},
    ],
    'japanese': [
        {'id': 'ja-JP-NanamiNeural', 'name': 'Nanami (女声)', 'gender': 'Female', 'language': 'Japanese'},
        {'id': 'ja-JP-KeitaNeural', 'name': 'Keita (男声)', 'gender': 'Male', 'language': 'Japanese'},
    ],
    'korean': [
        {'id': 'ko-KR-SunHiNeural', 'name': 'SunHi (女声)', 'gender': 'Female', 'language': 'Korean'},
        {'id': 'ko-KR-InJoonNeural', 'name': 'InJoon (男声)', 'gender': 'Male', 'language': 'Korean'},
    ],
    'french': [
        {'id': 'fr-FR-DeniseNeural', 'name': 'Denise (女声)', 'gender': 'Female', 'language': 'French'},
        {'id': 'fr-FR-HenriNeural', 'name': 'Henri (男声)', 'gender': 'Male', 'language': 'French'},
        {'id': 'fr-FR-EloiseNeural', 'name': 'Eloise (女声)', 'gender': 'Female', 'language': 'French'},
    ],
    'german': [
        {'id': 'de-DE-KatjaNeural', 'name': 'Katja (女声)', 'gender': 'Female', 'language': 'German'},
        {'id': 'de-DE-ConradNeural', 'name': 'Conrad (男声)', 'gender': 'Male', 'language': 'German'},
        {'id': 'de-DE-AmalaNeural', 'name': 'Amala (女声)', 'gender': 'Female', 'language': 'German'},
    ],
    'spanish': [
        {'id': 'es-ES-ElviraNeural', 'name': 'Elvira (女声)', 'gender': 'Female', 'language': 'Spanish (ES)'},
        {'id': 'es-ES-AlvaroNeural', 'name': 'Alvaro (男声)', 'gender': 'Male', 'language': 'Spanish (ES)'},
        {'id': 'es-MX-DaliaNeural', 'name': 'Dalia (女声)', 'gender': 'Female', 'language': 'Spanish (MX)'},
        {'id': 'es-MX-JorgeNeural', 'name': 'Jorge (男声)', 'gender': 'Male', 'language': 'Spanish (MX)'},
    ],
    'russian': [
        {'id': 'ru-RU-SvetlanaNeural', 'name': 'Svetlana (女声)', 'gender': 'Female', 'language': 'Russian'},
        {'id': 'ru-RU-DmitryNeural', 'name': 'Dmitry (男声)', 'gender': 'Male', 'language': 'Russian'},
    ],
}

@app.route('/api/tts/voices')
def get_tts_voices():
    """Get available TTS voices grouped by language"""
    return jsonify({
        'available': GSV_TTS_AVAILABLE,
        'voices': TTS_VOICES
    })

@app.route('/api/tts/generate', methods=['POST'])
def generate_tts():
    """Generate TTS audio from text"""
    return jsonify({'error': 'edge-tts is disabled. Only GSV-TTS-Lite is available.'}), 400

@app.route('/api/health')
def health_check():
    """Simple health check endpoint for frontend monitoring"""
    import psutil
    
    # Get system memory info
    memory = psutil.virtual_memory()
    memory_info = {
        'total_gb': round(memory.total / (1024 ** 3), 2),
        'used_gb': round(memory.used / (1024 ** 3), 2),
        'percent': memory.percent
    }
    
    # Get CPU usage
    cpu_percent = psutil.cpu_percent(interval=0.1)
    
    # Get GPU info if available
    gpu_info = get_gpu_info()
    
    return jsonify({
        'status': 'healthy',
        'version': '0.3.0',
        'timestamp': datetime.now().isoformat(),
        'memory': memory_info,
        'cpu_percent': cpu_percent,
        'gpu': gpu_info
    })

@app.route('/api/llama-cpp/health')
def llama_cpp_health():
    """Check llama.cpp server health status"""
    # Use existing check_llama_cpp_health function
    if check_llama_cpp_health():
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat()
        })
    else:
        return jsonify({
            'status': 'unavailable',
            'error': 'llama.cpp service not running'
        }), 503

@app.route('/api/vllm/health')
def vllm_health():
    """Check vLLM server health status"""
    # Use existing check_vllm_health function
    if check_vllm_health():
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat()
        })
    else:
        return jsonify({
            'status': 'unavailable',
            'error': 'vLLM service not running'
        }), 503

@app.route('/api/system/health')
def system_health():
    """System health check for long-running monitoring"""
    import gc
    import threading
    
    memory_info = {'rss_mb': 'N/A', 'vms_mb': 'N/A'}
    
    try:
        import psutil
        process = psutil.Process()
        mem_info = process.memory_info()
        memory_info = {
            'rss_mb': round(mem_info.rss / (1024 * 1024), 2),
            'vms_mb': round(mem_info.vms / (1024 * 1024), 2)
        }
    except ImportError:
        pass
    except Exception as e:
        print(ConsoleColor.warning(f"Could not get memory info: {e}"))
    
    # Get detailed cache stats
    translation_stats = translation_cache.get_stats() if hasattr(translation_cache, 'get_stats') else {}
    tts_stats = gsv_tts_cache.get_stats() if hasattr(gsv_tts_cache, 'get_stats') else {}
    
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'memory': memory_info,
        'cache': {
            'translation': translation_stats,
            'tts': tts_stats
        },
        'threads': threading.active_count(),
        'gc_collected': gc.get_stats() if hasattr(gc, 'get_stats') else 'N/A'
    })

@app.route('/api/system/reset-caches')
def reset_caches():
    """Reset all caches to free memory"""
    if hasattr(translation_cache, 'clear'):
        translation_cache.clear()
    if hasattr(gsv_tts_cache, 'clear'):
        gsv_tts_cache.clear()
    
    import gc
    gc.collect()
    
    return jsonify({
        'success': True,
        'message': 'Caches reset and garbage collection performed'
    })

@app.route('/api/tts/status')
def tts_status():
    """Check TTS availability"""
    return jsonify({
        'available': TTS_AVAILABLE,
        'voice_clone_available': VOICE_CLONE_AVAILABLE,
        'gsv_tts_available': GSV_TTS_AVAILABLE,
        'engine': 'edge-tts' if TTS_AVAILABLE else None,
        'clone_engine': 'xtts_v2' if VOICE_CLONE_AVAILABLE else None,
        'gsv_engine': 'gsv_tts_lite' if GSV_TTS_AVAILABLE else None
    })

@app.route('/api/voice-clone/upload', methods=['POST'])
def upload_voice_sample():
    """Upload a voice sample for voice cloning"""
    if not GSV_TTS_AVAILABLE:
        return jsonify({'error': 'Voice cloning not available. Please install GSV-TTS-Lite: pip install gsv-tts-lite==0.3.5'}), 400
    
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file provided'}), 400
    
    file = request.files['audio']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_AUDIO_EXTENSIONS:
        return jsonify({'error': f'Invalid file format. Allowed: {", ".join(ALLOWED_AUDIO_EXTENSIONS)}'}), 400
    
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_filename = f"voice_{timestamp}{file_ext}"
        filepath = os.path.join(VOICE_CLONE_DIR, safe_filename)
        
        file.save(filepath)
        
        file_size = os.path.getsize(filepath)
        if file_size > MAX_AUDIO_SIZE:
            os.remove(filepath)
            return jsonify({'error': 'File too large. Maximum size is 10MB'}), 400
        
        return jsonify({
            'success': True,
            'filename': safe_filename,
            'path': filepath,
            'size': file_size,
            'message': 'Voice sample uploaded successfully'
        })
        
    except Exception as e:
        print(ConsoleColor.error(f"Upload error: {e}"))
        return jsonify({'error': str(e)}), 500

@app.route('/voice_samples/<filename>')
def serve_voice_sample(filename):
    """Serve uploaded voice sample files"""
    try:
        return send_from_directory(VOICE_CLONE_DIR, filename)
    except Exception as e:
        return jsonify({'error': 'File not found'}), 404

@app.route('/api/voice-clone/list')
def list_voice_samples():
    """List all uploaded voice samples"""
    samples = []
    try:
        if os.path.exists(VOICE_CLONE_DIR):
            for filename in os.listdir(VOICE_CLONE_DIR):
                filepath = os.path.join(VOICE_CLONE_DIR, filename)
                if os.path.isfile(filepath):
                    file_ext = os.path.splitext(filename)[1].lower()
                    if file_ext in ALLOWED_AUDIO_EXTENSIONS:
                        stat = os.stat(filepath)
                        samples.append({
                            'filename': filename,
                            'path': filepath,
                            'size': stat.st_size,
                            'created': datetime.fromtimestamp(stat.st_ctime).isoformat()
                        })
        return jsonify({
            'success': True,
            'samples': samples,
            'count': len(samples)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/voice-clone/delete/<filename>', methods=['DELETE'])
def delete_voice_sample(filename):
    """Delete a voice sample"""
    try:
        filepath = os.path.join(VOICE_CLONE_DIR, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            return jsonify({'success': True, 'message': 'Voice sample deleted'})
        return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/voice-clone/generate', methods=['POST'])
def generate_voice_clone_tts():
    """Generate TTS audio using voice cloning"""
    return jsonify({'error': 'Voice cloning (XTTS v2) not available for Python 3.13. Use GSV-TTS-Lite instead.'}), 400

@app.route('/api/gsv-tts/generate', methods=['POST'])
def generate_gsv_tts():
    """Generate TTS audio using GSV-TTS-Lite"""
    if not GSV_TTS_AVAILABLE:
        return jsonify({'error': 'GSV-TTS-Lite not available. Please install gsv-tts-lite: pip install gsv-tts-lite==0.3.5'}), 400
    
    global gsv_tts_cache
    
    data = request.json
    text = data.get('text', '')
    speaker_wav = data.get('speaker_wav', '')
    use_flash_attn = data.get('use_flash_attn', False)
    speed = data.get('speed', 1.0)  # Add speed control parameter
    reference_text = data.get('reference_text', '')  # Get reference text from request
    
    print(ConsoleColor.info(f"GSV-TTS request: text='{text[:30]}...', speaker='{speaker_wav}'"))
    if reference_text:
        print(ConsoleColor.info(f"Using custom reference text: '{reference_text[:50]}...'"))
    
    if not text:
        return jsonify({'error': 'Text is required'}), 400
    
    if len(text) < 4:
        return jsonify({'error': 'Text is too short. Please provide at least 4 characters.'}), 400
    
    if not speaker_wav:
        print(ConsoleColor.error("GSV-TTS error: No speaker audio file specified"))
        return jsonify({'error': 'Speaker audio file is required'}), 400
    
    speaker_path = os.path.join(VOICE_CLONE_DIR, speaker_wav)
    print(ConsoleColor.info(f"Looking for speaker audio at: {speaker_path}"))
    
    if not os.path.exists(speaker_path):
        print(ConsoleColor.error(f"GSV-TTS error: Speaker audio file not found: {speaker_path}"))
        return jsonify({'error': 'Speaker audio file not found'}), 404
    
    print(ConsoleColor.success(f"Speaker audio file found: {speaker_path}"))
    
    # Generate optimized cache key
    cache_key = generate_gsv_tts_cache_key(speaker_wav, text, speed)
    
    # Check cache first
    if cache_key in gsv_tts_cache:
        print(ConsoleColor.highlight(f"⚡ GSV-TTS CACHE HIT for: '{text[:20]}...'"))
        audio_data = gsv_tts_cache.get(cache_key)
        
        # Direct bytes response without BytesIO wrapper
        response = send_file(
            io.BytesIO(audio_data),
            mimetype='audio/wav',
            as_attachment=False,
            download_name='tts_output.wav'
        )
        response.headers['Content-Length'] = str(len(audio_data))
        response.headers['Cache-Control'] = 'public, max-age=3600'  # Cache for 1 hour
        return response
    
    try:
        global gsv_tts
        if gsv_tts is None:
            print(ConsoleColor.info("GSV-TTS-Lite instance not preloaded, creating new instance..."))
            gsv_tts = GSVTTS(
                models_dir=TTS_MODELS_DIR,
                is_half=True,  # FP16 for speed
                use_flash_attn=False,
                use_bert=True,
                always_load_cnhubert=False,
                always_load_sv=False
            )
            print(ConsoleColor.info("Loading GPT model..."))
            gsv_tts.load_gpt_model()
            print(ConsoleColor.info("Loading SoVITS model..."))
            gsv_tts.load_sovits_model()
            print(ConsoleColor.success("GSV-TTS-Lite model loaded successfully"))
        else:
            print(ConsoleColor.info("Using preloaded GSV-TTS-Lite instance"))
        
        # Use a temporary directory for better file management
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, 'output.wav')
            
            try:
                print(ConsoleColor.info(f"Generating audio for text: '{text}'"))
                
                # Use provided reference text or fall back to first 50 chars of input text
                prompt_text = reference_text if reference_text else text[:50]
                
                audio = gsv_tts.infer(
                    text=text,
                    spk_audio_path=speaker_path,
                    prompt_audio_path=speaker_path,
                    prompt_audio_text=prompt_text,
                    speed=speed
                )
                
                print(ConsoleColor.success("Audio generated successfully"))
            except Exception as e:
                print(ConsoleColor.error(f"Inference error: {e}"))
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'Inference error: {str(e)}'}), 500
            
            # Save audio to file
            try:
                audio.save(output_path)
                print(ConsoleColor.success(f"Audio saved to: {output_path}"))
            except Exception as e:
                print(ConsoleColor.error(f"Error saving audio: {e}"))
                import traceback
                traceback.print_exc()
                return jsonify({'error': f'Error saving audio: {str(e)}'}), 500
            
            # Read the file into memory
            with open(output_path, 'rb') as f:
                audio_data = f.read()
            
            audio_size = len(audio_data)
            print(ConsoleColor.success(f"Generated audio: {audio_size} bytes ({audio_size/1024:.1f} KB)"))
            
            # Cache the result
            gsv_tts_cache.put(cache_key, audio_data)
            
            # Create a BytesIO object for in-memory file handling
            from io import BytesIO
            audio_io = BytesIO(audio_data)
            audio_io.seek(0)
            
            # Send the in-memory file
            response = send_file(
                audio_io,
                mimetype='audio/wav',
                as_attachment=False,
                download_name='tts_output.wav'
            )
            
            # Add additional headers to ensure proper audio playback
            response.headers['Content-Length'] = str(audio_size)
            response.headers['Content-Transfer-Encoding'] = 'binary'
            response.headers['Cache-Control'] = 'no-cache'
            
            # No need for cleanup since temporary directory is automatically cleaned up
        
        print(ConsoleColor.success(f"GSV-TTS audio sent successfully"))
        return response
        
    except Exception as e:  # pyright: ignore[reportUnreachable]
        # 处理 GSV-TTS-Lite 生成过程中的错误
        print(ConsoleColor.error(f"GSV-TTS-Lite error: {e}"))
        return jsonify({'error': str(e)}), 500
        print(ConsoleColor.error(f"GSV-TTS-Lite error: {e}"))
        return jsonify({'error': str(e)}), 500

@app.route('/api/languages')
def get_languages():
    """Get available languages"""
    languages_file = os.path.join(CONFIG_DIR, 'languages.json')
    try:
        if os.path.exists(languages_file):
            with open(languages_file, 'r', encoding='utf-8') as f:
                languages = json.load(f)
            return jsonify(languages)
        else:
            return jsonify({'error': 'Languages file not found'}), 404
    except Exception as e:
        print(ConsoleColor.error(f"Error loading languages: {e}"))
        return jsonify({'error': str(e)}), 500

@app.route('/api/performance')
def get_performance_stats():
    """Get performance statistics"""
    try:
        import psutil
        process = psutil.Process()
        
        memory_info = process.memory_info()
        cpu_percent = process.cpu_percent(interval=0.1)
        
        # Get detailed cache stats
        translation_stats = translation_cache.get_stats() if hasattr(translation_cache, 'get_stats') else {}
        tts_stats = gsv_tts_cache.get_stats() if hasattr(gsv_tts_cache, 'get_stats') else {}
        
        return jsonify({
            'memory_used_mb': memory_info.rss / (1024 * 1024),
            'memory_percent': process.memory_percent(),
            'cpu_percent': cpu_percent,
            'translation_cache': translation_stats,
            'tts_cache': tts_stats,
            'pending_translations': len(pending_translations)
        })
    except ImportError:
        # Get detailed cache stats without psutil
        translation_stats = translation_cache.get_stats() if hasattr(translation_cache, 'get_stats') else {}
        tts_stats = gsv_tts_cache.get_stats() if hasattr(gsv_tts_cache, 'get_stats') else {}
        
        return jsonify({
            'error': 'psutil not available',
            'translation_cache': translation_stats,
            'tts_cache': tts_stats,
            'pending_translations': len(pending_translations)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# FRP Management API
FRP_CONFIG_FILE = os.path.join(BASE_DIR, 'config', 'frp_tunnels.json')
FRP_PROCESS = None
FRP_OUTPUT = []

# Ensure config directory exists
if not os.path.exists(os.path.join(BASE_DIR, 'config')):
    os.makedirs(os.path.join(BASE_DIR, 'config'))

# Load tunnels from config file
def load_tunnels():
    """Load tunnels from config file"""
    if os.path.exists(FRP_CONFIG_FILE):
        try:
            with open(FRP_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(ConsoleColor.error(f"Failed to load tunnels: {e}"))
            return []
    return []

# Save tunnels to config file
def save_tunnels(tunnels):
    """Save tunnels to config file"""
    try:
        with open(FRP_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(tunnels, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(ConsoleColor.error(f"Failed to save tunnels: {e}"))
        return False

@app.route('/api/frp/tunnels')
def get_frp_tunnels():
    """Get all saved FRP tunnels"""
    tunnels = load_tunnels()
    return jsonify({
        'tunnels': tunnels,
        'count': len(tunnels),
        'is_running': FRP_PROCESS is not None and FRP_PROCESS.poll() is None
    })

@app.route('/api/frp/tunnels', methods=['POST'])
def add_frp_tunnel():
    """Add a new FRP tunnel"""
    data = request.json
    tunnel_name = data.get('name')
    tunnel_command = data.get('command')
    
    if not tunnel_name or not tunnel_command:
        return jsonify({'error': 'Tunnel name and command are required'}), 400
    
    tunnels = load_tunnels()
    
    # Check if tunnel with same name exists
    for tunnel in tunnels:
        if tunnel['name'] == tunnel_name:
            return jsonify({'error': 'Tunnel with this name already exists'}), 400
    
    new_tunnel = {
        'id': str(int(time.time())),
        'name': tunnel_name,
        'command': tunnel_command,
        'created_at': datetime.now().isoformat()
    }
    
    tunnels.append(new_tunnel)
    if save_tunnels(tunnels):
        return jsonify({
            'success': True,
            'tunnel': new_tunnel,
            'message': 'Tunnel added successfully'
        })
    else:
        return jsonify({'error': 'Failed to save tunnel'}), 500

@app.route('/api/frp/tunnels/<tunnel_id>', methods=['DELETE'])
def delete_frp_tunnel(tunnel_id):
    """Delete a FRP tunnel"""
    tunnels = load_tunnels()
    new_tunnels = [t for t in tunnels if t['id'] != tunnel_id]
    
    if len(new_tunnels) == len(tunnels):
        return jsonify({'error': 'Tunnel not found'}), 404
    
    if save_tunnels(new_tunnels):
        return jsonify({
            'success': True,
            'message': 'Tunnel deleted successfully'
        })
    else:
        return jsonify({'error': 'Failed to delete tunnel'}), 500

@app.route('/api/frp/start', methods=['POST'])
def start_frp_tunnel():
    """Start a FRP tunnel"""
    global FRP_PROCESS, FRP_OUTPUT
    
    data = request.json
    tunnel_id = data.get('tunnel_id')
    
    if not tunnel_id:
        return jsonify({'error': 'Tunnel ID is required'}), 400
    
    # Check if tunnel is already running
    if FRP_PROCESS is not None and FRP_PROCESS.poll() is None:
        return jsonify({'error': 'A tunnel is already running. Please stop it first.'}), 400
    
    tunnels = load_tunnels()
    tunnel = next((t for t in tunnels if t['id'] == tunnel_id), None)
    
    if not tunnel:
        return jsonify({'error': 'Tunnel not found'}), 404
    
    # Build command
    frp_exe = os.path.join(BASE_DIR, 'core', 'frp', 'mefrpc.exe')
    if not os.path.exists(frp_exe):
        return jsonify({'error': 'mefrpc.exe not found in core/frp directory'}), 404
    
    # Extract arguments from the command
    command_parts = tunnel['command'].split()
    args = []
    for part in command_parts:
        if part.startswith('./mefrpc'):
            continue
        args.append(part)
    
    # Start the tunnel
    try:
        FRP_OUTPUT = []
        FRP_PROCESS = subprocess.Popen(
            [frp_exe] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=os.path.join(BASE_DIR, 'core', 'frp')
        )
        
        # Start a thread to read output
        def read_output():
            global FRP_OUTPUT
            while FRP_PROCESS and FRP_PROCESS.poll() is None:
                try:
                    line = FRP_PROCESS.stdout.readline()
                    if line:
                        FRP_OUTPUT.append(line.strip())
                        # Limit output to last 100 lines
                        if len(FRP_OUTPUT) > 100:
                            FRP_OUTPUT = FRP_OUTPUT[-100:]
                except:
                    break
        
        output_thread = threading.Thread(target=read_output, daemon=True)
        output_thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Tunnel started successfully',
            'tunnel_id': tunnel_id
        })
    except Exception as e:
        return jsonify({'error': f'Failed to start tunnel: {str(e)}'}), 500

@app.route('/api/frp/stop', methods=['POST'])
def stop_frp_tunnel():
    """Stop the running FRP tunnel"""
    global FRP_PROCESS, FRP_OUTPUT
    
    if FRP_PROCESS is None or FRP_PROCESS.poll() is not None:
        return jsonify({'error': 'No tunnel is running'}), 400
    
    try:
        FRP_PROCESS.terminate()
        FRP_PROCESS.wait(timeout=5)
        FRP_PROCESS = None
        FRP_OUTPUT.append('Tunnel stopped')
        return jsonify({
            'success': True,
            'message': 'Tunnel stopped successfully'
        })
    except Exception as e:
        return jsonify({'error': f'Failed to stop tunnel: {str(e)}'}), 500

@app.route('/api/frp/output')
def get_frp_output():
    """Get FRP tunnel output"""
    global FRP_OUTPUT
    return jsonify({
        'output': FRP_OUTPUT,
        'is_running': FRP_PROCESS is not None and FRP_PROCESS.poll() is None
    })

# Static files serving
@app.route('/static/<path:path>')
def serve_static(path):
    """Serve static files"""
    return send_from_directory('static', path)

# SocketIO events
@socketio.on('connect')
def handle_connect():
    print(ConsoleColor.info('Client connected'))
    emit('connected', {'message': 'Connected to server'})

@socketio.on('disconnect')
def handle_disconnect():
    print(ConsoleColor.info('Client disconnected'))
    global is_processing
    is_processing = False

@socketio.on('start_recognition')
def handle_start_recognition(data):
    global is_processing, processing_thread
    
    if is_processing:
        emit('error', {'message': 'Already processing, please wait'})
        return
    
    mic_index = data.get('mic_index', 0)
    model_name = data.get('model_name', 'default')
    vosk_model_path = data.get('vosk_model_path', None)
    translation_style = data.get('translation_style', '')
    preset_id = data.get('preset_id', None)
    
    # Load the specified vosk model
    if not load_model(vosk_model_path):
        emit('error', {'message': 'Failed to load speech recognition model'})
        return
    
    # Auto select provider based on availability, prioritize llama.cpp
    provider = data.get('provider', 'llama.cpp')
    
    # Check if llama.cpp is available
    llama_cpp_available = True  # We'll implement this check later
    
    if provider == 'llama.cpp' and not llama_cpp_available:
        print(ConsoleColor.warning("llama.cpp is not available, switching to vLLM"))
        provider = 'vllm'
    elif provider == 'vllm' and not VLLM_AVAILABLE:
        print(ConsoleColor.warning("vLLM is not available, switching to Ollama"))
        provider = 'ollama'
    
    is_processing = True
    processing_thread = threading.Thread(
        target=process_audio_stream,
        args=(mic_index, model_name, provider, translation_style, preset_id)
    )
    processing_thread.start()

@socketio.on('stop_recognition')
def handle_stop_recognition():
    global is_processing
    is_processing = False
    emit('status', {'status': 'stopped', 'message': 'Stopped'})

@socketio.on('start_loading')
def handle_start_loading(data):
    """Handle loading process with real-time progress"""
    global components_loaded
    
    components = data.get('components', {})
    total_steps = sum(1 for key, value in components.items() if value)
    
    # Ensure at least one step to avoid division by zero
    if total_steps == 0:
        total_steps = 1
    
    current_step = 0
    
    try:
        # 1. System file validation
        emit('loading_progress', {
            'component': 'core',
            'status': 'loading',
            'message': 'Validating system files...',
            'progress': 0
        })
        
        # Validate system files
        validate_system_files()
        current_step += 1
        emit('loading_progress', {
            'component': 'core',
            'status': 'completed',
            'message': 'System files validated',
            'progress': (current_step / total_steps) * 100
        })
        
        # 2. Load core engine
        if components.get('core', True):
            emit('loading_progress', {
                'component': 'core',
                'status': 'loading',
                'message': 'Initializing core engine...',
                'progress': (current_step / total_steps) * 100
            })
            
            # Initialize core components
            initialize_core_engine()
            current_step += 1
            emit('loading_progress', {
                'component': 'core',
                'status': 'completed',
                'message': 'Core engine initialized',
                'progress': (current_step / total_steps) * 100
            })
        
        # 3. Load speech recognition
        if components.get('speech', True):
            emit('loading_progress', {
                'component': 'speech',
                'status': 'loading',
                'message': 'Loading speech recognition...',
                'progress': (current_step / total_steps) * 100
            })
            
            # Load speech recognition models
            load_speech_recognition()
            current_step += 1
            emit('loading_progress', {
                'component': 'speech',
                'status': 'completed',
                'message': 'Speech recognition loaded',
                'progress': (current_step / total_steps) * 100
            })
        
        # 4. Load translation engine
        if components.get('translation', True):
            emit('loading_progress', {
                'component': 'translation',
                'status': 'loading',
                'message': 'Initializing translation engine...',
                'progress': (current_step / total_steps) * 100
            })
            
            # Initialize translation engine
            initialize_translation_engine()
            current_step += 1
            emit('loading_progress', {
                'component': 'translation',
                'status': 'completed',
                'message': 'Translation engine initialized',
                'progress': (current_step / total_steps) * 100
            })
        
        # 5. Load text-to-speech
        if components.get('tts', True):
            emit('loading_progress', {
                'component': 'tts',
                'status': 'loading',
                'message': 'Loading text-to-speech...',
                'progress': (current_step / total_steps) * 100
            })
            
            # Load TTS models
            load_text_to_speech()
            current_step += 1
            emit('loading_progress', {
                'component': 'tts',
                'status': 'completed',
                'message': 'Text-to-speech loaded',
                'progress': (current_step / total_steps) * 100
            })
        
        # 6. Load model manager
        if components.get('models', True):
            emit('loading_progress', {
                'component': 'models',
                'status': 'loading',
                'message': 'Loading model manager...',
                'progress': (current_step / total_steps) * 100
            })
            
            # Initialize model manager
            initialize_model_manager()
            current_step += 1
            emit('loading_progress', {
                'component': 'models',
                'status': 'completed',
                'message': 'Model manager loaded',
                'progress': (current_step / total_steps) * 100
            })
        
        # 7. Load llama.cpp (separate step)
        if components.get('llama_cpp', True):
            total_steps += 1  # Add llama.cpp as a separate step
        
        # 8. Load llama.cpp server
        if components.get('llama_cpp', True):
            emit('loading_progress', {
                'component': 'llama_cpp',
                'status': 'loading',
                'message': 'Starting llama.cpp server...',
                'progress': (current_step / total_steps) * 100
            })
            
            # Load llama.cpp and start server
            load_llama_cpp()
            current_step += 1
            emit('loading_progress', {
                'component': 'llama_cpp',
                'status': 'completed',
                'message': 'llama.cpp server ready',
                'progress': (current_step / total_steps) * 100
            })
        
        # Final progress update
        emit('loading_progress', {
            'message': 'All components loaded successfully!',
            'progress': 100
        })
        
        # Mark components as loaded
        global components_loaded
        components_loaded = True
        
        # Notify completion
        emit('loading_complete')
        
    except Exception as e:
        print(f"Loading error: {e}")
        emit('loading_error', {'error': str(e)})

def validate_system_files():
    """Validate system files and directories"""
    # Check required directories
    required_dirs = [
        os.path.join(BASE_DIR, 'models'),
        os.path.join(BASE_DIR, 'models', 'vosk'),
        os.path.join(BASE_DIR, 'config')
    ]
    
    for dir_path in required_dirs:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
            print(f"Created directory: {dir_path}")
    
    # Check required files
    required_files = [
        os.path.join(BASE_DIR, 'config', 'languages.json'),
        os.path.join(BASE_DIR, 'config', 'vllm_models.json')
    ]
    
    for file_path in required_files:
        if not os.path.exists(file_path):
            print(f"Warning: {file_path} not found")

def initialize_core_engine():
    """Initialize core engine components"""
    # Initialize core services
    global translation_cache, gsv_tts_cache
    
    # Ensure caches are initialized
    if 'translation_cache' not in globals():
        from functools import lru_cache
        translation_cache = {}
    
    if 'gsv_tts_cache' not in globals():
        gsv_tts_cache = {}

def load_speech_recognition():
    """Load speech recognition components"""
    # Speech recognition is loaded on demand, but we can preload models
    pass

def initialize_translation_engine():
    """Initialize translation engine"""
    # Translation engine is initialized on demand
    pass

def load_text_to_speech():
    """Load text-to-speech components"""
    # TTS is loaded on demand
    pass

def initialize_model_manager():
    """Initialize model manager"""
    # Model manager is initialized on demand
    pass

def load_llama_cpp():
    """Load llama.cpp and GGUF models"""
    global llama_cpp_process
    
    # Check for GGUF models in models directory
    gguf_models = get_gguf_models()
    if not gguf_models:
        print("No GGUF models found in models/ directory")
        print("Please download GGUF models and place them in the models/ directory")
        print("Models can be in subdirectories like: models/llm/GGUF/, models/gguf/, etc.")
        return
    
    print(f"Found {len(gguf_models)} GGUF model(s) in models/ directory:")
    for model in gguf_models:
        print(f"  - {model['relative_path']} ({model['size']})")
    
    # Check if llama.cpp is available
    llama_cpp_exe = find_llama_cpp_exe()
    if not llama_cpp_exe:
        print("llama.cpp executable not found")
        print("Please install llama.cpp and add it to PATH")
        return
    
    print(f"Found llama.cpp executable: {llama_cpp_exe}")
    
    # Get first GGUF model as default (sorted alphabetically)
    default_model = gguf_models[0]['path']
    print(f"Using default model: {gguf_models[0]['relative_path']}")
    
    # Start llama.cpp server
    try:
        print("Starting llama.cpp server...")
        llama_cpp_process = start_llama_cpp_server(llama_cpp_exe, default_model)
        
        # Wait for server to start
        time.sleep(3)
        
        # Check if server is running
        if check_llama_cpp_health():
            print("llama.cpp server started successfully")
        else:
            print("Failed to start llama.cpp server")
            if llama_cpp_process:
                llama_cpp_process.terminate()
                llama_cpp_process = None
    except Exception as e:
        print(f"Error starting llama.cpp server: {e}")
        if llama_cpp_process:
            try:
                llama_cpp_process.terminate()
            except:
                pass
            llama_cpp_process = None

def find_llama_cpp_exe():
    """Find llama.cpp executable"""
    # Check in common locations
    common_paths = [
        os.path.join(BASE_DIR, 'llama.cpp', 'server.exe'),
        os.path.join(BASE_DIR, 'llama.cpp', 'main.exe'),
        'server.exe',
        'main.exe'
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            return path
    
    # Check PATH
    import shutil
    llama_cpp_exe = shutil.which('server.exe')
    if llama_cpp_exe:
        return llama_cpp_exe
    
    llama_cpp_exe = shutil.which('main.exe')
    if llama_cpp_exe:
        return llama_cpp_exe
    
    return None

def start_llama_cpp_server(executable, model_path):
    """Start llama.cpp server with the specified model"""
    import subprocess
    
    # Command to start llama.cpp server
    cmd = [
        executable,
        '-m', model_path,
        '--host', '127.0.0.1',
        '--port', '8080',
        '--ctx-size', '2048',
        '--batch-size', '128'
    ]
    
    print(f"Starting llama.cpp with command: {' '.join(cmd)}")
    
    # Start the process
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    return process

def check_llama_cpp_health():
    """Check if llama.cpp server is healthy"""
    try:
        import requests
        response = requests.get('http://localhost:8080/health', timeout=5)
        return response.status_code == 200
    except:
        return False

# Global variable to track llama.cpp process
llama_cpp_process = None

# Global flag to track if components are loaded
components_loaded = False

if __name__ == '__main__':
    print(ConsoleColor.title("=" * 60))
    print(ConsoleColor.title("Speech Recognition and Translation System - Windows Optimized"))
    print(ConsoleColor.title("=" * 60))
    print()
    
    # Display system information
    print(ConsoleColor.info("System Information:"))
    print(ConsoleColor.info(f"  Operating System: {sys.platform}"))
    print(ConsoleColor.info(f"  Python Version: {sys.version.split()[0]}"))
    print(ConsoleColor.info(f"  Working Directory: {os.getcwd()}"))
    print()
    
    # Check port
    PORT = 5001
    if is_port_in_use(PORT):
        print(ConsoleColor.error(f"Error: Port {PORT} is already in use"))
        print(ConsoleColor.info(f"  Please check if another program is using this port"))
        input("\nPress Enter to exit...")
        sys.exit(1)
    
    print(ConsoleColor.success(f"Port {PORT} is available"))
    print()
    
    # Display configuration information
    print(ConsoleColor.info("Configuration Information:"))
    print(ConsoleColor.info(f"  Vosk Models Directory: {VOSK_MODELS_DIR}"))
    print(ConsoleColor.info(f"  Default Model Path: {DEFAULT_MODEL_PATH}"))
    print(ConsoleColor.info(f"  Ollama API: {OLLAMA_URL}"))
    print(ConsoleColor.info(f"  vLLM API: {VLLM_URL}"))
    print(ConsoleColor.info(f"  Sample Rate: {SAMPLE_RATE} Hz"))
    print(ConsoleColor.info(f"  Buffer Size: {CHUNK_SIZE}"))
    print()
    
    # Check and start vLLM service (default translation provider)
    print(ConsoleColor.title("-" * 60))
    print(ConsoleColor.title("vLLM Service Check (Default Translation Provider)"))
    print(ConsoleColor.title("-" * 60))
    print()
    
    vllm_process = None
    vllm_available = check_vllm_health()
    
    # Update global flag
    VLLM_AVAILABLE = vllm_available
    
    # Check if auto-start is enabled in config
    vllm_config = APP_CONFIG.get('vllm', {})
    translation_config = APP_CONFIG.get('translation', {})
    auto_start_vllm = vllm_config.get('auto_start', True) or translation_config.get('auto_start_vllm', True)
    
    if vllm_available:
        print(ConsoleColor.success("✓ vLLM service is already running"))
        print(ConsoleColor.info(f"  vLLM URL: {VLLM_URL}"))
        vllm_models = get_vllm_models()
        if vllm_models:
            print(ConsoleColor.success(f"  Available models: {', '.join(vllm_models[:3])}"))
            if len(vllm_models) > 3:
                print(ConsoleColor.info(f"  ... and {len(vllm_models) - 3} more"))
    elif auto_start_vllm:
        print(ConsoleColor.warning("✗ vLLM service is not running"))
        print(ConsoleColor.info("  Auto-start is enabled, attempting to start vLLM..."))
        print()
        
        # Try to start vLLM
        try:
            import subprocess
            import shutil
            
            # Find Python executable (prefer venv)
            python_exe = sys.executable
            
            # Check if vLLM is installed
            try:
                result = subprocess.run(
                    [python_exe, "-c", "import vllm; print(vllm.__version__)"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    print(ConsoleColor.success(f"✓ vLLM is installed (version: {result.stdout.strip()})"))
                else:
                    print(ConsoleColor.error("✗ vLLM is not installed"))
                    print(ConsoleColor.info("  Please install vLLM: pip install vllm"))
                    print(ConsoleColor.info("  Or use: python start_vllm.py --install"))
                    raise ImportError("vLLM not installed")
            except Exception as e:
                print(ConsoleColor.error(f"✗ Cannot verify vLLM installation: {e}"))
                print(ConsoleColor.info("  Please install vLLM manually"))
                raise
            
            # Check if vLLM models exist locally
            vllm_models_dir = os.path.join(BASE_DIR, 'models', 'llm')
            available_models = get_local_vllm_models(vllm_models_dir)
            
            if not available_models:
                print()
                print(ConsoleColor.warning("⚠ No local vLLM models found!"))
                print(ConsoleColor.info("  Please download a model from the Model Management page"))
                print(ConsoleColor.info("  Or use the API: POST /api/vllm-models/download"))
                print()
                print(ConsoleColor.info("  Recommended models:"))
                print(ConsoleColor.info("    - Qwen/Qwen2.5-7B-Instruct (Chinese translation)"))
                print(ConsoleColor.info("    - microsoft/Phi-4 (Fast inference)"))
                print()
                raise ImportError("No local vLLM models available")
            
            # Use the first available model
            default_vllm_model = available_models[0]['path']
            model_name = available_models[0]['name']
            print(ConsoleColor.info(f"  Using local model: {model_name}"))
            print()
            
            # Build vLLM command with local model
            vllm_cmd = [
                python_exe, "-m", "vllm.entrypoints.openai.api_server",
                "--model", default_vllm_model,
                "--port", "8000",
                "--tensor-parallel-size", "1",
                "--max-model-len", "2048",
                "--gpu-memory-utilization", "0.9",
                "--max-num-seqs", "256",
                "--dtype", "auto"
            ]
            
            print(ConsoleColor.info("  Command: " + " ".join(vllm_cmd)))
            print()
            
            # Start vLLM process
            vllm_process = subprocess.Popen(
                vllm_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0
            )
            
            # Wait for vLLM to be ready
            print(ConsoleColor.info("  Waiting for vLLM to start (this may take 30-60 seconds)..."))
            max_wait = 120  # Maximum wait time in seconds
            wait_interval = 2
            waited = 0
            
            while waited < max_wait:
                time.sleep(wait_interval)
                waited += wait_interval
                
                # Check if process is still running
                if vllm_process.poll() is not None:
                    stdout, stderr = vllm_process.communicate()
                    print(ConsoleColor.error("✗ vLLM process exited unexpectedly"))
                    print(ConsoleColor.error(f"  Exit code: {vllm_process.returncode}"))
                    if stderr:
                        print(ConsoleColor.error(f"  Error: {stderr.decode('utf-8', errors='ignore')[:500]}"))
                    vllm_process = None
                    break
                
                # Check if vLLM is responding
                if check_vllm_health():
                    print()
                    print(ConsoleColor.success("✓ vLLM service started successfully!"))
                    vllm_models = get_vllm_models()
                    if vllm_models:
                        print(ConsoleColor.success(f"  Available models: {', '.join(vllm_models)}"))
                    vllm_available = True
                    VLLM_AVAILABLE = True
                    break
                
                # Show progress
                if waited % 10 == 0:
                    print(ConsoleColor.info(f"  Still waiting... ({waited}s)"))
            
            if not vllm_available and vllm_process:
                print()
                print(ConsoleColor.warning("⚠ vLLM did not start within the expected time"))
                print(ConsoleColor.info("  The process is still running in the background"))
                print(ConsoleColor.info("  Translation may become available shortly"))
                
        except Exception as e:
            print()
            print(ConsoleColor.error(f"✗ Failed to start vLLM: {e}"))
            print(ConsoleColor.info("  Please download a model from Model Management page"))
            print(ConsoleColor.info("  Or manually download and place in: models/llm/"))
            print()
            print(ConsoleColor.warning("  System will continue without vLLM"))
            print(ConsoleColor.info("  You can switch to Ollama in the web interface"))
    else:
        # Auto-start is disabled
        print(ConsoleColor.warning("✗ vLLM service is not running"))
        print(ConsoleColor.info("  Auto-start is disabled in config.json"))
        print(ConsoleColor.info("  To enable auto-start, set vllm.auto_start or translation.auto_start_vllm to true"))
        print()
    
    print()
    print(ConsoleColor.title("-" * 60))
    print()
    
    # List available vosk models
    print(ConsoleColor.info("Available Vosk Models:"))
    vosk_models = get_vosk_models()
    if vosk_models:
        for m in vosk_models:
            print(ConsoleColor.info(f"  - {m['name']}"))
    else:
        print(ConsoleColor.info("  (None found)"))
    print()
    
    # Load default model
    print(ConsoleColor.info("Loading default speech recognition model..."))
    if not load_model():
        print("\n" + ConsoleColor.error("Failed to load speech recognition model"))
        print(ConsoleColor.info("  System will start, but speech recognition will not be available"))
        print(ConsoleColor.info("  Please download Vosk models from:"))
        print(ConsoleColor.info("  https://alphacephei.com/vosk/models"))
        print(ConsoleColor.info("  Recommended models:"))
        print(ConsoleColor.info("    - vosk-model-small-cn-0.22 (Chinese)"))
        print(ConsoleColor.info("    - vosk-model-small-en-us-0.15 (English)"))
        print()
        print(ConsoleColor.info("  Extract the model to: models/stt/"))
        print(ConsoleColor.info("  Note: Translation function is still available"))
        print()
        import time
        time.sleep(3)  # Give user time to read information
    else:
        print()
    
    # Test Ollama connection
    print(ConsoleColor.info("Checking Ollama service..."))
    OLLAMA_AVAILABLE = True
    try:
        response = requests.get(f'{OLLAMA_URL}/api/tags', timeout=5)
        if response.status_code == 200:
            print(ConsoleColor.success("Ollama service connected successfully"))
        else:
            print(ConsoleColor.warning(f"Ollama service responded abnormally: {response.status_code}"))
            OLLAMA_AVAILABLE = False
    except Exception as e:
        print(ConsoleColor.warning(f"Cannot connect to Ollama service: {e}"))
        print(ConsoleColor.info("  Translation功能将被禁用，请确保Ollama服务正在运行: ollama serve"))
        OLLAMA_AVAILABLE = False
    
    if not OLLAMA_AVAILABLE:
        print(ConsoleColor.info("  系统将继续启动，但翻译功能不可用"))
        print(ConsoleColor.info("  语音识别和TTS功能仍然可用"))
        import time
        time.sleep(2)  # Give user time to read information
    
    # Check and download GSV-TTS models
    if GSV_TTS_AVAILABLE:
        print(ConsoleColor.info("Checking GSV-TTS models..."))
        
        # Define required GSV-TTS models
        required_gsv_models = [
            {
                'id': 'chinese-hubert',
                'name': 'Chinese HuBERT',
                'target_dir': 'chinese-hubert-base'
            },
            {
                'id': 'chinese-roberta',
                'name': 'Chinese RoBERTa',
                'target_dir': 'chinese-roberta-wwm-ext-large'
            },
            {
                'id': 'g2p',
                'name': 'G2P Model',
                'target_dir': 'g2p'
            },
            {
                'id': 'speaker-verification',
                'name': 'Speaker Verification',
                'target_dir': 'sv'
            },
            {
                'id': 's1v3',
                'name': 'GPT s1v3',
                'target_dir': 's1v3'
            },
            {
                'id': 's2Gv2ProPlus',
                'name': 'SoVITS s2Gv2ProPlus',
                'target_dir': 's2Gv2ProPlus'
            }
        ]
        
        # Check each model
        models_to_download = []
        for model in required_gsv_models:
            target_dir = os.path.join(TTS_MODELS_DIR, model['target_dir'])
            if not os.path.exists(target_dir) or len(os.listdir(target_dir)) == 0:
                models_to_download.append(model)
            else:
                print(ConsoleColor.success(f"  ✓ {model['name']} is already installed"))
        
        # Download missing models
        if models_to_download:
            print(ConsoleColor.info(f"  {len(models_to_download)} models need to be downloaded"))
            
            # Download each model
            for model in models_to_download:
                print(ConsoleColor.info(f"\nDownloading {model['name']}..."))
                
                # Get download URL using GHProxy (faster in China)
                download_urls = {
                    'chinese-hubert': 'https://ghproxy.com/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/cnhubert.zip',
                    'chinese-roberta': 'https://ghproxy.com/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/cnroberta.zip',
                    'g2p': 'https://ghproxy.com/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/g2p.zip',
                    'speaker-verification': 'https://ghproxy.com/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/sv.zip',
                    's1v3': 'https://ghproxy.com/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/s1v3.zip',
                    's2Gv2ProPlus': 'https://ghproxy.com/https://github.com/chinokikiss/GSV-TTS-Lite/releases/download/v0.3.5/s2Gv2ProPlus.zip'
                }
                
                download_url = download_urls.get(model['id'])
                if not download_url:
                    print(ConsoleColor.error(f"  ✗ No download URL for {model['name']}"))
                    continue
                
                try:
                    # Create target directory
                    target_dir = os.path.join(TTS_MODELS_DIR, model['target_dir'])
                    os.makedirs(target_dir, exist_ok=True)
                    
                    # Download with progress
                    import tempfile
                    import zipfile
                    import shutil
                    
                    temp_dir = tempfile.mkdtemp()
                    zip_path = os.path.join(temp_dir, f'{model["id"]}.zip')
                    
                    print(ConsoleColor.info(f"  Downloading from: {download_url}"))
                    
                    # Download with progress
                    response = requests.get(download_url, stream=True, timeout=600)
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    chunk_size = 8192
                    start_time = time.time()
                    
                    with open(zip_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total_size > 0:
                                    progress = (downloaded / total_size) * 100
                                    elapsed = time.time() - start_time
                                    speed = downloaded / elapsed / (1024 * 1024) if elapsed > 0 else 0
                                    print(f"  Progress: {progress:.1f}% | {speed:.1f} MB/s", end='\r')
                    
                    print()
                    print(ConsoleColor.info(f"  Extracting {model['name']}..."))
                    
                    # Extract
                    extract_temp = os.path.join(temp_dir, 'extract')
                    os.makedirs(extract_temp, exist_ok=True)
                    
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(extract_temp)
                    
                    # Move files
                    extracted_items = os.listdir(extract_temp)
                    if len(extracted_items) == 1 and os.path.isdir(os.path.join(extract_temp, extracted_items[0])):
                        src_dir = os.path.join(extract_temp, extracted_items[0])
                        # Clear target directory
                        if os.path.exists(target_dir):
                            shutil.rmtree(target_dir)
                        shutil.move(src_dir, target_dir)
                    else:
                        # Clear target directory
                        if os.path.exists(target_dir):
                            for item in os.listdir(target_dir):
                                item_path = os.path.join(target_dir, item)
                                if os.path.isdir(item_path):
                                    shutil.rmtree(item_path)
                                else:
                                    os.remove(item_path)
                        # Move all items
                        for item in extracted_items:
                            src_path = os.path.join(extract_temp, item)
                            dst_path = os.path.join(target_dir, item)
                            if os.path.isdir(src_path):
                                shutil.move(src_path, dst_path)
                            else:
                                shutil.move(src_path, dst_path)
                    
                    # Clean up
                    os.remove(zip_path)
                    shutil.rmtree(extract_temp)
                    shutil.rmtree(temp_dir)
                    
                    print(ConsoleColor.success(f"  ✓ {model['name']} downloaded and installed successfully"))
                    
                except Exception as e:
                    print(ConsoleColor.error(f"  ✗ Failed to download {model['name']}: {e}"))
                    # Clean up
                    try:
                        if 'temp_dir' in locals() and os.path.exists(temp_dir):
                            shutil.rmtree(temp_dir)
                    except:
                        pass
        else:
            print(ConsoleColor.success("  All GSV-TTS models are already installed"))
        
        print()
    
    # Background thread for periodic cleanup and health monitoring
    def maintenance_thread():
        while True:
            try:
                time.sleep(1800)  # Run every 30 minutes
                
                print(ConsoleColor.info("\n[MAINTENANCE] Running periodic cleanup..."))
                
                # Clear expired cache entries
                if hasattr(translation_cache, '_periodic_cleanup'):
                    translation_cache._periodic_cleanup()
                    t_stats = translation_cache.get_stats() if hasattr(translation_cache, 'get_stats') else {}
                    print(ConsoleColor.success(f"  Translation cache: {t_stats.get('entries', 0)} entries, {t_stats.get('memory_mb', 0):.1f} MB"))
                
                if hasattr(gsv_tts_cache, '_periodic_cleanup'):
                    gsv_tts_cache._periodic_cleanup()
                    tts_stats = gsv_tts_cache.get_stats() if hasattr(gsv_tts_cache, 'get_stats') else {}
                    print(ConsoleColor.success(f"  TTS cache: {tts_stats.get('entries', 0)} entries, {tts_stats.get('memory_mb', 0):.1f} MB, {tts_stats.get('hit_rate', 0):.1f}% hit rate"))
                
                # Force garbage collection
                import gc
                collected = gc.collect()
                print(ConsoleColor.success(f"  Garbage collection completed: {collected} objects collected"))
                
            except Exception as e:
                print(ConsoleColor.error(f"  Maintenance error: {e}"))
    
    # Start maintenance thread
    maintenance_thread_obj = threading.Thread(target=maintenance_thread, daemon=True, name='maintenance')
    maintenance_thread_obj.start()
    print(ConsoleColor.success("✓ Maintenance thread started"))
    
    # Preload GSV-TTS-Lite model
    if GSV_TTS_AVAILABLE:
        preload_gsv_tts()
    
    print()
    print(ConsoleColor.title("=" * 60))
    print(ConsoleColor.title("System ready, starting server..."))
    print(ConsoleColor.info(f"Access URL: http://localhost:{PORT}"))
    print(ConsoleColor.info("Press Ctrl+C to stop server"))
    print(ConsoleColor.title("=" * 60))
    print()
    
    try:
        # Start server
        socketio.run(
            app,
            host='0.0.0.0',
            port=PORT,
            debug=False,
            use_reloader=False,
            log_output=True
        )
    except KeyboardInterrupt:
        print("\n\n✓ Server stopped")
    except Exception as e:
        print(f"\n✗ Server startup failed: {e}")
        input("\nPress Enter to exit...")
    finally:
        # Clean up resources
        if pyaudio_instance:
            try:
                pyaudio_instance.terminate()
            except Exception as e:
                print(f"Warning: Failed to clean up PyAudio resources: {e}")
        
        # Clean up vLLM process if we started it
        if 'vllm_process' in locals() and vllm_process:
            try:
                print(ConsoleColor.info("Shutting down vLLM process..."))
                vllm_process.terminate()
                vllm_process.wait(timeout=5)
                print(ConsoleColor.success("✓ vLLM process stopped"))
            except Exception as e:
                print(ConsoleColor.warning(f"Warning: Failed to stop vLLM process: {e}"))
                try:
                    vllm_process.kill()
                except:
                    pass