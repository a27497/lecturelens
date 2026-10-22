# ASR connectivity fixture

`tone.wav` is a repository-generated, one-second 400 Hz square wave (16 kHz,
mono, signed 16-bit PCM). It contains no speech, recordings or third-party media
and is distributed under the repository's MIT license. It tests transport and
response parsing, not recognition quality; an empty transcript is acceptable.

Reproduce from the repository root:

```python
import struct
import wave

with wave.open("backend/src/main/resources/system-model-probe/tone.wav", "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(16000)
    wav.writeframes(struct.pack("<16000h", *[
        1000 if (i // 20) % 2 == 0 else -1000 for i in range(16000)
    ]))
```
