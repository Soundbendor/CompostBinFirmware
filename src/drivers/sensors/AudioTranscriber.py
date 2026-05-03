"""
Will Richards, Oregon State University, 2024

Abstraction layer for automated speech recognition (ASR) of recorded audio
"""
from faster_whisper import WhisperModel
import logging
from time import time

class AudioTranscriber():
    def __init__(self, model="small.en"):
        self.model = WhisperModel(model, device="cpu", compute_type="int8")

    def transcribe(self, inputFile: str):
        start_time = time()
        segments, info = self.model.transcribe(inputFile, beam_size=5)

        # segments is a generator, so we need to join them
        processed_str = "".join([segment.text for segment in segments]).strip()

        end_time = time()
        logging.info(f"Transcription took: {end_time - start_time} seconds")

        return processed_str
        