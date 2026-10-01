"""Transcription lifecycle and upload retries, without models or Pi hardware."""

import json
import multiprocessing
import os
from pathlib import Path
from queue import Queue
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from drivers.sensors.AudioTranscriber import AudioTranscriber
from drivers.sensors.AsyncPublisher import AsyncPublisher
from drivers.ThreadedDriver import ThreadedDriver


class FakeRequests:
    def __init__(self):
        self.uploads = []
        self.responses = [(True, 200, "ok")]

    def sendAPIRequest(self, files, data):
        self.uploads.append((files, data))
        return self.responses.pop(0)

    def sendHeartbeat(self):
        return True


class UnpicklableModel:
    def __init__(self, *args, **kwargs):
        self.pid = os.getpid()

    def __getstate__(self):
        raise TypeError("A native model must not cross a process boundary")


def create_fake_model_files(directory):
    for filename in ("model.bin", "config.json", "tokenizer.json"):
        (Path(directory) / filename).write_bytes(b"synthetic model fixture")


def initialize_in_child(publisher, model_dir, result):
    with patch.dict(os.environ, {"WHISPER_MODEL_PATH": model_dir}):
        with patch.dict("sys.modules", {"faster_whisper": SimpleNamespace(WhisperModel=UnpicklableModel)}):
            publisher.initialize()
    result.put((os.getpid(), publisher.transcriber.model.pid))


class AudioTranscriberTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        create_fake_model_files(self.temp.name)
        self.factory = Mock()
        patcher = patch.dict("sys.modules", {"faster_whisper": SimpleNamespace(WhisperModel=self.factory)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_loads_only_a_local_cpu_model(self):
        with patch.dict(os.environ, {"WHISPER_CPU_THREADS": "1"}):
            AudioTranscriber(self.temp.name)
        self.factory.assert_called_once_with(
            self.temp.name, device="cpu", compute_type="int8",
            cpu_threads=1, local_files_only=True,
        )

    def test_missing_model_never_falls_back_to_a_download(self):
        with self.assertRaises(FileNotFoundError):
            AudioTranscriber(str(Path(self.temp.name) / "missing"))
        self.factory.assert_not_called()

    def test_missing_tokenizer_never_falls_back_to_a_download(self):
        (Path(self.temp.name) / "tokenizer.json").unlink()
        with self.assertRaises(FileNotFoundError):
            AudioTranscriber(self.temp.name)
        self.factory.assert_not_called()

    def test_consumes_segments_and_preserves_the_string_contract(self):
        model = self.factory.return_value
        model.transcribe.return_value = (
            iter([SimpleNamespace(text=" apple"), SimpleNamespace(text=" peel ")]), None,
        )
        transcriber = AudioTranscriber(self.temp.name)
        self.assertEqual(transcriber.transcribe("synthetic.wav"), "apple peel")
        model.transcribe.assert_called_once_with("synthetic.wav", language="en", beam_size=5)

    def test_silence_returns_an_empty_string(self):
        self.factory.return_value.transcribe.return_value = (iter([]), None)
        self.assertEqual(AudioTranscriber(self.temp.name).transcribe("silence.wav"), "")


class PublisherTranscriptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        create_fake_model_files(root)
        self.data_dir = root / "data"
        self.data_dir.mkdir()
        (root / "src").mkdir()
        self.previous_dir = Path.cwd()
        os.chdir(root / "src")
        self.addCleanup(os.chdir, self.previous_dir)
        self.cache = self.data_dir / "cachedData.dat"
        self.requests = FakeRequests()
        request_patcher = patch("drivers.sensors.AsyncPublisher.RequestHandler", return_value=self.requests)
        request_patcher.start()
        self.addCleanup(request_patcher.stop)
        sleep_patcher = patch("drivers.sensors.AsyncPublisher.sleep")
        sleep_patcher.start()
        self.addCleanup(sleep_patcher.stop)

    def publisher(self, queue=None):
        publisher = AsyncPublisher(queue if queue is not None else Queue())
        publisher.data = {"AsyncPublisher": {"data": publisher.createDataDict()}}
        return publisher

    def enqueue(self, publisher, uid="synthetic-scan", user_trigger=True):
        files = {}
        for field in ["voiceRecording", "colorImage", "depthImage", "heatmapImage", "topologyMap"]:
            path = self.data_dir / f"{uid}-{field}"
            path.write_bytes(b"synthetic fixture")
            files[field] = str(path)
        data = {
            "DriverManager": {"data": {"userTrigger": user_trigger}},
            "SoundController": {"data": {"TranscribedText": ""}},
        }
        publisher.dataQueue.put((uid, files, data, False))
        return files

    def test_constructor_does_not_load_a_native_model(self):
        with patch("drivers.sensors.AsyncPublisher.AudioTranscriber") as factory:
            publisher = self.publisher()
        factory.assert_not_called()
        self.assertIsNone(publisher.transcriber)

    def test_forkserver_initializes_the_model_only_in_the_child(self):
        context = multiprocessing.get_context("forkserver")
        queue = context.Queue()
        result = context.Queue()
        self.addCleanup(queue.close)
        self.addCleanup(result.close)
        publisher = self.publisher(queue)
        process = context.Process(
            target=initialize_in_child,
            args=(publisher, self.temp.name, result),
        )
        process.start()
        try:
            child_pid, model_pid = result.get(timeout=10)
            process.join(timeout=10)
            self.assertEqual(process.exitcode, 0)
            self.assertEqual(child_pid, model_pid)
            self.assertNotEqual(model_pid, os.getpid())
            self.assertIsNone(publisher.transcriber)
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            process.close()

    def test_model_load_failure_is_retried_without_losing_the_scan(self):
        publisher = self.publisher()
        files = self.enqueue(publisher)
        transcriber = Mock()
        transcriber.transcribe.return_value = "apple peel"
        with patch("drivers.sensors.AsyncPublisher.AudioTranscriber", side_effect=[RuntimeError("model unavailable"), transcriber]):
            with self.assertLogs(level="ERROR"):
                publisher.initialize()
            self.assertEqual(publisher.data["AsyncPublisher"]["data"]["initialized"].value, 0)
            publisher.measure()
        self.assertEqual(publisher.data["AsyncPublisher"]["data"]["initialized"].value, 1)
        self.assertEqual(len(self.requests.uploads), 1)
        self.assertTrue(all(not Path(path).exists() for path in files.values()))

    def test_failed_scan_is_requeued_and_survives_restart(self):
        publisher = self.publisher()
        files = self.enqueue(publisher)
        publisher.transcriber = Mock()
        publisher.transcriber.transcribe.side_effect = RuntimeError("bad audio")
        with self.assertLogs(level="ERROR"):
            publisher.measure()
        self.assertEqual(publisher.dataQueue.qsize(), 1)
        self.assertEqual(self.requests.uploads, [])
        self.assertTrue(all(Path(path).exists() for path in files.values()))
        self.assertIn("synthetic-scan", json.loads(self.cache.read_text()))

        restarted = self.publisher()
        with patch("drivers.sensors.AsyncPublisher.AudioTranscriber") as factory:
            factory.return_value.transcribe.return_value = "apple peel"
            restarted.initialize()
            restarted.measure()
        self.assertEqual(self.requests.uploads[0][1]["SoundController"]["data"]["TranscribedText"], "apple peel")
        self.assertEqual(json.loads(self.cache.read_text()), {})
        self.assertTrue(all(not Path(path).exists() for path in files.values()))

    def test_generator_failure_does_not_kill_the_worker(self):
        def failed_segments():
            yield SimpleNamespace(text="partial")
            raise RuntimeError("inference failed during iteration")

        publisher = self.publisher()
        self.enqueue(publisher)
        publisher.transcriber = AudioTranscriber.__new__(AudioTranscriber)
        publisher.transcriber.model = Mock()
        publisher.transcriber.model.transcribe.side_effect = [
            (failed_segments(), None),
            (iter([SimpleNamespace(text=" apple peel")]), None),
        ]
        worker = ThreadedDriver(publisher, publisher.data["AsyncPublisher"]["data"])
        send_request = self.requests.sendAPIRequest
        measure = publisher.measure
        iterations = 0

        def bounded_measure():
            nonlocal iterations
            iterations += 1
            self.assertLessEqual(iterations, 3, "The worker did not retry the scan")
            measure()

        def upload_and_stop(files, data):
            worker.isRunning = False
            return send_request(files, data)

        with patch.object(self.requests, "sendAPIRequest", side_effect=upload_and_stop):
            with patch.object(publisher, "measure", side_effect=bounded_measure):
                with patch("drivers.ThreadedDriver.sleep"):
                    with self.assertLogs(level="ERROR"):
                        worker.run()
        self.assertEqual(iterations, 2)
        self.assertEqual(len(self.requests.uploads), 1)
        self.assertEqual(self.requests.uploads[0][1]["SoundController"]["data"]["TranscribedText"], "apple peel")
        self.assertTrue(publisher.dataQueue.empty())

    def test_files_are_deleted_only_after_server_acknowledgement(self):
        publisher = self.publisher()
        files = self.enqueue(publisher)
        publisher.transcriber = Mock()
        publisher.transcriber.transcribe.return_value = "apple peel"
        self.requests.responses = [(False, 503, "unavailable"), (True, 200, "ok")]
        publisher.measure()
        self.assertTrue(all(Path(path).exists() for path in files.values()))
        self.assertIn("synthetic-scan", json.loads(self.cache.read_text()))
        publisher.measure()
        self.assertTrue(all(not Path(path).exists() for path in files.values()))
        self.assertEqual(json.loads(self.cache.read_text()), {})

    def test_failed_recording_does_not_block_other_queued_scans(self):
        publisher = self.publisher()
        self.enqueue(publisher, "bad-audio")
        self.enqueue(publisher, "good-audio")
        publisher.transcriber = Mock()
        publisher.transcriber.transcribe.side_effect = [RuntimeError("bad audio"), "apple peel"]
        with self.assertLogs(level="ERROR"):
            publisher.measure()
        publisher.measure()
        self.assertEqual(len(self.requests.uploads), 1)
        self.assertEqual(set(json.loads(self.cache.read_text())), {"bad-audio"})


if __name__ == "__main__":
    unittest.main()
