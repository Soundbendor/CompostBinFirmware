"""
Unit tests for the MLX90640 driver and ThermalCam helper.
"""

import numpy as np
from unittest.mock import Mock, patch

from drivers.sensors.MLX90640 import MLX90640, ThermalCam


def build_driver():
    fake_cam = Mock()
    fake_pipe = Mock()

    with patch("drivers.sensors.MLX90640.ThermalCam", return_value=fake_cam):
        driver = MLX90640(fake_pipe)
        driver.testing = True
        driver.data = driver.createDataDict()

    return driver, fake_cam, fake_pipe


def test_initialize_sets_initialized_flag():
    # initialize() should mark the shared initialized flag for the driver manager
    driver, _, _ = build_driver()

    driver.initialize()

    assert driver.data["initialized"].value == 1


def test_measure_does_nothing_when_capture_event_is_not_set():
    # measure() should skip camera capture until the CAPTURE event is raised
    driver, fake_cam, fake_pipe = build_driver()

    driver.measure()

    fake_cam.capture.assert_not_called()
    fake_pipe.send.assert_not_called()


def test_measure_sends_filename_and_clears_capture_event():
    # measure() should capture an image, send the filename, and clear the event
    driver, fake_cam, fake_pipe = build_driver()
    fake_cam.capture.return_value = "../data/heatmap_test.jpg"
    driver.events["CAPTURE"].set()

    driver.measure()

    fake_cam.capture.assert_called_once_with()
    fake_pipe.send.assert_called_once_with({"heatmapImage": "../data/heatmap_test.jpg"})
    assert not driver.events["CAPTURE"].is_set()


def test_kill_closes_camera():
    # kill() should forward shutdown to the wrapped ThermalCam instance
    driver, fake_cam, _ = build_driver()

    driver.kill()

    fake_cam.close.assert_called_once_with()


def test_rescale_temps_returns_uint8_matrix():
    # _rescaleTemps() should normalize data to a 24x32 uint8 image matrix
    fake_sensor = Mock()

    with patch("drivers.sensors.MLX90640.mlx90640", return_value=fake_sensor):
        cam = ThermalCam()

    temps = np.linspace(0.0, 100.0, 24 * 32)
    result = cam._rescaleTemps(temps, 0.0, 100.0)

    assert result.shape == (24, 32)
    assert result.dtype == np.uint8


def test_format_file_name_uses_expected_output_path():
    # _formatFileName() should build the ../data path with the expected timestamp format
    fake_sensor = Mock()

    with patch("drivers.sensors.MLX90640.mlx90640", return_value=fake_sensor):
        cam = ThermalCam()

    with patch("drivers.sensors.MLX90640.strftime", return_value="../data/heatmap_2026-04-29--12-00-00.jpg"):
        result = cam._formatFileName("heatmap.jpg", 0)

    assert result == "../data/heatmap_2026-04-29--12-00-00.jpg"


def test_capture_writes_heatmap_and_returns_filename():
    # capture() should preload, capture, render, write the image, and return its filename
    fake_sensor = Mock()

    with patch("drivers.sensors.MLX90640.mlx90640", return_value=fake_sensor):
        cam = ThermalCam()

    with patch.object(cam, "_preloadImage") as preload, \
         patch.object(cam, "_captureRaw", return_value="raw_data") as capture_raw, \
         patch.object(cam, "_createHeatmap", return_value="heatmap") as create_heatmap, \
         patch.object(cam, "_formatFileName", return_value="../data/heatmap_test.jpg") as format_name, \
         patch("drivers.sensors.MLX90640.cv2.imwrite") as imwrite, \
         patch("drivers.sensors.MLX90640.time", return_value=123.0):
        result = cam.capture()

    preload.assert_called_once_with()
    capture_raw.assert_called_once_with()
    create_heatmap.assert_called_once_with("raw_data")
    format_name.assert_called_once_with("heatmap.jpg", 123.0)
    imwrite.assert_called_once_with("../data/heatmap_test.jpg", "heatmap")
    assert result == "../data/heatmap_test.jpg"


def test_close_tears_down_i2c():
    # close() should tear down the underlying sensor I2C connection
    fake_sensor = Mock()

    with patch("drivers.sensors.MLX90640.mlx90640", return_value=fake_sensor):
        cam = ThermalCam()

    cam.close()

    fake_sensor.i2c_tear_down.assert_called_once_with()
