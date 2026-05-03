from unittest.mock import patch
from drivers.sensors.LEDDriver import LEDDriver, LEDMode

PIXEL_COUNT = 16

# Fake NeoPixel strip so tests can inspect rendered colors and show() calls
class FakePixels:
    def __init__(self, count=PIXEL_COUNT):
        self.buffer = [(0, 0, 0, 0)] * count
        self.show_calls = 0

    def fill(self, color):
        self.buffer = [color] * len(self.buffer)

    def __setitem__(self, index, value):
        self.buffer[index] = value

    def show(self):
        self.show_calls += 1


def build_driver(pixel_count=PIXEL_COUNT, is_boot_from_update=True):
    fake_pixels = FakePixels(pixel_count)

    # Patch fake SPI/LED into real drivers
    with patch("drivers.sensors.LEDDriver.board.SPI", return_value=object()), patch("drivers.sensors.LEDDriver.neopixel.NeoPixel_SPI", return_value=fake_pixels):
        driver = LEDDriver(is_boot_from_update, pixel_count=pixel_count)
        # testing=True makes DriverBase.getEvent() read raw events instead of [event, callback]
        driver.testing = True
        driver.data = driver.createDataDict()

    return driver, fake_pixels


def test_camera_mode_fills_white():
    driver, pixels = build_driver()

    driver.cameraMode()

    assert pixels.buffer == [(0, 0, 0, 255)] * PIXEL_COUNT


def test_done_mode_fills_green():
    driver, pixels = build_driver()

    driver.doneMode()

    assert pixels.buffer == [(0, 255, 0, 0)] * PIXEL_COUNT


def test_none_mode_turns_leds_off():
    driver, pixels = build_driver()

    driver.noneMode()

    assert pixels.buffer == [(0, 0, 0, 0)] * PIXEL_COUNT


def test_error_mode_fills_red():
    driver, pixels = build_driver()

    driver.errorMode()

    assert pixels.buffer == [(255, 0, 0, 0)] * PIXEL_COUNT


def test_processing_mode_trailing_pixels():
    driver, pixels = build_driver()
    driver.currentLed = 3

    # Check the bright head and dimming trail
    driver.proccessingMode()

    assert pixels.buffer[3] == (252, 186, 3, 0)
    assert pixels.buffer[2] == (252//2,186//2,3//2,0)
    assert pixels.buffer[1] == (252//3,186//3,3//3,0)
    assert pixels.buffer[0] == (0,0,0,0)
    assert driver.currentLed == 4


def test_processing_mode_wraps_at_end():
    driver, pixels = build_driver()
    driver.currentLed = PIXEL_COUNT - 1

    driver.proccessingMode()

    assert pixels.buffer[PIXEL_COUNT - 1] == (252, 186, 3, 0)
    assert driver.currentLed == 0


def test_handle_events_switches_to_camera_and_clears_event():
    driver, _ = build_driver()

    driver.events["CAMERA"].set()

    driver.handleEvents()

    assert driver.mode == LEDMode.CAMERA
    assert not driver.events["CAMERA"].is_set()


def test_handle_events_switches_to_done_and_clears_event():
    driver, _ = build_driver()

    driver.events["DONE"].set()

    driver.handleEvents()

    assert driver.mode == LEDMode.DONE
    assert not driver.events["DONE"].is_set()


def test_measure_renders_current_mode_and_calls_show():
    driver, pixels = build_driver()
    driver.mode = LEDMode.DONE

    driver.measure()

    assert pixels.buffer == [(0, 255, 0, 0)] * PIXEL_COUNT
    assert pixels.show_calls == 1


def test_kill_turns_leds_off_and_calls_show():
    driver, pixels = build_driver()

    # Put the strip into a non-off state first so the test proves kill changed it
    driver.doneMode()
    assert pixels.buffer == [(0, 255, 0, 0)] * PIXEL_COUNT
    assert pixels.show_calls == 0

    driver.kill()

    assert pixels.buffer == [(0, 0, 0, 0)] * PIXEL_COUNT
    assert pixels.show_calls == 1

