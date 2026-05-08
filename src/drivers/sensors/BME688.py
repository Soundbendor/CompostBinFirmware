""""
Will Richards, Oregon State University, 2023

Abstraction layer for the BME688 gas sensor
"""

import board
import adafruit_bme680

import logging
from time import  time
import os


from drivers.DriverBase import DriverBase
from multiprocessing import Event, Value

class BME688(DriverBase):

    """
    Basic constructor for the BME688

    :param i2c_address: The given I2C address this device is registered with
    """
    def __init__(self, i2c_address = 0x77):
        super().__init__("BME688")

        self.i2c_address = i2c_address
        self.sensor = None
        self.failedToInit = False

        # Set this proccess to loop once a second
        self.setLoopTime(1)

        # When the device is restarted we want to clear the last savedState
        if(os.path.exists("savedState.dat")):
            os.remove("savedState.dat")

        self.startTime = time()


    """
    Initialize the BME688 to begin taking sensor readings
    """
    def initialize(self):
        try:
            i2c = board.I2C()
            self.sensor = adafruit_bme680.Adafruit_BME680_I2C(i2c, address=self.i2c_address)
            
            # Set oversampling amounts
            self.sensor.temperature_oversample = 8
            self.sensor.humidity_oversample = 2
            self.sensor.pressure_oversample = 4
            
            # Set IIR Filter size
            self.sensor.filter_size = 3
            
            # Set heater temperature and duration
            self.sensor.set_gas_heater(320, 150)
            
            logging.info("Initialization complete!")
            self.initialized = True
            self.data["initialized"].value = 1
        except Exception as e:
            logging.error(f"An error occured intializing BME680: {e}")
            self.failedToInit = True
            self.initialized = False
            self.data["initialized"].value = 0
       

    """
    Measure and store the readings from the BME688.
    Note: IAQ, sIAQ, CO2-eq, and bVOC-eq are no longer calculated as BSEC has been removed.
    """
    def measure(self):
        if self.sensor is None or self.failedToInit:
            return

        try:
            self.data["temperature(c)"].value = self.sensor.temperature
            self.data["pressure(kpa)"].value = self.sensor.pressure * 0.1  # Convert hPa to kPa
            self.data["humidity(%rh)"].value = self.sensor.relative_humidity

            # Measure gas resistance
            gas_res = self.sensor.gas
            if gas_res is not None:
                self.data["gas_resistance(ohms)"].value = gas_res
            else:
                logging.warning("Gas data was not ready to collect at this time")

            # BSEC metrics are no longer available
            self.data["iaq"].value = 0.0
            self.data["sIAQ"].value = 0.0
            self.data["CO2-eq"].value = 0.0
            self.data["bVOC-eq"].value = 0.0
                
        except Exception as e:
            logging.error(f"The following error occured while attempting to read data: {e}")
        
    
    """
    Create a dictionary of the data that this sensor will output
    """
    def createDataDict(self):
        self.data = {
            "temperature(c)": Value('d', 0.0),
            "pressure(kpa)": Value('d', 0.0),
            "humidity(%rh)": Value('d', 0.0),
            "gas_resistance(ohms)": Value('d', 0.0),
            "iaq": Value('d', 0.0),
            "sIAQ": Value('d', 0.0),
            "CO2-eq": Value('d', 0.0),
            "bVOC-eq": Value('d', 0.0),
            "initialized": Value('i', 0)
        }
        return self.data
    
    """
    Shutdown the process
    """
    def kill(self):
        self.sensor = None

