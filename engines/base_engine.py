"""
语音引擎基类
定义所有语音引擎的统一接口
"""

import asyncio
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod
import json


class BaseSpeechEngine(ABC):
    """语音引擎抽象基类"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化引擎
        
        Args:
            config: 引擎配置字典
        """
        self.config = config
        self.is_ready = False
        self.is_processing = False
        self.engine_name = "base"
        self.engine_display_name = "基础引擎"
        
    @abstractmethod
    async def initialize(self) -> bool:
        """
        初始化引擎
        
        Returns:
            bool: 初始化是否成功
        """
        pass
    
    @abstractmethod
    async def process_audio(self, audio_data: bytes) -> Dict[str, Any]:
        """
        处理音频输入
        
        Args:
            audio_data: 音频数据
            
        Returns:
            Dict: 处理结果，包含 asr, translation, tts 等字段
        """
        pass
    
    @abstractmethod
    async def get_asr_result(self, timestamp: float) -> str:
        """
        获取指定时间戳的 ASR 结果
        
        Args:
            timestamp: 时间戳（秒）
            
        Returns:
            str: ASR 识别文本
        """
        pass
    
    @abstractmethod
    async def get_translation_result(self, timestamp: float) -> str:
        """
        获取指定时间戳的翻译结果
        
        Args:
            timestamp: 时间戳（秒）
            
        Returns:
            str: 翻译文本
        """
        pass
    
    @abstractmethod
    async def get_tts_audio(self) -> Optional[bytes]:
        """
        获取 TTS 音频
        
        Returns:
            bytes: TTS 音频数据
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """
        关闭引擎，释放资源
        """
        pass
    
    def get_engine_info(self) -> Dict[str, Any]:
        """
        获取引擎信息
        
        Returns:
            Dict: 引擎信息
        """
        return {
            'name': self.engine_name,
            'display_name': self.engine_display_name,
            'is_ready': self.is_ready,
            'is_processing': self.is_processing,
            'config': self.config
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            Dict: 健康状态
        """
        return {
            'status': 'healthy' if self.is_ready else 'unhealthy',
            'engine': self.engine_name,
            'ready': self.is_ready
        }
