"""
Unit tests for the openBalena device-tag reporter.

The balena SDK is replaced by a recording fake, so no test contacts openBalena
and every identifier is synthetic.
"""

import threading
import time

import pytest

from drivers.BalenaTagReporter import (
    API_KEY_VARIABLE,
    API_URL_VARIABLE,
    DEVICE_UUID_VARIABLE,
    RETRY_MAX_DELAY_SECONDS,
    RETRY_INITIAL_DELAY_SECONDS,
    STATE_CALIBRATED,
    STATE_CALIBRATING,
    STATE_UNHEALTHY,
    TAG_KEY,
    BalenaTagReporter,
    _balena_host_from_api_url,
    next_retry_delay,
)

DEVICE_UUID = "fixture-device-uuid"
API_URL = "https://api.example.invalid"


class FrozenClock:
    """
    Monotonic clock that never advances, so the throttle window stays open and
    every retry deadline has already passed.
    """

    def __init__(self, now=1_000.0):
        self.now = now

    def __call__(self):
        return self.now


class AdvancingClock:
    """
    Monotonic clock that jumps past any pending retry deadline on every reading,
    so retry loops resolve without real waiting.
    """

    def __init__(self, step=10_000.0, now=1_000.0):
        self.now = now
        self._step = step

    def __call__(self):
        now = self.now
        self.now += self._step
        return now


class FakeTagResource:
    def __init__(self, calls, failures, hold, entered):
        self._calls = calls
        self._failures = failures
        self._hold = hold
        self._entered = entered

    def set(self, device_uuid, tag_key, value):
        """Records every attempt, including the ones that fail."""
        self._entered.set()
        if self._hold is not None:
            self._hold.wait(5.0)
        self._calls.append((device_uuid, tag_key, value))
        if self._failures:
            raise self._failures.pop(0)


class FakeDevice:
    def __init__(self, tags):
        self.tags = tags


class FakeModels:
    def __init__(self, device):
        self.device = device


class FakeClient:
    """
    Imitates balena.Balena. ``failures`` and ``hold`` are shared with the fake
    tag resource so tests can force retries and in-flight requests.
    """

    def __init__(self, calls, failures=None, hold=None, entered=None):
        failures = [] if failures is None else failures
        entered = threading.Event() if entered is None else entered
        self.entered = entered
        self.models = FakeModels(
            FakeDevice(FakeTagResource(calls, failures, hold, entered))
        )


def make_reporter(client_factory, clock=None):
    return BalenaTagReporter(
        tag_key=TAG_KEY,
        device_uuid=DEVICE_UUID,
        client_factory=client_factory,
        clock=clock or AdvancingClock(),
    )


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


@pytest.fixture(name="calls")
def calls_fixture():
    return []


def test_tag_key_matches_the_documented_contract():
    assert TAG_KEY == "BME688_CALIBRATED_STATE"


def test_api_url_is_reduced_to_a_balena_host():
    # The SDK builds its endpoint as https://api.<balena_host>/, so both the
    # full API address and the bare host must configure the same host.
    for api_url in (
        "https://api.example.invalid",
        "https://api.example.invalid/",
        "https://api.example.invalid/v7",
        "api.example.invalid",
        "example.invalid",
    ):
        assert _balena_host_from_api_url(api_url) == "example.invalid"

    assert _balena_host_from_api_url("https://api.example.invalid:8443") == (
        "example.invalid:8443"
    )
    assert _balena_host_from_api_url("https://other.example.invalid") == (
        "other.example.invalid"
    )


@pytest.mark.parametrize("api_url", ["", "   ", "https://", "https://api."])
def test_unusable_api_urls_yield_no_host(api_url):
    assert _balena_host_from_api_url(api_url) is None


def test_set_state_publishes_the_exact_tag_contract(calls):
    reporter = make_reporter(lambda: FakeClient(calls))
    try:
        assert reporter.set_state(STATE_CALIBRATED) is True
        assert wait_for(lambda: len(calls) == 1)
    finally:
        reporter.close()

    assert calls == [(DEVICE_UUID, TAG_KEY, STATE_CALIBRATED)]


def test_acknowledged_duplicates_are_suppressed(calls):
    reporter = make_reporter(lambda: FakeClient(calls))
    try:
        reporter.set_state(STATE_CALIBRATED)
        assert wait_for(lambda: len(calls) == 1)
        assert wait_for(lambda: reporter.acknowledged_state == STATE_CALIBRATED)

        assert reporter.set_state(STATE_CALIBRATED) is False
        time.sleep(0.1)
        assert len(calls) == 1
    finally:
        reporter.close()


def test_state_is_republished_on_every_process_start(calls):
    for _ in range(2):
        published = len(calls)
        reporter = make_reporter(lambda: FakeClient(calls))
        try:
            reporter.set_state(STATE_CALIBRATED)
            assert wait_for(lambda: len(calls) == published + 1)
        finally:
            reporter.close()

    assert [value for _, _, value in calls] == [
        STATE_CALIBRATED,
        STATE_CALIBRATED,
    ]


def test_a_newer_state_replaces_a_pending_older_state(calls):
    hold = threading.Event()
    entered = threading.Event()
    reporter = make_reporter(lambda: FakeClient(calls, hold=hold, entered=entered))
    try:
        reporter.set_state(STATE_CALIBRATING)
        assert entered.wait(5.0)

        # CALIBRATED only becomes pending; UNHEALTHY supersedes it before the
        # worker picks it up.
        reporter.set_state(STATE_CALIBRATED)
        assert reporter.set_state(STATE_UNHEALTHY) is True

        hold.set()
        assert wait_for(lambda: len(calls) == 2)
    finally:
        hold.set()
        reporter.close()

    assert [value for _, _, value in calls] == [STATE_CALIBRATING, STATE_UNHEALTHY]


def test_an_older_in_flight_response_does_not_discard_a_newer_update(calls):
    hold = threading.Event()
    entered = threading.Event()
    reporter = make_reporter(lambda: FakeClient(calls, hold=hold, entered=entered))
    try:
        reporter.set_state(STATE_CALIBRATING)
        assert entered.wait(5.0)
        reporter.set_state(STATE_UNHEALTHY)

        hold.set()
        assert wait_for(lambda: len(calls) == 2)
        assert wait_for(lambda: reporter.acknowledged_state == STATE_UNHEALTHY)

        # CALIBRATING was never acknowledged in this process, so it is not
        # suppressed even though openBalena saw it first.
        assert reporter.set_state(STATE_CALIBRATING) is True
    finally:
        hold.set()
        reporter.close()

    assert [value for _, _, value in calls][:2] == [STATE_CALIBRATING, STATE_UNHEALTHY]


def test_failures_are_retried_until_acknowledged(calls):
    failures = [RuntimeError("first"), RuntimeError("second")]
    reporter = make_reporter(lambda: FakeClient(calls, failures=failures))
    try:
        reporter.set_state(STATE_CALIBRATED)
        assert wait_for(lambda: len(calls) == 3)
        assert wait_for(lambda: reporter.acknowledged_state == STATE_CALIBRATED)
    finally:
        reporter.close()

    assert [value for _, _, value in calls] == [STATE_CALIBRATED] * 3


def test_retry_backoff_doubles_to_the_documented_maximum():
    delay = RETRY_INITIAL_DELAY_SECONDS
    observed = []
    for _ in range(10):
        observed.append(delay)
        delay = next_retry_delay(delay)

    assert observed[:3] == [5.0, 10.0, 20.0]
    assert observed[-1] == RETRY_MAX_DELAY_SECONDS


def test_backoff_is_abandoned_when_a_newer_state_arrives(calls):
    failures = [RuntimeError] * 100
    reporter = make_reporter(lambda: FakeClient(calls, failures=failures))
    try:
        reporter.set_state(STATE_CALIBRATING)
        assert wait_for(lambda: reporter._last_failure_log is not None)
        stale_sequence = reporter._sequence - 1
        assert reporter._wait_before_retry(5.0, stale_sequence) is None
    finally:
        reporter.close()


def test_failure_logs_are_throttled(calls, caplog):
    failures = [RuntimeError] * 50
    reporter = make_reporter(lambda: FakeClient(calls, failures=failures), FrozenClock())
    try:
        with caplog.at_level("WARNING"):
            reporter.set_state(STATE_UNHEALTHY)
            assert wait_for(lambda: reporter._last_failure_log is not None)
            time.sleep(0.2)
    finally:
        reporter.close()

    warnings = [
        record for record in caplog.records if "Reporting Balena device tag" in record.message
    ]
    assert len(warnings) == 1


def test_failure_logs_omit_credentials_and_request_details(calls, caplog):
    failures = [RuntimeError("token=fixture-secret url=https://api.example.invalid")]
    reporter = make_reporter(lambda: FakeClient(calls, failures=failures), FrozenClock())
    try:
        with caplog.at_level("WARNING"):
            reporter.set_state(STATE_UNHEALTHY)
            assert wait_for(lambda: reporter._last_failure_log is not None)
    finally:
        reporter.close()

    text = "\n".join(record.message for record in caplog.records)
    assert "fixture-secret" not in text
    assert "RuntimeError" in text


def test_from_environment_builds_the_sdk_client(calls):
    built = []

    def client_factory():
        built.append(True)
        return FakeClient(calls)

    reporter = BalenaTagReporter.from_environment(
        environ={
            API_URL_VARIABLE: API_URL,
            API_KEY_VARIABLE: "fixture-api-key",
            DEVICE_UUID_VARIABLE: DEVICE_UUID,
        },
        client_factory=client_factory,
    )
    try:
        assert reporter is not None
        assert reporter.tag_key == TAG_KEY
        reporter.set_state(STATE_CALIBRATED)
        assert wait_for(lambda: bool(built))
        assert wait_for(lambda: len(calls) == 1)
    finally:
        reporter.close()

    assert calls == [(DEVICE_UUID, TAG_KEY, STATE_CALIBRATED)]


def test_from_environment_is_disabled_and_warns_once_without_credentials(caplog):
    with caplog.at_level("WARNING"):
        reporter = BalenaTagReporter.from_environment(environ={})

    assert reporter is None
    warnings = [
        record
        for record in caplog.records
        if "device-tag reporting is disabled" in record.message
    ]
    assert len(warnings) == 1
    for name in (API_URL_VARIABLE, API_KEY_VARIABLE, DEVICE_UUID_VARIABLE):
        assert name in warnings[0].message


def test_from_environment_is_disabled_for_an_unusable_api_url(caplog):
    with caplog.at_level("WARNING"):
        reporter = BalenaTagReporter.from_environment(
            environ={
                API_URL_VARIABLE: "https://",
                API_KEY_VARIABLE: "fixture-api-key",
                DEVICE_UUID_VARIABLE: DEVICE_UUID,
            }
        )

    assert reporter is None
    assert any("not a usable API address" in record.message for record in caplog.records)


def test_set_state_after_close_is_ignored(calls):
    reporter = make_reporter(lambda: FakeClient(calls))
    reporter.close()

    assert reporter.set_state(STATE_CALIBRATED) is False
    time.sleep(0.1)
    assert calls == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
