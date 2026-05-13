"""
Unit tests for BluetoothDriver state transition logic
"""

import logging
import os
from unittest.mock import Mock, patch

from drivers.NetworkDriver import BluetoothDriver


# Fake Wi-Fi manager to handle Bluetooth connection transition branches
class FakeWiFiManager:
    def __init__(self, internet_access):
        self.internet_access = internet_access

    def checkConnection(self):
        return {"internet_access": self.internet_access}


# Fake Wi-Fi setup service used to test initialize() without real bluez or nmcli
class FakeWiFiSetupService:
    def __init__(self, internet_access=True):
        self.wifi = FakeWiFiManager(internet_access)


# Fake API setup service used to test initialize() without RequestHandler setup
class FakeAPISetupService:
    pass


# Fake debug service that preserves the muted state passed by BluetoothDriver
class FakeDebugService:
    def __init__(self, muted):
        self.isMuted = muted


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


def test_initialize_sets_services_state_and_starts_server():
    # initialize() should set up service helpers, cache Wi-Fi status, set muted data, and start the server
    driver = build_bluetooth_driver(muted=True)
    fake_wifi_service = FakeWiFiSetupService(internet_access=True)
    fake_api_service = FakeAPISetupService()
    fake_debug_service = FakeDebugService(muted=True)

    with patch.object(BluetoothDriver, "WiFiSetupSerivce", return_value=fake_wifi_service) as wifi_service_ctor:
        with patch.object(BluetoothDriver, "APISetupService", return_value=fake_api_service) as api_service_ctor:
            with patch.object(BluetoothDriver, "DebugService", return_value=fake_debug_service) as debug_service_ctor:
                with patch.object(driver, "startServer") as start_server:
                    driver.initialize()

    wifi_service_ctor.assert_called_once_with()
    api_service_ctor.assert_called_once_with()
    debug_service_ctor.assert_called_once_with(True)
    start_server.assert_called_once_with()
    assert driver.wifiService is fake_wifi_service
    assert driver.apiService is fake_api_service
    assert driver.debugService is fake_debug_service
    assert driver.wifi is fake_wifi_service.wifi
    assert driver.lastConnectionStatus is True
    assert driver.data["muted"].value == 1
    assert driver.loopTime == 20


def test_api_setup_service_check_api_connection_delegates_to_request_handler():
    # APISetupService.checkAPIConnection() should forward to RequestHandler.sendSecureHeartbeat()
    fake_requests = Mock()
    fake_requests.sendSecureHeartbeat.return_value = True
    service = BluetoothDriver.APISetupService.__new__(BluetoothDriver.APISetupService)
    service.requests = fake_requests

    assert service.checkAPIConnection() is True
    fake_requests.sendSecureHeartbeat.assert_called_once_with()


def test_debug_service_clear_cache_removes_files_and_skips_directories():
    # DebugService._clearCache() should delete regular cached files but leave directories alone
    service = BluetoothDriver.DebugService.__new__(BluetoothDriver.DebugService)
    data_files = ["cachedData.dat", "color.jpg", "nested"]

    def is_file(path):
        return not path.endswith("nested")

    with patch("drivers.NetworkDriver.os.listdir", return_value=data_files) as listdir:
        with patch("drivers.NetworkDriver.os.path.isfile", side_effect=is_file) as isfile:
            with patch("drivers.NetworkDriver.os.remove") as remove:
                result = service._clearCache()

    assert result is True
    listdir.assert_called_once_with("../data")
    assert isfile.call_count == 3
    assert [args[0] for args, _ in remove.call_args_list] == [
        os.path.join("../data", "cachedData.dat"),
        os.path.join("../data", "color.jpg"),
    ]


def test_debug_service_clear_cache_returns_false_on_os_error(caplog):
    # DebugService._clearCache() should log and return False when cache listing fails
    service = BluetoothDriver.DebugService.__new__(BluetoothDriver.DebugService)

    with patch("drivers.NetworkDriver.os.listdir", side_effect=OSError("boom")):
        with caplog.at_level(logging.ERROR):
            result = service._clearCache()

    assert result is False
    assert "Failed to clear cache" in caplog.text
