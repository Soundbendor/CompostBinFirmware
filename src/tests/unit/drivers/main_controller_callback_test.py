"""
Unit tests for MainController callback handling
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from drivers.MainController import MainController


class FakeManager:
    def __init__(self):
        self.event_states = {
            "LidSwitch.LID_CLOSED": False,
            "BluetoothDriver.LOST_WIFI_CONNECTION": False,
            "BluetoothDriver.GOT_WIFI_CONNECTION": False,
            "BluetoothDriver.BLUETOOTH_STOPPED": False,
        }
        self.set_calls = []
        self.clear_calls = []
        self.data = {
            "NAU7802": {"data": {"weight": SimpleNamespace(value=0.0)}},
            "BluetoothDriver": {"data": {"muted": SimpleNamespace(value=0)}},
        }

    def getEvent(self, event):
        return self.event_states.get(event, False)

    def setEvent(self, event):
        self.set_calls.append(event)

    def clearEvent(self, event):
        self.clear_calls.append(event)
        self.event_states[event] = False

    def getData(self):
        return self.data


def build_controller(is_initialized=True, is_muted=False):
    controller = MainController.__new__(MainController)
    controller.manager = FakeManager()
    controller.is_initialized = is_initialized
    controller.isMuted = is_muted
    controller.startingWeight = 0.0
    controller.collectData = Mock()
    controller.updateConfig = Mock()
    return controller


def test_handle_callbacks_collects_data_after_lid_closed():
    # Lid close should trigger collection, refresh starting weight, and clear the event
    controller = build_controller()
    controller.manager.event_states["LidSwitch.LID_CLOSED"] = True
    controller.manager.data["NAU7802"]["data"]["weight"].value = 67

    with patch("drivers.MainController.time.sleep"):
        controller.handleCallbacks()

    controller.collectData.assert_called_once_with(triggeredByLid=True)
    assert controller.startingWeight == 67
    assert "LidSwitch.LID_CLOSED" in controller.manager.clear_calls


def test_handle_callbacks_ignores_lid_closed_when_not_initialized():
    # Lid close should do nothing until the controller has finished initializing
    controller = build_controller(is_initialized=False)
    controller.startingWeight = 12.0
    controller.manager.event_states["LidSwitch.LID_CLOSED"] = True
    controller.manager.data["NAU7802"]["data"]["weight"].value = 67

    with patch("drivers.MainController.time.sleep"):
        controller.handleCallbacks()

    controller.collectData.assert_not_called()
    assert controller.startingWeight == 12.0
    assert "LidSwitch.LID_CLOSED" not in controller.manager.clear_calls


def test_handle_callbacks_forwards_lost_wifi_event_when_unmuted():
    # Losing Wi-Fi should notify SoundController and clear the bluetooth event
    controller = build_controller(is_muted=False)
    controller.manager.event_states["BluetoothDriver.LOST_WIFI_CONNECTION"] = True

    controller.handleCallbacks()

    assert "SoundController.NO_WIFI" in controller.manager.set_calls
    assert "BluetoothDriver.LOST_WIFI_CONNECTION" in controller.manager.clear_calls


def test_handle_callbacks_does_not_forward_lost_wifi_event_when_muted():
    # Losing Wi-Fi should not trigger audio feedback while the controller is muted
    controller = build_controller(is_muted=True)
    controller.manager.event_states["BluetoothDriver.LOST_WIFI_CONNECTION"] = True
    controller.manager.data["BluetoothDriver"]["data"]["muted"].value = 1

    controller.handleCallbacks()

    assert "SoundController.NO_WIFI" not in controller.manager.set_calls
    assert "BluetoothDriver.LOST_WIFI_CONNECTION" not in controller.manager.clear_calls
    controller.updateConfig.assert_not_called()


def test_handle_callbacks_forwards_got_wifi_event_when_unmuted():
    # Regained Wi-Fi should notify SoundController and clear the bluetooth event.
    controller = build_controller(is_muted=False)
    controller.manager.event_states["BluetoothDriver.GOT_WIFI_CONNECTION"] = True

    controller.handleCallbacks()

    assert "SoundController.CONNECTED_TO_WIFI" in controller.manager.set_calls
    assert "BluetoothDriver.GOT_WIFI_CONNECTION" in controller.manager.clear_calls


def test_handle_callbacks_forwards_bluetooth_stopped_event_when_unmuted():
    # Bluetooth shutdown should notify SoundController and clear the bluetooth event
    controller = build_controller(is_muted=False)
    controller.manager.event_states["BluetoothDriver.BLUETOOTH_STOPPED"] = True

    controller.handleCallbacks()

    assert "SoundController.BLUETOOTH_STOPPED" in controller.manager.set_calls
    assert "BluetoothDriver.BLUETOOTH_STOPPED" in controller.manager.clear_calls


def test_handle_callbacks_sets_muted_state_and_updates_config():
    # A muted bluetooth state should flip the controller mute flag and persist config.
    controller = build_controller(is_muted=False)
    controller.manager.data["BluetoothDriver"]["data"]["muted"].value = 1

    controller.handleCallbacks()

    assert "SoundController.MUTED" in controller.manager.set_calls
    assert controller.isMuted is True
    controller.updateConfig.assert_called_once_with()


def test_handle_callbacks_does_not_repeat_muted_event_when_already_muted():
    # Already-muted state should not emit another MUTED event or rewrite config
    controller = build_controller(is_muted=True)
    controller.manager.data["BluetoothDriver"]["data"]["muted"].value = 1

    controller.handleCallbacks()

    assert "SoundController.MUTED" not in controller.manager.set_calls
    assert controller.isMuted is True
    controller.updateConfig.assert_not_called()


def test_handle_callbacks_sets_unmuted_state_and_updates_config():
    # An unmuted bluetooth state should clear the controller mute flag and persist config
    controller = build_controller(is_muted=True)
    controller.manager.data["BluetoothDriver"]["data"]["muted"].value = 0

    controller.handleCallbacks()

    assert "SoundController.UNMUTED" in controller.manager.set_calls
    assert controller.isMuted is False
    controller.updateConfig.assert_called_once_with()
