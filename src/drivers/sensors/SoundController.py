"""
Will Richards, Oregon State University, 2023

Wrapper for Microphone and Audio output to be threadified to avoid truly blocking the main thread
"""

import logging
import os
import subprocess
import time
from multiprocessing import Event, Value

from drivers.DriverBase import DriverBase
from drivers.sensors.Microphone import Microphone
from drivers.sensors.Speaker import Speaker


class SoundController(DriverBase):
    """
    Create a new SoundController device to manage our microphone and speaker

    :param soundControllerConnection: This is a reference to a multiproccessing.Pipe to send our transcription back to the main thread
    :param record_duration: The lenght of time the microphone should be recording for
    """

    def __init__(self, soundControllerConnection, muted, record_duration=4):
        super().__init__("SoundController")

        # Create our new mic and speaker instances
        self.microphone = Microphone(record_duration)
        self.speaker = Speaker()
        self.soundControllerConnection = soundControllerConnection
        self.alsaSoundCardNum = 0
        self.isMuted = muted

        # Set our loop time to 0.05 cause we dont need super fast looping
        self.loopTime = 0.001

        self.events = {
            "RECORD": Event(),
            "WAIT_FOR_BLUETOOTH": Event(),
            "NO_WIFI": Event(),
            "CONNECTED_TO_WIFI": Event(),
            "BLUETOOTH_STOPPED": Event(),
            "MUTED": Event(),
            "UNMUTED": Event(),
            "FAILED_TO_UPLOAD": Event(),
            "SERVER_ERROR": Event(),
            "STOP_RECORDING": Event(),
            "CLOSE_LID_TO_TARE": Event(),
        }

    """
    Mute both the speaker and microphone to avoid feedback and then initialize our microphone
    """

    def initialize(self):
        self.muteMic()
        self.muteSpeaker()
        self.speaker.initialize()
        self.microphone.initialize()
        self.initialized = True
        self.data["initialized"].value = 1

    """
    Mute the speaker attatched to the waveshare adapter
    """

    def muteSpeaker(self):
        self.speaker.muteSpeaker(self.alsaSoundCardNum)

    """
    Unmute the speaker attatched to the waveshare adapter
    """

    def unmuteSpeaker(self):
        self.speaker.unmuteSpeaker(self.alsaSoundCardNum)

    """
    Mute the mic attatched to the waveshare adapter
    """

    def muteMic(self):
        with open(os.devnull, "wb") as devnull:
            while True:
                try:
                    subprocess.check_call(
                        [
                            "/usr/bin/amixer",
                            "-c",
                            str(self.alsaSoundCardNum),
                            "sset",
                            "Mic",
                            "mute",
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
    Unmute the mic attatched to the waveshare adapter
    """

    def unmuteMic(self):
        with open(os.devnull, "wb") as devnull:
            subprocess.check_call(
                [
                    "/usr/bin/amixer",
                    "-c",
                    str(self.alsaSoundCardNum),
                    "sset",
                    "Mic",
                    "unmute",
                ],
                stdout=devnull,
                stderr=subprocess.STDOUT,
            )

    """ 
    Unmutes the speaker plays a sound and then mutes it again
    NOTE: We must mute and unmute the speaker and micophpone channels otherwise the cause huge amounts of deafening feedback

    :param clip: File path to the clip we want to play
    """

    def playClip(self, clip):
        self.unmuteSpeaker()
        self.speaker.playClip(clip)
        self.muteSpeaker()

    """
    If a capture request was recieved we want to play the audio and then record a clip until a non-silent clip is recieved
    """

    def measure(self):
        if self.events["CONNECTED_TO_WIFI"][0].is_set() and not self.isMuted:
            self.playClip("../media/connectionSuccessful.wav")
            self.events["CONNECTED_TO_WIFI"][0].clear()
        elif self.events["NO_WIFI"][0].is_set() and not self.isMuted:
            self.playClip("../media/noWifi.wav")
            self.events["NO_WIFI"][0].clear()
        elif self.events["WAIT_FOR_BLUETOOTH"][0].is_set() and not self.isMuted:
            self.playClip("../media/bluetoothEnabled.wav")
            self.events["WAIT_FOR_BLUETOOTH"][0].clear()
        elif self.events["BLUETOOTH_STOPPED"][0].is_set() and not self.isMuted:
            self.playClip("../media/bluetoothTerminated.wav")
            self.events["BLUETOOTH_STOPPED"][0].clear()
        elif self.events["MUTED"][0].is_set() and not self.isMuted:
            self.playClip("../media/muted.wav")
            self.isMuted = True
            self.events["MUTED"][0].clear()
        elif self.events["UNMUTED"][0].is_set() and self.isMuted:
            self.playClip("../media/unmuted.wav")
            self.isMuted = False
            self.events["UNMUTED"][0].clear()
        elif self.events["FAILED_TO_UPLOAD"][0].is_set() and not self.isMuted:
            self.playClip("../media/failedToUpload.wav")
            self.events["FAILED_TO_UPLOAD"][0].clear()
        elif self.events["SERVER_ERROR"][0].is_set() and not self.isMuted:
            self.playClip("../media/internalServerError.wav")
            self.events["SERVER_ERROR"][0].clear()
        elif self.events["STOP_RECORDING"][0].is_set() and not self.isMuted:
            self.playClip("../media/stopRecording.wav")
            self.events["STOP_RECORDING"][0].clear()
        if self.events["CLOSE_LID_TO_TARE"][0].is_set() and not self.isMuted:
            self.playClip("../media/closeLidToTare.wav")
            self.events["CLOSE_LID_TO_TARE"][0].clear()
        elif self.events["RECORD"][0].is_set():

            if not self.isMuted:
                self.playClip("../media/itemRequest.wav")

            # Check if we actually saved the audio to the file or not if not we want to ask the user for another transcription
            gotRecording = False
            retries = 0

            while not gotRecording and retries < 3:

                self.playClip("../media/startRecording.wav")

                # Record the microphone and return the file name that it was saved at
                self.unmuteMic()
                fileName = self.microphone.record()
                self.muteMic()

                # If the file was saved succsessfully send it and move on but if not TELL the user that we are re-recording
                if len(fileName) != 0:
                    gotRecording = True
                    self.soundControllerConnection.send({"voiceRecording": fileName})
                else:
                    self.playClip("../media/itemRequest.wav")
                    retries += 1

            self.events["RECORD"][0].clear()

    """
    Shutdown our microphone and speaker
    """

    def kill(self):
        self.microphone.kill()
        self.speaker.kill()

    """
    Add TranscribedText to our data dictionary that will be populated by the main thread
    """

    def createDataDict(self):
        self.data = {"TranscribedText": "", "initialized": Value("i", 0)}
        return self.data

