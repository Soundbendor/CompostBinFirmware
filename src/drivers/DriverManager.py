"""
Will Richards, Oregon State University, 2023

Proccess manager for each of our subsensor proccesses
"""

import logging
from time import time, sleep
from multiprocessing.sharedctypes import Synchronized
from multiprocessing import Pipe

from drivers.DriverBase import DriverBase
from drivers.ThreadedDriver import ThreadedDriver


class DriverManager:
    """
    Create a new instance of our DriverManager to control all of the subproccess threads

    :param sensors: A list of as many sensors as we want to use on our current device
    """

    def __init__(self, *sensors: DriverBase):
        # Store a list of sensors, spawned sensor proccesses and a data dictionary to store our data
        self.sensors: list[DriverBase] = list(sensors)
        self.proccessList: list[ThreadedDriver] = []
        self.data = {}
        self.timeTriggers = {}

        logging.info("Waiting for proccesses to initialize...")

        # Loop over all sensors we are using and "threadify" them
        for sensor in self.sensors:
            # Format a new sensor objecti in the dectionary
            self._formatNewSensor(sensor)

            # Spawn the sensor into a proccess passing the data object along to be manipulated, if our procces is the async publisher we want to pass the whole data object to it
            if sensor.moduleName == "AsyncPublisher":
                sensor.data = self.data
            proccess = ThreadedDriver(sensor, self.data[sensor.moduleName]["data"])

            # Start the proccess
            proccess.start()
            logging.info(
                f"{sensor.moduleName} proccess started with pid: {proccess.pid}"
            )
            self.proccessList.append(proccess)

        # Check if all of our proccesses have been initialized
        self.allProcsInitialized = False
        startTime = time()
        while (not self.allProcsInitialized) and (startTime + 25) > time():
            allInit = True
            for proccess in self.proccessList:
                if proccess.data["initialized"].value != 1:
                    allInit = False
                    break

            if allInit:
                self.allProcsInitialized = True
                break
            sleep(0.3)

        # We know that calibration status is set during initializtion, so no need for time-delay loop
        # Verify that BME688 is calibrated
        self.isBMECalibrated = self.data["BME688"]["data"]["calibrated"].value

        # If not all initailized tell us which ones
        if not self.allProcsInitialized:
            output = "The following proccesses failed to initialize:\n"
            for proccess in self.proccessList:
                if proccess.data["initialized"].value != 1:
                    output += f"\t{proccess.driver.moduleName}\n"
            logging.error(output)
        else:
            logging.info("All proccesses initialized succssessfully")

        self.data["DriverManager"] = {}
        self.data["DriverManager"]["data"] = {}
        self.data["DriverManager"]["data"]["userTrigger"] = False
        self.data["DriverManager"]["events"] = {}

        self.createJSONFormattedDict()

    """
    Register a function to run on a given call back

    :param event: String formatted as follows to select event SENSOR.EVENT
    :param callback: Function call back to supply for a given events
    """

    def registerEventCallback(self, event: str, callback):
        try:
            splitName = event.split(".")

            # Set the call back for the specific event
            self.data[splitName[0]]["events"][splitName[1]][1] = callback
        except KeyError:
            logging.error(f"Specified event/sensor doesn't exist: {event}")

    """
    Set an event on a given sub-module

    :param event: The event we want to set in the form of ModuleName.EventName
    """

    def setEvent(self, event):
        try:
            splitName = event.split(".")
            self.data[splitName[0]]["events"][splitName[1]][0].set()
        except KeyError:
            logging.error(f"Specified event/sensor doesn't exist: {event}")

    """
    Get an event on a given sub-module

    :param event: The event we want to get in the form of ModuleName.EventName
    """

    def getEvent(self, event):
        try:
            splitName = event.split(".")
            return self.data[splitName[0]]["events"][splitName[1]][0].is_set()
        except KeyError:
            logging.error(f"Specified event/sensor doesn't exist: {event}")

    """
    Clear an event on a given sub-module

    :param event: The event we want to clear in the form of ModuleName.EventName
    """

    def clearEvent(self, event):
        try:
            splitName = event.split(".")
            return self.data[splitName[0]]["events"][splitName[1]][0].clear()
        except KeyError:
            logging.error(f"Specified event/sensor doesn't exist: {event}")

    """
    Clears all the events on every sensor
    """

    def clearAllEvents(self):
        for sensor in self.data:
            for name in self.data[sensor]["events"]:
                self.data[sensor]["events"][name][0].clear()

    """
    Check what callbacks need to be called per loop, and execute them as needed
    """

    def handleCallbacks(self):
        # Go through each sensors events and see if there is a callback set and if the event has triggered
        for sensor in self.sensors:
            for key, value in self.data[sensor.moduleName]["events"].items():
                if value[1] != None:
                    if value[0].is_set():
                        value[1](value[0])

    """
    Get the data from the manager

    :return: Dictionary of sensor data
    """

    def getData(self) -> dict:
        return self.data

    """
    Create the initial JSON dictionary so that we can just update values later
    """

    def createJSONFormattedDict(self):
        self.jsonDict = {}
        originalData = self.getData()
        for key, value in originalData.items():
            self.jsonDict[key] = {}
            # self.jsonDict[key]["data"] = originalData[key]["data"]
            self.jsonDict[key]["data"] = {}
            for dataKey, value in originalData[key]["data"].items():
                if type(value) == Synchronized:
                    self.jsonDict[key]["data"][dataKey] = value.value
                else:
                    self.jsonDict[key]["data"][dataKey] = value
            self.jsonDict[key]["events"] = {}
            for eventKey, eventValue in originalData[key]["events"].items():
                self.jsonDict[key]["events"][eventKey] = list(
                    originalData[key]["events"][eventKey]
                )
                self.jsonDict[key]["events"][eventKey][0] = self.jsonDict[key][
                    "events"
                ][eventKey][0].is_set()

                if self.jsonDict[key]["events"][eventKey][1] != None:
                    self.jsonDict[key]["events"][eventKey][1] = self.jsonDict[key][
                        "events"
                    ][eventKey][1].__name__
        return self.jsonDict

    """
    Parse our data into a JSON readable format
    """

    def getJSON(self):
        originalData = self.getData()

        # Update the data values for each sensor
        for key, _ in originalData.items():
            for dataKey, _ in self.jsonDict[key]["data"].items():
                if type(originalData[key]["data"][dataKey]) == Synchronized:
                    self.jsonDict[key]["data"][dataKey] = originalData[key]["data"][
                        dataKey
                    ].value
                else:
                    self.jsonDict[key]["data"][dataKey] = originalData[key]["data"][
                        dataKey
                    ]

        # Update the events for each sensor
        for key, _ in originalData.items():
            for eventKey, _ in self.jsonDict[key]["events"].items():
                self.jsonDict[key]["events"][eventKey][0] = originalData[key]["events"][
                    eventKey
                ][0].is_set()

                if originalData[key]["events"][eventKey][1] != None:
                    self.jsonDict[key]["events"][eventKey][1] = originalData[key][
                        "events"
                    ][eventKey][1].__name__
        return self.jsonDict

    """
    Format a new dictionary for the given sensor

    :param sensor: The sensor we are creating the dictionary for
    """

    def _formatNewSensor(self, sensor: DriverBase) -> None:
        self.data[sensor.moduleName] = {}
        self.data[sensor.moduleName]["data"] = sensor.createDataDict()
        self.data[sensor.moduleName]["events"] = sensor.getEvents()
        for key, value in self.data[sensor.moduleName]["events"].items():
            self.data[sensor.moduleName]["events"][key] = [value, None]

    """
    Main driver control loop
    """

    def loop(self):
        self.handleCallbacks()

    """
    Shutdown the manager killing all running proccess
    """

    def kill(self):
        for proc in self.proccessList:
            proc.kill()
