#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模拟麦克风实时输入测试 ASR 流式识别
使用 WAV 文件模拟麦克风分块输入
"""
import sys
import os
import time
import json
import io
import numpy as np
import socketio

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# === 配置 ===
WAV_FILE = "C:/Users/26276/Desktop/au_dlg_commvo_zhuangfy_agree_02.wav"
SERVER_URL = "http://localhost:5000"
SAMPLE_RATE = 16000
CHUNK_DURATION = 0.2  # 每次发送200ms的音频（模拟前端bufferSize=4096 ≈ 256ms，用200ms更精确）
SEND_INTERVAL = 0.05   # 发送间隔50ms（模拟实时到达的速率）

# === 加载 WAV 文件 ===
print(f"Loading WAV file: {WAV_FILE}")
try:
    import soundfile as sf
    audio, sr = sf.read(WAV_FILE, dtype='float32')
    if len(audio.shape) > 1:
        audio = audio[:, 0]  # 转单声道
    if sr != SAMPLE_RATE:
        print(f"WARNING: Expected {SAMPLE_RATE}Hz, got {sr}Hz. Resampling...")
        import librosa
        audio = librosa.resample(audio, orig_sr=sr, target_sr=SAMPLE_RATE)
except ImportError:
    import wave
    with wave.open(WAV_FILE, 'rb') as wf:
        sr = wf.getframerate()
        n_frames = wf.getnframes()
        audio_bytes = wf.readframes(n_frames)
        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    if sr != SAMPLE_RATE:
        print(f"WARNING: Expected {SAMPLE_RATE}Hz, got {sr}Hz. Resampling...")
        import librosa
        audio = librosa.resample(audio, orig_sr=sr, target_sr=SAMPLE_RATE)

# 标准化音量
if np.max(np.abs(audio)) > 0:
    audio = audio / np.max(np.abs(audio)) * 0.85
audio_int16 = (audio * 32767).astype(np.int16)

duration = len(audio) / SAMPLE_RATE
print(f"Audio loaded: {len(audio)} samples, {duration:.2f}s at {SAMPLE_RATE}Hz")

# 播放一下让管理员听
print(f"\nExpected text: 是这样没错。")

# === 连接 Socket.IO ===
sio = socketio.Client(logger=False, engineio_logger=False)
results = []

@sio.on('connect')
def on_connect():
    print('[SOCKET] Connected')

@sio.on('disconnect')
def on_disconnect():
    print('[SOCKET] Disconnected')

@sio.on('recognition_result')
def on_recognition_result(data):
    results.append(data)
    text = data.get('text', '')
    conf = data.get('confidence', 0)
    lang = data.get('language', '?')
    print(f'[ASR] text="{text}" | conf={conf:.0f}% | lang={lang}')

@sio.on('log')
def on_log(data):
    msg = data.get('message', '')
    if 'error' in msg.lower() or 'fail' in msg.lower():
        print(f'[LOG] {msg}')

@sio.on('audio_level')
def on_audio_level(data):
    pass  # 不打印音频电平

print(f"Connecting to {SERVER_URL}...")
sio.connect(SERVER_URL)
time.sleep(1)

# === 分块发送音频（模拟麦克风实时输入）===
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION)
total_chunks = (len(audio_int16) + CHUNK_SAMPLES - 1) // CHUNK_SAMPLES

print(f"\nSending {total_chunks} chunks @ {CHUNK_DURATION*1000:.0f}ms each...")
print(f"Total duration: {duration:.2f}s\n")

send_start = time.time()
for i in range(0, len(audio_int16), CHUNK_SAMPLES):
    chunk = audio_int16[i:i + CHUNK_SAMPLES]
    
    sio.emit('stream_audio', {
        'data': chunk.tolist(),
        'device': 'test_mic_sim',
        'language': 'zh',
        'target_language': 'English'
    })
    
    elapsed = time.time() - send_start
    print(f'  Chunk {i//CHUNK_SAMPLES+1}/{total_chunks}: {len(chunk)} samples '
          f'@ {elapsed:.2f}s (audio pos: {i/SAMPLE_RATE:.2f}s)')
    
    # 模拟实时速率：200ms音频在200ms内发送完
    # 每个chunk之间有50ms间隔，加上睡眠 = 200ms总计
    time.sleep(CHUNK_DURATION - SEND_INTERVAL)

send_end = time.time()
print(f"\nSend complete in {send_end - send_start:.2f}s")

# 等待异步结果返回
print("Waiting for final results...")
time.sleep(3)

# 发送停止信号
sio.emit('stop_stream')
time.sleep(1)

print(f"\n{'='*60}")
print(f"RESULTS SUMMARY")
print(f"{'='*60}")
print(f"Total results received: {len(results)}")
for i, r in enumerate(results):
    print(f"  [{i+1}] text=\"{r.get('text','')}\" | conf={r.get('confidence',0):.0f}% | lang={r.get('language','?')}")

# 拼接所有结果
all_text = ' '.join([r.get('text', '') for r in results])
print(f"\nCombined text: \"{all_text}\"")
print(f"Expected text: \"是这样没错。\"")

sio.disconnect()
print("\nDone.")