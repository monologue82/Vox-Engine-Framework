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
import base64
from datetime import datetime
from collections import OrderedDict
import functools
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, session, redirect
from flask_socketio import SocketIO, emit
import pyaudio

# 语音识别支持：仅使用 FunASR，不使用 fallback
FUNASR_AVAILABLE = False
try:
    from funasr_asr import initialize_funasr, transcribe_audio_stream, transcribe_audio_file, is_available, get_device
    FUNASR_AVAILABLE = is_available()
except Exception as e:
    print(f"[ERROR] FunASR not available: {e}")

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

# 如果 FunASR 不可用，不允许启动系统
if not FUNASR_AVAILABLE:
    print(ConsoleColor.error("FunASR is not available. The system cannot start without ASR support."))
    print(ConsoleColor.error("Please install FunASR first: pip install funasr"))
    sys.exit(1)

# edge-tts is removed, only GSV-TTS-Lite is used
TTS_AVAILABLE = False
print(ConsoleColor.warning("edge-tts is disabled. Only GSV-TTS-Lite is available."))

# TTS (Coqui) is not compatible with Python 3.13
# Using GSV-TTS-Lite as alternative
VOICE_CLONE_AVAILABLE = False
voice_clone_tts = None
print(ConsoleColor.warning("TTS (Coqui) not available for Python 3.13. Using GSV-TTS-Lite as alternative."))

# GSV-TTS-Lite: Lightweight TTS with voice cloning
GSV_TTS_AVAILABLE = False
gsv_tts = None

try:
    from gsv_tts import TTS as GSVTTS
    GSV_TTS_AVAILABLE = True
except ImportError:
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
    async_handlers=False,
    logger=True,
    engineio_logger=False
)

# Configuration
# Windows adaptation: Use absolute paths to avoid encoding issues
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Load main config.json
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
def load_config():
    """Load main configuration from config.json"""
    default_config = {
        'translation': {'default_provider': 'lps', 'default_model': ''},
        'lps': {
            'enabled': True,
            'backend': 'openai_compatible',
            'openai_url': 'http://localhost:8080/v1',
            'models_dir': 'models/translate',
            'default_model': '',
            'n_ctx': 2048,
            'n_threads': 4,
            'n_gpu_layers': 0,
            'temperature': 0.3,
            'max_tokens': 512,
            'top_p': 0.8,
            'verbose': False
        },
        'system': {'enable_monitor': False},
        'speech': {'default_microphone': 'auto', 'sample_rate': '16000'},
        'tts': {'enabled': True, 'default_model': 's2Gv2ProPlus'},
        'server': {'port': '5001', 'enable_cors': True, 'debug': True}
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

# TTS model directory
TTS_MODELS_DIR = os.path.abspath(os.path.join(BASE_DIR, 'models', 'tts'))
TTS_GPT_DIR = os.path.join(TTS_MODELS_DIR, 'gpt')
TTS_SOVITS_DIR = os.path.join(TTS_MODELS_DIR, 'sovits')
TTS_REFERENCES_DIR = os.path.join(TTS_MODELS_DIR, 'references')

# 创建TTS模型目录
for tts_dir in [TTS_MODELS_DIR, TTS_GPT_DIR, TTS_SOVITS_DIR, TTS_REFERENCES_DIR]:
    if not os.path.exists(tts_dir):
        os.makedirs(tts_dir)
        print(ConsoleColor.info(f"Created TTS directory: {tts_dir}"))


# Global flags for service availability

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
pending_translations = set()  # Track pending translations to avoid duplicates
_translation_seq = 0  # Translation sequence number for ordering
_translation_seq_lock = threading.Lock()  # Lock for sequence counter
_active_translation_seq = 0  # Currently active translation seq (newer supersedes older)

# LM Studio settings
lmstudio_url = 'http://localhost:1234'
lmstudio_api_key = ''

# LPS (Local Python Server) settings - GGUF model inference via llama-cpp-python
LPS_AVAILABLE = False
try:
    from llama_cpp import Llama
    LPS_AVAILABLE = True
except ImportError:
    print(ConsoleColor.warning("llama-cpp-python not installed. LPS provider will not be available."))
    print(ConsoleColor.warning("Install with: pip install llama-cpp-python"))

_lps_model = None
_lps_model_lock = threading.Lock()
_lps_current_model_path = None

def _next_translation_seq():
    global _translation_seq, _active_translation_seq
    with _translation_seq_lock:
        _translation_seq += 1
        _active_translation_seq = _translation_seq
        return _translation_seq

def _is_translation_stale(seq):
    if seq is None:
        return False
    return seq < _active_translation_seq

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

# Get microphone list (Windows optimized version)
def get_microphones():
    mics = []
    p = None
    try:
        p = pyaudio.PyAudio()
        
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
    finally:
        if p is not None:
            try:
                p.terminate()
            except Exception:
                pass


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


# Speech recognition processing thread (Windows optimized version)
def process_audio_stream(mic_index, model_name, provider='lps', translation_style='', preset_id=None):
    global is_processing, model
    
    p = None
    stream = None
    funasr_initialized = False
    
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
        
        # 仅使用 FunASR 进行语音识别
        device = get_device()
        print(ConsoleColor.info(f"Initializing FunASR on {device}..."))
        funasr_initialized = initialize_funasr(
            model_name="C:/Users/26276/Desktop/project/main/V0.3/models/stt/SenseVoiceSmall",
            device=device
        )
        
        if not funasr_initialized:
            error_msg = "Failed to initialize FunASR. Cannot start speech recognition."
            print(ConsoleColor.error(error_msg))
            socketio.emit('error', {'message': error_msg})
            return
        
        print(ConsoleColor.success("FunASR initialized successfully (GPU accelerated)"))
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
        funasr_cache = {}  # 持久 FunASR 缓存，维护跨chunk的流式ASR状态
        
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
                
                # 使用 FunASR 处理音频（传入持久缓存以维护流式ASR状态）
                text = transcribe_audio_stream(data, cache=funasr_cache, is_final=False)
                if text:
                    segment_count += 1
                    segment_time = time.time() - start_time
                    
                    print(ConsoleColor.success(f"Segment {segment_count}: {text[:50]}..."))
                    
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
                        translate_stream(accumulated_recognition.strip(), model_name, provider, preset_id)
                        accumulated_recognition = ""
                        last_translation_time = time.time()
                        
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
        
        # 最终刷新：通知 FunASR 流结束，处理缓冲区中剩余的音频
        try:
            import numpy as np
            final_text = transcribe_audio_stream(
                np.array([0]*160, dtype=np.int16), 
                cache=funasr_cache, 
                is_final=True
            )
            if final_text:
                print(ConsoleColor.success(f"Final flush text: {final_text[:50]}..."))
                all_text += final_text + " "
                accumulated_recognition += final_text + " "
        except Exception as e:
            print(ConsoleColor.warning(f"Final flush error (non-critical): {e}"))
        
        # 最终翻译：处理剩余的累积文本
        if accumulated_recognition.strip():
            print(ConsoleColor.info(f"Final translation for accumulated text: {accumulated_recognition.strip()[:50]}"))
            translate_stream(accumulated_recognition.strip(), model_name, provider, preset_id)
            accumulated_recognition = ""
        
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
        
        # 卸载 FunASR 模型（如果已初始化）
        if funasr_initialized:
            try:
                from funasr_asr import unload_model
                unload_model()
                print(ConsoleColor.info("FunASR model unloaded"))
            except Exception as e:
                print(ConsoleColor.warning(f"Failed to unload FunASR: {e}"))

import concurrent.futures

# Streaming translation with provider routing
def translate_stream(text, model_name, provider='lps', preset_id=None, target_lang=None):
    global translation_cache, current_translation_style, current_translation_prompt, pending_translations, APP_CONFIG
    
    seq = _next_translation_seq()
    
    if not provider or provider == 'auto':
        provider = APP_CONFIG.get('translation', {}).get('default_provider', 'lps')
    
    if provider == 'lps':
        translate_stream_lps(text, model_name, target_lang=target_lang, seq=seq)
        return
    
    # LM Studio API endpoint (OpenAI-compatible)
    API_URL = lmstudio_url if lmstudio_url else 'http://localhost:1234'
    service_name = 'LM Studio'
    
    # Set default model if not provided
    if not model_name:
        models = get_lmstudio_models()
        model_name = models[0] if models else 'default'
    
    # Determine target language for prompt
    if not target_lang:
        target_lang = 'English'
    
    # Build Hy-MT2 style translation prompt
    prompt = f"翻译成{target_lang}，只输出译文：{text}"
    style_key = target_lang.lower()
    
    # Store the optimized prompt
    current_translation_prompt = prompt
    
    # Create cache key with hash for faster lookup
    import hashlib
    text_hash = hashlib.md5(text.encode()).hexdigest()[:12]
    cache_key = f"lmstudio:{model_name}:{style_key}:{text_hash}"
    
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
                'char_count': i+1,
                'seq': seq
            })
            time.sleep(0.003)  # Simulate streaming
        
        socketio.emit('translation_complete', {
            'translation': cached_result,
            'total_time': '0.00s',
            'chars': len(cached_result),
            'first_chunk_time': '0.001s',
            'seq': seq
        })
        return
    
    # Use thread pool for asynchronous processing
    def fetch_translation():
        global lmstudio_api_key
        try:
            if _is_translation_stale(seq):
                print(ConsoleColor.debug(f"Translation seq={seq} already superseded at start"))
                return
            start_time = time.time()
            
            # Prepare headers
            headers = {'Content-Type': 'application/json'}
            if lmstudio_api_key:
                headers['Authorization'] = f'Bearer {lmstudio_api_key}'
            
            # LM Studio API call (OpenAI-compatible)
            response = requests.post(
                f'{API_URL}/v1/chat/completions',
                json={
                    'model': model_name,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'stream': True,
                    'temperature': 0.3,
                    'max_tokens': 1024,
                    'top_p': 0.8
                },
                headers=headers,
                stream=True,
                timeout=60
            )
            
            translation = ""
            char_count = 0
            first_chunk_time = None
            
            for line in response.iter_lines(decode_unicode=True):
                if line:
                    if line.startswith('data: '):
                        data_str = line[6:]
                        if data_str.strip() == '[DONE]':
                            break
                        try:
                            data = json.loads(data_str)
                            choices = data.get('choices', [])
                            if choices:
                                delta = choices[0].get('delta', {})
                                chunk = delta.get('content', '')
                                
                                if chunk:
                                    if _is_translation_stale(seq):
                                        print(ConsoleColor.debug(f"Translation seq={seq} superseded, stopping early"))
                                        return
                                    
                                    if first_chunk_time is None:
                                        first_chunk_time = time.time() - start_time
                                        print(ConsoleColor.highlight(f"⚡ FIRST CHUNK in {first_chunk_time:.3f}s"))
                                    
                                    translation += chunk
                                    char_count += len(chunk)
                                    
                                    socketio.emit('translation_chunk', {
                                        'chunk': chunk,
                                        'translation': translation,
                                        'char_count': char_count,
                                        'seq': seq
                                    })
                        
                        except json.JSONDecodeError:
                            continue
                        except Exception as e:
                            print(ConsoleColor.warning(f"Failed to parse translation data: {e}"))
                            continue
            
            total_time = time.time() - start_time
            
            if _is_translation_stale(seq):
                pending_translations.discard(cache_key)
                return
            
            # Cache the result
            if translation:
                translation_cache.put(cache_key, translation)
            
            socketio.emit('translation_complete', {
                'translation': translation,
                'total_time': f"{total_time:.2f}s",
                'chars': char_count,
                'first_chunk_time': f"{first_chunk_time:.3f}s" if first_chunk_time else "N/A",
                'seq': seq
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

# Unified translation API call function (LM Studio only)
def call_translation_api(text, model_name='default'):
    """Call translation API - routes to configured default provider."""
    global APP_CONFIG
    provider = APP_CONFIG.get('translation', {}).get('default_provider', 'lps')
    return translate_stream(text, model_name, provider)


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
        import hashlib
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
            
            # Use dtype='float16' for FP16 to reduce VRAM usage by ~50%
            # Set always_load_cnhubert and always_load_sv to False to save VRAM
            try:
                gsv_tts = GSVTTS(
                    models_dir=TTS_MODELS_DIR,
                    dtype="float16",
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
                    dtype="float16",
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

# Global flag for components loaded state
components_loaded = False
_loading_lock = threading.Lock()


def require_loaded(f):
    """Decorator: redirect to /start if components are not yet loaded"""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not components_loaded:
            return redirect('/start')
        return f(*args, **kwargs)
    return wrapper


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
@require_loaded
def main_app():
    """Direct access to main application (skip loading)"""
    current_language = session.get('language', default_language)

    rendered = render_template('index.html')

    return rendered

@app.route('/asr-debug')
@require_loaded
def asr_debug():
    """ASR Debug page for streaming recognition"""
    return render_template('asr_debug.html')

@app.route('/translation-debug')
@require_loaded
def translation_debug():
    """Translation Debug page for streaming translation"""
    return render_template('translation_debug.html')

@app.route('/tts-debug')
@require_loaded
def tts_debug():
    """TTS Debug page for full pipeline: ASR → Translation → TTS"""
    return render_template('tts_debug.html')

@app.route('/tts-only-debug')
@require_loaded
def tts_only_debug():
    """TTS Only Debug page: ASR → TTS directly (no translation)"""
    return render_template('tts_only_debug.html')

@app.route('/settings')
@require_loaded
def settings():
    """System settings page"""
    current_language = session.get('language', default_language)
    return render_template('settings.html', current_language=current_language, get_text=get_text)

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
    global lmstudio_url, lmstudio_api_key
    try:
        LMSTUDIO_URL = lmstudio_url if lmstudio_url else 'http://localhost:1234'
        headers = {}
        if lmstudio_api_key:
            headers['Authorization'] = f'Bearer {lmstudio_api_key}'
        response = requests.get(f'{LMSTUDIO_URL}/v1/models', timeout=5, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return [model['id'] for model in data.get('data', [])]
    except Exception as e:
        print(ConsoleColor.error(f"Failed to get LM Studio models: {e}"))
    return []

def get_available_models():
    """Get available models from all configured providers"""
    global APP_CONFIG
    default_provider = APP_CONFIG.get('translation', {}).get('default_provider', 'lps')
    if default_provider == 'lps' and LPS_AVAILABLE:
        lps_models = get_lps_models()
        if lps_models:
            return [m['model_path'] for m in lps_models]
    return get_lmstudio_models()


# ═══════════════════════════════════════════════════════════════
# LPS (Local Python Server) Provider - GGUF via llama-cpp-python
# ═══════════════════════════════════════════════════════════════

def _get_lps_config(param_name, default=None):
    """Read a parameter from the LPS config section"""
    global APP_CONFIG
    return APP_CONFIG.get('lps', {}).get(param_name, default)


def get_lps_models_dir():
    """Get the LPS models directory from config, resolved to absolute path"""
    global APP_CONFIG
    lps_config = APP_CONFIG.get('lps', {})
    models_dir = lps_config.get('models_dir', 'models/translate')
    if not os.path.isabs(models_dir):
        models_dir = os.path.join(BASE_DIR, models_dir)
    return os.path.normpath(models_dir)


def get_lps_models():
    """
    Scan models/translate/ for GGUF model files.
    Directory structure:
        models/translate/
          ├── tencent/           (vendor sub-directory)
          │   ├── Hy-MT2-1.8B-2Bit-GGUF/
          │   │   └── Hy-MT2-1.8B-2Bit.gguf
          │   └── Hy-MT2-1.8B-1.25Bit-GGUF/
          │       └── Hy-MT2-1.8B-1.25Bit.gguf
          └── other_vendor/
              └── model.gguf
    Returns list of dicts: [{vendor, model_name, filename, model_path, size_mb}]
    """
    models_dir = get_lps_models_dir()
    if not os.path.isdir(models_dir):
        print(ConsoleColor.warning(f"LPS models directory not found: {models_dir}"))
        return []

    models = []
    try:
        for vendor_name in sorted(os.listdir(models_dir)):
            vendor_path = os.path.join(models_dir, vendor_name)
            if not os.path.isdir(vendor_path):
                continue
            for model_dir_name in sorted(os.listdir(vendor_path)):
                model_dir_path = os.path.join(vendor_path, model_dir_name)
                if not os.path.isdir(model_dir_path):
                    continue
                for file_name in sorted(os.listdir(model_dir_path)):
                    if file_name.lower().endswith('.gguf'):
                        full_path = os.path.join(model_dir_path, file_name)
                        size_bytes = os.path.getsize(full_path)
                        size_mb = round(size_bytes / (1024 * 1024), 1)
                        relative_path = os.path.relpath(full_path, BASE_DIR).replace('\\', '/')
                        models.append({
                            'vendor': vendor_name,
                            'model_name': model_dir_name,
                            'filename': file_name,
                            'model_path': relative_path,
                            'absolute_path': full_path,
                            'size_mb': size_mb
                        })
    except Exception as e:
        print(ConsoleColor.error(f"Error scanning LPS models: {e}"))
    return models


def load_lps_model(model_path=None):
    """Load a GGUF model into memory via llama-cpp-python"""
    global _lps_model, _lps_current_model_path, APP_CONFIG

    if not LPS_AVAILABLE:
        print(ConsoleColor.error("llama-cpp-python is not installed. Cannot load LPS model."))
        return False

    if model_path is None:
        model_path = _get_lps_config('default_model', '')

    if not model_path:
        print(ConsoleColor.error("No LPS model specified"))
        return False

    if not os.path.isabs(model_path):
        model_path = os.path.join(BASE_DIR, model_path)
    model_path = os.path.normpath(model_path)

    if not os.path.exists(model_path):
        print(ConsoleColor.error(f"LPS model file not found: {model_path}"))
        return False

    with _lps_model_lock:
        if _lps_model is not None and _lps_current_model_path == model_path:
            return True

        if _lps_model is not None:
            print(ConsoleColor.info(f"Unloading previous LPS model: {_lps_current_model_path}"))
            _lps_model = None
            _lps_current_model_path = None
            import gc
            gc.collect()

        n_ctx = int(_get_lps_config('n_ctx', 2048))
        n_threads = int(_get_lps_config('n_threads', 4))
        n_gpu_layers = int(_get_lps_config('n_gpu_layers', 0))
        verbose = bool(_get_lps_config('verbose', False))

        print(ConsoleColor.info(f"Loading LPS model: {model_path}"))
        print(ConsoleColor.info(f"  n_ctx={n_ctx}, n_threads={n_threads}, n_gpu_layers={n_gpu_layers}"))

        try:
            _lps_model = Llama(
                model_path=model_path,
                n_ctx=n_ctx,
                n_threads=n_threads,
                n_gpu_layers=n_gpu_layers,
                verbose=verbose
            )
            _lps_current_model_path = model_path
            print(ConsoleColor.success(f"LPS model loaded: {os.path.basename(model_path)}"))
            return True
        except Exception as e:
            print(ConsoleColor.error(f"Failed to load LPS model: {e}"))
            _lps_model = None
            return False


def unload_lps_model():
    """Unload the current LPS model from memory"""
    global _lps_model, _lps_current_model_path
    with _lps_model_lock:
        if _lps_model is not None:
            print(ConsoleColor.info(f"Unloading LPS model: {_lps_current_model_path}"))
            _lps_model = None
            _lps_current_model_path = None
            import gc
            gc.collect()


def translate_stream_lps(text, model_path=None, target_lang=None, seq=0):
    """Streaming translation using LPS — supports llama_cpp and openai_compatible backends"""
    global translation_cache, current_translation_style, pending_translations

    if not target_lang:
        target_lang = 'English'

    backend = _get_lps_config('backend', 'openai_compatible')

    if backend == 'openai_compatible':
        _translate_via_openai(text, model_path, target_lang, seq=seq)
        return

    if not LPS_AVAILABLE:
        socketio.emit('translation_error', {'message': 'LPS (llama_cpp) not available. Install llama-cpp-python.', 'seq': seq})
        return

    if model_path is None:
        model_path = _get_lps_config('default_model', '')

    if not os.path.isabs(model_path):
        model_path = os.path.join(BASE_DIR, model_path)
    model_path = os.path.normpath(model_path)

    import hashlib
    text_hash = hashlib.md5(text.encode()).hexdigest()[:12]
    model_key = os.path.basename(model_path)
    style_key = target_lang.lower()
    cache_key = f"lps:{model_key}:{style_key}:{text_hash}"

    if cache_key in pending_translations:
        return
    pending_translations.add(cache_key)

    if cache_key in translation_cache:
        cached_result = translation_cache.get(cache_key)
        print(ConsoleColor.highlight(f"⚡ LPS CACHE HIT: '{text[:20]}...'"))
        pending_translations.discard(cache_key)
        for i, char in enumerate(cached_result):
            socketio.emit('translation_chunk', {
                'chunk': char,
                'translation': cached_result[:i+1],
                'char_count': i+1,
                'seq': seq
            })
            time.sleep(0.01)
        socketio.emit('translation_complete', {
            'translation': cached_result,
            'total_time': '0.00s',
            'chars': len(cached_result),
            'first_chunk_time': '0.001s',
            'seq': seq
        })
        return

    system_prompt = (
        f"You are a professional translator. Translate the following text from Chinese to {target_lang}. "
        f"Output ONLY the translated text, nothing else. Do NOT add explanations, notes, quotes, or prefixes. "
        f"Do NOT say 'here is the translation' or similar. Just output the raw translated text directly."
    )

    temperature = float(_get_lps_config('temperature', 0.3))
    max_tokens = int(_get_lps_config('max_tokens', 512))
    top_p = float(_get_lps_config('top_p', 0.8))

    def _do_lps_translation():
        global _lps_model
        try:
            if _is_translation_stale(seq):
                print(ConsoleColor.debug(f"LPS translation seq={seq} already superseded at start"))
                pending_translations.discard(cache_key)
                return
            if not load_lps_model(model_path):
                socketio.emit('translation_error', {'message': f'Failed to load LPS model: {model_path}', 'seq': seq})
                pending_translations.discard(cache_key)
                return

            start_time = time.time()
            translation = ""
            char_count = 0
            first_chunk_time = None

            with _lps_model_lock:
                if _lps_model is None:
                    socketio.emit('translation_error', {'message': 'LPS model not loaded', 'seq': seq})
                    pending_translations.discard(cache_key)
                    return

                stream = _lps_model.create_chat_completion(
                    messages=[
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': text}
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    stream=True
                )

            for chunk in stream:
                choices = chunk.get('choices', [])
                if choices:
                    delta = choices[0].get('delta', {})
                    content = delta.get('content', '')
                    if content:
                        if _is_translation_stale(seq):
                            print(ConsoleColor.debug(f"LPS translation seq={seq} superseded, stopping early"))
                            return
                        if first_chunk_time is None:
                            first_chunk_time = time.time() - start_time
                        translation += content
                        char_count += len(content)
                        socketio.emit('translation_chunk', {
                            'chunk': content,
                            'translation': translation,
                            'char_count': char_count,
                            'seq': seq
                        })

            total_time = time.time() - start_time

            if _is_translation_stale(seq):
                pending_translations.discard(cache_key)
                return

            if translation:
                translation_cache.put(cache_key, translation)

            socketio.emit('translation_complete', {
                'translation': translation,
                'total_time': f'{total_time:.2f}s',
                'chars': char_count,
                'first_chunk_time': f'{first_chunk_time:.3f}s' if first_chunk_time else 'N/A',
                'seq': seq
            })

            print(ConsoleColor.success(f"LPS DONE: {char_count} chars, total {total_time:.3f}s"))

        except Exception as e:
            error_msg = f'LPS translation error: {str(e)}'
            socketio.emit('translation_error', {'message': error_msg, 'seq': seq})
            print(ConsoleColor.error(error_msg))
            import traceback
            traceback.print_exc()
        finally:
            pending_translations.discard(cache_key)

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix='lps_translator') as executor:
        executor.submit(_do_lps_translation)


def _translate_via_openai(text, model_path, target_lang, seq=0):
    """Translation via OpenAI-compatible API (e.g. llama-server, Ollama, vLLM)"""
    global translation_cache, pending_translations

    api_url = _get_lps_config('openai_url', 'http://localhost:8080/v1')
    api_url = api_url.rstrip('/')
    model_name = model_path or _get_lps_config('default_model', 'default')
    if '/' in model_name:
        model_name = os.path.basename(model_name).replace('.gguf', '')

    import hashlib
    text_hash = hashlib.md5(text.encode()).hexdigest()[:12]
    style_key = target_lang.lower()
    cache_key = f"lps_openai:{model_name}:{style_key}:{text_hash}"

    if cache_key in pending_translations:
        return
    pending_translations.add(cache_key)

    if cache_key in translation_cache:
        cached_result = translation_cache.get(cache_key)
        print(ConsoleColor.highlight(f"⚡ LPS OpenAI CACHE HIT: '{text[:20]}...'"))
        pending_translations.discard(cache_key)
        for i, char in enumerate(cached_result):
            socketio.emit('translation_chunk', {
                'chunk': char, 'translation': cached_result[:i+1], 'char_count': i+1, 'seq': seq
            })
            time.sleep(0.01)
        socketio.emit('translation_complete', {
            'translation': cached_result, 'total_time': '0.00s',
            'chars': len(cached_result), 'first_chunk_time': '0.001s', 'seq': seq
        })
        return

    system_prompt = (
        f"Translate the following text from Chinese to {target_lang}. "
        f"Output ONLY the translated text, nothing else."
    )

    temperature = float(_get_lps_config('temperature', 0.3))
    max_tokens = int(_get_lps_config('max_tokens', 512))
    top_p = float(_get_lps_config('top_p', 0.8))

    def _do_openai_translation():
        try:
            if _is_translation_stale(seq):
                print(ConsoleColor.debug(f"OpenAI translation seq={seq} already superseded at start"))
                pending_translations.discard(cache_key)
                return
            start_time = time.time()
            translation = ""
            char_count = 0

            response = requests.post(
                f'{api_url}/chat/completions',
                json={
                    'model': model_name,
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': text}
                    ],
                    'stream': True,
                    'temperature': temperature,
                    'max_tokens': max_tokens,
                    'top_p': top_p
                },
                headers={'Content-Type': 'application/json'},
                stream=True,
                timeout=120
            )

            for line in response.iter_lines(decode_unicode=True):
                if line and line.startswith('data: '):
                    data_str = line[6:]
                    if data_str.strip() == '[DONE]':
                        break
                    try:
                        chunk_data = json.loads(data_str)
                        choices = chunk_data.get('choices', [])
                        if choices:
                            delta = choices[0].get('delta', {})
                            content = delta.get('content', '')
                            if content:
                                if _is_translation_stale(seq):
                                    print(ConsoleColor.debug(f"OpenAI translation seq={seq} superseded, stopping early"))
                                    return
                                translation += content
                                char_count += len(content)
                                socketio.emit('translation_chunk', {
                                    'chunk': content,
                                    'translation': translation,
                                    'char_count': char_count,
                                    'seq': seq
                                })
                    except json.JSONDecodeError:
                        continue

            total_time = time.time() - start_time

            if _is_translation_stale(seq):
                pending_translations.discard(cache_key)
                return

            if translation:
                translation_cache.put(cache_key, translation)

            socketio.emit('translation_complete', {
                'translation': translation,
                'total_time': f'{total_time:.2f}s',
                'chars': char_count,
                'first_chunk_time': f'{total_time:.3f}s',
                'seq': seq
            })

            print(ConsoleColor.success(f"LPS OpenAI DONE: {char_count} chars, total {total_time:.3f}s via {api_url}"))

        except Exception as e:
            error_msg = f'LPS OpenAI translation error: {str(e)}'
            socketio.emit('translation_error', {'message': error_msg, 'seq': seq})
            print(ConsoleColor.error(error_msg))
        finally:
            pending_translations.discard(cache_key)

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix='lps_openai') as executor:
        executor.submit(_do_openai_translation)


@app.route('/api/models')
def get_models():
    """Get available models from configured providers"""
    models = get_available_models()
    return jsonify(models)

@app.route('/api/providers')
def get_providers():
    """Get available translation providers and their status"""
    global APP_CONFIG

    lps_models = []
    if LPS_AVAILABLE:
        lps_models = get_lps_models()

    providers = {
        'lps': {
            'name': 'LPS (Local Python Server)',
            'available': LPS_AVAILABLE and len(lps_models) > 0,
            'models_dir': get_lps_models_dir(),
            'default_model': _get_lps_config('default_model', ''),
            'model_count': len(lps_models),
            'models': [{
                'model_path': m['model_path'],
                'vendor': m['vendor'],
                'model_name': m['model_name'],
                'filename': m['filename'],
                'size_mb': m['size_mb']
            } for m in lps_models],
            'description': 'Local GGUF model inference via llama-cpp-python'
        },
        'lmstudio': {
            'name': 'LM Studio',
            'available': len(get_lmstudio_models()) > 0,
            'url': lmstudio_url if lmstudio_url else 'http://localhost:1234',
            'description': 'LM Studio local server'
        }
    }
    return jsonify(providers)

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
    global APP_CONFIG, lmstudio_url, lmstudio_api_key
    settings = {
        # LM Studio 配置
        'lmstudio_url': lmstudio_url,
        'lmstudio_api_key': lmstudio_api_key,
        
        # LPS 配置
        'lps': APP_CONFIG.get('lps', {
            'enabled': True, 'models_dir': 'models/translate', 'default_model': '',
            'n_ctx': 2048, 'n_threads': 4, 'n_gpu_layers': 0,
            'temperature': 0.3, 'max_tokens': 512, 'top_p': 0.8, 'verbose': False
        }),
        'lps_available': LPS_AVAILABLE,
        'lps_models': get_lps_models() if LPS_AVAILABLE else [],
        
        # 翻译设置
        'translation': APP_CONFIG.get('translation', {'default_provider': 'lps', 'default_model': ''}),
        
        # 系统设置
        'system': APP_CONFIG.get('system', {'enable_monitor': False}),
        
        # 语音识别设置
        'speech': APP_CONFIG.get('speech', {'default_microphone': 'auto', 'sample_rate': '16000'}),
        
        # TTS 设置
        'tts': APP_CONFIG.get('tts', {'enabled': True, 'default_model': 's2Gv2ProPlus'}),
        
        # 网络设置
        'server': APP_CONFIG.get('server', {'port': '5001', 'enable_cors': True})
    }
    return jsonify(settings)

@app.route('/api/settings', methods=['POST'])
def save_settings():
    """Save system settings"""
    global APP_CONFIG, lmstudio_url, lmstudio_api_key
    data = request.json
    
    try:
        # Update LM Studio configuration
        if 'lmstudio_url' in data:
            lmstudio_url = data['lmstudio_url']
        
        if 'lmstudio_api_key' in data:
            lmstudio_api_key = data['lmstudio_api_key']
        
        # 翻译设置
        if 'translation' in data:
            APP_CONFIG['translation'] = data['translation']
        
        # LPS 设置
        if 'lps' in data:
            APP_CONFIG['lps'] = data['lps']
        
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
    global components_loaded
    
    try:
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
    """Optimize translation style using AI (LM Studio)"""
    global lmstudio_url, lmstudio_api_key
    data = request.json
    user_input = data.get('input', '')
    
    if not user_input:
        return jsonify({'error': 'Input is required'}), 400
    
    # LM Studio API (OpenAI-compatible)
    API_URL = lmstudio_url if lmstudio_url else 'http://localhost:1234'
    
    # Check if service is available
    headers = {}
    if lmstudio_api_key:
        headers['Authorization'] = f'Bearer {lmstudio_api_key}'
    try:
        response = requests.get(f'{API_URL}/v1/models', timeout=5, headers=headers)
        if response.status_code != 200:
            return jsonify({'error': 'LM Studio service is unavailable. Please start LM Studio service'}), 503
    except Exception as e:
        return jsonify({'error': f'Unable to connect to LM Studio service: {str(e)}'}), 503
    
    # Prompt to optimize user input
    optimization_prompt = f"Analyze the following user input and optimize it to create a clear, concise translation style instruction. The input may describe a style, occasion, or context for translation.\n\nUser input: {user_input}\n\nOptimized style instruction:"
    
    try:
        models = get_lmstudio_models()
        model_name = models[0] if models else 'default'
        response = requests.post(
            f'{API_URL}/v1/chat/completions',
            json={
                'model': model_name,
                'messages': [{'role': 'user', 'content': optimization_prompt}],
                'temperature': 0.7,
                'max_tokens': 100,
                'top_p': 0.9
            },
            headers=headers,
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            choices = data.get('choices', [])
            if choices:
                optimized_style = choices[0].get('message', {}).get('content', '').strip()
            else:
                optimized_style = ''
            
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
        'version': '0.4.1',
        'timestamp': datetime.now().isoformat(),
        'memory': memory_info,
        'cpu_percent': cpu_percent,
        'gpu': gpu_info
    })

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
                dtype="float16",  # FP16 for speed
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
                
                # Use provided reference text or fall back to a short segment
                prompt_text = reference_text if reference_text else text[:15]
                
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
    
    provider = APP_CONFIG.get('translation', {}).get('default_provider', 'lps')
    
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

streaming_clients = {}

def clean_sensevoice_text(text):
    """Clean up special tokens from SenseVoice output using official postprocess function"""
    if not text:
        return ""
    
    try:
        from funasr.utils.postprocess_utils import rich_transcription_postprocess
        result = rich_transcription_postprocess(text)
        # Remove emoji and other special unicode characters
        result = _remove_non_text_chars(result)
        return result
    except Exception as e:
        # Fallback to manual cleaning if the function is not available
        tokens_to_remove = [
            '<|zh|>', '<|en|>', '<|ja|>', '<|ko|>', '<|yue|>', '<|ca|>', '<|ru|>',
            '<|pt|>', '<|ar|>', '<|ta|>', '<|hi|>', '<|mi|>', '<|id|>', '<|de|>',
            '<|fr|>', '<|es|>', '<|emo|>', '<|EMO_UNKNOWN|>', '<|Speech|>',
            '<|Music|>', '<|Noise|>', '<|Punctuation|>', '<|woitn|>', '<|withitn|>',
            '<|HAPPY|>', '<|SAD|>', '<|ANGRY|>', '<|NEUTRAL|>', '<|FEARFUL|>',
            '<|DISGUSTED|>', '<|SURPRISED|>', '<|EMO_UNKNOWN|>',
        ]
        
        cleaned = text
        for token in tokens_to_remove:
            cleaned = cleaned.replace(token, '')
        
        cleaned = ' '.join(cleaned.split())
        return cleaned


def _remove_non_text_chars(text):
    """Remove emoji, special symbols, and other non-text unicode from ASR output"""
    import re
    # Keep: CJK characters, ASCII letters/digits, common punctuation, spaces
    # Remove: emojis, special unicode symbols
    cleaned = re.sub(r'[^\u4e00-\u9fff\u3000-\u303f\uff00-\uffefa-zA-Z0-9\s\.\,\!\?\;\:\'\"\-\(\)\[\]\{\}，。！？；：、""''…—～·《》【】（）]', '', text)
    # Clean up multiple spaces
    cleaned = ' '.join(cleaned.split())
    return cleaned

def _asr_worker(client_id):
    """Background thread: process audio queue → run ASR → emit results"""
    global streaming_clients
    
    while client_id in streaming_clients and streaming_clients[client_id]['is_streaming']:
        try:
            item = streaming_clients[client_id]['audio_queue'].get(timeout=0.1)
        except queue.Empty:
            continue
        
        if item is None:
            break
        
        audio_data, language = item
        recognizer = streaming_clients[client_id]['recognizer']
        
        try:
            import numpy as np
            
            results = recognizer.process_stream(audio_data, language)
            
            if results:
                for result in results:
                    text = result.get('text', '')
                    confidence = result.get('confidence', 0)
                    detected_lang = result.get('language', 'zh')
                    elapsed_ms = result.get('elapsed_ms', 0)
                    
                    cleaned_text = clean_sensevoice_text(text)
                    
                    if cleaned_text:
                        socketio.emit('recognition_result', {
                            'text': cleaned_text,
                            'confidence': confidence * 100 if confidence else 85,
                            'language': detected_lang,
                            'is_partial': True,
                            'elapsed_ms': elapsed_ms
                        }, room=client_id)
                        print(f"[ASR Thread {client_id[:6]}] {cleaned_text[:40]} ({elapsed_ms}ms)")
            
            if len(audio_data) > 0:
                audio_np = np.array(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
                audio_level = float(min(100, np.abs(audio_np).mean() * 200))
                socketio.emit('audio_level', {'level': audio_level}, room=client_id)
                
        except Exception as e:
            print(f"ASR worker error ({client_id[:6]}): {e}")
            import traceback
            traceback.print_exc()


@socketio.on('stream_audio')
def handle_stream_audio(data):
    global streaming_clients
    
    client_id = request.sid
    audio_data = data.get('data', [])
    device = data.get('device', 'auto')
    language = data.get('language', None)
    
    if client_id not in streaming_clients:
        print(f"Creating new streaming client: {client_id}")

        from funasr_asr import StreamingRecognizer, get_device, initialize_funasr, _funasr_model

        if _funasr_model is None:
            print(ConsoleColor.warning("FunASR model not loaded, initializing now..."))
            model_path = "C:/Users/26276/Desktop/project/main/V0.3/models/stt/SenseVoiceSmall"
            device_type = get_device()
            ok = initialize_funasr(model_name=model_path, device=device_type)
            if not ok:
                emit('error', {'message': 'Failed to load speech recognition model'})
                return
            print(ConsoleColor.success("FunASR model loaded on demand"))

        model_path = "C:/Users/26276/Desktop/project/main/V0.3/models/stt/SenseVoiceSmall"
        device_type = get_device()
        
        recognizer = StreamingRecognizer(model_path=model_path, device=device_type, use_vad=True)
        
        audio_queue = queue.Queue()
        worker_thread = threading.Thread(target=_asr_worker, args=(client_id,), daemon=True)
        
        streaming_clients[client_id] = {
            'is_streaming': True,
            'device': device,
            'language': language,
            'recognizer': recognizer,
            'audio_queue': audio_queue,
            'worker_thread': worker_thread
        }
        
        worker_thread.start()
        print(f"Created streaming client {client_id} with background thread")
        emit('log', {'message': 'Streaming recognizer initialized', 'type': 'success'})
    
    if not streaming_clients[client_id]['is_streaming']:
        return
    
    try:
        streaming_clients[client_id]['audio_queue'].put_nowait((audio_data, language))
    except queue.Full:
        pass


@socketio.on('stop_stream')
def handle_stop_stream():
    global streaming_clients
    
    client_id = request.sid
    if client_id in streaming_clients:
        streaming_clients[client_id]['is_streaming'] = False
        try:
            streaming_clients[client_id]['audio_queue'].put_nowait(None)
        except queue.Full:
            pass
        recognizer = streaming_clients[client_id].get('recognizer')
        if recognizer:
            recognizer.reset()
        del streaming_clients[client_id]

@socketio.on('translate_debug_text')
def handle_translate_debug_text(data):
    """Handle direct text translation for debug page"""
    global APP_CONFIG
    text = data.get('text', '').strip()
    provider = APP_CONFIG.get('translation', {}).get('default_provider', 'lps')
    model_name = data.get('model_name', '')
    source_lang = data.get('source_lang', 'zh')
    target_lang = data.get('target_lang', 'en')
    preset_id = data.get('preset_id', None)
    translation_style = data.get('translation_style', '')
    
    if not text:
        emit('translation_error', {'message': 'No text provided for translation'})
        return
    
    print(ConsoleColor.info(f"[Translation Debug] Text: '{text[:50]}...' ({source_lang}→{target_lang}), Provider: LM Studio"))
    emit('translation_status', {'status': 'translating', 'message': f'Translating ({source_lang}→{target_lang})...'})
    
    try:
        global current_translation_style
        if translation_style:
            current_translation_style = translation_style
        
        translate_stream(text, model_name, provider, preset_id, target_lang=target_lang)
            
    except Exception as e:
        error_msg = f'Translation failed: {str(e)}'
        print(ConsoleColor.error(error_msg))
        emit('translation_error', {'message': error_msg})

SENTENCE_END_PUNCT = set('。.!！?？\n')


def _tts_infer(speaker_path, text):
    global gsv_tts, gsv_tts_cache
    cache_key = generate_gsv_tts_cache_key(speaker_path, text)
    if cache_key in gsv_tts_cache:
        audio_data = gsv_tts_cache.get(cache_key)
        return audio_data, True
    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = os.path.join(temp_dir, 'output.wav')
        audio = gsv_tts.infer(
            text=text,
            spk_audio_path=speaker_path,
            prompt_audio_path=speaker_path,
            prompt_audio_text=text[:15],
            speed=1.0
        )
        audio.save(output_path)
        with open(output_path, 'rb') as f:
            audio_data = f.read()
        gsv_tts_cache.put(cache_key, audio_data)
        return audio_data, False


def _tts_worker(tts_queue, speaker_path, results_out):
    global gsv_tts
    while True:
        item = tts_queue.get()
        if item is None:
            break
        seq, sentence = item
        try:
            audio_data, cached = _tts_infer(speaker_path, sentence)
            results_out.append((seq, sentence, audio_data, cached))
        except Exception as e:
            print(ConsoleColor.error(f"TTS worker error (seq={seq}): {e}"))
            results_out.append((seq, sentence, None, False))


def _maybe_extract_sentences(buffer, tts_queue, seq_counter):
    """Extract complete sentences from buffer and push to TTS queue."""
    extracted = []
    remaining = buffer
    while True:
        found = -1
        for i, ch in enumerate(remaining):
            if ch in SENTENCE_END_PUNCT:
                found = i
                break
        if found < 0:
            break
        sentence = remaining[:found + 1].strip()
        remaining = remaining[found + 1:]
        if len(sentence) >= 4:
            seq = seq_counter[0]
            seq_counter[0] += 1
            tts_queue.put((seq, sentence))
            extracted.append(sentence)
    return remaining, extracted


def _emit_tts_results(results_out, done_event, emit_func, event_name='tts_pipeline_audio_chunk'):
    last_emitted_idx = 0
    all_done = False
    while not all_done:
        if done_event.is_set():
            all_done = True
        while last_emitted_idx < len(results_out):
            seq, sentence, audio_data, cached = results_out[last_emitted_idx]
            last_emitted_idx += 1
            if audio_data:
                emit_func(event_name, {
                    'seq': seq,
                    'audio': audio_data,
                    'size': len(audio_data),
                    'cached': cached,
                    'text': sentence
                })
                print(ConsoleColor.success(
                    f"[TTS chunk] seq={seq}: '{sentence[:20]}...' ({len(audio_data)} bytes)")
                )
        time.sleep(0.02)


def _tts_pipeline_translate_lps(text, model_name, target_lang, speaker_wav):
    """TTS pipeline using LPS for translation then GSV-TTS for audio.
    Supports both llama_cpp and openai_compatible backends."""
    global gsv_tts, gsv_tts_cache, APP_CONFIG

    if not model_name:
        model_name = _get_lps_config('default_model', '')

    backend = _get_lps_config('backend', 'openai_compatible')

    if backend == 'openai_compatible':
        _tts_pipeline_openai(text, model_name, target_lang, speaker_wav)
        return

    if not LPS_AVAILABLE:
        emit('tts_pipeline_error', {'message': 'LPS (llama_cpp) not available'})
        return

    lps_model_path = model_name
    if not os.path.isabs(lps_model_path):
        lps_model_path = os.path.join(BASE_DIR, lps_model_path)
    lps_model_path = os.path.normpath(lps_model_path)

    system_prompt = f"Translate from Chinese to {target_lang}. Output only the translation."

    temperature = float(_get_lps_config('temperature', 0.3))
    max_tokens = int(_get_lps_config('max_tokens', 512))
    top_p = float(_get_lps_config('top_p', 0.8))

    emit('tts_pipeline_status', {'stage': 'translating', 'message': 'Translating vía LPS (llama_cpp)...'})

    speaker_path = os.path.join(VOICE_CLONE_DIR, speaker_wav)

    tts_queue = queue.Queue()
    results_out = []
    done_event = threading.Event()
    seq_counter = [0]

    worker = threading.Thread(target=_tts_worker, args=(tts_queue, speaker_path, results_out), daemon=True)
    worker.start()

    emitter_thread = threading.Thread(
        target=_emit_tts_results, args=(results_out, done_event, emit), daemon=True
    )
    emitter_thread.start()

    def _do_lps_pipeline():
        try:
            if not load_lps_model(lps_model_path):
                emit('tts_pipeline_error', {'message': f'Failed to load LPS model: {lps_model_path}'})
                done_event.set()
                return

            start_time = time.time()
            translation = ""
            char_count = 0
            sentence_buffer = ""

            with _lps_model_lock:
                if _lps_model is None:
                    emit('tts_pipeline_error', {'message': 'LPS model not loaded'})
                    done_event.set()
                    return

                stream = _lps_model.create_chat_completion(
                    messages=[
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': text}
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    stream=True
                )

            for chunk in stream:
                choices = chunk.get('choices', [])
                if choices:
                    delta = choices[0].get('delta', {})
                    content = delta.get('content', '')
                    if content:
                        translation += content
                        char_count += len(content)
                        sentence_buffer += content

                        emit('tts_pipeline_chunk', {
                            'chunk': content,
                            'translation': translation,
                            'char_count': char_count
                        })

                        if _is_sentence_end(content):
                            sentence_text = sentence_buffer.strip()
                            if sentence_text:
                                seq_counter[0] += 1
                                tts_queue.put({
                                    'text': sentence_text,
                                    'seq': seq_counter[0],
                                    'is_final': False
                                })
                            sentence_buffer = ""

            if sentence_buffer.strip():
                seq_counter[0] += 1
                tts_queue.put({
                    'text': sentence_buffer.strip(),
                    'seq': seq_counter[0],
                    'is_final': True
                })

            tts_queue.put(None)
            done_event.set()

            total_time = time.time() - start_time
            emit('tts_pipeline_translation_complete', {
                'translation': translation,
                'total_time': f'{total_time:.2f}s',
                'chars': char_count,
                'first_chunk_time': f'{total_time:.3f}s'
            })

            print(ConsoleColor.success(f"TTS Pipeline (LPS llama_cpp) complete: {char_count} chars"))

        except Exception as e:
            print(ConsoleColor.error(f"TTS Pipeline (LPS) error: {e}"))
            import traceback
            traceback.print_exc()
            emit('tts_pipeline_error', {'message': f'Pipeline error: {str(e)}'})
            done_event.set()

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix='tts_lps') as executor:
        executor.submit(_do_lps_pipeline)


def _tts_pipeline_openai(text, model_name, target_lang, speaker_wav):
    """TTS pipeline via OpenAI-compatible API for translation, then GSV-TTS for audio"""
    global gsv_tts, gsv_tts_cache

    api_url = _get_lps_config('openai_url', 'http://localhost:8080/v1')
    api_url = api_url.rstrip('/')
    model = model_name or _get_lps_config('default_model', 'default')
    if '/' in model:
        model = os.path.basename(model).replace('.gguf', '')

    system_prompt = f"Translate from Chinese to {target_lang}. Output only the translation."

    temperature = float(_get_lps_config('temperature', 0.3))
    max_tokens = int(_get_lps_config('max_tokens', 512))
    top_p = float(_get_lps_config('top_p', 0.8))

    emit('tts_pipeline_status', {'stage': 'translating', 'message': f'Translating vía LPS OpenAI ({api_url})...'})

    speaker_path = os.path.join(VOICE_CLONE_DIR, speaker_wav)

    tts_queue = queue.Queue()
    results_out = []
    done_event = threading.Event()
    seq_counter = [0]

    worker = threading.Thread(target=_tts_worker, args=(tts_queue, speaker_path, results_out), daemon=True)
    worker.start()

    emitter_thread = threading.Thread(
        target=_emit_tts_results, args=(results_out, done_event, emit), daemon=True
    )
    emitter_thread.start()

    def _do_openai_pipeline():
        try:
            start_time = time.time()
            translation = ""
            char_count = 0
            sentence_buffer = ""

            response = requests.post(
                f'{api_url}/chat/completions',
                json={
                    'model': model,
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': text}
                    ],
                    'stream': True,
                    'temperature': temperature,
                    'max_tokens': max_tokens,
                    'top_p': top_p
                },
                headers={'Content-Type': 'application/json'},
                stream=True,
                timeout=120
            )

            for line in response.iter_lines(decode_unicode=True):
                if line and line.startswith('data: '):
                    data_str = line[6:]
                    if data_str.strip() == '[DONE]':
                        break
                    try:
                        chunk_data = json.loads(data_str)
                        choices = chunk_data.get('choices', [])
                        if choices:
                            delta = choices[0].get('delta', {})
                            content = delta.get('content', '')
                            if content:
                                translation += content
                                char_count += len(content)
                                sentence_buffer += content

                                emit('tts_pipeline_chunk', {
                                    'chunk': content,
                                    'translation': translation,
                                    'char_count': char_count
                                })

                                if _is_sentence_end(content):
                                    sentence_text = sentence_buffer.strip()
                                    if sentence_text:
                                        seq_counter[0] += 1
                                        tts_queue.put({
                                            'text': sentence_text,
                                            'seq': seq_counter[0],
                                            'is_final': False
                                        })
                                    sentence_buffer = ""
                    except json.JSONDecodeError:
                        continue

            if sentence_buffer.strip():
                seq_counter[0] += 1
                tts_queue.put({
                    'text': sentence_buffer.strip(),
                    'seq': seq_counter[0],
                    'is_final': True
                })

            tts_queue.put(None)
            done_event.set()

            total_time = time.time() - start_time
            emit('tts_pipeline_translation_complete', {
                'translation': translation,
                'total_time': f'{total_time:.2f}s',
                'chars': char_count,
                'first_chunk_time': f'{total_time:.3f}s'
            })

            print(ConsoleColor.success(f"TTS Pipeline (LPS OpenAI) complete: {char_count} chars via {api_url}"))

        except Exception as e:
            print(ConsoleColor.error(f"TTS Pipeline (LPS OpenAI) error: {e}"))
            import traceback
            traceback.print_exc()
            emit('tts_pipeline_error', {'message': f'Pipeline error: {str(e)}'})
            done_event.set()

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix='tts_openai') as executor:
        executor.submit(_do_openai_pipeline)


@socketio.on('tts_debug_pipeline')
def handle_tts_debug_pipeline(data):
    """Handle TTS debug pipeline: translate → streaming sentence-level TTS"""
    global gsv_tts, current_translation_style, lmstudio_url, lmstudio_api_key, APP_CONFIG

    text = data.get('text', '').strip()
    model_name = data.get('model_name', '')
    source_lang = data.get('source_lang', 'zh')
    target_lang = data.get('target_lang', 'en')
    speaker_wav = data.get('speaker_wav', '')
    preset_id = data.get('preset_id', None)
    translation_style = data.get('translation_style', '')

    if not text:
        emit('tts_pipeline_error', {'message': 'No text provided'})
        return

    if not GSV_TTS_AVAILABLE or gsv_tts is None:
        emit('tts_pipeline_error', {'message': 'TTS not available'})
        return

    if not speaker_wav:
        emit('tts_pipeline_error', {'message': 'No speaker audio selected'})
        return

    speaker_path = os.path.join(VOICE_CLONE_DIR, speaker_wav)
    if not os.path.exists(speaker_path):
        emit('tts_pipeline_error', {'message': f'Speaker audio not found: {speaker_wav}'})
        return

    print(ConsoleColor.info(f"[TTS Debug Pipeline] Text: '{text[:50]}...' ({source_lang}→{target_lang})"))

    provider = APP_CONFIG.get('translation', {}).get('default_provider', 'lps')

    if provider == 'lps' and LPS_AVAILABLE:
        _tts_pipeline_translate_lps(text, model_name, target_lang, speaker_wav)
        return

    API_URL = lmstudio_url if lmstudio_url else 'http://localhost:1234'
    if not model_name:
        models = get_lmstudio_models()
        model_name = models[0] if models else 'default'

    headers = {'Content-Type': 'application/json'}
    if lmstudio_api_key:
        headers['Authorization'] = f'Bearer {lmstudio_api_key}'

    system_prompt = (
        f"Translate from Chinese to {target_lang}. Output only the translation."
    )

    if translation_style:
        current_translation_style = translation_style

    emit('tts_pipeline_status', {'stage': 'translating', 'message': 'Translating + streaming TTS...'})

    tts_queue = queue.Queue()
    results_out = []
    done_event = threading.Event()
    seq_counter = [0]

    worker = threading.Thread(target=_tts_worker, args=(tts_queue, speaker_path, results_out), daemon=True)
    worker.start()

    emitter_thread = threading.Thread(
        target=_emit_tts_results, args=(results_out, done_event, emit), daemon=True
    )
    emitter_thread.start()

    try:
        response = requests.post(
            f'{API_URL}/v1/chat/completions',
            json={
                'model': model_name,
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': text}
                ],
                'stream': True,
                'temperature': 0.3,
                'max_tokens': 512,
                'top_p': 0.8,
                'stop': None
            },
            headers=headers,
            stream=True,
            timeout=60
        )

        translation = ""
        char_count = 0
        sentence_buffer = ""
        first_chunk_time = None
        start_time = time.time()
        last_emit_time = start_time
        EMIT_INTERVAL = 0.03

        for line in response.iter_lines(decode_unicode=True):
            if line:
                if line.startswith('data: '):
                    data_str = line[6:]
                    if data_str.strip() == '[DONE]':
                        break
                    try:
                        chunk_data = json.loads(data_str)
                        choices = chunk_data.get('choices', [])
                        if choices:
                            choice = choices[0]
                            delta = choice.get('delta', {})
                            chunk = delta.get('content', '')
                            finish_reason = choice.get('finish_reason', '')

                            if chunk:
                                if first_chunk_time is None:
                                    first_chunk_time = time.time() - start_time

                                translation += chunk
                                char_count += len(chunk)
                                sentence_buffer += chunk

                                sentence_buffer, extracted = _maybe_extract_sentences(
                                    sentence_buffer, tts_queue, seq_counter
                                )
                                if extracted:
                                    print(ConsoleColor.debug(
                                        f"[TTS Pipeline] Sentences for TTS: {[s[:20]+'...' for s in extracted]}"
                                    ))

                                now = time.time()
                                if now - last_emit_time >= EMIT_INTERVAL:
                                    emit('tts_pipeline_chunk', {
                                        'chunk': chunk,
                                        'translation': translation,
                                        'char_count': char_count
                                    })
                                    last_emit_time = now

                            if finish_reason:
                                print(ConsoleColor.debug(
                                    f"[TTS Pipeline] finish_reason: {finish_reason}, chars: {char_count}"
                                ))

                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        print(ConsoleColor.warning(f"TTS pipeline translation parse error: {e}"))
                        continue

        total_time = time.time() - start_time

        sentence_buffer = sentence_buffer.strip()
        if len(sentence_buffer) >= 4:
            seq = seq_counter[0]
            seq_counter[0] += 1
            tts_queue.put((seq, sentence_buffer))
            print(ConsoleColor.debug(f"[TTS Pipeline] Final sentence: '{sentence_buffer[:30]}...'"))

        if translation:
            emit('tts_pipeline_chunk', {
                'chunk': '',
                'translation': translation,
                'char_count': char_count
            })

        emit('tts_pipeline_translation_complete', {
            'translation': translation,
            'total_time': f'{total_time:.2f}s',
            'chars': char_count,
            'sentence_count': seq_counter[0],
            'first_chunk_time': f'{first_chunk_time:.3f}s' if first_chunk_time else 'N/A'
        })

        tts_queue.put(None)
        worker.join(timeout=30)
        done_event.set()
        emitter_thread.join(timeout=5)

        emit('tts_pipeline_status', {
            'stage': 'complete',
            'message': f'Pipeline complete ({seq_counter[0]} sentences)'
        })

        print(ConsoleColor.success(
            f"TTS Pipeline complete: {char_count} chars, {seq_counter[0]} sentences"
        ))

    except requests.exceptions.Timeout:
        tts_queue.put(None)
        done_event.set()
        emit('tts_pipeline_error', {'message': 'Translation timeout'})
    except requests.exceptions.ConnectionError:
        tts_queue.put(None)
        done_event.set()
        emit('tts_pipeline_error', {'message': 'Cannot connect to LM Studio'})
    except Exception as e:
        tts_queue.put(None)
        done_event.set()
        print(ConsoleColor.error(f"TTS pipeline error: {e}"))
        import traceback
        traceback.print_exc()
        emit('tts_pipeline_error', {'message': f'Pipeline error: {str(e)}'})


@socketio.on('tts_only_pipeline')
def handle_tts_only_pipeline(data):
    """ASR text → TTS directly (no translation), streaming sentence-level"""
    global gsv_tts

    text = data.get('text', '').strip()
    speaker_wav = data.get('speaker_wav', '')

    if not text:
        emit('tts_only_error', {'message': 'No text provided'})
        return

    if not GSV_TTS_AVAILABLE or gsv_tts is None:
        emit('tts_only_error', {'message': 'TTS not available'})
        return

    if not speaker_wav:
        emit('tts_only_error', {'message': 'No speaker audio selected'})
        return

    speaker_path = os.path.join(VOICE_CLONE_DIR, speaker_wav)
    if not os.path.exists(speaker_path):
        emit('tts_only_error', {'message': f'Speaker audio not found: {speaker_wav}'})
        return

    print(ConsoleColor.info(f"[TTS Only Pipeline] Text: '{text[:50]}...', speaker: {speaker_wav}"))

    emit('tts_only_status', {'stage': 'generating_tts', 'message': 'Streaming TTS...'})

    tts_queue = queue.Queue()
    results_out = []
    done_event = threading.Event()
    seq_counter = [0]

    worker = threading.Thread(target=_tts_worker, args=(tts_queue, speaker_path, results_out), daemon=True)
    worker.start()

    emitter_thread = threading.Thread(
        target=_emit_tts_results, args=(results_out, done_event, emit, 'tts_only_audio_chunk'), daemon=True
    )
    emitter_thread.start()

    try:
        sentence_buffer = text

        sentence_buffer, extracted = _maybe_extract_sentences(
            sentence_buffer, tts_queue, seq_counter
        )

        sentence_buffer = sentence_buffer.strip()
        if len(sentence_buffer) >= 4:
            seq = seq_counter[0]
            seq_counter[0] += 1
            tts_queue.put((seq, sentence_buffer))

        tts_queue.put(None)
        worker.join(timeout=30)
        done_event.set()
        emitter_thread.join(timeout=5)

        emit('tts_only_status', {
            'stage': 'complete',
            'message': f'TTS complete ({seq_counter[0]} sentences)'
        })
        emit('tts_only_sentence_count', {'count': seq_counter[0]})

        print(ConsoleColor.success(
            f"TTS Only Pipeline complete: {len(text)} chars, {seq_counter[0]} sentences"
        ))

    except Exception as e:
        tts_queue.put(None)
        done_event.set()
        print(ConsoleColor.error(f"TTS only pipeline error: {e}"))
        import traceback
        traceback.print_exc()
        emit('tts_only_error', {'message': f'TTS error: {str(e)}'})


@socketio.on('start_loading')
def handle_start_loading(data):
    """Handle loading process with real-time progress for all models"""
    global components_loaded
    
    if not _loading_lock.acquire(blocking=False):
        emit('loading_progress', {
            'component': 'core',
            'status': 'warning',
            'message': 'Loading already in progress...',
            'progress': 0
        })
        return
    
    try:
        components = data.get('components', {})
        total_active = sum(1 for v in components.values() if v)
        if total_active == 0:
            total_active = 5
        
        current_step = 0
        
        # 1. System file validation (core)
        emit('loading_progress', {
            'component': 'core',
            'status': 'loading',
            'message': 'Validating system files...',
            'progress': 0
        })
        validate_system_files()
        current_step += 1
        emit('loading_progress', {
            'component': 'core',
            'status': 'completed',
            'message': 'System files validated',
            'progress': (current_step / total_active) * 100
        })
        
        # 2. Speech Recognition - FunASR
        if components.get('speech', True):
            emit('loading_progress', {
                'component': 'speech',
                'status': 'loading',
                'message': 'Loading speech recognition model (FunASR)...',
                'progress': (current_step / total_active) * 100
            })
            
            if FUNASR_AVAILABLE:
                try:
                    device = get_device()
                    print(ConsoleColor.info(f"Loading FunASR on {device}..."))
                    funasr_initialized = initialize_funasr(
                        model_name="C:/Users/26276/Desktop/project/main/V0.3/models/stt/SenseVoiceSmall",
                        device=device
                    )
                    if funasr_initialized:
                        emit('loading_progress', {
                            'component': 'speech',
                            'status': 'completed',
                            'message': f'Speech recognition ready ({device})',
                            'progress': ((current_step + 1) / total_active) * 100
                        })
                    else:
                        emit('loading_progress', {
                            'component': 'speech',
                            'status': 'error',
                            'message': 'Failed to load speech recognition model',
                            'progress': ((current_step + 1) / total_active) * 100
                        })
                except Exception as e:
                    print(ConsoleColor.error(f"FunASR loading error: {e}"))
                    emit('loading_progress', {
                        'component': 'speech',
                        'status': 'error',
                        'message': f'Speech recognition error: {str(e)[:50]}',
                        'progress': ((current_step + 1) / total_active) * 100
                    })
            else:
                emit('loading_progress', {
                    'component': 'speech',
                    'status': 'error',
                    'message': 'FunASR not available',
                    'progress': ((current_step + 1) / total_active) * 100
                })
            current_step += 1
        
        # 3. Translation Engine - LM Studio
        if components.get('translation', True):
            emit('loading_progress', {
                'component': 'translation',
                'status': 'loading',
                'message': 'Connecting to LM Studio...',
                'progress': (current_step / total_active) * 100
            })
            
            try:
                models = get_lmstudio_models()
                if models:
                    emit('loading_progress', {
                        'component': 'translation',
                        'status': 'completed',
                        'message': f'LM Studio connected ({len(models)} models)',
                        'progress': ((current_step + 1) / total_active) * 100
                    })
                else:
                    emit('loading_progress', {
                        'component': 'translation',
                        'status': 'warning',
                        'message': 'LM Studio not detected - translation unavailable',
                        'progress': ((current_step + 1) / total_active) * 100
                    })
            except Exception as e:
                emit('loading_progress', {
                    'component': 'translation',
                    'status': 'warning',
                    'message': f'LM Studio check failed: {str(e)[:50]}',
                    'progress': ((current_step + 1) / total_active) * 100
                })
            current_step += 1
        
        # 4. Text-to-Speech - GSV-TTS-Lite
        if components.get('tts', True):
            emit('loading_progress', {
                'component': 'tts',
                'status': 'loading',
                'message': 'Loading text-to-speech model...',
                'progress': (current_step / total_active) * 100
            })
            
            if GSV_TTS_AVAILABLE:
                try:
                    preload_gsv_tts()
                    emit('loading_progress', {
                        'component': 'tts',
                        'status': 'completed',
                        'message': 'TTS model ready',
                        'progress': ((current_step + 1) / total_active) * 100
                    })
                except Exception as e:
                    print(ConsoleColor.error(f"TTS loading error: {e}"))
                    emit('loading_progress', {
                        'component': 'tts',
                        'status': 'error',
                        'message': f'TTS loading failed: {str(e)[:50]}',
                        'progress': ((current_step + 1) / total_active) * 100
                    })
            else:
                emit('loading_progress', {
                    'component': 'tts',
                    'status': 'error',
                    'message': 'GSV-TTS-Lite not installed',
                    'progress': ((current_step + 1) / total_active) * 100
                })
            current_step += 1
        
        # 5. Model Manager
        if components.get('models', True):
            emit('loading_progress', {
                'component': 'models',
                'status': 'loading',
                'message': 'Initializing model manager...',
                'progress': (current_step / total_active) * 100
            })
            
            try:
                emit('loading_progress', {
                    'component': 'models',
                    'status': 'completed',
                    'message': 'Model manager ready',
                    'progress': ((current_step + 1) / total_active) * 100
                })
            except Exception as e:
                emit('loading_progress', {
                    'component': 'models',
                    'status': 'warning',
                    'message': f'Model manager: {str(e)[:30]}',
                    'progress': ((current_step + 1) / total_active) * 100
                })
            current_step += 1
        
        # Mark components as loaded
        components_loaded = True
        
        emit('loading_complete', {
            'status': 'success',
            'message': 'All models loaded successfully'
        })
        print(ConsoleColor.success("All models loaded successfully"))
        
    except Exception as e:
        error_msg = f'Loading failed: {str(e)}'
        print(ConsoleColor.error(error_msg))
        import traceback
        traceback.print_exc()
        emit('loading_error', {'message': error_msg})
    finally:
        _loading_lock.release()


def validate_system_files():
    """Validate that required system files and directories exist"""
    required_files = []
    required_dirs = [
        os.path.join(BASE_DIR, 'templates'),
        os.path.join(BASE_DIR, 'static'),
        os.path.join(BASE_DIR, 'config'),
    ]
    
    # Check required directories
    for dir_path in required_dirs:
        if not os.path.exists(dir_path):
            print(ConsoleColor.warning(f"Creating directory: {dir_path}"))
            os.makedirs(dir_path, exist_ok=True)
    
    # Check required files
    for file_path in required_files:
        if not os.path.exists(file_path):
            print(ConsoleColor.warning(f"Missing file: {file_path}"))
    
    print(ConsoleColor.success("System files validated"))


# Application initialization on startup (lightweight - models load via Socket.IO)
def run_application_init():
    """Initialize the application on startup - lightweight, non-blocking"""
    global components_loaded
    
    print(ConsoleColor.title("=" * 60))
    print(ConsoleColor.title("  Real-time Translation System v0.3"))
    print(ConsoleColor.title("  FunASR + LM Studio + GSV-TTS-Lite"))
    print(ConsoleColor.title("=" * 60))
    
    validate_system_files()
    
    port = APP_CONFIG.get('server', {}).get('port', 5001)
    print(ConsoleColor.info(f"  Server starting on port {port}"))
    print(ConsoleColor.info("  Models will load via loading screen with progress..."))
    print(ConsoleColor.title("=" * 60))


# Legacy model loading function (kept for backward compatibility with Vosk references)
def load_model(model_path=None):
    """Model loading placeholder - FunASR handles model loading internally"""
    global model, current_model_path
    # Models are loaded through FunASR, this is a compatibility shim
    return True


if __name__ == '__main__':
    import subprocess
    
    # Run application initialization
    run_application_init()
    
    port = int(APP_CONFIG.get('server', {}).get('port', 5001))
    debug = APP_CONFIG.get('server', {}).get('debug', True)
    
    print(ConsoleColor.info(f"\nStarting server on port {port}..."))
    print(ConsoleColor.info(f"  Hot reload: {'ON' if debug else 'OFF'}"))
    print(ConsoleColor.info(f"  Main app: http://localhost:{port}/app"))
    print(ConsoleColor.info(f"  Settings: http://localhost:{port}/settings"))
    print(ConsoleColor.info(f"  ASR Debug: http://localhost:{port}/asr-debug"))
    print(ConsoleColor.info(f"  Translation Debug: http://localhost:{port}/translation-debug"))
    print(ConsoleColor.info(f"  TTS Debug: http://localhost:{port}/tts-debug"))
    
    try:
        socketio.run(app, host='0.0.0.0', port=port, debug=debug, use_reloader=debug,
                      allow_unsafe_werkzeug=True,
                      extra_files=[os.path.join(BASE_DIR, 'config.json'),
                                   os.path.join(BASE_DIR, 'funasr_asr.py')])
    except OSError as e:
        if hasattr(e, 'winerror') and e.winerror == 10038:
            pass
        else:
            raise