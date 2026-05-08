""""
Will Richards, Oregon State University, 2023

Abstraction layer for the NAU7802 to allow us to add stablitiy improvements if needed
"""

import PyNAU7802
import smbus2
import logging
import time

from drivers.DriverBase import DriverBase
from multiprocessing import Event, Value

class NAU7802(DriverBase):

    """
    Basic constructor for the NAU7802

    :param calibration_factor: Pre-calculated calibration factor to get valid weight readings
    """
    def __init__(self, calibration_factor = 0):
        super().__init__("NAU7802")

        self.nau = None
        self.collectedData = 0
        
        if(calibration_factor == 0):
            logging.warning("No calibration factor entered!")


        self.calFactor = calibration_factor

        # How much additional weight will trigger a weight change event
        self.WEIGHT_THRESHOLD = 1.5
        self.weightDetectedLastTime = 0

        # List of events that the sensor can raise
        self.events = {
            "WEIGHT_CHANGE": Event(),
            "CALIBRATE": Event(),
            "TARE": Event()
        }

        

    """
    Initialize the NAU7802 to begin taking sensor readings, DOES NOT TARE
    """
    def initialize(self):
        self.nau = PyNAU7802.NAU7802()
        i2cBus = smbus2.SMBus(1)
        if self.nau.begin(i2cBus):
            logging.info("Connected to NAU7802!")
        else:
            logging.error("Failed to connect to NAU7802")
            return False

        
        self.nau.setSampleRate(PyNAU7802.NAU7802_SPS_40)
        self.nau.setGain(PyNAU7802.NAU7802_GAIN_16)
        self.nau.setLDO(PyNAU7802.NAU7802_LDO_4V5)
        self.nau.calibrateAFE()

        self.nau.setCalibrationFactor(self.calFactor)
        self.initialized = True
        self.data["initialized"].value = 1

    """
    Measure and return the weight read from the load cell
    """
    def measure(self):
        if self.nau is None:
            return

        if self.getEvent("CALIBRATE").is_set():
            self.calibrate()
            self.getEvent("CALIBRATE").clear()
        elif self.getEvent("TARE").is_set():
            self.tareScale()
            self.getEvent("TARE").clear()
        else:
            logging.debug("Measuring...")
            self.lastWeight = self.collectedData

            #Average 100 samples to get a fairly accurate reading
            data = []
            for i in range(4):
                data.append(self.nau.getWeight(True, 25))
            
            self.collectedData = sum(data)/len(data)
            data.clear()

            # This will determine wether or not the event has occured in this cycle or not
            #self.determineEventState()
            self.data["weight"].value = self.collectedData
        


    """
    Calibrate the load cell with a known weight
    """
    def calibrate(self):
        # Tare the scale again in case any weight was on it during initialize
        logging.info("Remove any weight present on the scale. You have 10 seconds...")
        time.sleep(10)
        self.tareScale()

        # Prompt the user for the mass of a known object in grams
        mass = 100
        logging.info("Waiting 10 seconds for weight to be put on scale")
        time.sleep(10)

        # Calibrate the scale using the known mass
        self.nau.calculateCalibrationFactor(mass)

        print(f"Calibration Factor: {self.nau.getCalibrationFactor()}")
    
    """
    Tare the values of the load cell
    """
    def tareScale(self):
        logging.info("Taring scale...")
        self.nau.calculateZeroOffset()
    
    """
    Determine wether or not the events on this object should be triggered on this measure cycle
    """
    def determineEventState(self) -> None:
         # If the absolute value of the current weight - the last is greater than the threshold trigger the event, we also don't want to trigger twice in a row
        if(abs(self.collectedData - self.lastWeight) > self.WEIGHT_THRESHOLD and not self.weightDetectedLastTime) :
            self.getEvent("WEIGHT_CHANGE").set()
            self.weightDetectedLastTime = True
        # If our weight didn't change and our weight changed last time then we want to clear this flag so we can trigger another event on the next cycle
        elif(self.weightDetectedLastTime):
            self.weightDetectedLastTime = False
    
    """
    Add the weight pramameter to the NAU's data field
    """
    def createDataDict(self):
        self.data = {
            "weight": Value('d', 0.0),
            "weight_delta": Value('d', 0.0),
            "initialized": Value('i', 0)
        }
        return self.data