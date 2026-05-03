""""
Will Richards, Oregon State University, 2023

Abstraction layer for the BME688 gas sensor
"""

import bme680

import logging
from time import  time
import os
from ctypes import *


from drivers.DriverBase import DriverBase
from multiprocessing import Event, Value

class BME688(DriverBase):

    """
    Basic constructor for the BME688

    :param i2c_address: The given I2C address this device is registered with
    """
    def __init__(self, i2c_address = 0x77):
        super().__init__("BME688")

        self.failedToInit = False
        try:
            self.sensor = bme680.BME680(i2c_address)
        except RuntimeError as e:
            logging.error(f"An error occured intializing BME680: {e}")
            self.failedToInit = True

        script_dir = os.path.abspath(os.path.dirname(__file__))
        lib_path = os.path.join(script_dir, "bsec_python.so")
        self.functions = cdll.LoadLibrary(lib_path)
        self.functions.proccess_bme_data.argtypes = [c_int, c_float, c_float, c_float, c_float, POINTER(c_float)]
        self.functions.proccess_bme_data.restype = c_int

        # Set this proccess to loop once every 3 seconds to match BSEC Low Power mode
        self.setLoopTime(3)

        self.startTime = time()


    """
    Initialize the BME688 to begin taking sensor readings
    """
    def initialize(self):
        if not self.failedToInit:
            # Set oversampling amounts
            self.sensor.set_humidity_oversample(bme680.OS_2X)
            self.sensor.set_pressure_oversample(bme680.OS_4X)
            self.sensor.set_temperature_oversample(bme680.OS_8X)

            # Set IIR Filter size and whether or not we should be measuring gas
            self.sensor.set_filter(bme680.FILTER_SIZE_3)
            self.sensor.set_gas_status(bme680.ENABLE_GAS_MEAS)

            # Set heater temperature and duration and finally select the profile
            self.sensor.set_gas_heater_temperature(320)
            self.sensor.set_gas_heater_duration(150)
            self.sensor.select_gas_heater_profile(0)
            logging.info("Initialization complete!")
            self.initialized = True
            self.data["initialized"].value = 1
        else:
            logging.error("Failed to initialize sensor!")
            self.initialized = False
            self.data["initialized"].value = 0
       

    """
    Measure and store the readigns from the BME688 passing the gas resistance values through the Bosch BSEC library to compute equivelent CO2 and bVOC
    """
    def measure(self):
        try:
            if(self.sensor.get_sensor_data()):
                ts = int(time()-self.startTime)
                self.data["temperature(c)"].value = self.sensor.data.temperature
                self.data["pressure(kpa)"].value = self.sensor.data.pressure * 0.1  # Convert hectopascals to kilopascals
                self.data["humidity(%rh)"].value = self.sensor.data.humidity

                # Only measure the gas if the measurement is ready
                if(self.sensor.data.heat_stable):
                    self.data["gas_resistance(ohms)"].value = self.sensor.data.gas_resistance
                else:
                    logging.warning("Gas data was not ready to collect at this time the last value will be returned in place")

                # BSEC expects pressure in Pa (Pascals). self.sensor.data.pressure is in hPa (hectopascals).
                pressure_pa = self.sensor.data.pressure * 100.0

                # Call our BSEC library to give us additional data
                arr = [0, 0, 0, 0, 0, 0, 0]
                arr_c = (c_float * 7)(*arr)
                ret = self.functions.proccess_bme_data(c_int(ts), c_float(self.sensor.data.temperature), c_float(pressure_pa), c_float(self.sensor.data.humidity), c_float(self.sensor.data.gas_resistance), arr_c) 
                
                if ret != 0:
                    logging.error(f"BSEC proccess_bme_data returned error code: {ret}")

                self.data["iaq"].value = arr_c[0]
                self.data["iaq_accuracy"].value = arr_c[1]
                self.data["sIAQ"].value = arr_c[4]
                self.data["CO2-eq"].value = arr_c[5]
                self.data["bVOC-eq"].value = arr_c[6]
                
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
            "iaq_accuracy": Value('d', 0.0),
            "sIAQ": Value('d', 0.0),
            "CO2-eq": Value('d', 0.0),
            "bVOC-eq": Value('d', 0.0),
            "initialized": Value('i', 0)
        }
        return self.data
    
    """
    Shutdown the proccess
    """
    def kill(self):
        self.sensor._i2c.close()
        
