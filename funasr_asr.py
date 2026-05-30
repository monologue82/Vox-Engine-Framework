#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import threading
import queue
import time
import numpy as np
from typing import Optional, Callable, Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_funasr_model = None
_vad_model = None
_model_lock = threading.Lock()
_audio_queue = queue.Queue()
_is_running = False
_processing_thread = None

SUPPORTED_LANGUAGES = ["zh", "en", "ja", "ko", "yue", "ca", "ru", "pt", "ar", "ta", "hi", "mi", "id", "de", "fr", "es"]

LANG_MAP = {
    "zh": "Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "yue": "Cantonese",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
}


def initialize_funasr(model_name: str = "iic/SenseVoiceSmall", 
                      device: str = "cuda:0",
                      use_vad: bool = False) -> bool:
    """
    初始化 FunASR 模型，参考 streaming-sensevoice 实现
    
    Args:
        model_name: 模型名称 (iic/SenseVoiceSmall 或本地模型路径)
        device: 设备 (cuda:0 或 cpu)
        use_vad: 是否使用 VAD 模型（StreamingRecognizer 已有自己的 VAD，不建议开启）
    
    Returns:
        初始化是否成功
    """
    global _funasr_model, _vad_model
    
    try:
        with _model_lock:
            if _funasr_model is not None:
                logger.info("FunASR model already initialized")
                return True
            
            logger.info(f"Loading FunASR model: {model_name} on {device}")
            
            from funasr import AutoModel
            
            is_local_path = os.path.isdir(model_name) or os.path.isfile(model_name)
            
            model_kwargs = {
                "model": model_name,
                "device": device,
                "disable_update": True,
                "model_revision": None,
            }
            
            if is_local_path:
                logger.info(f"Loading local model from: {model_name}")
                model_kwargs["download_mode"] = "offline"
            
            if use_vad:
                model_kwargs["vad_model"] = "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"
            
            _funasr_model = AutoModel(**model_kwargs)
            
            if use_vad:
                logger.info("VAD model loaded successfully")
            
            logger.info("FunASR model loaded successfully")
            return True
            
    except Exception as e:
        logger.error(f"Failed to initialize FunASR: {e}")
        import traceback
        traceback.print_exc()
        return False


def detect_language(audio_np: np.ndarray) -> str:
    """
    基于频谱特征的语言检测
    
    Args:
        audio_np: 音频数据 (float32, 16kHz)
    
    Returns:
        检测到的语言代码
    """
    try:
        if len(audio_np) < 1600:
            return "zh"
        
        fft_result = np.fft.fft(audio_np)
        freq = np.fft.fftfreq(len(audio_np), 1/16000)
        
        positive_freq_mask = freq > 0
        fft_magnitude = np.abs(fft_result[positive_freq_mask])
        positive_freqs = freq[positive_freq_mask]
        
        low_freq_energy = np.sum(fft_magnitude[(positive_freqs >= 0) & (positive_freqs <= 1000)])
        mid_freq_energy = np.sum(fft_magnitude[(positive_freqs > 1000) & (positive_freqs <= 3000)])
        high_freq_energy = np.sum(fft_magnitude[(positive_freqs > 3000) & (positive_freqs <= 8000)])
        
        total_energy = low_freq_energy + mid_freq_energy + high_freq_energy
        
        if total_energy > 0:
            low_ratio = low_freq_energy / total_energy
            high_ratio = high_freq_energy / total_energy
            
            if high_ratio > 0.25:
                return "en"
            elif low_ratio > 0.4:
                return "zh"
            else:
                return "zh"
        else:
            return "zh"
            
    except Exception as e:
        logger.error(f"Language detection error: {e}")
        return "zh"


def transcribe_audio_stream(audio_data, cache=None, is_final=False, language=None):
    """
    流式转录音频数据（参考 streaming-sensevoice 实现）
    """
    global _funasr_model

    if isinstance(audio_data, bytes):
        audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
    elif isinstance(audio_data, np.ndarray):
        audio_np = audio_data
    else:
        return None

    if cache is None:
        cache = {}

    if language is None:
        language = detect_language(audio_np)
        logger.debug(f"Auto-detected language: {language}")

    try:
        with _model_lock:
            if _funasr_model is None:
                logger.error("FunASR model is None, cannot transcribe")
                return None

            result = _funasr_model.generate(
                input=audio_np,
                cache=cache,
                is_final=is_final,
                chunk_size=[0, 10, 5],  # 流式参数: [首块上下文帧数, 后续块上下文帧数, 步长帧数]
                language=language,
                use_itn=True,
                remove_pun=False,
                disable_pbar=True,
                hotword=""
            )
        
        if result and len(result) > 0:
            if isinstance(result[0], dict):
                text = result[0].get('text', '').strip()
            else:
                text = str(result[0]).strip()
        else:
            text = ""
        
        if text:
            text = _strip_sensevoice_tags(text)
        
        return text if text else None

    except Exception as e:
        logger.error(f"Error during streaming transcription: {e}")
        import traceback
        traceback.print_exc()
        return None


def _strip_sensevoice_tags(text):
    """去除 SenseVoice 特殊标记（<|...|>），保留纯文本"""
    import re
    # 移除所有 <|...|> 格式的标记
    cleaned = re.sub(r'<\|[^|]*\|>', '', text)
    return ' '.join(cleaned.split())


class StreamingRecognizer:
    """
    流式识别器 v3 — FunASR 原生 streaming cache + 增量文本提取
    
    核心改进：
    - 使用 FunASR 的 cache/chunk_size 流式推理，而非每次全量推理
    - audio_buffer 仅累积新音频块，识别后清空，不再无限增长
    - CTC 模型通过 cache 维护内部状态，新块只做增量计算
    
    参数：
    - CHUNK_ACCUMULATE: 累积多少秒新音频后触发一次识别
    - MIN_AUDIO_LENGTH: 最少音频采样点数才触发识别
    """
    
    def __init__(self, model_path=None, device=None, use_vad=True):
        self.model_path = model_path or "iic/SenseVoiceSmall"
        self.device = device or self._get_device()
        self.use_vad = use_vad
        self.funasr_cache = {}
        self.is_running = False
        self.last_text = ""
        self.detected_language = "zh"
        self.silence_count = 0
        self.has_speech = False
        
        self.audio_buffer = []
        self.last_recognize_time = 0
        self.CHUNK_ACCUMULATE = 0.15
        self.MIN_AUDIO_LENGTH = 1600
        self.SILENCE_THRESHOLD = 30
        self.MIN_VOICE_ENERGY = 0.001
        
        if not _funasr_model:
            initialize_funasr(self.model_path, self.device, use_vad=False)
    
    def _get_device(self):
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda:0"
            return "cpu"
        except ImportError:
            return "cpu"
    
    def process_stream(self, audio_data, language=None):
        """
        处理音频流 v3 — 使用 FunASR cache 做增量流式推理
        """
        if isinstance(audio_data, list):
            self.audio_buffer.extend(audio_data)
            audio_np = np.array(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
        elif isinstance(audio_data, np.ndarray):
            if audio_data.dtype == np.int16:
                self.audio_buffer.extend(audio_data.tolist())
                audio_np = audio_data.astype(np.float32) / 32768.0
            else:
                audio_np = audio_data
                self.audio_buffer.extend((audio_np * 32767).astype(np.int16).tolist())
        else:
            return []
        
        if len(audio_np) < 160:
            return []
        
        energy = np.mean(np.abs(audio_np))
        if self.use_vad and energy < self.MIN_VOICE_ENERGY:
            self.silence_count += 1
            if self.silence_count > self.SILENCE_THRESHOLD and self.has_speech:
                self.audio_buffer = []
                self.funasr_cache = {}
                self.has_speech = False
                self.last_text = ""
            return []
        
        self.silence_count = 0
        self.has_speech = True
        
        buffer_duration = len(self.audio_buffer) / 16000.0
        if buffer_duration < self.CHUNK_ACCUMULATE or len(self.audio_buffer) < self.MIN_AUDIO_LENGTH:
            return []
        
        results = self._recognize_chunk(language)
        return results
    
    def _recognize_chunk(self, language=None):
        """对累积的新音频块做增量流式识别"""
        if len(self.audio_buffer) < self.MIN_AUDIO_LENGTH:
            return []
        
        audio_np = np.array(self.audio_buffer, dtype=np.int16).astype(np.float32) / 32768.0
        self.audio_buffer = []
        
        target_language = language if language else self.detected_language
        
        try:
            t_start = time.time()
            with _model_lock:
                if _funasr_model is None:
                    logger.error("[streaming] FunASR model is None! ASR cannot proceed.")
                    return []
                
                result = _funasr_model.generate(
                    input=audio_np,
                    cache=self.funasr_cache,
                    is_final=False,
                    chunk_size=[0, 10, 5],
                    language=target_language,
                    use_itn=True,
                    remove_pun=False,
                    disable_pbar=True
                )
            t_elapsed = time.time() - t_start
            
            if result and len(result) > 0:
                text = result[0].get('text', '').strip()
                
                if 'language' in result[0]:
                    self.detected_language = result[0].get('language', 'zh')
                
                if text:
                    clean = _strip_sensevoice_tags(text)
                    if not clean:
                        return []
                    
                    last_clean = _strip_sensevoice_tags(self.last_text) if self.last_text else ""
                    if clean == last_clean:
                        return []
                    
                    self.last_text = text
                    return [{
                        'text': clean,
                        'confidence': result[0].get('confidence', 0),
                        'language': self.detected_language,
                        'elapsed_ms': round(t_elapsed * 1000)
                    }]
        except Exception as e:
            logger.error(f"Recognize chunk error: {e}")
        
        return []
    
    def reset(self):
        """重置识别器状态"""
        self.funasr_cache = {}
        self.audio_buffer = []
        self.last_text = ""
        self.silence_count = 0
        self.has_speech = False


def transcribe_audio_file(file_path: str, language: str = "zh") -> Optional[str]:
    """
    转录音频文件
    
    Args:
        file_path: 音频文件路径
        language: 语言代码
    
    Returns:
        转录文本
    """
    global _funasr_model
    
    try:
        with _model_lock:
            if _funasr_model is None:
                raise RuntimeError("FunASR model not initialized")
        
        result = _funasr_model.generate(
            input=file_path,
            cache={},
            batch_size_s=0,
            language=language,
            use_itn=True,
            remove_pun=False
        )
        
        if result and len(result) > 0:
            text = result[0].get('text', '')
            return text.strip()
        
        return None
        
    except Exception as e:
        logger.error(f"FunASR file transcription error: {e}")
        return None


def is_available() -> bool:
    """检查 FunASR 是否可用"""
    try:
        import funasr
        return True
    except ImportError:
        return False


def get_device() -> str:
    """获取当前使用的设备"""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda:0"
        return "cpu"
    except ImportError:
        return "cpu"


def unload_model():
    """卸载 FunASR 模型"""
    global _funasr_model, _vad_model
    with _model_lock:
        if _funasr_model is not None:
            logger.info("Unloading FunASR model")
            _funasr_model = None
            _vad_model = None
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass