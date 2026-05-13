"""
Unit tests for SoundController event routing and audio management
"""

import sys
from types import SimpleNamespace

import pytest
from unittest.mock import Mock, call, patch

# Replace pyaudio with a stub
# SoundController imports Microphone/Speaker, which import pyaudio at module load
sys.modules.setdefault(
    "pyaudio",
    SimpleNamespace(paInt16=8, PyAudio=Mock),
)

from drivers.sensors.SoundController import SoundController


# Fake microphone that records lifecycle calls and returns configurable filenames
class FakeMicrophone:
    def __init__(self, recordings=None):
        self.recordings = list(recordings or ["../data/audio.wav"])
        self.initialize_calls = 0
        self.record_calls = 0
        self.kill_calls = 0

    def initialize(self):
        self.initialize_calls += 1

    def record(self):
        self.record_calls += 1
        if self.recordings:
            return self.recordings.pop(0)
        return ""

    def kill(self):
        self.kill_calls += 1


# Fake speaker that records mute, unmute, playback, and shutdown calls
class FakeSpeaker:
    def __init__(self):
        self.mute_calls = []
        self.unmute_calls = []
        self.play_calls = []
        self.kill_calls = 0

    def muteSpeaker(self, card_num):
        self.mute_calls.append(card_num)

    def unmuteSpeaker(self, card_num):
        self.unmute_calls.append(card_num)

    def playClip(self, clip):
        self.play_calls.append(clip)

    def kill(self):
        self.kill_calls += 1


# Fake pipe endpoint that records voice recording payloads sent to MainController
class FakeConnection:
    def __init__(self):
        self.send_calls = []

    def send(self, payload):
        self.send_calls.append(payload)


def wrap_events_for_manager(driver):
    for name, event in list(driver.events.items()):
        driver.events[name] = [event, None]


def build_controller(muted=False, recordings=None):
    fake_mic = FakeMicrophone(recordings=recordings)
    fake_speaker = FakeSpeaker()
    fake_connection = FakeConnection()

    with patch("drivers.sensors.SoundController.Microphone", return_value=fake_mic):
        with patch("drivers.sensors.SoundController.Speaker", return_value=fake_speaker):
            controller = SoundController(fake_connection, muted, record_duration=4)

    wrap_events_for_manager(controller)
    controller.data = controller.createDataDict()
    return controller, fake_mic, fake_speaker, fake_connection


# initialize() should mute audio paths, initialize the mic, and mark shared data ready
def test_initialize_mutes_audio_initializes_microphone_and_sets_initialized():
    controller, fake_mic, _, _ = build_controller()

    with patch.object(controller, "muteMic") as mute_mic:
        with patch.object(controller, "muteSpeaker") as mute_speaker:
            controller.initialize()

    mute_mic.assert_called_once_with()
    mute_speaker.assert_called_once_with()
    assert fake_mic.initialize_calls == 1
    assert controller.initialized is True
    assert controller.data["initialized"].value == 1


# playClip() should unmute the speaker, play exactly one clip, then mute again
def test_play_clip_unmutes_plays_and_remutes_speaker():
    controller, _, fake_speaker, _ = build_controller()

    controller.playClip("../media/noWifi.wav")

    assert fake_speaker.unmute_calls == [0]
    assert fake_speaker.play_calls == ["../media/noWifi.wav"]
    assert fake_speaker.mute_calls == [0]


@pytest.mark.parametrize(
    ("event_name", "clip"),
    [
        ("CONNECTED_TO_WIFI", "../media/connectionSuccessful.wav"),
        ("NO_WIFI", "../media/noWifi.wav"),
        ("WAIT_FOR_BLUETOOTH", "../media/bluetoothEnabled.wav"),
        ("BLUETOOTH_STOPPED", "../media/bluetoothTerminated.wav"),
        ("FAILED_TO_UPLOAD", "../media/failedToUpload.wav"),
        ("SERVER_ERROR", "../media/internalServerError.wav"),
        ("STOP_RECORDING", "../media/stopRecording.wav"),
        ("CLOSE_LID_TO_TARE", "../media/closeLidToTare.wav"),
    ],
)
def test_measure_plays_clip_and_clears_unmuted_sound_events(event_name, clip):
    # Unmuted sound events should play their cue and clear after one measure tick
    controller, _, _, _ = build_controller(muted=False)
    controller.playClip = Mock()
    controller.events[event_name][0].set()

    controller.measure()

    controller.playClip.assert_called_once_with(clip)
    assert not controller.events[event_name][0].is_set()


# Muted controllers should leave normal sound cue events set and play no clip
def test_measure_does_not_play_normal_cue_when_muted():
    controller, _, _, _ = build_controller(muted=True)
    controller.playClip = Mock()
    controller.events["NO_WIFI"][0].set()

    controller.measure()

    controller.playClip.assert_not_called()
    assert controller.events["NO_WIFI"][0].is_set()


# MUTED should play cue once, set muted state, and clear the event
def test_measure_muted_event_plays_cue_sets_muted_and_clears_event():
    controller, _, _, _ = build_controller(muted=False)
    controller.playClip = Mock()
    controller.events["MUTED"][0].set()

    controller.measure()

    controller.playClip.assert_called_once_with("../media/muted.wav")
    assert controller.isMuted is True
    assert not controller.events["MUTED"][0].is_set()


# UNMUTED should play its cue once, clear muted state, and clear the event
def test_measure_unmuted_event_plays_cue_unsets_muted_and_clears_event():
    controller, _, _, _ = build_controller(muted=True)
    controller.playClip = Mock()
    controller.events["UNMUTED"][0].set()

    controller.measure()

    controller.playClip.assert_called_once_with("../media/unmuted.wav")
    assert controller.isMuted is False
    assert not controller.events["UNMUTED"][0].is_set()


# RECORD should prompt, record once, send the filename payload, and clear the event
def test_measure_record_success_sends_voice_recording_and_clears_event():
    controller, fake_mic, _, fake_connection = build_controller(
        muted=False,
        recordings=["../data/voice.wav"],
    )
    controller.playClip = Mock()
    controller.unmuteMic = Mock()
    controller.muteMic = Mock()
    controller.events["RECORD"][0].set()

    controller.measure()

    assert controller.playClip.call_args_list == [
        call("../media/itemRequest.wav"),
        call("../media/startRecording.wav"),
    ]
    controller.unmuteMic.assert_called_once_with()
    controller.muteMic.assert_called_once_with()
    assert fake_mic.record_calls == 1
    assert fake_connection.send_calls == [{"voiceRecording": "../data/voice.wav"}]
    assert not controller.events["RECORD"][0].is_set()


# RECORD should retry empty recordings up to success and repeat the item prompt after failures
def test_measure_record_retries_empty_recording_until_success():
    controller, fake_mic, _, fake_connection = build_controller(
        muted=False,
        recordings=["", "", "../data/voice.wav"],
    )
    controller.playClip = Mock()
    controller.unmuteMic = Mock()
    controller.muteMic = Mock()
    controller.events["RECORD"][0].set()

    controller.measure()

    assert fake_mic.record_calls == 3
    assert controller.unmuteMic.call_count == 3
    assert controller.muteMic.call_count == 3
    assert controller.playClip.call_args_list == [
        call("../media/itemRequest.wav"),
        call("../media/startRecording.wav"),
        call("../media/itemRequest.wav"),
        call("../media/startRecording.wav"),
        call("../media/itemRequest.wav"),
        call("../media/startRecording.wav"),
    ]
    assert fake_connection.send_calls == [{"voiceRecording": "../data/voice.wav"}]
    assert not controller.events["RECORD"][0].is_set()


# Muted RECORD should skip the initial item prompt but still record and send audio
def test_measure_record_when_muted_skips_initial_prompt_but_records():
    controller, _, _, fake_connection = build_controller(
        muted=True,
        recordings=["../data/voice.wav"],
    )
    controller.playClip = Mock()
    controller.unmuteMic = Mock()
    controller.muteMic = Mock()
    controller.events["RECORD"][0].set()

    controller.measure()

    controller.playClip.assert_called_once_with("../media/startRecording.wav")
    assert fake_connection.send_calls == [{"voiceRecording": "../data/voice.wav"}]
    assert not controller.events["RECORD"][0].is_set()


# kill() should forward shutdown to both audio collaborators
def test_kill_forwards_to_microphone_and_speaker():
    controller, fake_mic, fake_speaker, _ = build_controller()

    controller.kill()

    assert fake_mic.kill_calls == 1
    assert fake_speaker.kill_calls == 1
