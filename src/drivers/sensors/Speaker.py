"""
Will Richards, Oregon State University, 2024

Provides a functionality to interface with a standard USB speaker using PyAudio and play sound over it
"""

import logging
import pyaudio
import wave
import subprocess
import os


class Speaker():

    """
    Create a new instance of a speaker
    """
    def __init__(self):

        # Audio playback parameters
        self.device_index = 0
        self.channels = 1
        self.frames_per_buffer = 1024
        self.pAudio = None
        self.initialized = False

    def initialize(self):
        self.pAudio = pyaudio.PyAudio()
        self.initialized = True
    
    """
    Play a given audio file out of the waveshare connected speaker

    :pram clipName: The name of the .wav file to paly
    """
    def playClip(self, clipName):
        if self.pAudio is None:
            return

        wf = wave.open(clipName, 'r')

        # Attempt to open the speaker stream
        try:
            self.stream = self.pAudio.open(format = self.pAudio.get_format_from_width(wf.getsampwidth()),
                channels = self.channels,
                rate = wf.getframerate(),
                output = True,
                output_device_index=self.device_index)
        except Exception as e:
            logging.error(f"Failed to open audio input device: {e}")
            self.initialized = False

        # Only if the device succsessfully initialized should we actually attempt to write to it
        if(self.initialized):
            data = wf.readframes(self.frames_per_buffer)
            while data:
                self.stream.write(data)
                data = wf.readframes(self.frames_per_buffer)
        
        self.stream.close()

    def kill(self):
        if self.pAudio:
            self.pAudio.terminate()

    """
    Mute the speaker attatched to the waveshare adapter
    """
    def muteSpeaker(self, alsaSoundCardNum):
        with open(os.devnull, 'wb') as devnull:
            subprocess.check_call(['/usr/bin/amixer', '-c', str(alsaSoundCardNum), 'sset', 'Speaker', 'mute'], stdout=devnull, stderr=subprocess.STDOUT)

    """
    Unmute the speaker attatched to the waveshare adapter
    """
    def unmuteSpeaker(self, alsaSoundCardNum):
        with open(os.devnull, 'wb') as devnull:
            subprocess.check_call(['/usr/bin/amixer', '-c', str(alsaSoundCardNum), 'sset', 'Speaker', 'unmute'], stdout=devnull, stderr=subprocess.STDOUT)


        
