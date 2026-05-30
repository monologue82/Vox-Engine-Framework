"""
引擎管理 API 路由
将这些路由添加到 app.py 中以支持引擎切换
"""

from flask import request, jsonify
from engines import get_engine_manager

# 初始化引擎管理器
engine_manager = get_engine_manager('config/engines.json')


@app.route('/api/engine/list', methods=['GET'])
def list_engines():
    """获取可用引擎列表"""
    engines = engine_manager.list_engines()
    
    engine_info = {
        'engines': [
            {
                'id': 'traditional',
                'name': '传统级联引擎',
                'display_name': 'Traditional Engine',
                'description': 'Vosk ASR + vLLM/llama.cpp 翻译 + GSV-TTS',
                'features': ['中文优化', '多模型选择', '声音克隆', 'FRP 支持'],
                'performance': {
                    'latency': '中等 (800-1500ms)',
                    'quality': '依赖模型',
                    'resource_usage': '中等'
                },
                'status': next((e for e in engines if e['name'] == 'traditional'), {}).get('is_ready', False)
            },
            {
                'id': 'streamspeech',
                'name': 'StreamSpeech 端到端引擎',
                'display_name': 'StreamSpeech Engine',
                'description': '单一模型实现 ASR+S2TT+S2ST',
                'features': ['低延迟', '增量输出', '联合优化', '端到端处理'],
                'performance': {
                    'latency': '低 (320-640ms)',
                    'quality': 'SOTA 级别',
                    'resource_usage': '较低'
                },
                'status': next((e for e in engines if e['name'] == 'streamspeech'), {}).get('is_ready', False),
                'badge': '推荐'
            }
        ],
        'active_engine': engine_manager.active_engine_name
    }
    
    return jsonify(engine_info)


@app.route('/api/engine/switch', methods=['POST'])
async def switch_engine():
    """切换引擎"""
    data = request.json
    engine_name = data.get('engine')
    
    if not engine_name:
        return jsonify({
            'success': False,
            'error': '未指定引擎名称'
        }), 400
    
    result = await engine_manager.switch_engine(engine_name)
    
    if result['success']:
        return jsonify(result), 200
    else:
        return jsonify(result), 400


@app.route('/api/engine/health', methods=['GET'])
async def engine_health():
    """引擎健康检查"""
    health = await engine_manager.health_check()
    return jsonify(health)


@app.route('/api/engine/stats', methods=['GET'])
def engine_stats():
    """获取引擎统计信息"""
    stats = engine_manager.get_engine_stats()
    return jsonify(stats)


@app.route('/api/audio/process', methods=['POST'])
async def process_audio():
    """
    处理音频（使用当前活跃引擎）
    
    请求格式:
    - audio: 音频文件 (multipart/form-data)
    
    返回格式:
    {
        'asr': '识别文本',
        'translation': '翻译文本',
        'tts': '音频数据 (base64)',
        'engine': '使用的引擎',
        'latency': 延迟 (ms)
    }
    """
    if 'audio' not in request.files:
        return jsonify({
            'error': '未提供音频文件'
        }), 400
    
    audio_file = request.files['audio']
    audio_data = audio_file.read()
    
    # 使用当前引擎处理音频
    result = await engine_manager.process_audio(audio_data)
    
    if 'error' in result:
        return jsonify(result), 500
    
    return jsonify(result)


@app.route('/api/engine/info', methods=['GET'])
def engine_info():
    """获取当前引擎详细信息"""
    engine = engine_manager.get_active_engine()
    
    if not engine:
        return jsonify({
            'error': '没有活跃的引擎'
        }), 404
    
    info = engine.get_engine_info()
    return jsonify(info)


@app.route('/api/engine/set_chunk_size', methods=['POST'])
async def set_chunk_size():
    """
    设置 StreamSpeech 引擎的 chunk size
    
    请求格式:
    {
        'chunk_size': 320  # ms
    }
    """
    data = request.json
    chunk_size = data.get('chunk_size')
    
    if not chunk_size:
        return jsonify({
            'error': '未指定 chunk_size'
        }), 400
    
    engine = engine_manager.get_active_engine()
    
    if engine and engine.engine_name == 'streamspeech':
        await engine.set_chunk_size(chunk_size)
        return jsonify({
            'success': True,
            'chunk_size': chunk_size
        })
    else:
        return jsonify({
            'error': '当前引擎不支持调整 chunk_size'
        }), 400


@app.route('/api/engine/reset', methods=['POST'])
async def reset_engine():
    """重置当前引擎状态"""
    engine = engine_manager.get_active_engine()
    
    if engine:
        await engine.reset()
        return jsonify({
            'success': True,
            'message': '引擎状态已重置'
        })
    else:
        return jsonify({
            'error': '没有活跃的引擎'
        }), 404


# 应用启动和关闭时的引擎管理
@app.before_first_request
async def before_first_request():
    """应用首次请求前初始化引擎"""
    await engine_manager.initialize_engines()
    
    # 设置默认引擎
    default_engine = engine_manager.config.get('default_engine', 'traditional')
    await engine_manager.switch_engine(default_engine)


@app.teardown_appcontext
async def teardown_appcontext(exception=None):
    """应用关闭时清理引擎"""
    # 注意：Flask 的 teardown_appcontext 不支持 async
    # 可以使用 atexit 模块或者在应用关闭时手动调用
    pass


# 如果需要优雅关闭，可以使用 atexit
import atexit

@atexit.register
def cleanup_engines():
    """清理所有引擎"""
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(engine_manager.shutdown_all())
    except RuntimeError:
        # 如果事件循环已经关闭
        pass
