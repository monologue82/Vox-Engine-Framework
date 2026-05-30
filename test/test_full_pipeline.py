#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全流程测试：音频文件 → ASR → 翻译 → TTS
使用 FLAC 文件模拟麦克风输入，通过 Socket.IO 和服务端 API 测试全链路
"""
import sys
import os
import io
import time
import json
import subprocess
import numpy as np
import socketio
import requests
import soundfile as sf
from scipy import signal

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ═══════════════════════════════════════
# 配置
# ═══════════════════════════════════════
AUDIO_FILE = r"C:\Users\26276\Desktop\朗诵1.mp3"
SERVER_URL = "http://localhost:5000"
SAMPLE_RATE = 16000
CHUNK_DURATION = 0.2       # 每次 200ms
SEND_INTERVAL = 0.05       # 发送间隔 50ms
TARGET_LANG = "English"     # 翻译目标语言
ASR_LANG = "zh"            # 源语言
TTS_OUTPUT = os.path.join(os.path.dirname(__file__), "tts_output.wav")

# ═══════════════════════════════════════
# Step 0: 检查音频文件
# ═══════════════════════════════════════
print("=" * 60)
print("全流程测试：音频文件 → ASR → 翻译 → TTS")
print("=" * 60)

if not os.path.exists(AUDIO_FILE):
    print(f"ERROR: 音频文件不存在: {AUDIO_FILE}")
    sys.exit(1)

print(f"\n[0/5] 加载音频文件: {AUDIO_FILE}")

audio, sr = sf.read(AUDIO_FILE, dtype='float32')
if len(audio.shape) > 1:
    audio = audio[:, 0]  # 转单声道

print(f"  原始: {len(audio)} 采样, {sr}Hz, {len(audio)/sr:.2f}s, 声道数: {2 if len(audio.shape) > 1 else 1}")

# 重采样到 16kHz
if sr != SAMPLE_RATE:
    print(f"  重采样 {sr}Hz → {SAMPLE_RATE}Hz...")
    num_samples = int(len(audio) * SAMPLE_RATE / sr)
    audio = signal.resample(audio, num_samples)
    sr = SAMPLE_RATE

# 标准化音量 + 转 int16
if np.max(np.abs(audio)) > 0:
    audio = audio / np.max(np.abs(audio)) * 0.85
audio_int16 = (audio * 32767).astype(np.int16)

duration = len(audio) / sr
print(f"  处理后: {len(audio)} 采样, {sr}Hz, {duration:.2f}s")
print(f"  文件大小(估算): {len(audio_int16) * 2 / 1024:.1f} KB")

# ═══════════════════════════════════════
# Step 1: 上传音频作为音色参考
# ═══════════════════════════════════════
print(f"\n[1/5] 准备音色参考音频...")

# 先检查服务器是否在运行
try:
    resp = requests.get(f"{SERVER_URL}/api/microphones", timeout=3)
    print(f"  服务器状态: OK (HTTP {resp.status_code})")
except Exception as e:
    print(f"  ERROR: 无法连接到服务器 {SERVER_URL}")
    print(f"  请先运行: cd {os.path.dirname(os.path.dirname(__file__))} && start.bat")
    sys.exit(1)

# 始终上传朗诵1.mp3作为音色参考，确保参考音频与文本匹配
speaker_filename = None
file_size_mb = os.path.getsize(AUDIO_FILE) / (1024 * 1024)
print(f"  上传 {os.path.basename(AUDIO_FILE)} ({file_size_mb:.2f}MB) 作为音色参考...")
with open(AUDIO_FILE, 'rb') as f:
    files = {'audio': (os.path.basename(AUDIO_FILE), f, 'audio/mpeg')}
    try:
        resp = requests.post(f"{SERVER_URL}/api/voice-clone/upload", files=files, timeout=30)
        if resp.status_code == 200:
            result = resp.json()
            speaker_filename = result.get('filename')
            print(f"  上传成功: {speaker_filename}")
        else:
            print(f"  上传失败: HTTP {resp.status_code} - {resp.text[:200]}")
    except Exception as e:
        print(f"  上传异常: {e}")

if speaker_filename is None:
    print(f"  ERROR: 无法上传音色参考音频")
    sys.exit(1)

# ═══════════════════════════════════════
# Step 2: ASR — 通过 Socket.IO 发送音频
# ═══════════════════════════════════════
print(f"\n[2/5] ASR: 通过 Socket.IO 模拟麦克风发送音频...")

asr_results = []
all_asr_text = ""

sio = socketio.Client(logger=False, engineio_logger=False)

@sio.on('connect')
def on_connect():
    print('  [Socket] 已连接')

@sio.on('disconnect')
def on_disconnect():
    print('  [Socket] 已断开')

@sio.on('recognition_result')
def on_recognition_result(data):
    asr_results.append(data)
    text = data.get('text', '')
    # Only print significant changes (FunASR sends cumulative updates)
    if text:
        conf = data.get('confidence', 0)
        lang = data.get('language', '?')
        print(f'  [ASR] cmd="{text[:40]}..." | conf={conf:.0f}% | lang={lang}')

@sio.on('log')
def on_log(data):
    msg = data.get('message', '')
    level = data.get('type', '')
    if 'error' in level or 'Error' in msg:
        print(f'  [LOG:{level}] {msg[:120]}')

@sio.on('audio_level')
def on_audio_level(data):
    pass

sio.connect(SERVER_URL)
time.sleep(0.5)

# 分块发送
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION)
total_chunks = (len(audio_int16) + CHUNK_SAMPLES - 1) // CHUNK_SAMPLES

print(f"  发送 {total_chunks} 个音频块 (每块 {CHUNK_DURATION*1000:.0f}ms, 共 {duration:.2f}s)...")

send_start = time.time()
for i in range(0, len(audio_int16), CHUNK_SAMPLES):
    chunk = audio_int16[i:i + CHUNK_SAMPLES]
    chunk_idx = i // CHUNK_SAMPLES + 1

    sio.emit('stream_audio', {
        'data': chunk.tolist(),
        'device': 'pipeline_test',
        'language': ASR_LANG,
        'target_language': TARGET_LANG
    })

    elapsed = time.time() - send_start
    if chunk_idx % 10 == 0 or chunk_idx == 1 or chunk_idx == total_chunks:
        print(f'  块 {chunk_idx}/{total_chunks}: {len(chunk)} 采样 @ {elapsed:.1f}s (音频位置: {i/sr:.1f}s)')

    time.sleep(CHUNK_DURATION - SEND_INTERVAL)

send_end = time.time()
print(f"  发送完成，耗时 {send_end - send_start:.1f}s")

# 等待最后的识别结果
print("  等待最终识别结果...")
time.sleep(3)

sio.emit('stop_stream')
time.sleep(1)

# 汇总 ASR 结果 — FunASR 每次返回累积结果，取最后一条最完整的
if asr_results:
    last_result = asr_results[-1]
    all_asr_text = last_result.get('text', '').strip()
else:
    all_asr_text = ""

all_asr_text = ' '.join(all_asr_text.split())  # 清理多余空格

print(f"\n  === ASR 结果汇总 ===")
print(f"  识别事件数: {len(asr_results)}")
print(f"  最终文本 ({len(all_asr_text)}字):")
# 分段打印长文本
if len(all_asr_text) > 200:
    print(f"  \"{all_asr_text[:200]}...\"")
    print(f"  (还有 {len(all_asr_text)-200} 字)")
else:
    print(f"  \"{all_asr_text}\"")

if not all_asr_text:
    print("  WARNING: ASR 没有返回任何文本，可能音频太短或无语音内容")
    print("  继续后续步骤...")

# ═══════════════════════════════════════
# Step 3: 翻译 — 通过 Socket.IO 发送翻译请求
# ═══════════════════════════════════════
print(f"\n[3/5] 翻译: {ASR_LANG} → {TARGET_LANG}")

# 自动检测 LM Studio 可用模型
lm_model_name = ''
try:
    resp = requests.get(f"{SERVER_URL}/api/models", timeout=5)
    if resp.status_code == 200:
        models = resp.json()
        if models:
            lm_model_name = models[0]
            print(f"  LM Studio 可用模型: {', '.join(models[:3])}")
            print(f"  使用模型: {lm_model_name}")
except Exception as e:
    print(f"  无法获取模型列表: {e}")

translation_text = ""
translation_complete = False

@sio.on('translation_chunk')
def on_translation_chunk(data):
    global translation_text
    chunk = data.get('chunk', '')
    translation_text += chunk

@sio.on('translation_complete')
def on_translation_complete(data):
    global translation_text, translation_complete
    translation_text = data.get('translation', translation_text)
    translation_complete = True
    print(f'\n  ✓ 翻译完成 ({len(translation_text)}字): "{translation_text}"')

@sio.on('translation_error')
def on_translation_error(data):
    print(f'  [ERROR] 翻译失败: {data.get("message", "未知错误")}')

@sio.on('translation_status')
def on_translation_status(data):
    print(f'  状态: {data.get("message", "")}')

if all_asr_text:
    # 截取合适长度用于翻译（避免过长导致超时）
    MAX_TRANSLATE_CHARS = 500
    translate_text = all_asr_text[:MAX_TRANSLATE_CHARS]
    if len(all_asr_text) > MAX_TRANSLATE_CHARS:
        print(f"  文本过长({len(all_asr_text)}字)，截取前{MAX_TRANSLATE_CHARS}字翻译")

    sio.emit('translate_debug_text', {
        'text': translate_text,
        'source_lang': ASR_LANG,
        'target_lang': 'en',
        'translation_style': '',
        'model_name': lm_model_name
    })
    print(f"  发送翻译: \"{translate_text[:60]}...\"")
    print("  等待翻译中", end='', flush=True)

    # 等待翻译完成（最多 120 秒）
    wait_start = time.time()
    while not translation_complete and time.time() - wait_start < 120:
        if translation_text:
            print('.', end='', flush=True)
            time.sleep(0.5)
        else:
            time.sleep(0.5)

    print()
    if translation_complete:
        print(f"  翻译结果: \"{translation_text}\"")
    elif translation_text:
        print(f"  部分结果: \"{translation_text}\"")
    else:
        print(f"  翻译超时（120s），未收到结果")
else:
    print("  跳过翻译（无 ASR 文本）")
    translation_text = "Hello, this is a test of the full pipeline."
    print(f"  使用默认文本: \"{translation_text}\"")

# ═══════════════════════════════════════
# Step 4: TTS — 调用 GSV-TTS API
# ═══════════════════════════════════════
print(f"\n[4/5] TTS: 使用音色参考 + 中文原文生成语音...")

# GSV-TTS 是中文语音克隆模型，始终使用 ASR 中文原文
tts_text = all_asr_text

if len(tts_text) < 4:
    tts_text = "这是一段测试语音。"
    print(f"  文本太短，使用默认文本")

# 截取合适长度
max_tts_len = 120
original_len = len(tts_text)
if len(tts_text) > max_tts_len:
    tts_text = tts_text[:max_tts_len]
    print(f"  文本过长({original_len}字)，截取前{max_tts_len}字")

print(f"  来源: ASR原文(中文)")
print(f"  输入 ({len(tts_text)}字): \"{tts_text}\"")
print(f"  音色参考: \"{speaker_filename}\"")
print(f"  参考文本: \"{all_asr_text[:25]}...\"")

try:
    resp = requests.post(
        f"{SERVER_URL}/api/gsv-tts/generate",
        json={
            'text': tts_text,
            'speaker_wav': speaker_filename,
            'speed': 1.0,
            'reference_text': all_asr_text
        },
        timeout=120
    )

    if resp.status_code == 200:
        with open(TTS_OUTPUT, 'wb') as f:
            f.write(resp.content)
        size_kb = len(resp.content) / 1024
        print(f"  TTS 生成成功！")
        print(f"  输出文件: {TTS_OUTPUT}")
        print(f"  文件大小: {size_kb:.1f} KB")
    else:
        error_text = resp.text[:300]
        print(f"  TTS 失败: HTTP {resp.status_code}")
        print(f"  错误详情: {error_text}")
except Exception as e:
    print(f"  TTS 请求异常: {e}")

# ═══════════════════════════════════════
# Step 5: 汇总
# ═══════════════════════════════════════
print(f"\n{'=' * 60}")
print(f"全流程测试完成")
print(f"{'=' * 60}")
print(f"  音频文件:  {os.path.basename(AUDIO_FILE)} ({duration:.1f}s)")
print(f"  ASR 文本:  \"{all_asr_text}\"")
print(f"  翻译文本:  \"{translation_text}\"")
print(f"  TTS 输出:  {TTS_OUTPUT} {'✓' if os.path.exists(TTS_OUTPUT) else '✗'}")
print(f"{'=' * 60}")

# 断开连接
sio.disconnect()
print("Done.")