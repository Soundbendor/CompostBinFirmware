"""
Will Richards, Oregon State University, 2024

Provides a functionality to interface with a standard USB microphone using a USB Audio DAC and PyAudio
"""

import logging
import os
import subprocess
import wave
from time import gmtime, strftime, time

import numpy as np
import pyaudio


class Microphone:
    """
    Create a new instance of the microhpone which will be used to collect item descriptions

    :param record_duration: The lenght of time in seconds that the microphone will record for
    """

    def __init__(self, record_duration=10, model="base.en-q5_0"):

        # Audio recording parameters
        self.sampling_rate = 16000
        self.device_index = 0
        self.channels = 2
        self.frames_per_buffer = 128
        self.format = pyaudio.paInt16
        self.record_duration = record_duration
        self.alsaSoundCardNum = 0

        self.pAudio = None

        # Enable the microphone capture
        with open(os.devnull, "wb") as devnull:
            while True:
                try:
                    subprocess.check_call(
                        [
                            "/usr/bin/amixer",
                            "-c",
                            str(self.alsaSoundCardNum),
                            "set",
                            "Mic",
                            "cap",
                        ],
                        stdout=devnull,
                        stderr=subprocess.STDOUT,
                    )
                    break
                except subprocess.CalledProcessError as e:
                    self.alsaSoundCardNum += 1
                    logging.info(e)
                except KeyboardInterrupt:
                    break

    """
    Initialize the whisper model and warm it up by feeding 0s into it
    """

    def initialize(self):
        logging.info("Microphone initialized!")
        self.pAudio = pyaudio.PyAudio()
        self.initialized = True

    """
    Write some audio data out to a .wav file

    :param data: Data to be written to the wav file
    :param outputFile: The name of the file the data should be written to
    """

    def writeWave(self, data, outputFile):
        # Write the pre downsampled audio to .wav file
        if self.pAudio:
            wf = wave.open(outputFile, "wb")
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.pAudio.get_sample_size(self.format))
            wf.setframerate(self.sampling_rate)
            wf.writeframes(b"".join(data))
            wf.close()

    """
    Record audio from the microphone and write it to a file

    :param outputFile: File to write the recorded audio to
    """

    def _record(self, outputFile):
        frames = []

        # Attempt to open the microphone stream
        try:
            self.stream = self.pAudio.open(
                format=pyaudio.paInt16,
                rate=self.sampling_rate,
                input=True,
                channels=2,
                input_device_index=self.device_index,
                frames_per_buffer=self.frames_per_buffer,
            )
        except Exception as e:
            logging.error("Failed to open audio input device: {e}")
            self.initialized = False

        logging.info("RECORDING....")
        self.stream.start_stream()

        for _ in range(
            0, int(self.sampling_rate / self.frames_per_buffer * self.record_duration)
        ):
            data = self.stream.read(self.frames_per_buffer, exception_on_overflow=False)
            frames.append(data)

        self.stream.stop_stream()

        fileName = outputFile.split(".")
        currentTime = time()
        outputFile = strftime(
            f"../data/{fileName[0]}_%Y-%m-%d--%H-%M-%S.{fileName[1]}",
            gmtime(currentTime),
        )
        self.writeWave(frames, outputFile)
        self.stream.close()
        logging.info("STOPPED RECORDING")
        return outputFile

    """
    Record a clip from the microphone
    """

    def record(self):
        if self.initialized:
            # Record and downsample the audio to 16khz
            return self._record("downsampledAudio.wav")
        else:
            logging.warning("Microphone not initialized!")
            return ""

    """
    Cleanup thread
    """

    def kill(self):
        if self.pAudio:
            self.pAudio.terminate()

