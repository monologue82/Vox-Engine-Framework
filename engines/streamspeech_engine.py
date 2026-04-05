"""
StreamSpeech 端到端引擎
基于 Fairseq 的单一模型实现 ASR+S2TT+S2ST
"""

import asyncio
import json
import os
import sys
from typing import Dict, Any, Optional, List
from pathlib import Path
import numpy as np

from .base_engine import BaseSpeechEngine


class StreamSpeechEngine(BaseSpeechEngine):
    """StreamSpeech 端到端语音引擎"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.engine_name = "streamspeech"
        self.engine_display_name = "StreamSpeech 端到端引擎"
        
        # 模型路径
        self.model_path = config.get('model_path', 'models/streamspeech/streamspeech.zh-en.pt')
        self.vocoder_path = config.get('vocoder_path', 'models/vocoder/g_00500000')
        self.vocoder_config_path = config.get('vocoder_config', 'models/vocoder/config.json')
        self.data_bin_path = config.get('data_bin', 'models/streamspeech/data-bin')
        self.config_yaml = config.get('config_yaml', 'config_gcmvn.yaml')
        self.multitask_config_yaml = config.get('multitask_config', 'config_mtl_asr_st_ctcst.yaml')
        
        # 流式参数
        self.chunk_size = config.get('chunk_size', 320)  # ms
        self.lagging_k1 = config.get('lagging_k1', 0)
        self.lagging_k2 = config.get('lagging_k2', 0)
        self.stride_n = config.get('stride_n', 1)
        
        # 模型组件
        self.agent = None
        self.models = None
        self.vocoder = None
        self.feature_extractor = None
        self.task = None
        
        # 结果缓存
        self.asr_results = {}
        self.translation_results = {}
        self.tts_audio = []
        self.current_offset_ms = -1
        
        # 状态
        self.audio_buffer = []
        self.is_initialized = False
    
    async def initialize(self) -> bool:
        """初始化 StreamSpeech 引擎"""
        try:
            print("Initializing StreamSpeech Engine...")
            
            # 1. 设置路径
            stream_speech_root = Path(__file__).parent.parent / 'StreamSpeech-main'
            sys.path.insert(0, str(stream_speech_root))
            
            # 2. 导入依赖
            await self._import_dependencies()
            
            # 3. 加载模型
            await self._load_models()
            
            # 4. 初始化 Agent
            await self._initialize_agent()
            
            # 5. 加载 Vocoder
            await self._load_vocoder()
            
            self.is_ready = True
            self.is_initialized = True
            print(f"StreamSpeech Engine initialized (chunk_size={self.chunk_size}ms)")
            return True
            
        except Exception as e:
            print(f"Failed to initialize StreamSpeech Engine: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _import_dependencies(self):
        """导入依赖"""
        loop = asyncio.get_event_loop()
        
        def import_libs():
            import torch
            import fairseq
            from fairseq import checkpoint_utils, tasks, utils
            from simuleval.agents import SpeechToSpeechAgent
            return True
        
        await loop.run_in_executor(None, import_libs)
        print("Dependencies imported")
    
    async def _load_models(self):
        """加载 StreamSpeech 模型"""
        loop = asyncio.get_event_loop()
        
        def load():
            from fairseq import checkpoint_utils, tasks, utils
            import yaml
            import numpy as np
            
            # 加载检查点
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"Model not found: {self.model_path}")
            
            state = checkpoint_utils.load_checkpoint_to_cpu(self.model_path)
            
            # 设置任务配置
            task_args = state["cfg"]["task"]
            task_args.data = self.data_bin_path
            task_args.config_yaml = self.config_yaml
            task_args.multitask_config_yaml = self.multitask_config_yaml
            
            # 加载 global cmvn
            config_path = Path(self.data_bin_path) / self.config_yaml
            if config_path.exists():
                with open(config_path, "r") as f:
                    config = yaml.load(f, Loader=yaml.BaseLoader)
                
                if "global_cmvn" in config:
                    self.global_cmvn = np.load(config["global_cmvn"]["stats_npz_path"])
            
            # 创建任务
            self.task = tasks.setup_task(task_args)
            
            # 加载模型
            overrides = eval(state["cfg"].common_eval.model_overrides)
            self.models, saved_cfg = checkpoint_utils.load_model_ensemble(
                [self.model_path],
                arg_overrides=overrides,
                task=self.task,
            )
            
            # 设置模型为评估模式
            for model in self.models:
                model.eval()
            
            print(f"Model loaded: {self.model_path}")
        
        await loop.run_in_executor(None, load)
    
    async def _initialize_agent(self):
        """初始化 Agent"""
        loop = asyncio.get_event_loop()
        
        def create_agent():
            # 导入 Agent
            from agent.speech_to_speech.streamspeech.agent import StreamSpeechS2STAgent
            
            # 创建 args
            import argparse
            args = argparse.Namespace(
                model_path=self.model_path,
                data_bin=self.data_bin_path,
                config_yaml=self.config_yaml,
                multitask_config_yaml=self.multitask_config_yaml,
                vocoder=self.vocoder_path,
                vocoder_cfg=self.vocoder_config_path,
                dur_prediction=True,
                lagging_k1=self.lagging_k1,
                lagging_k2=self.lagging_k2,
                segment_size=self.chunk_size,
                stride_n=self.stride_n,
                stride_n2=1,
                unit_per_subword=15,
                output_asr_translation=True,
                max_len=200,
                force_finish=False,
                shift_size=10,
                window_size=25,
                sample_rate=48000,
                feature_dim=80,
            )
            
            # 创建 Agent
            agent = StreamSpeechS2STAgent(args)
            return agent
        
        self.agent = await loop.run_in_executor(None, create_agent)
        print("Agent initialized")
    
    async def _load_vocoder(self):
        """加载 Vocoder"""
        loop = asyncio.get_event_loop()
        
        def load_vocoder():
            from agent.tts.vocoder import CodeHiFiGANVocoderWithDur
            import json
            
            with open(self.vocoder_config_path, 'r') as f:
                vocoder_cfg = json.load(f)
            
            vocoder = CodeHiFiGANVocoderWithDur(self.vocoder_path, vocoder_cfg)
            return vocoder
        
        self.vocoder = await loop.run_in_executor(None, load_vocoder)
        print(f"Vocoder loaded: {self.vocoder_path}")
    
    async def process_audio(self, audio_data: bytes) -> Dict[str, Any]:
        """
        处理音频（流式处理）
        
        Args:
            audio_data: PCM 音频数据 (16kHz, 16-bit)
            
        Returns:
            Dict: 包含 ASR、翻译、TTS 结果
        """
        self.is_processing = True
        
        try:
            # 1. 添加音频到缓冲
            self.audio_buffer.extend(audio_data)
            
            # 2. 转换为 numpy 数组
            samples = np.frombuffer(audio_data, dtype=np.float32)
            
            # 3. 更新 Agent 状态
            self.agent.states.source = samples
            self.agent.states.source_finished = False
            
            # 4. 执行策略
            loop = asyncio.get_event_loop()
            action = await loop.run_in_executor(None, self.agent.policy)
            
            # 5. 提取结果
            asr_text = self._get_current_asr()
            translation = self._get_current_translation()
            
            result = {
                'asr': asr_text,
                'translation': translation,
                'tts': None,  # TTS 音频
                'engine': 'streamspeech',
                'latency': self._calculate_latency()
            }
            
            return result
            
        finally:
            self.is_processing = False
    
    def _get_current_asr(self) -> str:
        """获取当前 ASR 结果"""
        # 从 ASR 字典中获取最新结果
        if self.agent.ASR:
            latest_key = max(self.agent.ASR.keys())
            return self.agent.ASR[latest_key]
        return ""
    
    def _get_current_translation(self) -> str:
        """获取当前翻译结果"""
        if self.agent.S2TT:
            latest_key = max(self.agent.S2TT.keys())
            return self.agent.S2TT[latest_key]
        return ""
    
    def _calculate_latency(self) -> float:
        """计算当前延迟"""
        if self.current_offset_ms == -1:
            return 0
        return self.current_offset_ms
    
    async def get_asr_result(self, timestamp: float) -> str:
        """获取指定时间戳的 ASR 结果"""
        # 查找最接近的时间戳
        if not self.agent.ASR:
            return ""
        
        keys = [k for k in self.agent.ASR.keys() if k < timestamp * 16000]
        if not keys:
            return ""
        
        latest_key = max(keys)
        return self.agent.ASR[latest_key]
    
    async def get_translation_result(self, timestamp: float) -> str:
        """获取指定时间戳的翻译结果"""
        if not self.agent.S2TT:
            return ""
        
        keys = [k for k in self.agent.S2TT.keys() if k < timestamp * 16000]
        if not keys:
            return ""
        
        latest_key = max(keys)
        return self.agent.S2TT[latest_key]
    
    async def get_tts_audio(self) -> Optional[bytes]:
        """获取 TTS 音频"""
        if not self.agent.S2ST:
            return None
        
        # 合并所有 TTS 音频
        audio_array = np.array(self.agent.S2ST, dtype=np.float32)
        return audio_array.tobytes()
    
    async def set_chunk_size(self, chunk_size: int) -> None:
        """动态调整 chunk size"""
        self.chunk_size = chunk_size
        if self.agent:
            self.agent.set_chunk_size(chunk_size)
        print(f"Chunk size updated: {chunk_size}ms")
    
    async def reset(self) -> None:
        """重置引擎状态"""
        if self.agent:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.agent.reset)
        
        self.audio_buffer = []
        self.asr_results = {}
        self.translation_results = {}
        self.tts_audio = []
        self.current_offset_ms = -1
    
    async def shutdown(self) -> None:
        """关闭引擎"""
        print("Shutting down StreamSpeech Engine...")
        
        # 重置状态
        await self.reset()
        
        # 释放模型
        self.agent = None
        self.models = None
        self.vocoder = None
        
        self.is_ready = False
        print("StreamSpeech Engine shut down")
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        status = {
            'status': 'healthy' if self.is_ready else 'unhealthy',
            'engine': self.engine_name,
            'components': {
                'model': self.models is not None,
                'agent': self.agent is not None,
                'vocoder': self.vocoder is not None
            },
            'chunk_size': self.chunk_size,
            'is_processing': self.is_processing
        }
        
        if all(status['components'].values()):
            status['status'] = 'healthy'
        else:
            status['status'] = 'degraded'
        
        return status
    
    def get_engine_info(self) -> Dict[str, Any]:
        """获取引擎详细信息"""
        info = super().get_engine_info()
        info.update({
            'model_path': self.model_path,
            'chunk_size': self.chunk_size,
            'supports_streaming': True,
            'latency_optimized': True
        })
        return info
