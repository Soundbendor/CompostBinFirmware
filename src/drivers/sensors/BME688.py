"""
Abstraction layer for the BME688 gas sensor
"""

import logging
import os
import threading
from time import time
from pathlib import Path

from bme68x import BME68X
import bme68xConstants as bme_cnst
import bsecConstants as bsec

from drivers.DriverBase import DriverBase
from drivers.BalenaTagReporter import (
    STATE_CALIBRATED,
    STATE_CALIBRATING,
    STATE_UNHEALTHY,
    BalenaTagReporter,
)
from multiprocessing import Value, Event

# BSEC_OK from the vendored bsec_datatypes.h
BSEC_OK = 0
# BSEC_MAX_STATE_BLOB_SIZE of the bsec_IAQ_Sel algo built by the Docker image.
BSEC_STATE_BLOB_LENGTH = 238


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
        self.calibration_file = "bme688_state.txt"
        self.debug_mode = self._readDebugMode()
        self.events = {"CALIBRATE": Event(), "STOP_CALIBRATION": Event()}

        # Threading and calibration state.
        # The thread primitives are built in initialize(), which runs in the
        # child process: DriverManager pickles this instance to start its
        # process, and threading primitives cannot cross a process boundary.
        self.sensor_lock = None
        self.calibration_lock = None
        self.calibration_wakeup = None
        self.is_calibrating = False
        self.calibration_thread = None
        self.calibration_generation = 0

        # Calibration truth, kept out of the shared sensor dictionary so scan
        # payloads are unchanged.
        self.has_valid_calibration = False

        # Created during initialize(), inside the driver process, because it
        # owns a worker thread and an SDK client.
        self.tag_reporter = None

        # Set this process to loop once a second
        self.setLoopTime(1)

        self.startTime = time()

    """
    Read the BME688 extension's debug flag from
    the environment. "1" enables debug output.
    """

    def _readDebugMode(self) -> int:
        return 1 if os.environ.get("BME688_DEBUG_MODE") == "1" else 0

    """
    Initialize the BME688 to begin taking sensor readings, then publish the
    resulting calibration tag.
    """

    def initialize(self):
        self.tag_reporter = self._createReporter()
        self.has_valid_calibration = False

        try:
            self.sensor_lock = threading.Lock()
            self.calibration_lock = threading.Lock()
            self.calibration_wakeup = threading.Event()
            self.sensor = BME68X(self.i2c_address, self.debug_mode)
            # self.sensor.set_heatr_conf(
            #     self.heater_status, self.temp_prof, self.dur_prof, self.parallel_mode
            # )

            # read config file
            state_int = self._readState(self.calibration_file)
            self.data["calibrated"].value = 1 if self._applyState(state_int) else 0

            if not self._configureSampleRate():
                raise RuntimeError("BSEC rejected the configured sample rate")

            logging.info("Initialization complete!")
            self.initialized = True
            self.data["initialized"].value = 1
            self._reportState(
                STATE_CALIBRATED if self.has_valid_calibration else STATE_UNHEALTHY
            )
        except Exception as e:
            logging.error(f"An error occured intializing BME688: {e}")
            self.failedToInit = True
            self.initialized = False
            self.has_valid_calibration = False
            self.data["initialized"].value = 0
            self.data["calibrated"].value = 0
            self._reportState(STATE_UNHEALTHY)

    """
    Measure and store the readings from the BME688.
    Now uses bme68x library with BSEC 2.0 to calculate IAQ, sIAQ, CO2-eq, and bVOC-eq.
    """

    def measure(self):
        # Always check events, even if sensor isn't ready,
        # but the handler must be safe.
        self.handleEvents()

        if self.sensor is None or self.failedToInit:
            return

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
            "calibrated": Value("i", 0),
        }
        return self.data

    """
    Build the openBalena device-tag reporter. It owns a worker thread and an SDK
    client, so it is created here rather than in the constructor.
    """

    def _createReporter(self) -> BalenaTagReporter | None:
        return BalenaTagReporter.from_environment()

    """
    Publish a calibration tag value. Reporting failures stay inside the
    reporter, so a tag problem never interrupts measurement or calibration.
    """

    def _reportState(self, state: str) -> None:
        reporter = self.tag_reporter
        if reporter is None:
            return

        try:
            reporter.set_state(state)
        except Exception as e:
            logging.error(
                f"Unexpected error while reporting calibration state: {type(e).__name__}"
            )

    """
    Report the outcome of one calibration run unless a newer run already owns
    the calibration state.
    """

    def _reportCalibrationOutcome(self, generation: int, saved: bool) -> None:
        with self.calibration_lock:
            if generation != self.calibration_generation:
                return
            healthy = saved or self.has_valid_calibration

        self._reportState(STATE_CALIBRATED if healthy else STATE_UNHEALTHY)

    """
    True while this run is still the one that owns calibration state.
    """

    def _ownsCalibration(self, generation: int) -> bool:
        with self.calibration_lock:
            return generation == self.calibration_generation

    def handleEvents(self):
        calibrate_event = self.getEvent("CALIBRATE")
        if calibrate_event.is_set():
            logging.info("CALIBRATE event is SET.")
            if not self.initialized or self.sensor is None or self.failedToInit:
                logging.error("Cannot calibrate: Sensor is not initialized.")
            elif self.is_calibrating or self._calibrationWorkerActive():
                logging.info("Calibration already running. Ignoring duplicate request.")
            else:
                logging.info("Starting background calibration thread.")
                self.calibration_wakeup.clear()
                with self.calibration_lock:
                    self.calibration_generation += 1
                    generation = self.calibration_generation
                    self.is_calibrating = True
                    self.calibration_thread = threading.Thread(
                        target=self._run_calibration_thread,
                        args=(generation,),
                        daemon=True,
                    )
                    self.calibration_thread.start()
                self._reportState(STATE_CALIBRATING)
            calibrate_event.clear()

        if self.getEvent("STOP_CALIBRATION").is_set():
            logging.info("STOP_CALIBRATION event is SET.")
            if self.is_calibrating:
                logging.info("Interrupting calibration thread.")
                self.is_calibrating = False
                # Wake the worker even while it waits for sensor data.
                self.calibration_wakeup.set()
            self.getEvent("STOP_CALIBRATION").clear()

    def _calibrationWorkerActive(self) -> bool:
        thread = self.calibration_thread
        return thread is not None and thread.is_alive()

    """
    Hand the saved calibration curve to the native extension. The file is left
    untouched on failure so it stays available for diagnosis.
    """

    def _applyState(self, state_int: list[int] | None) -> bool:
        if not state_int:
            logging.error("BME688 is missing calibration curve")
            return False

        if len(state_int) != BSEC_STATE_BLOB_LENGTH:
            logging.error(
                "BME688 calibration curve holds %d bytes, expected %d. Keeping the file.",
                len(state_int),
                BSEC_STATE_BLOB_LENGTH,
            )
            return False

        if not all(isinstance(value, int) and 0 <= value <= 255 for value in state_int):
            logging.error(
                "BME688 calibration curve holds non-byte values. Keeping the file."
            )
            return False

        try:
            result = self.sensor.set_bsec_state(state_int)
        except Exception as e:
            logging.error(f"BME688 rejected the saved calibration curve: {e}")
            return False

        if result != BSEC_OK:
            logging.error(
                "BME688 rejected the saved calibration curve: native status %s",
                result,
            )
            return False

        self.has_valid_calibration = True
        return True

    """
    Configure the BSEC sample rate, returning False when the native extension
    rejects it.
    """

    def _configureSampleRate(self) -> bool:
        try:
            result = self.sensor.set_sample_rate(self.sample_rate)
        except Exception as e:
            logging.error(f"BME688 sample rate configuration failed: {e}")
            return False

        if result != BSEC_OK:
            logging.error(
                "BME688 sample rate configuration failed: native status %s", result
            )
            return False

        return True

    """
    Background thread that runs for 24 hours, polls data, and saves state.
    """

    def _run_calibration_thread(self, generation: int):
        start_time = time()
        duration = 24 * 3600  # 24 hours
        log_interval = 60  # Log data every minute
        last_log = 0

        logging.info("BME688 Calibration thread started.")

        try:
            # 1: Run 24hr data collection loop
            while self.is_calibrating:
                state = None
                while state is None and self.is_calibrating:
                    with self.sensor_lock:
                        state = self.sensor.get_bsec_data()
                    if not state:
                        # allow the thread to sleep, release the lock on bme688
                        self.calibration_wakeup.wait(1)

                if state is None:
                    break

                elapsed = time() - start_time
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

                self.calibration_wakeup.wait(1)

            if not self.is_calibrating:
                logging.info("Calibration interrupted by user.")
                self._reportCalibrationOutcome(generation, saved=False)
                return

            # 2: Save state file
            if not self._ownsCalibration(generation):
                logging.info("Calibration superseded by a newer run. Not saving.")
                return

            with self.sensor_lock:
                state_int = self.sensor.get_bsec_state()

            saved = self._saveState(state_int)
            if saved:
                self.data["calibrated"].value = 1
            self._reportCalibrationOutcome(generation, saved=saved)

        except Exception as e:
            logging.error(f"Error during calibration thread: {e}")
            self._reportCalibrationOutcome(generation, saved=False)
        finally:
            with self.calibration_lock:
                if generation == self.calibration_generation:
                    self.is_calibrating = False
                    self.calibration_thread = None

    """
    Shutdown the process
    """

    def kill(self):
        reporter = self.tag_reporter
        self.tag_reporter = None
        self.sensor = None

        if reporter is not None:
            try:
                reporter.close()
            except Exception as e:
                logging.error(f"Calibration state reporter did not shut down: {e}")

    """
    Read the calibration curve for the BME688 sensor
    This calibration curve should be generated during bin calibration
    """

    def _get_state_path(self, state_file_name: str) -> Path:
        return Path("/firmware/data").joinpath(state_file_name)

    def _readState(self, state_file_name: str) -> list[int] | None:
        state_path = self._get_state_path(state_file_name)

        if not state_path.is_file():
            # Failed to load calibration curve
            return None

        try:
            with open(str(state_path), "r") as state_file:
                # strip the brackets [.....]
                state_str = state_file.read().strip()[1:-1]
                # split on delimiter ,
                state_list = state_str.split(",")
                return [int(x) for x in state_list]
        except (OSError, ValueError) as e:
            # Keep the file for diagnosis and treat the sensor as uncalibrated.
            logging.error(f"BME688 calibration curve is unreadable: {e}")
            return None

    """
    Persist a completed calibration curve through a temporary file and an
    atomic replace, keeping the previous valid curve when the write fails.
    """

    def _saveState(self, state_int: list[int]) -> bool:
        state_path = self._get_state_path(self.calibration_file)

        if (
            not isinstance(state_int, (list, tuple))
            or len(state_int) != BSEC_STATE_BLOB_LENGTH
        ):
            logging.error("BSEC returned an unexpected calibration curve. Not saving.")
            return False

        temp_path = state_path.with_name(f"{state_path.name}.{os.getpid()}.tmp")

        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(temp_path, "w") as state_file:
                state_file.write(str(list(state_int)))
            os.replace(temp_path, state_path)
        except Exception as e:
            logging.error(f"Failed to save the BME688 calibration curve: {e}")
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            return False

        self.has_valid_calibration = True
        logging.info(f"Calibration curve saved to {state_path}")
        return True
