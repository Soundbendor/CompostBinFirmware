"""
Unit test for the BME688 sensor module. The vendored BSEC extension is not
available on a workstation, so it is replaced by a fake that records how the
driver constructed it. All values are synthetic.
"""

import sys
import threading
import time
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

import pytest

from drivers.BalenaTagReporter import (
    STATE_CALIBRATED,
    STATE_CALIBRATING,
    STATE_UNHEALTHY,
)

CALIBRATION_SECONDS = 24 * 3600

SYNTHETIC_READING = {
    "temperature": 19.61,
    "raw_pressure": 102096.0,
    "humidity": 46.77,
    "raw_gas": 25376.685,
    "iaq": 25.0,
    "iaq_accuracy": 3,
    "static_iaq": 25.0,
    "co2_equivalent": 500.0,
    "breath_voc_equivalent": 0.5,
}


class FakeBME68X:
    """
    Fake BSEC extension. Imitates bme68x.BME68X.
    """

    instances = []

    def __init__(self, i2c_address, debug_mode):
        self.i2c_address = i2c_address
        self.debug_mode = debug_mode
        self.set_bsec_state_calls = []
        self.set_sample_rate_calls = []
        self.get_bsec_state_calls = 0
        # Overridable behaviour for failure-path tests.
        self.set_bsec_state_result = BSEC_OK
        self.set_sample_rate_result = BSEC_OK
        self.set_bsec_state_error = None
        self.bsec_data = dict(SYNTHETIC_READING)
        FakeBME68X.instances.append(self)

    def set_bsec_state(self, state):
        self.set_bsec_state_calls.append(state)
        if self.set_bsec_state_error is not None:
            raise self.set_bsec_state_error
        return self.set_bsec_state_result

    def set_sample_rate(self, sample_rate):
        self.set_sample_rate_calls.append(sample_rate)
        return self.set_sample_rate_result

    def get_bsec_state(self):
        self.get_bsec_state_calls += 1
        return list(SYNTHETIC_STATE)

    def get_bsec_data(self):
        return self.bsec_data


def install_native_stubs():
    """
    The driver imports the compiled extension at module scope. Register fakes
    for it and its constant modules before the driver is imported.
    """
    FakeBME68X.instances = []
    stubs = {
        "bme68x": ModuleType("bme68x"),
        "bme68xConstants": ModuleType("bme68xConstants"),
        "bsecConstants": ModuleType("bsecConstants"),
    }
    stubs["bme68x"].BME68X = FakeBME68X
    stubs["bme68xConstants"].BME68X_ENABLE = 1
    stubs["bme68xConstants"].BME68X_PARALLEL_MODE = 1
    stubs["bsecConstants"].BSEC_SAMPLE_RATE_LP = 0.5
    patcher = patch.dict(sys.modules, stubs)
    patcher.start()
    return patcher


patcher = install_native_stubs()
from drivers.sensors.BME688 import (  # noqa: E402
    BSEC_OK,
    BSEC_STATE_BLOB_LENGTH,
    BME688,
)

# A synthetic curve of the size the vendored BSEC blob requires.
SYNTHETIC_STATE = [index % 256 for index in range(BSEC_STATE_BLOB_LENGTH)]


class RecordingReporter:
    """
    Stands in for BalenaTagReporter and records every requested state.
    """

    instances = []

    def __init__(self):
        self.states = []
        self.closed = False
        RecordingReporter.instances.append(self)

    def set_state(self, state):
        self.states.append(state)
        return True

    def close(self):
        self.closed = True


class StepClock:
    """
    Stands in for the driver's time() so the 24 hour completion window is
    reached immediately. The first reading starts the run; later readings report
    the elapsed time.
    """

    def __init__(self, elapsed):
        self.elapsed = elapsed
        self.readings = 0

    def __call__(self):
        self.readings += 1
        return 0.0 if self.readings == 1 else self.elapsed


class BoundedWakeup:
    """
    Stands in for the driver's cancellable wait. Wakes instantly and ends the
    calibration loop after a bounded number of waits so a run that must never
    complete still terminates.
    """

    def __init__(self, driver, limit=5):
        self._driver = driver
        self._limit = limit
        self.waits = 0

    def clear(self):
        pass

    def set(self):
        pass

    def wait(self, timeout=None):
        self.waits += 1
        if self.waits >= self._limit:
            self._driver.is_calibrating = False
        return False


def raise_unavailable(self, *args, **kwargs):
    raise RuntimeError("i2c unavailable")


@pytest.fixture(name="reporter")
def reporter_fixture():
    """
    Replace the openBalena reporter with a recording double.
    """
    RecordingReporter.instances = []
    with patch.object(BME688, "_createReporter", lambda self: RecordingReporter()):
        yield RecordingReporter


@pytest.fixture(name="data_dir")
def data_dir_fixture(tmp_path):
    """
    Redirect the persistent calibration path to a temporary directory.
    """
    with patch.object(
        BME688, "_get_state_path", lambda self, name: Path(tmp_path) / name
    ):
        yield tmp_path


def write_state(data_dir, contents):
    (data_dir / "bme688_state.txt").write_text(contents)


def build_driver(env=None):
    with patch.dict("os.environ", env or {}, clear=True):
        driver = BME688()
    # testing=True makes DriverBase.getEvent() read raw events instead of [event, callback]
    driver.testing = True
    driver.data = driver.createDataDict()
    return driver


def start_calibration(driver):
    driver.getEvent("CALIBRATE").set()
    driver.handleEvents()


def run_calibration_loop(driver, elapsed=CALIBRATION_SECONDS + 1):
    """
    Run one calibration pass to completion in the calling thread.
    """
    driver.is_calibrating = True
    with patch("drivers.sensors.BME688.time", StepClock(elapsed)):
        driver._run_calibration_thread(generation=driver.calibration_generation)


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


def test_vendor_debug_output_is_off_by_default():
    driver = build_driver()
    assert driver.debug_mode == 0

    driver.initialize()

    assert driver.sensor.debug_mode == 0


def test_debug_output_is_opt_in_through_the_environment():
    driver = build_driver({"BME688_DEBUG_MODE": "1"})

    driver.initialize()

    assert driver.sensor.debug_mode == 1


def test_only_the_exact_value_one_enables_debug_output():
    driver = build_driver({"BME688_DEBUG_MODE": "true"})

    driver.initialize()

    assert driver.sensor.debug_mode == 0


def test_sensor_address_is_still_passed_positionally():
    driver = build_driver()
    driver.initialize()

    assert driver.sensor.i2c_address == 0x77


def test_measure_maps_bsec_data_onto_the_shared_dict():
    driver = build_driver()

    driver.initialize()
    driver.measure()

    assert driver.data["initialized"].value == 1
    assert driver.data["temperature(c)"].value == 19.61
    assert driver.data["pressure(kpa)"].value == pytest.approx(102.096)
    assert driver.data["humidity(%rh)"].value == 46.77
    assert driver.data["gas_resistance(ohms)"].value == pytest.approx(25376.685)
    assert driver.data["iaq"].value == 25.0
    assert driver.data["sIAQ"].value == 25.0
    assert driver.data["CO2-eq"].value == 500.0
    assert driver.data["bVOC-eq"].value == 0.5


def test_scan_payload_fields_are_unchanged():
    driver = build_driver()
    driver.initialize()

    assert set(driver.data) == {
        "temperature(c)",
        "pressure(kpa)",
        "humidity(%rh)",
        "gas_resistance(ohms)",
        "iaq",
        "iaq_accuracy",
        "sIAQ",
        "CO2-eq",
        "bVOC-eq",
        "initialized",
        "calibrated",
    }


def test_temporary_measurement_errors_do_not_change_the_tag(reporter, data_dir):
    write_state(data_dir, str(SYNTHETIC_STATE))
    driver = build_driver()
    driver.initialize()

    with patch.object(driver.sensor, "get_bsec_data", side_effect=OSError("bus error")):
        driver.measure()

    assert reporter.instances[0].states == [STATE_CALIBRATED]


def test_calibration_state_is_restored_on_initialize(reporter, data_dir):
    write_state(data_dir, str(SYNTHETIC_STATE))
    driver = build_driver()

    driver.initialize()

    assert driver.sensor.set_bsec_state_calls == [SYNTHETIC_STATE]
    assert driver.sensor.set_sample_rate_calls == [driver.sample_rate]
    assert driver.data["calibrated"].value == 1
    assert driver.has_valid_calibration is True
    assert reporter.instances[0].states == [STATE_CALIBRATED]


def test_missing_calibration_file_reports_unhealthy(reporter, data_dir):
    driver = build_driver()

    driver.initialize()

    assert driver.sensor.set_bsec_state_calls == []
    assert driver.data["calibrated"].value == 0
    assert driver.data["initialized"].value == 1
    assert reporter.instances[0].states == [STATE_UNHEALTHY]


@pytest.mark.parametrize(
    "contents",
    [
        "[not,valid]",
        "[]",
        "",
        "[1.5]",
        "not-a-list",
    ],
)
def test_malformed_calibration_file_reports_unhealthy(
    reporter, data_dir, contents
):
    write_state(data_dir, contents)
    driver = build_driver()

    driver.initialize()

    assert driver.sensor.set_bsec_state_calls == []
    assert driver.data["calibrated"].value == 0
    assert driver.data["initialized"].value == 1
    assert reporter.instances[0].states == [STATE_UNHEALTHY]
    # The file is preserved for diagnosis.
    assert (data_dir / "bme688_state.txt").read_text() == contents


@pytest.mark.parametrize(
    "state",
    [
        SYNTHETIC_STATE[:-1],
        SYNTHETIC_STATE + [0],
        [1, 2, 3],
    ],
)
def test_incorrectly_sized_calibration_file_reports_unhealthy(
    reporter, data_dir, state
):
    write_state(data_dir, str(state))
    driver = build_driver()

    driver.initialize()

    assert driver.sensor.set_bsec_state_calls == []
    assert driver.data["calibrated"].value == 0
    assert driver.data["initialized"].value == 1
    assert reporter.instances[0].states == [STATE_UNHEALTHY]
    assert (data_dir / "bme688_state.txt").exists()


def test_out_of_range_byte_values_are_rejected(reporter, data_dir):
    write_state(data_dir, str([999] + SYNTHETIC_STATE[1:]))
    driver = build_driver()

    driver.initialize()

    assert driver.sensor.set_bsec_state_calls == []
    assert reporter.instances[0].states == [STATE_UNHEALTHY]


def test_rejected_calibration_state_reports_unhealthy(reporter, data_dir):
    write_state(data_dir, str(SYNTHETIC_STATE))
    driver = build_driver()
    driver.initialize()

    with patch.object(FakeBME68X, "set_bsec_state", return_value=-33):
        driver.initialize()

    assert driver.data["calibrated"].value == 0
    assert driver.data["initialized"].value == 1
    assert reporter.instances[1].states == [STATE_UNHEALTHY]


def test_calibration_restoration_exception_reports_unhealthy(reporter, data_dir):
    write_state(data_dir, str(SYNTHETIC_STATE))
    driver = build_driver()
    driver.initialize()

    with patch.object(FakeBME68X, "set_bsec_state", side_effect=ValueError("rejected")):
        driver.initialize()

    assert driver.data["calibrated"].value == 0
    assert reporter.instances[1].states == [STATE_UNHEALTHY]


def test_sample_rate_failure_prevents_successful_initialization(reporter, data_dir):
    write_state(data_dir, str(SYNTHETIC_STATE))
    driver = build_driver()

    with patch.object(FakeBME68X, "set_sample_rate", return_value=-14):
        driver.initialize()

    assert driver.failedToInit is True
    assert driver.data["initialized"].value == 0
    assert driver.data["calibrated"].value == 0
    assert driver.has_valid_calibration is False
    assert reporter.instances[0].states == [STATE_UNHEALTHY]


def test_initialization_exception_reports_unhealthy(reporter, data_dir):
    driver = build_driver()

    with patch.object(FakeBME68X, "__init__", raise_unavailable):
        driver.initialize()

    assert driver.failedToInit is True
    assert driver.data["initialized"].value == 0
    assert reporter.instances[0].states == [STATE_UNHEALTHY]


def test_calibration_cannot_start_after_failed_initialization(reporter, data_dir):
    driver = build_driver()
    with patch.object(FakeBME68X, "__init__", raise_unavailable):
        driver.initialize()

    start_calibration(driver)

    assert driver.calibration_thread is None
    assert reporter.instances[0].states == [STATE_UNHEALTHY]


def test_calibration_start_reports_calibrating(reporter, data_dir):
    write_state(data_dir, str(SYNTHETIC_STATE))
    driver = build_driver()
    driver.initialize()
    release = threading.Event()

    with patch.object(driver, "_run_calibration_thread", lambda generation: release.wait(5)):
        start_calibration(driver)
        assert driver.calibration_thread is not None
        release.set()
        driver.calibration_thread.join(5)

    assert reporter.instances[0].states == [STATE_CALIBRATED, STATE_CALIBRATING]


def test_duplicate_calibration_start_is_ignored(reporter, data_dir):
    write_state(data_dir, str(SYNTHETIC_STATE))
    driver = build_driver()
    driver.initialize()
    release = threading.Event()
    started = threading.Event()

    def blocker(generation):
        started.set()
        release.wait(5)

    with patch.object(driver, "_run_calibration_thread", blocker):
        start_calibration(driver)
        assert started.wait(5)
        thread = driver.calibration_thread

        start_calibration(driver)
        assert driver.calibration_thread is thread

        release.set()
        thread.join(5)

    assert reporter.instances[0].states == [STATE_CALIBRATED, STATE_CALIBRATING]


def test_calibration_completion_saves_state_atomically(reporter, data_dir):
    driver = build_driver()
    driver.initialize()

    run_calibration_loop(driver)

    assert (data_dir / "bme688_state.txt").read_text() == str(SYNTHETIC_STATE)
    assert driver.data["calibrated"].value == 1
    assert driver.has_valid_calibration is True
    assert reporter.instances[0].states == [STATE_UNHEALTHY, STATE_CALIBRATED]
    assert list(data_dir.glob("*.tmp")) == []


def test_incomplete_elapsed_window_never_saves(reporter, data_dir):
    driver = build_driver()
    driver.initialize()
    driver.calibration_wakeup = BoundedWakeup(driver)

    run_calibration_loop(driver, elapsed=CALIBRATION_SECONDS - 1)

    assert not (data_dir / "bme688_state.txt").exists()
    assert driver.data["calibrated"].value == 0
    # The bounded wait ends the run, which reports the interrupted outcome.
    assert reporter.instances[0].states == [STATE_UNHEALTHY, STATE_UNHEALTHY]


def test_incomplete_accuracy_never_saves(reporter, data_dir):
    driver = build_driver()
    driver.initialize()
    driver.sensor.bsec_data = {**SYNTHETIC_READING, "iaq_accuracy": 2}
    driver.calibration_wakeup = BoundedWakeup(driver)

    run_calibration_loop(driver)

    assert not (data_dir / "bme688_state.txt").exists()
    assert driver.data["calibrated"].value == 0
    assert reporter.instances[0].states == [STATE_UNHEALTHY, STATE_UNHEALTHY]


def test_cancellation_while_waiting_for_sensor_data(reporter, data_dir):
    driver = build_driver()
    driver.initialize()
    driver.sensor.bsec_data = {}
    waiting = threading.Event()
    reading = driver.sensor.get_bsec_data

    def observed_reading():
        waiting.set()
        return reading()

    driver.sensor.get_bsec_data = observed_reading

    start_calibration(driver)
    assert waiting.wait(5)

    driver.getEvent("STOP_CALIBRATION").set()
    driver.handleEvents()
    # The cancellable wait wakes the worker immediately instead of after a
    # full polling interval.
    driver.calibration_thread.join(0.5)

    assert driver.calibration_thread is None
    assert driver.is_calibrating is False
    assert not (data_dir / "bme688_state.txt").exists()
    assert reporter.instances[0].states == [
        STATE_UNHEALTHY,
        STATE_CALIBRATING,
        STATE_UNHEALTHY,
    ]


def test_stop_request_while_idle_is_harmless(reporter, data_dir):
    write_state(data_dir, str(SYNTHETIC_STATE))
    driver = build_driver()
    driver.initialize()

    driver.getEvent("STOP_CALIBRATION").set()
    driver.handleEvents()

    assert driver.is_calibrating is False
    assert reporter.instances[0].states == [STATE_CALIBRATED]


def test_interrupted_calibration_recovers_to_prior_valid_calibration(
    reporter, data_dir
):
    write_state(data_dir, str(SYNTHETIC_STATE))
    driver = build_driver()
    driver.initialize()

    with patch.object(driver, "_saveState") as save_state:
        driver.is_calibrating = False
        driver._run_calibration_thread(generation=driver.calibration_generation)

    assert save_state.call_count == 0
    assert reporter.instances[0].states == [STATE_CALIBRATED, STATE_CALIBRATED]


def test_failed_calibration_save_keeps_the_previous_file(reporter, data_dir):
    write_state(data_dir, str(SYNTHETIC_STATE))
    driver = build_driver()
    driver.initialize()

    with patch("drivers.sensors.BME688.os.replace", side_effect=OSError("read-only")):
        run_calibration_loop(driver)

    assert (data_dir / "bme688_state.txt").read_text() == str(SYNTHETIC_STATE)
    assert list(data_dir.glob("*.tmp")) == []
    assert driver.data["calibrated"].value == 1
    assert reporter.instances[0].states == [STATE_CALIBRATED, STATE_CALIBRATED]


def test_calibration_thread_exception_reports_unhealthy(reporter, data_dir):
    driver = build_driver()
    driver.initialize()
    driver.sensor.get_bsec_data = Mock(side_effect=OSError("bus error"))

    run_calibration_loop(driver)

    assert not (data_dir / "bme688_state.txt").exists()
    assert reporter.instances[0].states == [STATE_UNHEALTHY, STATE_UNHEALTHY]


def test_save_state_write_failure_retains_the_previous_file(reporter, data_dir):
    write_state(data_dir, str(SYNTHETIC_STATE))
    driver = build_driver()
    driver.initialize()

    with patch("drivers.sensors.BME688.os.replace", side_effect=OSError("read-only")):
        assert driver._saveState(list(SYNTHETIC_STATE)) is False

    assert (data_dir / "bme688_state.txt").read_text() == str(SYNTHETIC_STATE)
    assert list(data_dir.glob("*.tmp")) == []


@pytest.mark.parametrize("state", [[], SYNTHETIC_STATE[:-1], "not-a-list"])
def test_save_state_rejects_an_unexpected_curve(reporter, data_dir, state):
    write_state(data_dir, str(SYNTHETIC_STATE))
    driver = build_driver()
    driver.initialize()

    assert driver._saveState(state) is False

    assert (data_dir / "bme688_state.txt").read_text() == str(SYNTHETIC_STATE)
    assert driver.has_valid_calibration is True


def test_an_exiting_worker_does_not_overwrite_a_newer_run(reporter, data_dir):
    driver = build_driver()
    driver.initialize()
    driver.is_calibrating = True
    driver.calibration_generation = 7

    with patch.object(driver, "_saveState") as save_state, patch(
        "drivers.sensors.BME688.time", StepClock(CALIBRATION_SECONDS + 1)
    ):
        # An older run that exits after a newer run started owns nothing.
        driver._run_calibration_thread(generation=6)

    assert save_state.call_count == 0
    assert reporter.instances[0].states == [STATE_UNHEALTHY]
    assert driver.calibration_generation == 7


def test_measurement_continues_while_reporting_fails(reporter, data_dir):
    write_state(data_dir, str(SYNTHETIC_STATE))
    driver = build_driver()
    driver.initialize()
    driver.tag_reporter.set_state = Mock(side_effect=RuntimeError("tag backend down"))

    driver.measure()
    driver.measure()
    driver._reportState(STATE_CALIBRATING)

    assert driver.data["temperature(c)"].value == 19.61
    assert driver.data["initialized"].value == 1
    assert driver.tag_reporter.set_state.call_count == 1


def test_missing_openbalena_configuration_only_disables_reporting(data_dir, caplog):
    driver = build_driver()
    with patch.dict("os.environ", {}, clear=True), caplog.at_level("WARNING"):
        driver.initialize()
        driver._reportState(STATE_CALIBRATED)

    assert driver.tag_reporter is None
    assert driver.data["initialized"].value == 1
    assert driver.data["calibrated"].value == 0
    assert any(
        "device-tag reporting is disabled" in record.message
        for record in caplog.records
    )


def test_kill_closes_the_reporter(reporter, data_dir):
    driver = build_driver()
    driver.initialize()

    driver.kill()

    assert reporter.instances[0].closed is True
    assert driver.tag_reporter is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
