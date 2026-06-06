# Vox Engine Framework v0.4.1 Release Notes

## Overview

This release marks a significant upgrade from v0.3 with major improvements to the ASR pipeline, translation ordering, and overall stability. The core focus has been on fixing audio chunk timing issues that caused inaccurate translations and adding robust out-of-order protection across the entire processing pipeline.

## What's New

### 1. FunASR Persisent Cache for Streaming ASR

- **Issue**: Each 0.5s audio chunk was processed independently by FunASR without cross-chunk context, causing fragmented or empty ASR results.
- **Fix**: `process_audio_stream` now maintains a persistent `funasr_cache` dictionary across the entire audio loop, enabling FunASR to maintain streaming state across chunks.
- **Final flush**: Added `is_final=True` call at loop end to flush any remaining audio in FunASR's internal buffer.

### 2. Sequence-Numbered Translation Ordering

- **Issue**: Multiple translation requests ran concurrently via `ThreadPoolExecutor`, and slower responses could overwrite newer, correct translations.
- **Fix**: Every translation request now carries a globally-incrementing `seq` number. The frontend ignores any response with a `seq` lower than the latest received.
- **Files affected**: `app.py` — `_translation_seq`, `_active_translation_seq`, `_next_translation_seq()`, `_is_translation_stale()`

### 3. Server-Side Stale Translation Early Termination

- **Issue**: Old translation threads continued consuming API resources even after being superseded.
- **Fix**: All three async translation paths (`fetch_translation`, `_do_lps_translation`, `_do_openai_translation`) now check `_is_translation_stale()` at entry, during streaming, and before emitting completion.
- **Benefit**: Saves API bandwidth and reduces unnecessary load on translation servers.

### 4. ASR Text Extraction & Cleaning

- **Issue**: `transcribe_audio_stream` returned raw FunASR dict results instead of extracted text, and SenseVoice tags (`<|zh|>`, `<|en|>`) were passed directly into translation.
- **Fix**: The function now properly extracts `result[0].get('text')` and calls `_strip_sensevoice_tags()` for clean text output.

### 5. Fixed Frontend Throttle Data Loss

- **Issue**: The `requestAnimationFrame` throttle in `translation_chunk` handler captured a fixed `data` closure, causing chunks arriving within the 50ms window to be silently dropped.
- **Fix**: RAF callback now reads the latest `pendingTranslationUpdate` instead of a captured variable, ensuring every chunk is rendered.
- **Files affected**: `static/js/main.js`

### 6. Fixed `seq=0` Falsy Bug

- **Issue**: `data.seq && data.seq < currentTranslationSeq` short-circuits on `seq=0` (falsy), allowing stale translations to bypass the order filter.
- **Fix**: Changed to `data.seq != null && data.seq < currentTranslationSeq`.

### 7. Streaming TTS Sequence Reset

- **Issue**: When a new translation replaced an older one, `handleStreamingTranslation` retained `lastProcessedLength` from the previous translation, causing TTS to skip the beginning of the new text.
- **Fix**: Added `streamingTranslationSeq` variable — when seq changes, `lastProcessedLength` is reset to 0.

## New Files

| File | Description |
|------|-------------|
| `test/test_asr_baseline.py` | ASR baseline benchmark |
| `test/test_asr_quick.py` | Quick ASR validation |
| `test/test_encoding.py` | Encoding test suite |
| `test/test_full_pipeline.py` | End-to-end pipeline test |
| `test/test_redirect.py` | URL redirect test |
| `test/test_strip.py` | Text stripping test |
| `templates/asr_debug.html` | ASR debug console |
| `templates/translation_debug.html` | Translation stream inspector |
| `templates/tts_debug.html` | TTS stream debugger |
| `templates/tts_only_debug.html` | Standalone TTS test page |
| `static/audio-processor.js` | Audio processing pipeline |
| `README-CN.md` | Chinese documentation |

## Removed Files

- `repair.bat`
- `INSTALLATION_GUIDE.md`
- `setup_env.ps1`
- `test_install.py`

## Configuration Changes

- **`.gitignore`**: Added patterns to exclude `.ckpt`, `.npz`, `.pickle`, `.onnx` and additional model directories (`models/stt/`, `models/tts/g2p/`, etc.)

## Documentation

- `README.md` and `README-CN.md`: Completely rewritten with accurate project structure, updated tech stack (FunASR/SenseVoice, not Vosk), correct port (5000), and all new files documented.

## Upgrade Notes

1. The `.gitignore` now excludes model files more aggressively — if you use `git add -A`, model files will not be tracked.
2. Translation engine configuration in `settings.json` defaults to `lps` — ensure your LPS backend or alternative provider is running.
3. The `repair.bat` script has been removed — dependencies are managed through `setup.bat`.

---

**Full Changelog**: https://github.com/monologue82/Vox-Engine-Framework/compare/v0.3...v0.4.1