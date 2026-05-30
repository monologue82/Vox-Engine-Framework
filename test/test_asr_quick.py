import sys, time, json, librosa, numpy as np, socketio

sio = socketio.Client()
asr_results = []

@sio.on('connect')
def on_connect():
    print('[SOCKET] Connected')

@sio.on('recognition_result')
def on_recognition_result(data):
    asr_results.append(data)
    print(f'[ASR] text="{data.get("text","")}" conf={data.get("confidence",0):.0f}%')

@sio.on('log')
def on_log(data):
    pass

@sio.on('audio_level')
def on_audio_level(data):
    pass

print('Loading audio...')
audio, sr = librosa.load('C:/Users/26276/Desktop/朗诵1.mp3', sr=16000, mono=True)
if np.max(np.abs(audio)) > 0:
    audio = audio / np.max(np.abs(audio)) * 0.95
audio_int16 = (audio * 32767).astype(np.int16)
print(f'Audio: {len(audio_int16)} samples @ 16kHz')

CHUNK_SAMPLES = int(16000 * 0.25)
num_chunks = 8  # Only send first 8 chunks (2 seconds)

print(f'Connecting to http://localhost:5000...')
sio.connect('http://localhost:5000')

print(f'Sending {num_chunks} chunks...')
for i in range(0, num_chunks * CHUNK_SAMPLES, CHUNK_SAMPLES):
    chunk = audio_int16[i:i+CHUNK_SAMPLES]
    chunk_list = chunk.tolist()
    sio.emit('stream_audio', {'data': chunk_list, 'device': 'test', 'language': 'zh'})
    time.sleep(0.05)

time.sleep(2)
sio.emit('stop_stream')
time.sleep(1)

print(f'\nASR results: {len(asr_results)}')
for r in asr_results:
    print(f'  - "{r.get("text","")}"')

sio.disconnect()
print('Done')