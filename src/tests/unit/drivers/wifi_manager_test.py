"""
Unit tests for WiFiManager using patched subprocess and request dependencies.
"""

import logging
from unittest.mock import Mock, call, patch

from drivers.NetworkDriver import WiFiManager


# Fake subprocess result so commanddriven methods can be tested without nmcli/iwlist
class FakeCompletedProcess:
    def __init__(self, stdout="", stderr=""):
        self.stdout = stdout.encode("utf-8")
        self.stderr = stderr.encode("utf-8")


class FakeRequests:
    def __init__(self, internet_access=False):
        self.checkNetworkConnection = Mock(return_value=internet_access)


def build_wifi_manager(internet_access=False):
    fake_requests = FakeRequests(internet_access=internet_access)

    # Most tests bypass constructor-time scanning so they can focus on one method at a time.
    with patch("drivers.NetworkDriver.RequestHandler", return_value=fake_requests):
        with patch.object(WiFiManager, "scanNetworks", return_value=True):
            wifi = WiFiManager()

    return wifi, fake_requests



def test_constructor_initializes_defaults_and_calls_scan_networks():
    # Verify constructor defaults and that the initial scan is called once
    fake_requests = FakeRequests()

    with patch("drivers.NetworkDriver.RequestHandler", return_value=fake_requests):
        with patch.object(WiFiManager, "scanNetworks", return_value=True) as scan_networks:
            wifi = WiFiManager()


    scan_networks.assert_called_once_with()
    assert wifi.requests is fake_requests
    assert wifi.lastConnectionResult == {"success": False, "message": "", "timestamp": 0}
    assert wifi.lastWiFiScan == {}
    assert wifi.isConnectedBool is False


def test_parse_network_list_handles_duplicates_and_colons():
    # Parse mixed network rows while deduplicating SSIDs and handling colons
    wifi, _ = build_wifi_manager()

    output = "\n".join(
        [
            "HomeWifi:75:WPA2",
            "GuestWifi:41:",
            "Cafe\\:Corner:83:WEP",
            "HomeWifi:10:Open",
        ]
    )

    parsed = wifi._parseNetworkList(output)

    assert parsed == {
        "HomeWifi": {"strength": 75, "security": "WPA2"},
        "GuestWifi": {"strength": 41, "security": "Open"},
        "Cafe:Corner": {"strength": 83, "security": "WEP"},
    }


def test_parse_network_list_prune():
    # Prune oversized scan results until the payload is under the size limit
    wifi, _ = build_wifi_manager()

    output = "\n".join(
        [f"VeryLongNetworkNameNumber{i:02d}:80:WPA2" for i in range(30)]
    )

    parsed = wifi._parseNetworkList(output)

    assert len(str(parsed)) <= 512
    assert 0 < len(parsed) < 30


def test_scan_networks_updates_last_scan_results_on_success():
    # Successful scans should run both commands in order, parse stdout, and save the result
    wifi, _ = build_wifi_manager()
    fake_process = FakeCompletedProcess(stdout="ignored")
    parsed_networks = {"HomeWifi": {"strength": 69, "security": "WPA2"}}

    command_results = [
        (0, FakeCompletedProcess()),  # iwlist scan
        (0, fake_process),            # nmcli list
    ]

    with patch.object(wifi, "_runCommand", side_effect=command_results) as run_command:
        # Bypass parsing network list
        with patch.object(wifi, "_parseNetworkList", return_value=parsed_networks) as parse_networks:
            result = wifi.scanNetworks()

    assert result is True
    assert wifi.lastWiFiScan == parsed_networks
    assert run_command.call_args_list == [
        call(["iwlist", "wlan0", "scan"]),
        call(["nmcli", "-g", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"]),
    ]
    parse_networks.assert_called_once_with("ignored")



def test_scan_networks_logs_and_preserves_last_scan_on_failure(caplog):
    # Failed scans should log an error and leave the previous scan cache unchanged
    wifi, _ = build_wifi_manager()
    wifi.lastWiFiScan = {"Existing": {"strength": 69, "security": "WPA2"}}

    command_results = [
        (0, FakeCompletedProcess()),                        # iwlist scan
        (1, FakeCompletedProcess(stderr="scan failed")),    # nmcli list
    ]

    with patch.object(wifi, "_runCommand", side_effect=command_results):
        with caplog.at_level(logging.ERROR):
            result = wifi.scanNetworks()

    assert result is False
    assert wifi.lastWiFiScan == {"Existing": {"strength": 69, "security": "WPA2"}}
    assert "Failed to scan WiFi networks!" in caplog.text


def test_getters_return_latest_cached_results():
    # Getter methods should return the last cached scan, connection, and connected state
    wifi, _ = build_wifi_manager()
    wifi.lastWiFiScan = {"MyWifi": {"strength": 69, "security": "Open"}}
    wifi.lastConnectionResult = {"success": True, "message": "ok", "timestamp": 5}
    wifi.isConnectedBool = True

    assert wifi.getLastScanResults() == {"MyWifi": {"strength": 69, "security": "Open"}}
    assert wifi.getLastConnectionResults() == {"success": True, "message": "ok", "timestamp": 5}
    assert wifi.isConnected() is True


def test_connect_to_network_updates_state_on_success():
    # Successful connections should update the cached result and enable auto-reconnect
    wifi, _ = build_wifi_manager()

    command_results = [
        (0, FakeCompletedProcess()),    # iwlist scan
        (0, FakeCompletedProcess()),    # nmcli list
    ]

    with patch.object(wifi, "_runCommand", side_effect=command_results) as run_command:
        with patch("drivers.NetworkDriver.time", return_value=420.69):
            result = wifi.connectToNetwork("MyWifi", "meow")

    assert result is True
    assert wifi.lastConnectionResult == {
        "message": "Wi-Fi configuration successful",
        "success": True,
        "timestamp": 420.69,
    }
    assert run_command.call_args_list == [
        call(["nmcli", "device", "wifi", "connect", "MyWifi", "password", "meow"]),
        call(["nmcli", "c", "modify", "MyWifi", "connection.autoconnect-retries", "0"]),
    ]


def test_connect_to_network_updates_state_on_failure(caplog):
    # Failed connections should store the stderr log and report an unsuccessful result
    wifi, _ = build_wifi_manager()

    with patch.object(wifi, "_runCommand", return_value=(1, FakeCompletedProcess(stderr="wrong password"))) as run_command:
        with patch("drivers.NetworkDriver.time", return_value=420.69):
            with caplog.at_level(logging.ERROR):
                result = wifi.connectToNetwork("MyWifi", "badpass")

    assert result is False
    assert wifi.lastConnectionResult == {
        "message": "Wi-Fi configuration failed",
        "log": "wrong password",
        "success": False,
        "timestamp": 420.69,
    }
    run_command.assert_called_once_with(
        ["nmcli", "device", "wifi", "connect", "MyWifi", "password", "badpass"]
    )
    assert "Failed to connect to network: MyWifi" in caplog.text


def test_check_connection_returns_connected_with_internet():
    # Active-network checks with internet access should mark the manager as connected
    wifi, fake_requests = build_wifi_manager(internet_access=True)

    with patch.object(wifi, "_runCommand", return_value=(0, FakeCompletedProcess(stdout="HomeWifi\nbleh"))) as run_command:
        result = wifi.checkConnection()

    assert result == {
        "message": "Connected to HomeWifi",
        "success": True,
        "internet_access": True,
    }
    assert wifi.isConnectedBool is True
    fake_requests.checkNetworkConnection.assert_called_once_with()
    run_command.assert_called_once_with(["nmcli", "-t", "-f", "NAME", "c", "show", "--active"])


def test_check_connection_without_internet_keep_current_connected_flag():
    # No internet checks should keep the current connected flag while reporting no internet access
    wifi, _ = build_wifi_manager(internet_access=False)
    wifi.isConnectedBool = True

    with patch.object(wifi, "_runCommand", return_value=(0, FakeCompletedProcess(stdout="HomeWifi\n"))):
        result = wifi.checkConnection()

    assert result == {
        "message": "Connected to HomeWifi",
        "success": True,
        "internet_access": False,
    }
    assert wifi.isConnectedBool is True


def test_check_connection_returns_not_connected_on_nmcli_failure():
    # nmcli failures should report no Wi-Fi connection and clear the connected flag.
    wifi, _ = build_wifi_manager(internet_access=True)
    wifi.isConnectedBool = True

    with patch.object(wifi, "_runCommand", return_value=(1, FakeCompletedProcess(stderr="not active"))):
        result = wifi.checkConnection()

    assert result == {"message": "Not connected to Wi-Fi", "success": False}
    assert wifi.isConnectedBool is False


def test_disconnect_from_network_sets_disconnected_on_success():
    # Successful disconnects should return True and clear the connected flag
    wifi, _ = build_wifi_manager()
    wifi.isConnectedBool = True

    with patch.object(wifi, "_runCommand", return_value=(0, FakeCompletedProcess())) as run_command:
        result = wifi.disconnectFromNetwork("MyWifi")

    assert result is True
    assert wifi.isConnectedBool is False
    run_command.assert_called_once_with(["nmcli", "connection", "delete", "MyWifi"])


def test_disconnect_from_network_returns_false_on_failure():
    # Failed disconnects should return False without changing the current connected flag
    wifi, _ = build_wifi_manager()
    wifi.isConnectedBool = True

    with patch.object(wifi, "_runCommand", return_value=(1, FakeCompletedProcess(stderr="delete failed"))) as run_command:
        result = wifi.disconnectFromNetwork("MyWifi")

    assert result is False
    assert wifi.isConnectedBool is True
    run_command.assert_called_once_with(["nmcli", "connection", "delete", "MyWifi"])
