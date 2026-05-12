"""
Will Richards, Oregon State University, 2024

Provides the top level of the whole system so individual components can be utilized individually without needing to give them their own thread via the DriverManager
"""

import json
import os
import time
import uuid
from multiprocessing import Pipe, Queue

from drivers.DriverManager import DriverManager
from drivers.NetworkDriver import BluetoothDriver, WiFiManager
from drivers.sensors.AsyncPublisher import AsyncPublisher
from drivers.sensors.BME688 import BME688
from drivers.sensors.LEDDriver import LEDDriver
from drivers.sensors.LidSwitch import LidSwitch
from drivers.sensors.MLX90640 import MLX90640

# Sensor Drivers
from drivers.sensors.NAU7802 import NAU7802
from drivers.sensors.RealsenseCamera import RealsenseCam
from drivers.sensors.SoundController import SoundController

# Additional Helper Methods
from helpers import CalibrationLoader, Logging


class MainController:

    """
    Create a new instance of our main controlller
    """

    def __init__(self) -> None:
        self.is_initialized = False
        calibration = CalibrationLoader("CalibrationDetails.json")

        if not os.path.exists("../data/"):
            os.mkdir("../data/")

        # Read in current commit number from git file
        # NOTE: This for sure feels like some security vulnerablity like lfi or something but idc
        with open("/firmware/.git/HEAD", "r") as HEADFile:
            refPath = HEADFile.read().split(" ")[1].strip()
            with open(f"/firmware/.git/{refPath}", "r") as commitIDFile:
                self.commitID = commitIDFile.read().strip()

        # Create pipes to all proccesses that create files so we can retrieve the file name that they save the most recent data as
        self.soundControllerConnection, soundControllerConnection = Pipe()
        self.realsenseControllerConenction, realsenseControllerConenction = Pipe()
        self.mlxControllerConenction, mlxControllerConenction = Pipe()

        # Queue of data that needs to be published to the server
        self.publisherQueue = Queue()

        self.isMuted = False
        self.loadConfig()
        self.isBootFromUpdate = os.path.exists("../data/updated.txt")
        if self.isBootFromUpdate:
            os.remove("../data/updated.txt")
        print(self.isBootFromUpdate)

        # Create a manager device passing the NAU7802 in as well as a generic TestDriver that just adds two numbers
        self.manager = DriverManager(
            LEDDriver(self.isBootFromUpdate),
            NAU7802(calibration.get("NAU7802_CALIBRATION_FACTOR")),
            BME688(),
            MLX90640(mlxControllerConenction),
            LidSwitch(),
            RealsenseCam(realsenseControllerConenction),
            SoundController(soundControllerConnection, self.isMuted),
            AsyncPublisher(self.publisherQueue, self.commitID),
            BluetoothDriver(self.isMuted)
        )

        self.wifiManager = WiFiManager()
        self.lastRecording = ""
        
        # Preform the device setup
        self.initialSetup()

        # After we have initialzied all the proccesses we want to flash green to signifiy we are done
        if self.manager.allProcsInitialized and not self.isBootFromUpdate:
            self.manager.setEvent("LEDDriver.DONE")
            time.sleep(2)
            self.manager.setEvent("LEDDriver.NONE")
        elif not self.isBootFromUpdate:
            self.manager.setEvent("LEDDriver.ERROR")
            time.sleep(2)
            self.manager.setEvent("LEDDriver.NONE")

        # First-time setup weight
        self.initialWeight = self.manager.getData()["NAU7802"]["data"]["weight"].value
        self.startingWeight = self.manager.getData()["NAU7802"]["data"]["weight"].value - self.initialWeight
        self.is_initialized = True
 

    """
    Handles the initial power on setup ensuring WiFi is connected and the bluetooth controller is running
    """
    def initialSetup(self):
        # Tell the user that bluetooth services have been enabled for the next 5 minutes
        if not self.isMuted and not self.isBootFromUpdate:
            self.manager.setEvent("SoundController.WAIT_FOR_BLUETOOTH")
            while self.manager.getEvent("SoundController.WAIT_FOR_BLUETOOTH"):
                time.sleep(0.1)

        # Inform the user the WiFi is not connected and check once every 20 seconds, wait until we are connected to WiFi
        wifiState = self.wifiManager.checkConnection()
        if not bool(wifiState["internet_access"]) and not self.isMuted and not self.isBootFromUpdate:
            self.manager.setEvent("SoundController.NO_WIFI")
            while self.manager.getEvent("SoundController.NO_WIFI"):
                time.sleep(0.1)

        # Retry to connect to wifi 4 times
        wifiRetries = 0
        try:
            while wifiRetries < 4:
                wifiState =  self.wifiManager.checkConnection()
                if bool(wifiState["internet_access"]):
                    break
                time.sleep(5)
                wifiRetries += 1
        except KeyboardInterrupt:
            pass

        if not self.isMuted and not self.isBootFromUpdate and bool(wifiState["internet_access"]):
            self.manager.setEvent("SoundController.CONNECTED_TO_WIFI")
            while self.manager.getEvent("SoundController.CONNECTED_TO_WIFI"):
                time.sleep(0.1)
        
        hadToWaitForClose = False
        # Check if the lid is open before taring and if so then yell at the user
        while self.manager.getData()["LidSwitch"]["data"]["Lid_State"].value == 1:
            hadToWaitForClose = True
            self.manager.setEvent("SoundController.CLOSE_LID_TO_TARE")
            while self.manager.getEvent("SoundController.CLOSE_LID_TO_TARE"):
                time.sleep(0.1)
            time.sleep(1)

        # If we did have to wait for the lid to close we need to just wait a while before we tare
        if hadToWaitForClose:
            time.sleep(6)

        self.manager.clearEvent("LidSwitch.LID_CLOSED")

        # Set a lid tare event
        self.manager.setEvent("NAU7802.TARE")
        while self.manager.getEvent("NAU7802.TARE"):
            time.sleep(1.0)

        self.manager.clearAllEvents()

    """
    Handles events that need to be checked quickly in the main loop
    """
    def handleCallbacks(self):
        # Check the state of the LidSwitch
        if self.manager.getEvent("LidSwitch.LID_CLOSED") and self.is_initialized:
            print("Lid closed event")
            time.sleep(0.25)
            self.collectData(triggeredByLid=True)

            # After the last sample is done being collected we want to get the current weight
            self.startingWeight = self.manager.getData()["NAU7802"]["data"][
                "weight"
            ].value
            self.manager.clearEvent("LidSwitch.LID_CLOSED")
        
        # If at any point we have lost our WiFi connection we want to tell the user that
        if self.manager.getEvent("BluetoothDriver.LOST_WIFI_CONNECTION") and not self.isMuted:
            self.manager.setEvent("SoundController.NO_WIFI")
            self.manager.clearEvent("BluetoothDriver.LOST_WIFI_CONNECTION")

        # If at any point we have lost our WiFi connection we want to tell the user that
        if self.manager.getEvent("BluetoothDriver.GOT_WIFI_CONNECTION") and not self.isMuted:
            self.manager.setEvent("SoundController.CONNECTED_TO_WIFI")
            self.manager.clearEvent("BluetoothDriver.GOT_WIFI_CONNECTION")

        if self.manager.getEvent("BluetoothDriver.BLUETOOTH_STOPPED") and not self.isMuted:
            self.manager.setEvent("SoundController.BLUETOOTH_STOPPED")
            self.manager.clearEvent("BluetoothDriver.BLUETOOTH_STOPPED")

        # If our bluetooth driver is requesting a mute than we want to check the last muted state to see if we should play the audio
        if bool(self.manager.getData()["BluetoothDriver"]["data"]["muted"].value) and not self.isMuted:
            self.manager.setEvent("SoundController.MUTED")
            self.isMuted = True
            self.updateConfig()
        elif not bool(self.manager.getData()["BluetoothDriver"]["data"]["muted"].value) and self.isMuted:
            self.manager.setEvent("SoundController.UNMUTED")
            self.isMuted = False
            self.updateConfig()

    """
    Collect a sample from all of the sensors on the device

    :param triggeredByLid: Whether or not our current sample was triggered by the lid opening or just the "cron job"
    """

    def collectData(self, triggeredByLid=True) -> bool:
        
        # When collect data is called we want to set the trigger type
        data = self.manager.getData()
        fileNames = {}
        data["DriverManager"]["data"]["userTrigger"] = triggeredByLid

        # Start recording the user annotation
        self.manager.setEvent("SoundController.RECORD")

        # We want to tell the "cameras" we would like to capture the latest frames
        # Delay the camera capture for a moment.
        self.manager.setEvent("LEDDriver.CAMERA")
        time.sleep(0.4)
        self.manager.setEvent("Realsense.CAPTURE")
        self.manager.setEvent("MLX90640.CAPTURE")

        # While the capture events are still set we should just wait until they are cleared meaning they succeeded
        while self.manager.getEvent("Realsense.CAPTURE") or self.manager.getEvent("MLX90640.CAPTURE") or self.manager.getEvent("SoundController.RECORD"):
            time.sleep(0.2)

        # Grab dictionaries of the file paths generated from the Realsense module and the MLX90640 module and microphone
        fileNames.update(self.soundControllerConnection.recv())
        fileNames.update(self.realsenseControllerConenction.recv())
        fileNames.update(self.mlxControllerConenction.recv())

        # Set the light to yellow before recording the
        self.manager.setEvent("LEDDriver.PROCESSING")

        

        # Add the most recent batch of data to the transcription and publishing queue
        

        self.manager.setEvent("SoundController.STOP_RECORDING")

        # Wait for debounce time for load cell
        time.sleep(6)
        data = self.manager.getData()
        data["NAU7802"]["data"]["weight_delta"].value = (
            data["NAU7802"]["data"]["weight"].value - self.startingWeight
        )
        uid = str(uuid.uuid4())
        self.publisherQueue.put((uid, fileNames, self.manager.getJSON(), False))

    """
    Shutdown device connected via the DriverManager
    """

    def kill(self):
        self.manager.kill()

    def updateConfig(self):
        with open("../data/config.json", 'w') as outFile:
            output = {"muted": self.isMuted}
            json.dump(output, outFile)
    
    def loadConfig(self):
         if os.path.exists("../data/config.json"):
            with open("../data/config.json", 'r') as inFile:
                data = json.load(inFile)
                self.isMuted = bool(data["muted"])
      

