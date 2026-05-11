"""
Unit tests for AsyncPublisher cache, publish, and retry behavior.
"""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, call, mock_open, patch

from drivers.sensors.AsyncPublisher import AsyncPublisher


# Fake queue that behaves like the multiprocessing queue methods used by AsyncPublisher
class FakeQueue:
    def __init__(self, items=None):
        self.items = list(items or [])
        self.put_calls = []

    def empty(self):
        return len(self.items) == 0

    def get_nowait(self):
        return self.items.pop(0)

    def put(self, item):
        self.put_calls.append(item)
        self.items.append(item)


# Fake event object for set/is_set used by LED event entries
class FakeEvent:
    def __init__(self, is_set=False):
        self.set_calls = 0
        self._is_set = is_set

    def set(self):
        self.set_calls += 1
        self._is_set = True

    def is_set(self):
        return self._is_set


def sample_file_names():
    return {
        "voiceRecording": "../data/audio.wav",
        "colorImage": "../data/color.jpg",
        "depthImage": "../data/depth.npy",
        "heatmapImage": "../data/heatmap.jpg",
    }


def sample_data(user_trigger=True):
    return {
        "DriverManager": {"data": {"userTrigger": user_trigger}},
        "SoundController": {"data": {"TranscribedText": ""}},
    }


def build_data(include_led=True, led_initialized=True, camera_active=False):
    data = {
        "AsyncPublisher": {
            "data": {"initialized": SimpleNamespace(value=0)},
            "events": {},
        },
        "SoundController": {"data": {"TranscribedText": ""}, "events": {}},
    }

    if include_led:
        data["LEDDriver"] = {
            "data": {"initialized": SimpleNamespace(value=1 if led_initialized else 0)},
            "events": {
                "CAMERA": [FakeEvent(camera_active), None],
                "DONE": [FakeEvent(), None],
                "NONE": [FakeEvent(), None],
                "ERROR": [FakeEvent(), None],
            },
        }

    return data


def build_publisher(queue=None, request_success=True, response_code=200, heartbeat=True):
    fake_queue = queue or FakeQueue()
    fake_requests = Mock()
    fake_requests.sendAPIRequest.return_value = (
        request_success,
        response_code,
        "response body",
    )
    fake_requests.sendHeartbeat.return_value = heartbeat
    fake_transcriber = Mock()
    fake_transcriber.transcribe.return_value = "compost note"

    with patch("drivers.sensors.AsyncPublisher.RequestHandler", return_value=fake_requests):
        with patch(
            "drivers.sensors.AsyncPublisher.AudioTranscriber",
            return_value=fake_transcriber,
        ):
            publisher = AsyncPublisher(fake_queue, "commit-sha")

    publisher.data = build_data()
    return publisher, fake_queue, fake_requests, fake_transcriber


def test_initialize_sets_initialized_flag_without_cache():
    # initialize() should mark the publisher initialized when no cached packets exists
    publisher, queue, _, _ = build_publisher()

    with patch("drivers.sensors.AsyncPublisher.os.path.exists", return_value=False):
        publisher.initialize()

    assert publisher.data["AsyncPublisher"]["data"]["initialized"].value == 1
    assert queue.put_calls == []
    assert publisher.cachedQueue == {}


def test_initialize_requeues_cached_data():
    # initialize() should reload cached packets and requeue them for publishing
    publisher, queue, _, _ = build_publisher()
    cached_data = {
        "cached-uid": {
            "fileNames": sample_file_names(),
            "data": sample_data(user_trigger=False),
        }
    }

    with patch("drivers.sensors.AsyncPublisher.os.path.exists", return_value=True):
        with patch("builtins.open", mock_open()):
            with patch("drivers.sensors.AsyncPublisher.json.load", return_value=cached_data):
                publisher.initialize()

    assert publisher.cachedQueue == cached_data
    assert queue.put_calls == [
        (
            "cached-uid",
            cached_data["cached-uid"]["fileNames"],
            cached_data["cached-uid"]["data"],
            False,
        )
    ]


def test_initialize_handles_malformed_cache_file(caplog):
    # initialize() should repair malformed cache JSON and continue with an empty cache
    publisher, queue, _, _ = build_publisher()
    json_error = ValueError("bad json")

    with patch("drivers.sensors.AsyncPublisher.os.path.exists", return_value=True):
        with patch("builtins.open", mock_open()):
            with patch("drivers.sensors.AsyncPublisher.json.load", side_effect=json_error):
                with patch("drivers.sensors.AsyncPublisher.json.JSONDecodeError", ValueError):
                    with patch("drivers.sensors.AsyncPublisher.json.dump") as json_dump:
                        publisher.initialize()

    assert "Failed to load cached data file." in caplog.text
    json_dump.assert_called_once()
    assert json_dump.call_args.args[0] == {}
    assert publisher.cachedQueue == {}
    assert queue.put_calls == []


def test_measure_does_nothing_when_queue_empty():
    # measure() should do nothing when there are no packets waiting
    publisher, _, fake_requests, fake_transcriber = build_publisher()

    with patch("builtins.open", mock_open()) as open_mock:
        publisher.measure()

    fake_requests.sendAPIRequest.assert_not_called()
    fake_transcriber.transcribe.assert_not_called()
    open_mock.assert_not_called()
    assert publisher.cachedQueue == {}


def test_measure_success_user_trigger_transcribes_uploads_deletes_and_flashes_done():
    # Successful user-triggered publishes should transcribe, upload, delete files, and flash DONE
    file_names = sample_file_names()
    data = sample_data(user_trigger=True)
    queue = FakeQueue([("sample-uid", file_names, data, False)])
    publisher, _, fake_requests, fake_transcriber = build_publisher(queue=queue)
    expected_cached_packet_before_transcription = deepcopy(data)
    cache_snapshots = []

    def capture_cache_write(cache_contents, _file):
        # json.dump() receives publisher.cachedQueue directly. Store a copy so
        # later mutations do not change what this assertion is checking
        cache_snapshots.append(deepcopy(cache_contents))

    with patch("builtins.open", mock_open()):
        with patch("drivers.sensors.AsyncPublisher.json.dump") as json_dump:
            json_dump.side_effect = capture_cache_write
            with patch("drivers.sensors.AsyncPublisher.os.remove") as remove:
                with patch("drivers.sensors.AsyncPublisher.sleep") as sleep:
                    publisher.measure()

    fake_transcriber.transcribe.assert_called_once_with("../data/audio.wav")
    assert data["SoundController"]["data"]["TranscribedText"] == "compost note"
    fake_requests.sendAPIRequest.assert_called_once_with(file_names, data, "commit-sha")
    assert remove.call_args_list == [call(path) for path in file_names.values()]
    assert "sample-uid" not in publisher.cachedQueue
    assert cache_snapshots[0] == {
        "sample-uid": {
            "fileNames": file_names,
            "data": expected_cached_packet_before_transcription,
        }
    }
    assert cache_snapshots[-1] == {}
    assert publisher.data["LEDDriver"]["events"]["DONE"][0].set_calls == 1
    assert publisher.data["LEDDriver"]["events"]["NONE"][0].set_calls == 1
    sleep.assert_called_once_with(2)
    assert publisher.lastResponseCode == 200


def test_measure_success_non_user_trigger_reuses_last_transcription():
    # Non-user-triggered publishes should reuse the previous transcription
    file_names = sample_file_names()
    data = sample_data(user_trigger=False)
    queue = FakeQueue([("sample-uid", file_names, data, False)])
    publisher, _, fake_requests, fake_transcriber = build_publisher(queue=queue)
    publisher.lastTranscription = "previous note"

    with patch("builtins.open", mock_open()):
        with patch("drivers.sensors.AsyncPublisher.json.dump"):
            with patch("drivers.sensors.AsyncPublisher.os.remove"):
                with patch("drivers.sensors.AsyncPublisher.sleep"):
                    publisher.measure()

    fake_transcriber.transcribe.assert_not_called()
    assert data["SoundController"]["data"]["TranscribedText"] == "previous note"
    fake_requests.sendAPIRequest.assert_called_once_with(file_names, data, "commit-sha")


def test_measure_failure_sends_error_email_once_requeues_and_updates_connection():
    # Failed publishes should email once for a new response code, heartbeat, and requeue
    file_names = sample_file_names()
    data = sample_data(user_trigger=True)
    queue = FakeQueue([("sample-uid", file_names, data, False)])
    publisher, _, fake_requests, _ = build_publisher(
        queue=queue,
        request_success=False,
        response_code=503,
        heartbeat=False,
    )

    with patch("builtins.open", mock_open()):
        with patch("drivers.sensors.AsyncPublisher.json.dump"):
            publisher.measure()

    fake_requests.sendErrorEmail.assert_called_once_with(503, "response body")
    fake_requests.sendHeartbeat.assert_called_once_with()
    assert queue.put_calls == [("sample-uid", file_names, data, True)]
    assert publisher.cachedQueue == {"sample-uid": {"fileNames": file_names, "data": data}}
    assert publisher.isConnected is False
    assert publisher.lastResponseCode == 503


def test_measure_failure_does_not_repeat_error_email_for_same_response_code():
    # Repeated failure response codes should not send duplicate error emails
    file_names = sample_file_names()
    data = sample_data(user_trigger=True)
    queue = FakeQueue([("sample-uid", file_names, data, False)])
    publisher, _, fake_requests, _ = build_publisher(
        queue=queue,
        request_success=False,
        response_code=503,
    )
    publisher.lastResponseCode = 503

    with patch("builtins.open", mock_open()):
        with patch("drivers.sensors.AsyncPublisher.json.dump"):
            publisher.measure()

    fake_requests.sendErrorEmail.assert_not_called()
    assert queue.put_calls == [("sample-uid", file_names, data, True)]
    assert publisher.lastResponseCode == 503


def test_measure_when_disconnected_requeues_and_heartbeats_without_upload():
    # Disconnected publishers should skip upload, requeue, heartbeat, and sleep briefly
    file_names = sample_file_names()
    data = sample_data(user_trigger=False)
    queue = FakeQueue([("sample-uid", file_names, data, False)])
    publisher, _, fake_requests, fake_transcriber = build_publisher(
        queue=queue,
        heartbeat=True,
    )
    publisher.isConnected = False

    with patch("builtins.open", mock_open()):
        with patch("drivers.sensors.AsyncPublisher.json.dump"):
            with patch("drivers.sensors.AsyncPublisher.sleep") as sleep:
                publisher.measure()

    fake_requests.sendAPIRequest.assert_not_called()
    fake_transcriber.transcribe.assert_not_called()
    fake_requests.sendHeartbeat.assert_called_once_with()
    assert queue.put_calls == [("sample-uid", file_names, data, True)]
    assert publisher.isConnected is True
    sleep.assert_called_once_with(1)


# Failed publishes should flash ERROR when LEDs are initialized and camera mode is inactive
def test_measure_failure_flashes_error_when_led_initialized():
    file_names = sample_file_names()
    data = sample_data(user_trigger=True)
    queue = FakeQueue([("sample-uid", file_names, data, False)])
    publisher, _, _, _ = build_publisher(
        queue=queue,
        request_success=False,
        response_code=500,
    )

    with patch("builtins.open", mock_open()):
        with patch("drivers.sensors.AsyncPublisher.json.dump"):
            with patch("drivers.sensors.AsyncPublisher.sleep"):
                publisher.measure()

    assert publisher.data["LEDDriver"]["events"]["ERROR"][0].set_calls == 1
    assert publisher.data["LEDDriver"]["events"]["NONE"][0].set_calls == 1
