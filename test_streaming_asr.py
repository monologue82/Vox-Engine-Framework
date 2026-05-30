#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模拟麦克风实时输入测试 ASR 流式识别
"""
import sys
import os
import time
import io
import numpy as np
import socketio
import soundfile as sf
from scipy import signal

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# === 配置 ===
WAV_FILE = "C:/Users/26276/Desktop/au_dlg_commvo_zhuangfy_agree_02.wav"
SERVER_URL = "http://localhost:5000"
TARGET_SR = 16000
CHUNK_DURATION = 0.2

# === 加载 WAV 文件 ===
print(f"Loading WAV file: {WAV_FILE}", flush=True)
audio, sr = sf.read(WAV_FILE, dtype='float32')
if len(audio.shape) > 1:
    audio = audio[:, 0]
print(f"Loaded: {len(audio)} samples, {sr}Hz, {len(audio)/sr:.2f}s", flush=True)

# 重采样到 16kHz
if sr != TARGET_SR:
    print(f"Resampling {sr}Hz -> {TARGET_SR}Hz...", flush=True)
    num_samples = int(len(audio) * TARGET_SR / sr)
    audio = signal.resample(audio, num_samples)
    sr = TARGET_SR

# 标准化 + 转 int16
if np.max(np.abs(audio)) > 0:
    audio = audio / np.max(np.abs(audio)) * 0.85
audio_int16 = (audio * 32767).astype(np.int16)

duration = len(audio) / sr
print(f"Ready: {len(audio)} samples, {duration:.2f}s @ {sr}Hz", flush=True)
print(f"Expected text: 是这样没错。", flush=True)

# === 连接 Socket.IO ===
results = []
sio = socketio.Client(logger=False, engineio_logger=False)

@sio.on('connect')
def on_connect():
    print('[SOCKET] Connected', flush=True)

@sio.on('recognition_result')
def on_recognition_result(data):
    results.append(data)
    text = data.get('text', '')
    conf = data.get('confidence', 0)
    partial = data.get('is_partial', False)
    print(f'[ASR] text="{text}" | conf={conf:.0f}% | partial={partial}', flush=True)

print(f"Connecting to {SERVER_URL}...", flush=True)
sio.connect(SERVER_URL)
time.sleep(0.5)

# === 分块发送音频 ===
CHUNK_SAMPLES = int(sr * CHUNK_DURATION)
total_chunks = (len(audio_int16) + CHUNK_SAMPLES - 1) // CHUNK_SAMPLES
print(f"\nSending {total_chunks} chunks...", flush=True)

for i in range(0, len(audio_int16), CHUNK_SAMPLES):
    chunk = audio_int16[i:i + CHUNK_SAMPLES]
    chunk_idx = i // CHUNK_SAMPLES + 1
    sio.emit('stream_audio', {
        'data': chunk.tolist(),
        'device': 'test_mic_sim',
        'language': 'zh',
        'target_language': 'English'
    })
    print(f'  Chunk {chunk_idx}/{total_chunks}: {len(chunk)} samples', flush=True)
    time.sleep(CHUNK_DURATION)

print(f"Send complete. Waiting for results...", flush=True)
time.sleep(4)

sio.emit('stop_stream')
time.sleep(1)

print(f"\n{'='*60}", flush=True)
print(f"RESULTS SUMMARY", flush=True)
print(f"{'='*60}", flush=True)
print(f"Total results: {len(results)}", flush=True)
for i, r in enumerate(results):
    print(f"  [{i+1}] text=\"{r.get('text','')}\" | conf={r.get('confidence',0):.0f}% | partial={r.get('is_partial',False)}", flush=True)

all_text = ''.join([r.get('text', '') for r in results])
print(f"\nAccumulated: \"{all_text}\"", flush=True)
print(f"Expected:    \"是这样没错。\"", flush=True)

sio.disconnect()
print("Done.", flush=True)