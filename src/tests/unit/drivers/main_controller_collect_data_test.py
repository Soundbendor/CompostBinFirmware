"""
Unit tests for MainController.collectData().
"""

from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from drivers.MainController import MainController


# Fake DriverManager to track events, data updates, and JSON payloads
class FakeManager:
    def __init__(self, weight=42.5):
        self.set_calls = []
        self.event_states = {}
        self.data = {
            "DriverManager": {"data": {"userTrigger": False}},
            "NAU7802": {
                "data": {
                    "weight": SimpleNamespace(value=weight),
                    "weight_delta": SimpleNamespace(value=0.0),
                }
            },
        }

    def getData(self):
        return self.data

    def setEvent(self, event):
        self.set_calls.append(event)
        self.event_states[event] = True

    def getEvent(self, event):
        is_set = self.event_states.get(event, False)
        if event in {
            "Realsense.CAPTURE",
            "MLX90640.CAPTURE",
            "SoundController.RECORD",
        }:
            self.event_states[event] = False
        return is_set

    def getJSON(self):
        return {
            "DriverManager": {
                "data": {"userTrigger": self.data["DriverManager"]["data"]["userTrigger"]}
            },
            "NAU7802": {
                "data": {
                    "weight": self.data["NAU7802"]["data"]["weight"].value,
                    "weight_delta": self.data["NAU7802"]["data"]["weight_delta"].value,
                }
            },
        }


# Fake pipe connection that returns one fixed filename payload
class FakeConnection:
    def __init__(self, payload):
        self.payload = payload
        self.recv_calls = 0

    def recv(self):
        self.recv_calls += 1
        return self.payload


def build_controller(weight=42.5, starting_weight=40.0):
    # Create new MainController without __init__() setup
    controller = MainController.__new__(MainController)
    controller.manager = FakeManager(weight=weight)
    controller.soundControllerConnection = FakeConnection({"audioFile": "../data/audio.wav"})
    controller.realsenseControllerConenction = FakeConnection(
        {"colorImage": "../data/color.jpg", "depthImage": "../data/depth.npy"}
    )
    controller.mlxControllerConenction = FakeConnection(
        {"heatmapImage": "../data/heatmap.jpg"}
    )
    controller.publisherQueue = Mock()
    controller.startingWeight = starting_weight
    return controller


# Main collection path should trigger recording/capture and queue a complete sample
def test_collect_data_triggers_capture_and_queues_sample_payload():
    controller = build_controller(weight=45.25, starting_weight=40.0)

    with patch("drivers.MainController.time.sleep") as sleep:
        with patch("drivers.MainController.uuid.uuid4", return_value="sample-uid"):
            controller.collectData(triggeredByLid=True)

    assert controller.manager.set_calls == [
        "SoundController.RECORD",
        "LEDDriver.CAMERA",
        "Realsense.CAPTURE",
        "MLX90640.CAPTURE",
        "LEDDriver.PROCESSING",
        "SoundController.STOP_RECORDING",
    ]
    assert sleep.call_args_list == [
        call(0.4),
        call(0.2),
        call(0.2),
        call(0.2),
        call(6),
    ]
    assert controller.manager.data["DriverManager"]["data"]["userTrigger"] is True
    assert controller.manager.data["NAU7802"]["data"]["weight_delta"].value == 5.25

    queued_uid, file_names, json_payload, should_retry = (
        controller.publisherQueue.put.call_args.args[0]
    )
    assert queued_uid == "sample-uid"
    assert file_names == {
        "audioFile": "../data/audio.wav",
        "colorImage": "../data/color.jpg",
        "depthImage": "../data/depth.npy",
        "heatmapImage": "../data/heatmap.jpg",
    }
    assert json_payload["DriverManager"]["data"]["userTrigger"] is True
    assert json_payload["NAU7802"]["data"]["weight_delta"] == 5.25
    assert should_retry is False

    assert controller.soundControllerConnection.recv_calls == 1
    assert controller.realsenseControllerConenction.recv_calls == 1
    assert controller.mlxControllerConenction.recv_calls == 1


# Manual collection should preserve userTrigger=False through the queued payload
def test_collect_data_preserves_manual_trigger_flag_in_payload():
    controller = build_controller(weight=37.0, starting_weight=40.0)

    with patch("drivers.MainController.time.sleep"):
        with patch("drivers.MainController.uuid.uuid4", return_value="manual-uid"):
            controller.collectData(triggeredByLid=False)

    queued_uid, _, json_payload, should_retry = controller.publisherQueue.put.call_args.args[0]

    assert queued_uid == "manual-uid"
    assert controller.manager.data["DriverManager"]["data"]["userTrigger"] is False
    assert controller.manager.data["NAU7802"]["data"]["weight_delta"].value == -3.0
    assert json_payload["DriverManager"]["data"]["userTrigger"] is False
    assert json_payload["NAU7802"]["data"]["weight_delta"] == -3.0
    assert should_retry is False
