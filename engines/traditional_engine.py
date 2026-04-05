"""
传统级联引擎
使用 Vosk ASR + vLLM/llama.cpp 翻译 + GSV-TTS 语音合成
"""

import asyncio
import json
import os
from typing import Dict, Any, Optional
from pathlib import Path

from .base_engine import BaseSpeechEngine


class TraditionalEngine(BaseSpeechEngine):
    """传统级联语音引擎"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.engine_name = "traditional"
        self.engine_display_name = "传统级联引擎"
        
        # 组件引用
        self.vosk_model = None
        self.vllm_client = None
        self.llama_cpp_process = None
        self.tts_model = None
        
        # 结果缓存
        self.asr_results = {}
        self.translation_results = {}
        self.tts_audio = None
        
        # 配置
        self.asr_model_path = config.get('asr_model', 'models/stt/vosk-model-cn-0.22')
        self.translation_provider = config.get('translation_provider', 'llama.cpp')
        self.tts_model_path = config.get('tts_model', 'models/tts/g2p')
    
    async def initialize(self) -> bool:
        """初始化传统引擎组件"""
        try:
            print("Initializing Traditional Engine...")
            
            # 1. 加载 Vosk 模型
            await self._load_vosk_model()
            
            # 2. 初始化翻译服务
            await self._init_translation()
            
            # 3. 加载 TTS 模型
            await self._load_tts_model()
            
            self.is_ready = True
            print("Traditional Engine initialized successfully")
            return True
            
        except Exception as e:
            print(f"Failed to initialize Traditional Engine: {e}")
            return False
    
    async def _load_vosk_model(self):
        """加载 Vosk 语音识别模型"""
        from vosk import Model
        model_path = Path(self.asr_model_path)
        
        if not model_path.exists():
            raise FileNotFoundError(f"Vosk model not found at {model_path}")
        
        # 在事件循环外加载模型，避免阻塞
        loop = asyncio.get_event_loop()
        self.vosk_model = await loop.run_in_executor(
            None,
            lambda: Model(str(model_path))
        )
        print(f"Vosk model loaded from {model_path}")
    
    async def _init_translation(self):
        """初始化翻译服务"""
        if self.translation_provider == 'vllm':
            # 初始化 vLLM 客户端
            await self._init_vllm_client()
        elif self.translation_provider == 'llama.cpp':
            # 启动 llama.cpp 服务
            await self._start_llama_cpp()
        else:
            raise ValueError(f"Unknown translation provider: {self.translation_provider}")
    
    async def _init_vllm_client(self):
        """初始化 vLLM HTTP 客户端"""
        import aiohttp
        vllm_url = self.config.get('vllm_url', 'http://localhost:8000')
        
        self.vllm_session = aiohttp.ClientSession(
            base_url=vllm_url,
            timeout=aiohttp.ClientTimeout(total=30)
        )
        print(f"vLLM client initialized, URL: {vllm_url}")
    
    async def _start_llama_cpp(self):
        """启动 llama.cpp 服务"""
        # 这里复用 app.py 中的 load_llama_cpp 逻辑
        from app import load_llama_cpp
        
        loop = asyncio.get_event_loop()
        self.llama_cpp_process = await loop.run_in_executor(
            None,
            load_llama_cpp
        )
        print("llama.cpp server started")
    
    async def _load_tts_model(self):
        """加载 TTS 模型"""
        # 加载 GSV-TTS 或其他 TTS 模型
        tts_path = Path(self.tts_model_path)
        
        if tts_path.exists():
            # 初始化 TTS
            from gsv_tts import TTS
            self.tts_model = TTS(
                model_path=str(tts_path),
                config_path=str(tts_path / 'hps.json')
            )
            print(f"TTS model loaded from {tts_path}")
        else:
            print(f"Warning: TTS model not found at {tts_path}")
    
    async def process_audio(self, audio_data: bytes) -> Dict[str, Any]:
        """
        处理音频（级联处理）
        
        Args:
            audio_data: PCM 音频数据
            
        Returns:
            Dict: 包含 ASR、翻译、TTS 结果
        """
        self.is_processing = True
        
        try:
            # 1. ASR 识别
            asr_text = await self._recognize_speech(audio_data)
            
            # 2. 翻译
            translation = await self._translate(asr_text)
            
            # 3. TTS 合成
            tts_audio = await self._synthesize_speech(translation)
            
            result = {
                'asr': asr_text,
                'translation': translation,
                'tts': tts_audio,
                'engine': 'traditional'
            }
            
            return result
            
        finally:
            self.is_processing = False
    
    async def _recognize_speech(self, audio_data: bytes) -> str:
        """语音识别"""
        from vosk import KaldiRecognizer
        import json
        
        rec = KaldiRecognizer(self.vosk_model, 16000)
        
        # 在事件循环外处理
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._vosk_recognize(rec, audio_data)
        )
        
        return result
    
    def _vosk_recognize(self, rec: KaldiRecognizer, audio_data: bytes) -> str:
        """Vosk 识别辅助函数"""
        if rec.AcceptWaveform(audio_data):
            result = json.loads(rec.Result())
            return result.get('text', '')
        else:
            partial = json.loads(rec.PartialResult())
            return partial.get('partial', '')
    
    async def _translate(self, text: str) -> str:
        """翻译文本"""
        if not text.strip():
            return ""
        
        if self.translation_provider == 'vllm':
            return await self._vllm_translate(text)
        elif self.translation_provider == 'llama.cpp':
            return await self._llama_cpp_translate(text)
        else:
            return text
    
    async def _vllm_translate(self, text: str) -> str:
        """使用 vLLM 翻译"""
        prompt = f"Translate the following Chinese text to English: {text}"
        
        async with self.vllm_session.post(
            '/generate',
            json={'prompt': prompt, 'max_tokens': 200}
        ) as response:
            result = await response.json()
            return result.get('text', '')
    
    async def _llama_cpp_translate(self, text: str) -> str:
        """使用 llama.cpp 翻译"""
        # 调用 llama.cpp API
        import aiohttp
        
        llama_url = self.config.get('llama_cpp_url', 'http://localhost:8080')
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f'{llama_url}/completion',
                json={
                    'prompt': f'Translate to English: {text}',
                    'n_predict': 200
                }
            ) as response:
                result = await response.json()
                return result.get('content', '')
    
    async def _synthesize_speech(self, text: str) -> Optional[bytes]:
        """语音合成"""
        if not self.tts_model or not text.strip():
            return None
        
        # 在事件循环外合成
        loop = asyncio.get_event_loop()
        audio = await loop.run_in_executor(
            None,
            lambda: self.tts_model.synthesize(text)
        )
        
        return audio
    
    async def get_asr_result(self, timestamp: float) -> str:
        """获取 ASR 结果"""
        return self.asr_results.get(timestamp, "")
    
    async def get_translation_result(self, timestamp: float) -> str:
        """获取翻译结果"""
        return self.translation_results.get(timestamp, "")
    
    async def get_tts_audio(self) -> Optional[bytes]:
        """获取 TTS 音频"""
        return self.tts_audio
    
    async def shutdown(self) -> None:
        """关闭引擎"""
        print("Shutting down Traditional Engine...")
        
        # 关闭 vLLM 会话
        if hasattr(self, 'vllm_session'):
            await self.vllm_session.close()
        
        # 停止 llama.cpp 进程
        if self.llama_cpp_process:
            self.llama_cpp_process.terminate()
        
        # 释放模型
        self.vosk_model = None
        self.tts_model = None
        
        self.is_ready = False
        print("Traditional Engine shut down")
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        status = {
            'status': 'healthy' if self.is_ready else 'unhealthy',
            'engine': self.engine_name,
            'components': {
                'vosk': self.vosk_model is not None,
                'translation': hasattr(self, 'vllm_session') or self.llama_cpp_process is not None,
                'tts': self.tts_model is not None
            }
        }
        
        if all(status['components'].values()):
            status['status'] = 'healthy'
        else:
            status['status'] = 'degraded'
        
        return status
