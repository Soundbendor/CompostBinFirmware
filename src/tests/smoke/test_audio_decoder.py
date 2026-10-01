"""Validate faster-whisper's native decoder without downloading a model."""

from io import BytesIO
import unittest
import wave

import numpy as np
from faster_whisper.audio import decode_audio


class AudioDecoderSmokeTests(unittest.TestCase):
    def test_decodes_synthetic_pcm_with_the_installed_pyav(self):
        source = BytesIO()
        with wave.open(source, "wb") as recording:
            recording.setnchannels(1)
            recording.setsampwidth(2)
            recording.setframerate(16000)
            recording.writeframes(b"\x00\x00" * 16000)
        source.seek(0)

        audio = decode_audio(source, sampling_rate=16000)

        self.assertEqual(audio.shape, (16000,))
        self.assertEqual(audio.dtype, np.float32)
        self.assertTrue(np.all(audio == 0))


if __name__ == "__main__":
    unittest.main()
