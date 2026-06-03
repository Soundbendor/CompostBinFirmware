"""
Unit tests for the helpers package public classes
External stuff such as network, AWS, SMTP, logging files, and /proc/cpuinfo are mocked
"""

import json
import logging
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, Mock, call, mock_open, patch

import pytest

# Stub module types
botocore_stub = ModuleType("botocore")
exceptions_stub = ModuleType("botocore.exceptions")
secrets_cache_stub = ModuleType("aws_secretsmanager_caching")
httpx_stub = ModuleType("httpx")


# Stub for botocore's missing-credentials exception type
class NoCredentialsError(Exception):
    pass


# Stub for botocore's partial-credentials exception type
class PartialCredentialsError(Exception):
    pass


exceptions_stub.NoCredentialsError = NoCredentialsError
exceptions_stub.PartialCredentialsError = PartialCredentialsError
secrets_cache_stub.SecretCache = object
secrets_cache_stub.SecretCacheConfig = object
httpx_stub.Client = object

sys.modules.setdefault("botocore", botocore_stub)
sys.modules.setdefault("botocore.exceptions", exceptions_stub)
sys.modules.setdefault("aws_secretsmanager_caching", secrets_cache_stub)
sys.modules.setdefault("httpx", httpx_stub)

import helpers
from helpers import CalibrationLoader, Logging, RequestHandler, TimeHelper


def build_request_handler():
    handler = RequestHandler.__new__(RequestHandler)
    handler.secret_file = "config.secret"
    handler.dataDir = "../data"
    handler.apiKey = "api-token"
    handler.endpoint = "https://api.example.test:443"
    handler.port = 443
    handler.serial = "device-serial"
    handler.appPassword = "app-password"
    handler.emailAddress = "alerts@example.test"
    handler.gotEmailCreds = True
    return handler


def sample_file_names():
    return {
        "colorImage": "../data/color.jpg",
        "depthImage": "../data/depth.npy",
        "heatmapImage": "../data/heatmap.jpg",
        "topologyMap": "../data/topology.npy",
        "voiceRecording": "../data/audio.wav",
    }


def sample_sensor_data():
    return {
        "NAU7802": {"data": {"weight": "12.5", "weight_delta": "1.25"}},
        "BME688": {
            "data": {
                "temperature(c)": "20.1",
                "pressure(kpa)": "101.2",
                "humidity(%rh)": "45.3",
                "iaq": "25.0",
                "CO2-eq": "500.0",
                "bVOC-eq": "0.5",
            }
        },
        "SoundController": {"data": {"TranscribedText": "banana peel"}},
        "DriverManager": {"data": {"userTrigger": True}},
    }


# TimeHelper should seed lastTime from the current clock value
def test_time_helper_initializes_last_time_from_time():
    with patch("helpers.time", return_value=123.4):
        helper = TimeHelper()

    assert helper.lastTime == 123.4


# 2h-multiple timestamps should not trigger the two-hour collection interval
def test_two_hour_interval_returns_false_when_not_at_multiple():
    helper = TimeHelper.__new__(TimeHelper)
    helper.lastTime = 1

    with patch("helpers.time", return_value=helpers.TWO_HOURS_SECONDS + 1):
        assert helper.twoHourInterval() is False

    assert helper.lastTime == 1


# Non 2h-multiple timestamps should trigger once and then be suppressed until time changes
def test_two_hour_interval_returns_true_once_per_multiple_timestamp():
    helper = TimeHelper.__new__(TimeHelper)
    helper.lastTime = 0

    with patch("helpers.time", return_value=helpers.TWO_HOURS_SECONDS):
        assert helper.twoHourInterval() is True
        assert helper.twoHourInterval() is False

    assert helper.lastTime == helpers.TWO_HOURS_SECONDS


# Logging should default to console INFO logging when no output file is provided
def test_logging_configures_info_console_logging_by_default():
    with patch("helpers.sys.argv", ["main.py"]):
        with patch("helpers.logging.basicConfig") as basic_config:
            with patch("helpers.logging.info") as log_info:
                Logging()

    basic_config.assert_called_once()
    assert basic_config.call_args.kwargs["level"] == logging.INFO
    assert "format" in basic_config.call_args.kwargs
    assert "handlers" not in basic_config.call_args.kwargs
    log_info.assert_called_once()


# Logging should lower console verbosity to WARNING when verbose mode is disabled
def test_logging_configures_warning_console_logging_when_not_verbose():
    with patch("helpers.sys.argv", ["main.py"]):
        with patch("helpers.logging.basicConfig") as basic_config:
            with patch("helpers.logging.info"):
                Logging(verbose=False)

    basic_config.assert_called_once()
    assert basic_config.call_args.kwargs["level"] == logging.WARNING


# Logging should attach file and stream handlers when sys.argv includes a log path
def test_logging_configures_file_and_stream_handlers_when_log_path_supplied():
    fake_file_handler = Mock(name="file_handler")
    fake_stream_handler = Mock(name="stream_handler")

    with patch("helpers.sys.argv", ["main.py", "bucket.log"]):
        with patch("helpers.logging.FileHandler", return_value=fake_file_handler) as file_handler:
            with patch(
                "helpers.logging.StreamHandler",
                return_value=fake_stream_handler,
            ) as stream_handler:
                with patch("helpers.logging.basicConfig") as basic_config:
                    Logging(verbose=False)

    file_handler.assert_called_once_with("bucket.log")
    stream_handler.assert_called_once_with()
    basic_config.assert_called_once()
    assert basic_config.call_args.kwargs["level"] == logging.INFO
    assert basic_config.call_args.kwargs["handlers"] == [
        fake_file_handler,
        fake_stream_handler,
    ]


# CalibrationLoader should read JSON calibration data and return requested fields
def test_calibration_loader_loads_json_and_returns_fields():
    calibration_data = {"NAU7802_CALIBRATION_FACTOR": 42.5}

    with patch("helpers.open", mock_open(), create=True) as open_mock:
        with patch("helpers.json.load", return_value=calibration_data) as json_load:
            loader = CalibrationLoader("CalibrationDetails.json")

    open_mock.assert_called_once_with("CalibrationDetails.json", "r")
    json_load.assert_called_once()
    assert loader.data == calibration_data
    assert loader.get("NAU7802_CALIBRATION_FACTOR") == 42.5


# CalibrationLoader should preserve the current KeyError behavior for missing fields
def test_calibration_loader_missing_field_raises_key_error():
    loader = CalibrationLoader.__new__(CalibrationLoader)
    loader.data = {}

    with pytest.raises(KeyError):
        loader.get("missing")


# RequestHandler construction should load credentials, email settings, and serial state
def test_request_handler_constructor_loads_credentials_and_formats_endpoint():
    with patch.object(RequestHandler, "loadFastAPICredentials", return_value=("api-key", "api.example.test", 8443)) as load_api:
        with patch.object(RequestHandler, "loadEmailCredentials", return_value=("app-password", "alerts@example.test")) as load_email:
            with patch.object(RequestHandler, "_getSerial", return_value="serial-123") as get_serial:
                with patch("helpers.logging.basicConfig"):
                    handler = RequestHandler(
                        dataDir="../custom-data",
                        secret_file="custom.secret",
                    )

    load_api.assert_called_once_with("custom.secret")
    load_email.assert_called_once_with()
    get_serial.assert_called_once_with()
    assert handler.secret_file == "custom.secret"
    assert handler.dataDir == "../custom-data"
    assert handler.apiKey == "api-key"
    assert handler.endpoint == "https://api.example.test:8443"
    assert handler.port == 8443
    assert handler.appPassword == "app-password"
    assert handler.emailAddress == "alerts@example.test"
    assert handler.gotEmailCreds is True
    assert handler.serial == "serial-123"


# RequestHandler should record that email credentials are missing when AWS lookup fails
def test_request_handler_constructor_marks_email_credentials_missing():
    with patch.object(RequestHandler, "loadFastAPICredentials", return_value=("api-key", "api.example.test", 8443)):
        with patch.object(RequestHandler, "loadEmailCredentials", return_value=("FAILED", "FAILED")):
            with patch.object(RequestHandler, "_getSerial", return_value="serial-123"):
                with patch("helpers.logging.basicConfig"):
                    handler = RequestHandler()

    assert handler.gotEmailCreds is False


# FastAPI credential loading should read the configured JSON secret file fields
def test_load_fast_api_credentials_reads_secret_file():
    handler = RequestHandler.__new__(RequestHandler)
    secret_data = {
        "FASTAPI_CREDS": {
            "apiKey": "api-key",
            "endpoint": "api.example.test",
            "port": 8443,
        }
    }

    with patch("helpers.open", mock_open(), create=True) as open_mock:
        with patch("helpers.json.load", return_value=secret_data) as json_load:
            result = handler.loadFastAPICredentials("config.secret")

    open_mock.assert_called_once_with("config.secret", "r")
    json_load.assert_called_once()
    assert result == ("api-key", "api.example.test", 8443)


# updateAPICreds should reload secret file values and rebuild the endpoint
def test_update_api_creds_reloads_credentials_and_formats_endpoint():
    handler = build_request_handler()
    handler.secret_file = "new.secret"

    with patch.object(handler, "loadFastAPICredentials", return_value=("new-key", "new-api.example.test", 9443)) as load_api:
        handler.updateAPICreds()

    load_api.assert_called_once_with("new.secret")
    assert handler.apiKey == "new-key"
    assert handler.endpoint == "https://new-api.example.test:9443"
    assert handler.port == 9443


# checkNetworkConnection should return true when the socket connects successfully
def test_check_network_connection_returns_true_on_socket_connect():
    handler = build_request_handler()
    fake_socket = Mock()

    with patch("helpers.socket.setdefaulttimeout") as set_default_timeout:
        with patch("helpers.socket.socket", return_value=fake_socket) as socket_ctor:
            result = handler.checkNetworkConnection(
                host="1.1.1.1",
                port=53,
                timeout=5,
            )

    assert result is True
    set_default_timeout.assert_called_once_with(5)
    socket_ctor.assert_called_once_with(helpers.socket.AF_INET, helpers.socket.SOCK_STREAM)
    fake_socket.connect.assert_called_once_with(("1.1.1.1", 53))


# checkNetworkConnection should log and return false when the socket connect fails
def test_check_network_connection_returns_false_on_socket_error(caplog):
    handler = build_request_handler()
    fake_socket = Mock()
    fake_socket.connect.side_effect = helpers.socket.error("boom")

    with patch("helpers.socket.socket", return_value=fake_socket):
        with caplog.at_level(logging.ERROR):
            result = handler.checkNetworkConnection(host="1.1.1.1")

    assert result is False
    assert "Failed to connect to 1.1.1.1" in caplog.text


# getAPIKey should expose the currently loaded API token
def test_get_api_key_returns_current_key():
    handler = build_request_handler()

    assert handler.getAPIKey() == "api-token"


# sendHeartbeat should report success and retry email credential loading after recovery
def test_send_heartbeat_returns_true_and_retries_email_credentials():
    handler = build_request_handler()
    handler.gotEmailCreds = False
    fake_client = Mock()
    fake_client.get.return_value.json.return_value = {"is_alive": True}

    with patch("helpers.httpx.Client", return_value=fake_client) as client_ctor:
        with patch.object(handler, "loadEmailCredentials", return_value=("new-password", "new-email@example.test")) as load_email:
            result = handler.sendHeartbeat()

    assert result is True
    client_ctor.assert_called_once_with(verify=False)
    fake_client.get.assert_called_once_with(
        "https://api.example.test:443/api/health/heartbeat"
    )
    fake_client.close.assert_called_once_with()
    load_email.assert_called_once_with()
    assert handler.appPassword == "new-password"
    assert handler.emailAddress == "new-email@example.test"
    assert handler.gotEmailCreds is True


@pytest.mark.parametrize("response_json", [{}, {"is_alive": False}])
# sendHeartbeat should return false for missing or negative health responses
def test_send_heartbeat_returns_false_when_response_is_not_alive(response_json):
    handler = build_request_handler()
    fake_client = Mock()
    fake_client.get.return_value.json.return_value = response_json

    with patch("helpers.httpx.Client", return_value=fake_client):
        result = handler.sendHeartbeat()

    assert result is False
    fake_client.close.assert_called_once_with()


# sendHeartbeat should log and return false when the HTTP client raises
def test_send_heartbeat_returns_false_on_http_exception(caplog):
    handler = build_request_handler()
    fake_client = Mock()
    fake_client.get.side_effect = RuntimeError("network down")

    with patch("helpers.httpx.Client", return_value=fake_client):
        with caplog.at_level(logging.ERROR):
            result = handler.sendHeartbeat()

    assert result is False
    assert "Exception occurred while sending hearbeat" in caplog.text
    fake_client.close.assert_called_once_with()


# sendSecureHeartbeat should call the secure endpoint with the token header
def test_send_secure_heartbeat_sends_token_header_and_returns_true():
    handler = build_request_handler()
    fake_client = Mock()
    fake_client.get.return_value.json.return_value = {"is_alive": True}

    with patch("helpers.httpx.Client", return_value=fake_client) as client_ctor:
        result = handler.sendSecureHeartbeat()

    assert result is True
    client_ctor.assert_called_once_with(verify=False)
    fake_client.get.assert_called_once_with(
        "https://api.example.test:443/api/health/secure_heartbeat",
        headers={"token": "api-token"},
    )
    fake_client.close.assert_called_once_with()


@pytest.mark.parametrize("response_json", [{}, {"is_alive": False}])
# sendSecureHeartbeat should return false for missing or negative health responses
def test_send_secure_heartbeat_returns_false_when_response_is_not_alive(response_json):
    handler = build_request_handler()
    fake_client = Mock()
    fake_client.get.return_value.json.return_value = response_json

    with patch("helpers.httpx.Client", return_value=fake_client):
        result = handler.sendSecureHeartbeat()

    assert result is False
    fake_client.close.assert_called_once_with()


# sendAPIRequest should build the upload payload, attach files, and return success
def test_send_api_request_posts_expected_payload_and_returns_success():
    handler = build_request_handler()
    file_names = sample_file_names()
    sensor_data = sample_sensor_data()
    file_handles = [Mock(name=f"file_{index}") for index in range(5)]
    fake_response = Mock(status_code=201, text="created")
    fake_response.json.return_value = {"status": True}
    fake_client = Mock()
    fake_client.post.return_value = fake_response
    fake_context = MagicMock()
    fake_context.__enter__.return_value = fake_client

    with patch("helpers.open", side_effect=file_handles, create=True) as open_mock:
        with patch("helpers.httpx.Client", return_value=fake_context) as client_ctor:
            result = handler.sendAPIRequest(file_names, sensor_data, "commit-sha")

    assert result == (True, 201, "created")
    assert open_mock.call_args_list == [
        call("../data/color.jpg", "rb"),
        call("../data/depth.npy", "rb"),
        call("../data/heatmap.jpg", "rb"),
        call("../data/topology.npy", "rb"),
        call("../data/audio.wav", "rb"),
    ]
    client_ctor.assert_called_once_with(
        headers={"token": "api-token", "accept": "application/json"},
        timeout=60,
        verify=False,
    )
    fake_client.post.assert_called_once()
    assert fake_client.post.call_args.args[0] == "https://api.example.test:443/api/scan"
    assert fake_client.post.call_args.kwargs["files"] == [
        ("files", handle) for handle in file_handles
    ]
    payload = json.loads(fake_client.post.call_args.kwargs["data"]["data"])
    assert payload == {
        "colorImage": "color.jpg",
        "depthImage": "depth.npy",
        "heatmapImage": "heatmap.jpg",
        "topologyMap": "topology.npy",
        "voiceRecording": "audio.wav",
        "total_weight": 12.5,
        "weight_delta": 1.25,
        "temperature": 20.1,
        "pressure": 101.2,
        "humidity": 45.3,
        "iaq": 25.0,
        "co2_eq": 500.0,
        "tvoc": 0.5,
        "transcription": "banana peel",
        "userTrigger": True,
        "deviceID": "device-serial",
        "commitID": "commit-sha",
    }


# sendAPIRequest should return API level failure responses without raising
def test_send_api_request_returns_false_when_api_status_is_false():
    handler = build_request_handler()
    fake_response = Mock(status_code=500, text="server error")
    fake_response.json.return_value = {"status": False}
    fake_client = Mock()
    fake_client.post.return_value = fake_response
    fake_context = MagicMock()
    fake_context.__enter__.return_value = fake_client

    with patch("helpers.open", side_effect=[Mock() for _ in range(5)], create=True):
        with patch("helpers.httpx.Client", return_value=fake_context):
            result = handler.sendAPIRequest(
                sample_file_names(),
                sample_sensor_data(),
                "commit-sha",
            )

    assert result == (False, 500, "server error")


# sendAPIRequest should return the standard error tuple when the post raises
def test_send_api_request_returns_error_tuple_when_http_post_raises(caplog):
    handler = build_request_handler()
    fake_client = Mock()
    fake_client.post.side_effect = RuntimeError("upload failed")
    fake_context = MagicMock()
    fake_context.__enter__.return_value = fake_client

    with patch("helpers.open", side_effect=[Mock() for _ in range(5)], create=True):
        with patch("helpers.httpx.Client", return_value=fake_context):
            with caplog.at_level(logging.ERROR):
                result = handler.sendAPIRequest(
                    sample_file_names(),
                    sample_sensor_data(),
                    "commit-sha",
                )

    assert result == (False, -1, "upload failed")
    assert "Exception occurred while sending API request" in caplog.text


# sendErrorEmail should authenticate and send the formatted support email
def test_send_error_email_logs_in_sends_message_and_returns_true():
    handler = build_request_handler()
    fake_smtp = Mock()
    fake_context = MagicMock()
    fake_context.__enter__.return_value = fake_smtp

    with patch("helpers.smtplib.SMTP_SSL", return_value=fake_context) as smtp_ssl:
        result = handler.sendErrorEmail(500, "server exploded")

    assert result is True
    smtp_ssl.assert_called_once_with("smtp.gmail.com", 465)
    fake_smtp.login.assert_called_once_with("alerts@example.test", "app-password")
    fake_smtp.sendmail.assert_called_once()
    assert fake_smtp.sendmail.call_args.args[0] == "alerts@example.test"
    assert fake_smtp.sendmail.call_args.args[1] == "alerts@example.test"
    message = fake_smtp.sendmail.call_args.args[2]
    assert "[Bucket Upload Error] Device: device-serial encountered a 500 error code." in message
    assert "server exploded" in message


# sendErrorEmail should log and return false when SMTP setup fails
def test_send_error_email_returns_false_on_smtp_failure(caplog):
    handler = build_request_handler()

    with patch("helpers.smtplib.SMTP_SSL", side_effect=RuntimeError("smtp down")):
        with caplog.at_level(logging.ERROR):
            result = handler.sendErrorEmail(500, "server exploded")

    assert result is False
    assert "Error occurred sending email" in caplog.text


# loadEmailCredentials should read notification email and password from AWS secrets
def test_load_email_credentials_returns_aws_secret_values():
    handler = RequestHandler.__new__(RequestHandler)
    fake_client = Mock()
    fake_session = Mock()
    fake_session.create_client.return_value = fake_client
    fake_cache = Mock()
    fake_cache.get_secret_string.side_effect = [
        "alerts@example.test",
        "app-password",
    ]
    fake_cache_config = Mock(name="cache_config")

    with patch.object(
        helpers.botocore,
        "session",
        SimpleNamespace(get_session=Mock(return_value=fake_session)),
        create=True,
    ) as botocore_session:
        with patch("helpers.SecretCacheConfig", return_value=fake_cache_config) as cache_config:
            with patch("helpers.SecretCache", return_value=fake_cache) as cache_ctor:
                result = handler.loadEmailCredentials()

    botocore_session.get_session.assert_called_once_with()
    fake_session.create_client.assert_called_once_with(
        "secretsmanager",
        region_name="us-west-2",
    )
    cache_config.assert_called_once_with()
    cache_ctor.assert_called_once_with(config=fake_cache_config, client=fake_client)
    assert fake_cache.get_secret_string.call_args_list == [
        call("sb_notification_email"),
        call("sb_notification_password"),
    ]
    assert result == ("app-password", "alerts@example.test")


# loadEmailCredentials should return FAILED sentinels when AWS access raises
def test_load_email_credentials_returns_failed_values_on_exception(caplog):
    handler = RequestHandler.__new__(RequestHandler)

    with patch.object(
        helpers.botocore,
        "session",
        SimpleNamespace(get_session=Mock(side_effect=RuntimeError("aws down"))),
        create=True,
    ):
        with caplog.at_level(logging.ERROR):
            result = handler.loadEmailCredentials()

    assert result == ("FAILED", "FAILED")
    assert "Failed to retrieve email credentials" in caplog.text


# _getSerial should parse the Raspberry Pi serial value from /proc/cpuinfo
def test_get_serial_parses_cpuinfo_serial_line():
    handler = RequestHandler.__new__(RequestHandler)
    cpuinfo = "Hardware\t: BCM\nSerial\t\t: 000000001234abcd\n"

    with patch("helpers.open", mock_open(read_data=cpuinfo), create=True) as open_mock:
        result = handler._getSerial()

    open_mock.assert_called_once_with("/proc/cpuinfo", "r")
    assert result == "000000001234abcd"


# _getSerial should return the current error sentinel when cpuinfo cannot be read
def test_get_serial_returns_error_value_when_cpuinfo_fails():
    handler = RequestHandler.__new__(RequestHandler)

    with patch("helpers.open", side_effect=OSError("no cpuinfo"), create=True):
        result = handler._getSerial()

    assert result == "ERROR000000000"
