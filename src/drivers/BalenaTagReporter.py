"""
Publishes device health state as an openBalena device tag.

The reporter owns a single worker thread so callers never block on the network.
Only the newest desired value is retained, and values that openBalena has already
acknowledged are suppressed. Reporting is best effort: every failure is retried
with exponential backoff and logged without credentials or raw request data, and
no failure is allowed to reach the caller.
"""

import logging
import os
import threading
from time import monotonic
from typing import Any, Callable
from urllib.parse import urlsplit

# Cross-repository contract: dashboards and fleet queries read this exact name.
TAG_KEY = "BME688_CALIBRATED_STATE"

STATE_UNHEALTHY = "UNHEALTHY"
STATE_CALIBRATING = "CALIBRATING"
STATE_CALIBRATED = "CALIBRATED"

API_URL_VARIABLE = "BALENA_API_URL"
API_KEY_VARIABLE = "BALENA_API_KEY"
DEVICE_UUID_VARIABLE = "BALENA_DEVICE_UUID"

REQUIRED_VARIABLES = (API_URL_VARIABLE, API_KEY_VARIABLE, DEVICE_UUID_VARIABLE)

# The SDK documents this setting in milliseconds. TLS verification is left at
# the requests default; nothing here disables certificate checking.
SDK_TIMEOUT_MILLISECONDS = "5000"

RETRY_INITIAL_DELAY_SECONDS = 5.0
RETRY_MAX_DELAY_SECONDS = 300.0
LOG_THROTTLE_SECONDS = 60.0
SHUTDOWN_TIMEOUT_SECONDS = 10.0


def _balena_host_from_api_url(api_url: str) -> str | None:
    """
    Reduce a configured API address to the host the balena SDK expects.

    The SDK builds ``api_endpoint`` as ``https://api.<balena_host>/``, so a
    leading ``api.`` label is removed. Both ``https://api.example.invalid`` and
    ``example.invalid`` therefore configure the same host.
    """

    candidate = api_url.strip()
    if not candidate:
        return None

    if "//" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlsplit(candidate)
    if not parsed.hostname:
        return None

    host = parsed.hostname
    if host.startswith("api."):
        host = host[len("api.") :]

    if not host:
        return None

    if parsed.port:
        return f"{host}:{parsed.port}"
    return host


def _default_client_factory(api_host: str, api_key: str) -> Any:
    """
    Build a balena SDK client. Importing and constructing the SDK happens here
    so that a missing or broken dependency disables reporting instead of
    breaking the driver module import.
    """

    from balena import Balena

    client = Balena(
        {
            "balena_host": api_host,
            "timeout": SDK_TIMEOUT_MILLISECONDS,
            # Keep the API key in memory instead of writing ~/.balena/balena.cfg.
            "data_directory": False,
        }
    )
    client.auth.login_with_token(api_key)
    return client


def next_retry_delay(delay: float) -> float:
    """
    Double the retry delay, capped at the documented maximum.
    """

    return min(delay * 2, RETRY_MAX_DELAY_SECONDS)


class BalenaTagReporter:
    """
    Serialize device tag writes onto one worker thread.

    :param tag_key: Device tag name to publish
    :param device_uuid: UUID of the device that owns the tag
    :param client_factory: Callable returning an SDK client, injected by tests
    :param clock: Monotonic time source, injected by tests
    """

    def __init__(
        self,
        tag_key: str,
        device_uuid: str,
        client_factory: Callable[[], Any],
        clock: Callable[[], float] = monotonic,
    ):
        self._tag_key = tag_key
        self._device_uuid = device_uuid
        self._client_factory = client_factory
        self._clock = clock

        self._condition = threading.Condition()
        self._desired_state: str | None = None
        # Never acknowledged in this process, so startup always republishes.
        self._acknowledged_state: str | None = None
        self._sequence = 0
        self._stopping = False
        self._client_instance: Any | None = None
        self._last_failure_log: float | None = None

        self._worker = threading.Thread(
            target=self._run, name="balena-tag-reporter", daemon=True
        )
        self._worker.start()

    """
    Build a reporter from the service environment, or return None and warn once
    when reporting is not configured.
    """

    @classmethod
    def from_environment(
        cls,
        tag_key: str = TAG_KEY,
        environ: dict | None = None,
        client_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> "BalenaTagReporter | None":
        source = os.environ if environ is None else environ
        values = {
            name: (source.get(name) or "").strip() for name in REQUIRED_VARIABLES
        }
        missing = [name for name, value in values.items() if not value]

        if missing:
            logging.warning(
                "Balena device-tag reporting is disabled; missing configuration: %s",
                ", ".join(missing),
            )
            return None

        api_host = _balena_host_from_api_url(values[API_URL_VARIABLE])
        if api_host is None:
            logging.warning(
                "Balena device-tag reporting is disabled; %s is not a usable API address",
                API_URL_VARIABLE,
            )
            return None

        api_key = values[API_KEY_VARIABLE]
        factory = client_factory or (
            lambda: _default_client_factory(api_host, api_key)
        )

        return cls(
            tag_key=tag_key,
            device_uuid=values[DEVICE_UUID_VARIABLE],
            client_factory=factory,
            clock=clock,
        )

    @property
    def tag_key(self) -> str:
        return self._tag_key

    @property
    def acknowledged_state(self) -> str | None:
        with self._condition:
            return self._acknowledged_state

    """
    Queue a state for publication without contacting openBalena.

    Returns True when the state was queued for publication and False when the
    update was suppressed as an acknowledged or already queued duplicate.
    """

    def set_state(self, state: str) -> bool:
        with self._condition:
            if self._stopping:
                return False
            if state == self._acknowledged_state or state == self._desired_state:
                return False

            self._desired_state = state
            self._sequence += 1
            self._condition.notify_all()
            return True

    """
    Stop the worker. Any state that has not been published is dropped; the next
    process start derives the state again from initialization and saved
    calibration.
    """

    def close(self, timeout: float = SHUTDOWN_TIMEOUT_SECONDS) -> None:
        with self._condition:
            self._stopping = True
            self._condition.notify_all()

        if self._worker.is_alive() and threading.current_thread() is not self._worker:
            self._worker.join(timeout)

    def _run(self) -> None:
        while True:
            with self._condition:
                while self._desired_state is None and not self._stopping:
                    self._condition.wait()
                if self._stopping:
                    return
                state = self._desired_state
                self._desired_state = None
                sequence = self._sequence

            self._publish_until_settled(state, sequence)

    def _publish_until_settled(self, state: str, sequence: int) -> None:
        delay = RETRY_INITIAL_DELAY_SECONDS

        while True:
            try:
                self._client().models.device.tags.set(
                    self._device_uuid, self._tag_key, state
                )
            except Exception as error:
                self._log_failure(error)
                delay = self._wait_before_retry(delay, sequence)
                if delay is None:
                    return
                continue

            with self._condition:
                # A newer state arrived while this request was in flight, so the
                # response cannot be treated as the current published value.
                if not self._stopping and self._sequence == sequence:
                    self._acknowledged_state = state

            logging.info("Reported Balena device tag %s=%s", self._tag_key, state)
            return

    """
    Wait out the backoff delay. Returns the next delay, or None when a newer
    state or shutdown supersedes this retry.
    """

    def _wait_before_retry(self, delay: float, sequence: int) -> float | None:
        with self._condition:
            deadline = self._clock() + delay
            while (
                not self._stopping
                and self._sequence == sequence
                and self._clock() < deadline
            ):
                self._condition.wait(timeout=max(deadline - self._clock(), 0.0))

            if self._stopping or self._sequence != sequence:
                return None

        return next_retry_delay(delay)

    def _client(self) -> Any:
        if self._client_instance is None:
            self._client_instance = self._client_factory()
        return self._client_instance

    """
    Log at most one failure per throttle window. Only the exception type is
    recorded so credentials and request payloads cannot reach the logs.
    """

    def _log_failure(self, error: Exception) -> None:
        now = self._clock()
        with self._condition:
            if (
                self._last_failure_log is not None
                and now - self._last_failure_log < LOG_THROTTLE_SECONDS
            ):
                return
            self._last_failure_log = now

        logging.warning(
            "Reporting Balena device tag %s failed (%s); will retry",
            self._tag_key,
            type(error).__name__,
        )
