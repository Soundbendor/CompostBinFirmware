"""
Unit tests for DriverManager using fake sensors and a patched ThreadedDriver.
"""

import logging
from multiprocessing import Event, Value
from unittest.mock import Mock, patch

from drivers.DriverBase import DriverBase
from drivers.DriverManager import DriverManager


# Fake sensor to test DriverManager logic without hardware drivers
class FakeSensor(DriverBase):
    def __init__(self, module_name="FakeSensor", event_names=("PING",)):
        super().__init__(module_name)
        self.events = {name: Event() for name in event_names}

    def createDataDict(self):
        self.data = {
            "reading": Value("d", 0.0),
            "initialized": Value("i", 0),
        }
        return self.data


# Fake threaded wrapper that keeps DriverManager tests in-process and marks init as complete
class FakeThreadedDriver:
    next_pid = 1000

    def __init__(self, driver, data):
        self.driver = driver
        self.data = data
        self.pid = FakeThreadedDriver.next_pid
        FakeThreadedDriver.next_pid += 1
        self.start_called = False
        self.kill_called = False

    def start(self):
        self.start_called = True
        self.data["initialized"].value = 1

    def kill(self):
        self.kill_called = True


class NeverInitializedFakeThreadedDriver(FakeThreadedDriver):
    def start(self):
        self.start_called = True
        # initialized = 0


def test_constructor_formats_sensor_data_and_events():
    # Constructor should wrap sensor events/data and create the DriverManager bookkeeping dict
    sensor = FakeSensor(event_names=("PING", "PONG"))

    with patch("drivers.DriverManager.ThreadedDriver", FakeThreadedDriver):
        manager = DriverManager(sensor)

    assert manager.allProcsInitialized is True
    assert len(manager.proccessList) == 1
    assert manager.proccessList[0].start_called is True

    sensor_data = manager.data["FakeSensor"]["data"]
    sensor_events = manager.data["FakeSensor"]["events"]

    assert "reading" in sensor_data
    assert "initialized" in sensor_data
    assert sensor_events["PING"][0].is_set() is False
    assert sensor_events["PING"][1] is None
    assert sensor_events["PONG"][0].is_set() is False
    assert sensor_events["PONG"][1] is None

    assert manager.data["DriverManager"]["data"]["userTrigger"] is False
    assert manager.data["DriverManager"]["events"] == {}


def test_set_get_and_clear_event():
    # Event helpers should set, read, and clear wrapped sensor events by dotted name
    sensor = FakeSensor()

    with patch("drivers.DriverManager.ThreadedDriver", FakeThreadedDriver):
        manager = DriverManager(sensor)

    assert manager.getEvent("FakeSensor.PING") is False

    manager.setEvent("FakeSensor.PING")
    assert manager.getEvent("FakeSensor.PING") is True

    manager.clearEvent("FakeSensor.PING")
    assert manager.getEvent("FakeSensor.PING") is False


def test_clear_all_events_clears_every_sensor_event():
    # clearAllEvents() should clear events across all managed sensor
    sensor_a = FakeSensor(module_name="SensorA", event_names=("A_EVENT",))
    sensor_b = FakeSensor(module_name="SensorB", event_names=("B_EVENT",))

    with patch("drivers.DriverManager.ThreadedDriver", FakeThreadedDriver):
        manager = DriverManager(sensor_a, sensor_b)

    manager.setEvent("SensorA.A_EVENT")
    manager.setEvent("SensorB.B_EVENT")

    assert manager.getEvent("SensorA.A_EVENT") is True
    assert manager.getEvent("SensorB.B_EVENT") is True

    manager.clearAllEvents()

    assert manager.getEvent("SensorA.A_EVENT") is False
    assert manager.getEvent("SensorB.B_EVENT") is False


def test_register_event_callback_and_handle_callbacks():
    # Registered callbacks should fire only when the associated event is set
    sensor = FakeSensor()
    callback = Mock()

    with patch("drivers.DriverManager.ThreadedDriver", FakeThreadedDriver):
        manager = DriverManager(sensor)

    manager.registerEventCallback("FakeSensor.PING", callback)
    manager.setEvent("FakeSensor.PING")
    manager.handleCallbacks()

    callback.assert_called_once()
    event_arg = callback.call_args.args[0]
    assert event_arg.is_set() is True


def test_loop_delegates_to_handle_callbacks():
    # loop() should be a thin wrapper around handleCallbacks()
    sensor = FakeSensor()

    with patch("drivers.DriverManager.ThreadedDriver", FakeThreadedDriver):
        manager = DriverManager(sensor)

    manager.handleCallbacks = Mock()

    manager.loop()

    manager.handleCallbacks.assert_called_once_with()


def test_get_json_updates_values_event_states_and_callback_names():
    # getJSON() should expose plain values, event booleans, and callback names
    sensor = FakeSensor()

    with patch("drivers.DriverManager.ThreadedDriver", FakeThreadedDriver):
        manager = DriverManager(sensor)

    def on_ping(event):
        return None

    manager.registerEventCallback("FakeSensor.PING", on_ping)
    manager.data["FakeSensor"]["data"]["reading"].value = 12.5
    manager.setEvent("FakeSensor.PING")

    # getJSON() should return plain values and the callback name
    json_data = manager.getJSON()

    assert json_data["FakeSensor"]["data"]["reading"] == 12.5
    assert json_data["FakeSensor"]["data"]["initialized"] == 1
    assert json_data["FakeSensor"]["events"]["PING"][0] is True
    assert json_data["FakeSensor"]["events"]["PING"][1] == "on_ping"
    assert json_data["DriverManager"]["data"]["userTrigger"] is False


def test_kill_calls_kill_on_all_threaded_drivers():
    # kill() should forward shutdown to every managed threaded driver
    sensor_a = FakeSensor(module_name="SensorA")
    sensor_b = FakeSensor(module_name="SensorB")

    with patch("drivers.DriverManager.ThreadedDriver", FakeThreadedDriver):
        manager = DriverManager(sensor_a, sensor_b)

    manager.kill()

    assert all(proc.kill_called for proc in manager.proccessList)


def test_async_publisher_sensor_receives_full_manager_data_reference():
    # AsyncPublisher should receive the full manager data object instead of only its own data dict
    sensor = FakeSensor(module_name="AsyncPublisher")

    with patch("drivers.DriverManager.ThreadedDriver", FakeThreadedDriver):
        manager = DriverManager(sensor)

    assert sensor.data is manager.data


def test_invalid_event_path_logs_error_without_raising(caplog):
    # Invalid dotted event names should log an error instead of raising
    sensor = FakeSensor()

    with patch("drivers.DriverManager.ThreadedDriver", FakeThreadedDriver):
        manager = DriverManager(sensor)

    with caplog.at_level(logging.ERROR):
        result = manager.getEvent("FakeSensor.DOES_NOT_EXIST")

    assert result is None
    assert "Specified event/sensor doesn't exist" in caplog.text


def test_constructor_logs_uninitialized_processes(caplog):
    # Failed initialization should log the module names that never marked themselves ready
    sensor = FakeSensor()

    # Short-circuit time/sleep so the timeout path is tested without waiting 25 seconds.
    with patch("drivers.DriverManager.ThreadedDriver", NeverInitializedFakeThreadedDriver):
        with patch("drivers.DriverManager.time", side_effect=[0, 1, 30]):
            with patch("drivers.DriverManager.sleep", return_value=None):
                with caplog.at_level(logging.ERROR):
                    manager = DriverManager(sensor)

    assert manager.allProcsInitialized is False
    assert "The following proccesses failed to initialize" in caplog.text
    assert "FakeSensor" in caplog.text
