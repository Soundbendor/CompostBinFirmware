"""
Unit tests for BluetoothDriver state transition logic
"""

from unittest.mock import Mock

from drivers.NetworkDriver import BluetoothDriver


class FakeWiFiManager:
    def __init__(self, internet_access):
        self.internet_access = internet_access

    def checkConnection(self):
        return {"internet_access": self.internet_access}


def build_bluetooth_driver(muted=False):
    driver = BluetoothDriver(muted)
    driver.testing = True
    driver.data = driver.createDataDict()
    return driver


def test_create_data_dict_returns_initialized_and_muted_fields():
    # createDataDict() should expose the shared fields used by the controller
    driver = build_bluetooth_driver()

    assert set(driver.data.keys()) == {"initialized", "muted"}
    assert driver.data["initialized"].value == 0
    assert driver.data["muted"].value == 0


def test_update_connection_state_sets_lost_wifi_event_when_connection_drops():
    # Raise LOST_WIFI_CONNECTION when transitioning from connected to disconnected
    driver = build_bluetooth_driver()
    driver.wifi = FakeWiFiManager(False)
    driver.lastConnectionStatus = True

    driver.updateConnectionState()

    assert driver.events["LOST_WIFI_CONNECTION"].is_set()
    assert not driver.events["GOT_WIFI_CONNECTION"].is_set()
    assert driver.lastConnectionStatus is False


def test_update_connection_state_sets_got_wifi_event_when_connection_returns():
    # Raise GOT_WIFI_CONNECTION when transitioning from disconnected to connceted
    driver = build_bluetooth_driver()
    driver.wifi = FakeWiFiManager(True)
    driver.lastConnectionStatus = False

    driver.updateConnectionState()

    assert driver.events["GOT_WIFI_CONNECTION"].is_set()
    assert not driver.events["LOST_WIFI_CONNECTION"].is_set()
    assert driver.lastConnectionStatus is True


def test_update_connection_state_leaves_events_clear_when_status_does_not_change():
    # Repeated connection status should update the cached state without raising events
    driver = build_bluetooth_driver()
    driver.wifi = FakeWiFiManager(True)
    driver.lastConnectionStatus = True

    driver.updateConnectionState()

    assert not driver.events["LOST_WIFI_CONNECTION"].is_set()
    assert not driver.events["GOT_WIFI_CONNECTION"].is_set()
    assert driver.lastConnectionStatus is True


def test_measure_calls_update_connection_state():
    # measure() should simply forward to updateConnectionState().
    driver = build_bluetooth_driver()
    driver.updateConnectionState = Mock()

    driver.measure()

    driver.updateConnectionState.assert_called_once_with()
