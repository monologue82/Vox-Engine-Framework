"""
引擎管理器
管理多个语音引擎的加载、切换和状态监控
"""

import asyncio
import json
from typing import Dict, Any, Optional, List
from pathlib import Path
import logging

from .base_engine import BaseSpeechEngine
from .traditional_engine import TraditionalEngine
from .streamspeech_engine import StreamSpeechEngine

logger = logging.getLogger(__name__)


class EngineManager:
    """语音引擎管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化引擎管理器
        
        Args:
            config_path: 配置文件路径
        """
        self.engines: Dict[str, BaseSpeechEngine] = {}
        self.active_engine_name: Optional[str] = None
        self.config_path = config_path or 'config/engines.json'
        self.config: Dict[str, Any] = {}
        
        # 加载配置
        self.load_config()
    
    def load_config(self) -> None:
        """加载引擎配置"""
        try:
            if Path(self.config_path).exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                logger.info(f"Engine config loaded from {self.config_path}")
            else:
                # 使用默认配置
                self.config = self._get_default_config()
                logger.info("Using default engine config")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            self.config = self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'default_engine': 'traditional',
            'engines': {
                'traditional': {
                    'enabled': True,
                    'config': {
                        'asr_model': 'models/stt/vosk-model-cn-0.22',
                        'translation_provider': 'llama.cpp',
                        'tts_model': 'models/tts/g2p'
                    }
                },
                'streamspeech': {
                    'enabled': True,
                    'config': {
                        'model_path': 'models/streamspeech/streamspeech.zh-en.pt',
                        'vocoder_path': 'models/vocoder/g_00500000',
                        'vocoder_config': 'models/vocoder/config.json',
                        'data_bin': 'models/streamspeech/data-bin',
                        'chunk_size': 320
                    }
                }
            }
        }
    
    async def initialize_engines(self) -> None:
        """初始化所有启用的引擎"""
        engines_config = self.config.get('engines', {})
        
        for engine_name, engine_config in engines_config.items():
            if not engine_config.get('enabled', True):
                logger.info(f"Engine {engine_name} is disabled, skipping")
                continue
            
            try:
                await self.register_engine(engine_name, engine_config['config'])
                logger.info(f"Engine {engine_name} initialized")
            except Exception as e:
                logger.error(f"Failed to initialize engine {engine_name}: {e}")
    
    async def register_engine(self, name: str, config: Dict[str, Any]) -> None:
        """
        注册引擎
        
        Args:
            name: 引擎名称
            config: 引擎配置
        """
        try:
            if name == 'traditional':
                engine = TraditionalEngine(config)
            elif name == 'streamspeech':
                engine = StreamSpeechEngine(config)
            else:
                logger.warning(f"Unknown engine type: {name}")
                return
            
            # 初始化引擎
            success = await engine.initialize()
            if success:
                self.engines[name] = engine
                logger.info(f"Engine {name} registered successfully")
            else:
                logger.error(f"Engine {name} initialization failed")
                
        except Exception as e:
            logger.error(f"Failed to register engine {name}: {e}")
            raise
    
    async def switch_engine(self, engine_name: str) -> Dict[str, Any]:
        """
        切换引擎
        
        Args:
            engine_name: 目标引擎名称
            
        Returns:
            Dict: 切换结果
        """
        if engine_name not in self.engines:
            return {
                'success': False,
                'error': f'Engine {engine_name} not found'
            }
        
        try:
            # 关闭当前引擎
            if self.active_engine_name and self.active_engine_name in self.engines:
                current_engine = self.engines[self.active_engine_name]
                await current_engine.shutdown()
                logger.info(f"Engine {self.active_engine_name} shut down")
            
            # 激活新引擎
            self.active_engine_name = engine_name
            new_engine = self.engines[engine_name]
            
            if not new_engine.is_ready:
                await new_engine.initialize()
            
            logger.info(f"Switched to engine: {engine_name}")
            
            return {
                'success': True,
                'engine': engine_name,
                'message': f'Successfully switched to {engine_name}',
                'engine_info': new_engine.get_engine_info()
            }
            
        except Exception as e:
            logger.error(f"Failed to switch engine: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_active_engine(self) -> Optional[BaseSpeechEngine]:
        """获取当前活跃的引擎"""
        if self.active_engine_name and self.active_engine_name in self.engines:
            return self.engines[self.active_engine_name]
        return None
    
    async def process_audio(self, audio_data: bytes) -> Dict[str, Any]:
        """
        使用当前引擎处理音频
        
        Args:
            audio_data: 音频数据
            
        Returns:
            Dict: 处理结果
        """
        engine = self.get_active_engine()
        if not engine:
            return {
                'error': 'No active engine',
                'asr': '',
                'translation': '',
                'tts': None
            }
        
        try:
            result = await engine.process_audio(audio_data)
            return result
        except Exception as e:
            logger.error(f"Error processing audio: {e}")
            return {
                'error': str(e),
                'asr': '',
                'translation': '',
                'tts': None
            }
    
    def list_engines(self) -> List[Dict[str, Any]]:
        """列出所有可用引擎"""
        engine_list = []
        
        for name, engine in self.engines.items():
            info = engine.get_engine_info()
            info['is_active'] = (name == self.active_engine_name)
            engine_list.append(info)
        
        return engine_list
    
    async def health_check(self) -> Dict[str, Any]:
        """检查所有引擎的健康状态"""
        health_status = {
            'active_engine': self.active_engine_name,
            'engines': {}
        }
        
        for name, engine in self.engines.items():
            health_status['engines'][name] = await engine.health_check()
        
        return health_status
    
    async def shutdown_all(self) -> None:
        """关闭所有引擎"""
        logger.info("Shutting down all engines...")
        
        for name, engine in self.engines.items():
            try:
                await engine.shutdown()
                logger.info(f"Engine {name} shut down")
            except Exception as e:
                logger.error(f"Error shutting down engine {name}: {e}")
        
        self.engines.clear()
        self.active_engine_name = None
    
    def get_engine_stats(self) -> Dict[str, Any]:
        """获取引擎统计信息"""
        return {
            'total_engines': len(self.engines),
            'active_engine': self.active_engine_name,
            'available_engines': list(self.engines.keys()),
            'config_path': self.config_path
        }


# 全局引擎管理器实例
engine_manager: Optional[EngineManager] = None


def get_engine_manager(config_path: Optional[str] = None) -> EngineManager:
    """获取全局引擎管理器实例"""
    global engine_manager
    
    if engine_manager is None:
        engine_manager = EngineManager(config_path)
    
    return engine_manager
