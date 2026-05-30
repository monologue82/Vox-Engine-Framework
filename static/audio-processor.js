class AudioProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.buffer = new Float32Array(1024);
        this.bufferIndex = 0;
        this.sampleRate = 16000;
        this.downsampleRatio = 1;
    }

    process(inputs, outputs, parameters) {
        const input = inputs[0];
        if (!input || input.length === 0) {
            return true;
        }

        const channelData = input[0];
        
        if (this.downsampleRatio === 1) {
            for (let i = 0; i < channelData.length; i++) {
                this.buffer[this.bufferIndex++] = channelData[i];
                
                if (this.bufferIndex >= this.buffer.length) {
                    this.sendBuffer();
                }
            }
        } else {
            for (let i = 0; i < channelData.length; i += this.downsampleRatio) {
                this.buffer[this.bufferIndex++] = channelData[i];
                
                if (this.bufferIndex >= this.buffer.length) {
                    this.sendBuffer();
                }
            }
        }

        return true;
    }

    sendBuffer() {
        const int16Array = new Int16Array(this.buffer.length);
        for (let i = 0; i < this.buffer.length; i++) {
            int16Array[i] = Math.max(-32768, Math.min(32767, this.buffer[i] * 32768));
        }
        
        this.port.postMessage({
            type: 'audioData',
            buffer: int16Array
        });
        
        this.bufferIndex = 0;
    }
}

registerProcessor('audio-processor', AudioProcessor);