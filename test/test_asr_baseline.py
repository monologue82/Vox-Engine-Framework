#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线基准测试 - 确认 SenseVoice 模型能否正确识别音频"""
import sys, os, io, time
import numpy as np

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

WAV_FILE = "C:/Users/26276/Desktop/au_dlg_commvo_zhuangfy_agree_02.wav"

def clean_text(text):
    if not text:
        return ""
    try:
        from funasr.utils.postprocess_utils import rich_transcription_postprocess
        return rich_transcription_postprocess(text)
    except Exception:
        tokens_to_remove = [
            '<|zh|>', '<|en|>', '<|ja|>', '<|ko|>', '<|yue|>', '<|ca|>', '<|ru|>',
            '<|pt|>', '<|ar|>', '<|ta|>', '<|hi|>', '<|mi|>', '<|id|>', '<|de|>',
            '<|fr|>', '<|es|>', '<|emo|>', '<|EMO_UNKNOWN|>', '<|Speech|>',
            '<|Music|>', '<|Noise|>', '<|Punctuation|>', '<|woitn|>', '<|withitn|>',
            '<|HAPPY|>', '<|SAD|>', '<|ANGRY|>', '<|NEUTRAL|>', '<|EMO_UNKNOWN|>',
        ]
        cleaned = text
        for token in tokens_to_remove:
            cleaned = cleaned.replace(token, '')
        cleaned = ' '.join(cleaned.split())
        return cleaned

# Load audio
print(f"Loading: {WAV_FILE}")
import soundfile as sf
audio, sr = sf.read(WAV_FILE, dtype='float32')
if len(audio.shape) > 1:
    audio = audio[:, 0]
print(f"Audio: {len(audio)} samples, {sr}Hz, {len(audio)/sr:.2f}s")

if sr != 16000:
    import librosa
    audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
    print(f"Resampled to 16000Hz: {len(audio)} samples, {len(audio)/16000:.2f}s")

print(f"\nExpected text: 是这样没错。")
print(f"{'='*60}")

print("\nInitializing SenseVoiceSmall model...")
from funasr import AutoModel
from funasr_asr import initialize_funasr, _funasr_model, _model_lock

model_path = "C:/Users/26276/Desktop/project/main/V0.3/models/stt/SenseVoiceSmall"
device = "cuda:0"
try:
    import torch
    if not torch.cuda.is_available():
        device = "cpu"
except:
    device = "cpu"
print(f"Device: {device}")

ok = initialize_funasr(model_path, device, use_vad=False)
if not ok:
    print("FAILED to initialize!")
    sys.exit(1)

# Test 1: Offline
print("\n--- Test 1: Offline (full file) ---")
with _model_lock:
    result = _funasr_model.generate(
        input=WAV_FILE, language="zh", use_itn=True,
        remove_pun=False, disable_pbar=True
    )
text = result[0].get('text', '') if result else ""
print(f"Raw: {repr(text)}")
print(f"Cleaned: '{clean_text(text)}'")

# Test 2: Streaming with [0, 10, 5] (correct)
print("\n--- Test 2: Streaming chunk_size=[0, 10, 5] (correct) ---")
cache = {}
chunk_samples = int(16000 * 0.2)  # 200ms
results = []
for i in range(0, len(audio), chunk_samples):
    chunk = audio[i:i + chunk_samples].astype(np.float32)
    if len(chunk) < 400:
        break
    is_final = (i + chunk_samples >= len(audio))
    with _model_lock:
        result = _funasr_model.generate(
            input=chunk, cache=cache, is_final=is_final,
            chunk_size=[0, 10, 5], language="zh",
            use_itn=True, remove_pun=False, disable_pbar=True
        )
    if result and len(result) > 0 and result[0].get('text', ''):
        t = result[0]['text']
        print(f"  [{i//chunk_samples}] raw={repr(t[:80])} | clean='{clean_text(t)}'")
        results.append(clean_text(t))
print(f"\nCombined: {' '.join(results)}")

# Test 3: Streaming with chunk_size=50 (current broken)
print("\n--- Test 3: Streaming chunk_size=50 (current broken config) ---")
cache2 = {}
for i in range(0, len(audio), chunk_samples):
    chunk = audio[i:i + chunk_samples].astype(np.float32)
    if len(chunk) < 400:
        break
    is_final = (i + chunk_samples >= len(audio))
    with _model_lock:
        result = _funasr_model.generate(
            input=chunk, cache=cache2, is_final=is_final,
            chunk_size=50, chunk_size_ms=50, language="zh",
            use_itn=True, remove_pun=False, disable_pbar=True
        )
    if result and len(result) > 0 and result[0].get('text', ''):
        t = result[0]['text']
        print(f"  [{i//chunk_samples}] raw={repr(t[:80])} | clean='{clean_text(t)}'")
print("\nDone.")