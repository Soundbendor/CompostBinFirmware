"""
Unit tests for MainController.initialSetup().
"""

from types import SimpleNamespace
from unittest.mock import call, patch

import pytest

from drivers.MainController import MainController


# Sequence of shared values used to simulate lid state changes during setup
class SequenceValue:
    def __init__(self, values):
        self.values = list(values)
        self.last_value = self.values[-1] if self.values else 0

    @property
    def value(self):
        if self.values:
            self.last_value = self.values.pop(0)
        return self.last_value


# Fake DriverManager that records setup side effects and auto clears wait events
class FakeManager:
    def __init__(self, lid_states=None):
        self.set_calls = []
        self.clear_calls = []
        self.clear_all_calls = 0
        self.event_states = {"LidSwitch.LID_CLOSED": False}
        self.data = {
            "LidSwitch": {
                "data": {
                    "Lid_State": SequenceValue(lid_states or [0]),
                }
            },
            "NAU7802": {"data": {"weight": SimpleNamespace(value=0.0)}},
        }

    def getData(self):
        return self.data

    def setEvent(self, event):
        self.set_calls.append(event)
        self.event_states[event] = True

    def getEvent(self, event):
        is_set = self.event_states.get(event, False)
        if is_set:
            self.event_states[event] = False
        return is_set

    def clearEvent(self, event):
        self.clear_calls.append(event)
        self.event_states[event] = False

    def clearAllEvents(self):
        self.clear_all_calls += 1
        for event in self.event_states:
            self.event_states[event] = False


# Fake Wi-Fi manager that returns a deterministic connection sequence
class FakeWiFiManager:
    def __init__(self, internet_access_sequence):
        self.internet_access_sequence = list(internet_access_sequence)
        self.check_connection_calls = 0
        self.last_internet_access = (
            self.internet_access_sequence[-1]
            if self.internet_access_sequence
            else False
        )

    def checkConnection(self):
        self.check_connection_calls += 1
        if self.internet_access_sequence:
            self.last_internet_access = self.internet_access_sequence.pop(0)
        return {
            "message": "connected" if self.last_internet_access else "disconnected",
            "success": True,
            "internet_access": self.last_internet_access,
        }


def build_controller(
    internet_access_sequence=None,
    lid_states=None,
    is_muted=False,
    is_boot_from_update=False,
):
    controller = MainController.__new__(MainController)
    controller.manager = FakeManager(lid_states=lid_states)
    controller.wifiManager = FakeWiFiManager(
        internet_access_sequence or [True],
    )
    controller.isMuted = is_muted
    controller.isBootFromUpdate = is_boot_from_update
    return controller


def sleep_args(sleep):
    return [args[0] for args, _ in sleep.call_args_list]


# Connected startup should announce bluetooth/Wi-Fi readiness, tare, and clear setup events
def test_initial_setup_connected_lid_closed_runs_audio_tare_and_cleanup():
    controller = build_controller(internet_access_sequence=[True, True], lid_states=[0])

    with patch("drivers.MainController.time.sleep") as sleep:
        controller.initialSetup()

    assert controller.manager.set_calls == [
        "SoundController.WAIT_FOR_BLUETOOTH",
        "SoundController.CONNECTED_TO_WIFI",
        "NAU7802.TARE",
    ]
    assert controller.manager.clear_calls == ["LidSwitch.LID_CLOSED"]
    assert controller.manager.clear_all_calls == 1
    assert controller.wifiManager.check_connection_calls == 2
    assert sleep.call_args_list == [call(0.1), call(0.1), call(1.0)]


# Disconnected startup should warn once, retry Wi-Fi, and announce recovery when internet comes back
def test_initial_setup_disconnected_then_reconnected_warns_retries_and_announces_connected():
    controller = build_controller(
        internet_access_sequence=[False, False, True],
        lid_states=[0],
    )

    with patch("drivers.MainController.time.sleep") as sleep:
        controller.initialSetup()

    assert controller.manager.set_calls == [
        "SoundController.WAIT_FOR_BLUETOOTH",
        "SoundController.NO_WIFI",
        "SoundController.CONNECTED_TO_WIFI",
        "NAU7802.TARE",
    ]
    assert controller.wifiManager.check_connection_calls == 3
    assert sleep_args(sleep).count(5) == 1
    assert controller.manager.clear_calls == ["LidSwitch.LID_CLOSED"]
    assert controller.manager.clear_all_calls == 1


# Exhausted Wi-Fi retries should skip the connected cue and complete tare cleanup
def test_initial_setup_wifi_never_connects_does_not_announce_connected():
    controller = build_controller(
        internet_access_sequence=[False, False, False, False, False],
        lid_states=[0],
    )

    with patch("drivers.MainController.time.sleep") as sleep:
        controller.initialSetup()

    assert controller.wifiManager.check_connection_calls == 5
    assert sleep_args(sleep).count(5) == 4
    assert "SoundController.NO_WIFI" in controller.manager.set_calls
    assert "SoundController.CONNECTED_TO_WIFI" not in controller.manager.set_calls
    assert controller.manager.set_calls[-1] == "NAU7802.TARE"
    assert controller.manager.clear_calls == ["LidSwitch.LID_CLOSED"]
    assert controller.manager.clear_all_calls == 1


# Open-lid startup should prompt for closure, wait to settle, then tare and clean up
def test_initial_setup_waits_for_lid_close_before_tare():
    controller = build_controller(
        internet_access_sequence=[True, True],
        lid_states=[1, 0],
    )

    with patch("drivers.MainController.time.sleep") as sleep:
        controller.initialSetup()

    assert controller.manager.set_calls == [
        "SoundController.WAIT_FOR_BLUETOOTH",
        "SoundController.CONNECTED_TO_WIFI",
        "SoundController.CLOSE_LID_TO_TARE",
        "NAU7802.TARE",
    ]
    assert call(1) in sleep.call_args_list
    assert call(6) in sleep.call_args_list
    assert controller.manager.clear_calls == ["LidSwitch.LID_CLOSED"]
    assert controller.manager.clear_all_calls == 1

# Muted/update startup should suppress user audio cues while taring and cleaning up
@pytest.mark.parametrize(
    ("is_muted", "is_boot_from_update"),
    [(True, False), (False, True)],
)
def test_initial_setup_muted_or_update_boot_suppresses_startup_audio(
    is_muted,
    is_boot_from_update,
):
    controller = build_controller(
        internet_access_sequence=[False, True],
        lid_states=[0],
        is_muted=is_muted,
        is_boot_from_update=is_boot_from_update,
    )

    with patch("drivers.MainController.time.sleep"):
        controller.initialSetup()

    assert "SoundController.WAIT_FOR_BLUETOOTH" not in controller.manager.set_calls
    assert "SoundController.NO_WIFI" not in controller.manager.set_calls
    assert "SoundController.CONNECTED_TO_WIFI" not in controller.manager.set_calls
    assert controller.manager.set_calls == ["NAU7802.TARE"]
    assert controller.manager.clear_calls == ["LidSwitch.LID_CLOSED"]
    assert controller.manager.clear_all_calls == 1
