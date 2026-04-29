"""
Unit tests for ThreadedDriver using a fake in-process driver
"""

from unittest.mock import patch

from drivers.DriverBase import DriverBase
from drivers.ThreadedDriver import ThreadedDriver


class FakeDriver(DriverBase):
    def __init__(self):
        super().__init__("FakeDriver")
        self.initialize_calls = 0
        self.measure_calls = 0
        self.kill_calls = 0
        self.loopTime = 0.25
        self.on_measure = None
        self.raise_keyboard_interrupt = False

    # Track how many times the threaded wrapper initializes the underlying driver
    def initialize(self):
        self.initialize_calls += 1

    # Count measure loops and optionally trigger a KeyboardInterrupt
    def measure(self):
        self.measure_calls += 1
        if self.raise_keyboard_interrupt:
            raise KeyboardInterrupt()
        if self.on_measure is not None:
            self.on_measure()

    def kill(self):
        self.kill_calls += 1


def test_constructor_stores_driver_data_and_running_state():
    # Constructor should keep the driver/data references and start in the running state
    driver = FakeDriver()
    data = {"initialized": 0}

    threaded_driver = ThreadedDriver(driver, data)

    assert threaded_driver.driver is driver
    assert threaded_driver.data is data
    assert threaded_driver.isRunning is True


def test_run_initializes_and_measures_until_stopped():
    # run() should initialize once and keep measuring until the loop is stopped
    driver = FakeDriver()
    threaded_driver = ThreadedDriver(driver, {})

    def stop_after_nth_measure():
        if driver.measure_calls == 5:
            threaded_driver.isRunning = False

    driver.on_measure = stop_after_nth_measure

    with patch("drivers.ThreadedDriver.sleep") as sleep_mock:
        threaded_driver.run()

    assert driver.initialize_calls == 1
    assert driver.measure_calls == 5
    assert sleep_mock.call_count == 5
    sleep_mock.assert_called_with(driver.loopTime)


def test_kill_stops_driver_and_calls_driver_kill():
    # kill() should stop the loop and forward shutdown to the wrapped driver.
    driver = FakeDriver()
    threaded_driver = ThreadedDriver(driver, {})

    threaded_driver.kill()

    assert threaded_driver.isRunning is False
    assert driver.kill_calls == 1


def test_run_calls_kill_when_measure_raises_keyboard_interrupt():
    # KeyboardInterrupt during measure() should be handled by calling kill().
    driver = FakeDriver()
    driver.raise_keyboard_interrupt = True
    threaded_driver = ThreadedDriver(driver, {})

    with patch.object(threaded_driver, "kill", wraps=threaded_driver.kill) as kill_spy, \
         patch("drivers.ThreadedDriver.sleep") as sleep_mock:
        threaded_driver.run()

    assert driver.initialize_calls == 1
    assert driver.measure_calls == 1
    assert threaded_driver.isRunning is False
    assert driver.kill_calls == 1
    kill_spy.assert_called_once_with()
    sleep_mock.assert_not_called()
