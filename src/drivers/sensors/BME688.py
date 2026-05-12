""" "
Will Richards, Oregon State University, 2023

Abstraction layer for the BME688 gas sensor
"""

import logging
from time import time, sleep
import os

from bme68x import BME68X
import bsecConstants as bsec

from drivers.DriverBase import DriverBase
from multiprocessing import Event, Value


class BME688(DriverBase):
    """
    Basic constructor for the BME688

    :param i2c_address: The given I2C address this device is registered with
    """

    def __init__(self, i2c_address=0x77):
        super().__init__("BME688")

        self.i2c_address = i2c_address
        self.sensor = None
        self.failedToInit = False

        # Set this process to loop once a second
        self.setLoopTime(1)

        # When the device is restarted we want to clear the last savedState
        if os.path.exists("savedState.dat"):
            os.remove("savedState.dat")

        self.startTime = time()

    """
    Initialize the BME688 to begin taking sensor readings
    """

    def initialize(self):
        try:
            # i2c_bus = 1 is standard for Raspberry Pi main I2C bus
            self.sensor = BME68X(self.i2c_address, 1)
            self.sensor.set_heatr_conf(1, 320, 100, 1)
            self.sensor.set_sample_rate(bsec.BSEC_SAMPLE_RATE_LP)

            logging.info("Initialization complete!")
            self.initialized = True
            self.data["initialized"].value = 1
        except Exception as e:
            logging.error(f"An error occured intializing BME688: {e}")
            self.failedToInit = True
            self.initialized = False
            self.data["initialized"].value = 0

    """
    Measure and store the readings from the BME688.
    Now uses bme68x library with BSEC 2.0 to calculate IAQ, sIAQ, CO2-eq, and bVOC-eq.
    """

    def measure(self):
        if self.sensor is None or self.failedToInit:
            return

        try:
            bsec_data = self.sensor.get_bsec_data()
            if bsec_data is None or bsec_data == {}:
                # The sensor may not have data ready immediately
                return

            self.data["temperature(c)"].value = bsec_data.get("temperature", 0.0)

            # raw_pressure is returned in Pa, converting to kPa
            self.data["pressure(kpa)"].value = (
                bsec_data.get("raw_pressure", 0.0) / 1000.0
            )

            self.data["humidity(%rh)"].value = bsec_data.get("humidity", 0.0)

            # Measure gas resistance
            self.data["gas_resistance(ohms)"].value = bsec_data.get("raw_gas", 0.0)

            # BSEC metrics
            self.data["iaq"].value = bsec_data.get("iaq", 0.0)
            self.data["sIAQ"].value = bsec_data.get("static_iaq", 0.0)
            self.data["CO2-eq"].value = bsec_data.get("co2_equivalent", 0.0)
            self.data["bVOC-eq"].value = bsec_data.get("breath_voc_equivalent", 0.0)

        except Exception as e:
            logging.error(
                f"The following error occured while attempting to read data: {e}"
            )

    """
    Create a dictionary of the data that this sensor will output
    """

    def createDataDict(self):
        self.data = {
            "temperature(c)": Value("d", 0.0),
            "pressure(kpa)": Value("d", 0.0),
            "humidity(%rh)": Value("d", 0.0),
            "gas_resistance(ohms)": Value("d", 0.0),
            "iaq": Value("d", 0.0),
            "sIAQ": Value("d", 0.0),
            "CO2-eq": Value("d", 0.0),
            "bVOC-eq": Value("d", 0.0),
            "initialized": Value("i", 0),
        }
        return self.data

    """
    Shutdown the process
    """

    def kill(self):
        self.sensor = None
