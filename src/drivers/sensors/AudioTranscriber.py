"""Local, CPU-only transcription of recorded audio using faster-whisper."""

import logging
import os
from pathlib import Path
from time import monotonic


class AudioTranscriber:
    def __init__(self, model_path: str | None = None):
        model_dir = Path(
            model_path
            or os.environ.get(
                "WHISPER_MODEL_PATH", "/firmware/models/faster-whisper-small.en"
            )
        )
        if not model_dir.is_dir():
            raise FileNotFoundError(f"Packaged transcription model is missing: {model_dir}")
        # faster-whisper otherwise tries to fetch a tokenizer from the Hub when
        # tokenizer.json is absent, even when the model itself is a local path.
        for filename in ("model.bin", "config.json", "tokenizer.json"):
            if not (model_dir / filename).is_file():
                raise FileNotFoundError(f"Packaged transcription file is missing: {filename}")

        # Import and load native objects only in the publisher's child process.
        from faster_whisper import WhisperModel

        self.model = WhisperModel(
            str(model_dir),
            device="cpu",
            compute_type="int8",
            cpu_threads=int(os.environ.get("WHISPER_CPU_THREADS", "2")),
            local_files_only=True,
        )

    def transcribe(self, inputFile: str) -> str:
        start_time = monotonic()
        segments, _ = self.model.transcribe(inputFile, language="en", beam_size=5)
        # Inference happens while consuming this generator. Let the publisher
        # handle failures from both the call above and iteration below.
        transcription = "".join(segment.text for segment in segments).strip()
        logging.info("Transcription took %.2f seconds", monotonic() - start_time)
        return transcription
