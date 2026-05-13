"""
Abstraction layer for the BME688 gas sensor
"""

import logging
import threading
from time import time, sleep
from pathlib import Path

from bme68x import BME68X
import bme68xConstants as bme_cnst
import bsecConstants as bsec

from drivers.DriverBase import DriverBase
from multiprocessing import Value, Event


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
        self.sample_rate = bsec.BSEC_SAMPLE_RATE_LP
        self.heater_status = bme_cnst.BME68X_ENABLE
        self.parallel_mode = bme_cnst.BME68X_PARALLEL_MODE
        self.temp_prof = [320, 100, 100, 100, 200, 200, 200, 320, 320, 320]
        self.dur_prof = [5, 2, 10, 30, 5, 5, 5, 5, 5, 5]
        # TODO: Determine
        self.calibration_file = "conf/bme688_state.txt"
        self.events = {"CALIBRATE": Event(), "STOP_CALIBRATION": Event()}

        # Threading and calibration state
        self.sensor_lock = None
        self.is_calibrating = False
        self.calibration_thread = None

        # Set this process to loop once a second
        self.setLoopTime(1)

        self.startTime = time()

    """
    Initialize the BME688 to begin taking sensor readings
    """

    def initialize(self):
        try:
            self.sensor_lock = threading.Lock()
            # i2c_bus = 1 is standard for Raspberry Pi main I2C bus
            self.sensor = BME68X(self.i2c_address, 1)
            self.sensor.set_heatr_conf(
                self.heater_status, self.temp_prof, self.dur_prof, self.parallel_mode
            )
            # read config file
            state_int = self._readState(self.calibration_file)
            # If calibration file does not exist:
            if not state_int:
                logging.error("BME688 is missing calibration curve")
                self.data["calibrated"].value = 0
            else:
                self.sensor.set_bsec_state(state_int)
                self.data["calibrated"].value = 1
            self.sensor.set_sample_rate(self.sample_rate)

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

        self.handleEvents()

        try:
            with self.sensor_lock:
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
            self.data["iaq_accuracy"].value = bsec_data.get("iaq_accuracy", 0)
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
            "iaq_accuracy": Value("i", 0),
            "sIAQ": Value("d", 0.0),
            "CO2-eq": Value("d", 0.0),
            "bVOC-eq": Value("d", 0.0),
            "initialized": Value("i", 0),
            "calibrated": Value("i", 1),
        }
        return self.data

    def handleEvents(self):
        if self.getEvent("CALIBRATE").is_set():
            if not self.is_calibrating:
                logging.info("Calibration event triggered. Starting background thread.")
                self.is_calibrating = True
                self.calibration_thread = threading.Thread(
                    target=self._run_calibration_thread, daemon=True
                )
                self.calibration_thread.start()
            self.getEvent("CALIBRATE").clear()

        if self.getEvent("STOP_CALIBRATION").is_set():
            if self.is_calibrating:
                logging.info("Stop calibration event triggered. Interrupting thread.")
                self.is_calibrating = False
            self.getEvent("STOP_CALIBRATION").clear()

    def _run_calibration_thread(self):
        """
        Background thread that runs for 24 hours, polls data, and saves state.
        """
        start_time = time()
        duration = 24 * 3600  # 24 hours
        log_interval = 60  # Log data every minute
        last_log = 0

        logging.info("BME688 Calibration thread started.")

        try:
            # 1: Run 24hr data collection loop
            while self.is_calibrating:
                elapsed = time() - start_time
                with self.sensor_lock:
                    state = self.sensor.get_bsec_state()
                    while state is None:
                        state = self.sensor.get_bsec_state()

                accuracy = state.get("iaq_accuracy", 0)
                iaq = state.get("iaq", 0)

                # Termination condition: 24h passed AND accuracy is 3
                if elapsed >= duration and accuracy >= 3:
                    logging.info(
                        "24h Calibration period complete. Saving sensor state."
                    )
                    break

                if time() - last_log > log_interval:
                    logging.info(
                        f"Calibration in progress: {int(elapsed)}s elapsed. IAQ: {iaq}, Accuracy: {accuracy}"
                    )
                    last_log = time()

                sleep(1)

            # 2: Save state file
            if self.is_calibrating:
                logging.info("24h Calibration period complete. Saving sensor state.")
                with self.sensor_lock:
                    state = self.sensor.get_bsec_state()
                    # Saving state to file
                    state_path = (
                        Path(__file__).resolve().parent.joinpath(self.calibration_file)
                    )
                    state_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(state_path, "w") as f:
                        f.write(str(state))

                self.data["calibrated"].value = 1
                logging.info(f"Calibration curve saved to {state_path}")
            else:
                logging.info("Calibration interrupted by user.")

        except Exception as e:
            logging.error(f"Error during calibration thread: {e}")
        finally:
            self.is_calibrating = False
            self.calibration_thread = None

    """
    Shutdown the process
    """

    def kill(self):
        self.sensor = None

    """
    Read the calibration curve for the BME688 sensor
    This calibration curve should be generated during bin calibration
    """

    def _readState(self, state_file_name: str) -> list[int] | None:
        state_path = Path(__file__).resolve().parent.joinpath("conf", state_file_name)

        if state_path.is_file():
            state_file = open(str(state_path), "r")
            # strip the brackets [.....]
            state_str = state_file.read()[1:-1]
            # split on delimiter ,
            state_list = state_str.split(",")
            state_int = [int(x) for x in state_list]
            return state_int
        else:
            # Failed to load calibration curve
            return None
