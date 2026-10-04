"""
Unit test for the BME688 sensor module. The vendored BSEC extension is not
available on a workstation, so it is replaced by a fake that records how the
driver constructed it. All values are synthetic.
"""

import sys
from types import ModuleType
from unittest.mock import Mock, patch

import pytest


class FakeBME68X:
    """
    Fake BSEC extension. Imitates bme68x.BME68X.
    """

    instances = []

    def __init__(self, i2c_address, debug_mode):
        self.i2c_address = i2c_address
        self.debug_mode = debug_mode
        self.set_bsec_state_calls = []
        self.set_sample_rate_calls = []
        FakeBME68X.instances.append(self)

    def set_bsec_state(self, state):
        self.set_bsec_state_calls.append(state)

    def set_sample_rate(self, sample_rate):
        self.set_sample_rate_calls.append(sample_rate)

    def get_bsec_data(self):
        return {
            "temperature": 19.61,
            "raw_pressure": 102096.0,
            "humidity": 46.77,
            "raw_gas": 25376.685,
            "iaq": 25.0,
            "iaq_accuracy": 3,
            "static_iaq": 25.0,
            "co2_equivalent": 500.0,
            "breath_voc_equivalent": 0.5,
        }


def install_native_stubs():
    """
    The driver imports the compiled extension at module scope. Register fakes
    for it and its constant modules before the driver is imported.
    """
    FakeBME68X.instances = []
    stubs = {
        "bme68x": ModuleType("bme68x"),
        "bme68xConstants": ModuleType("bme68xConstants"),
        "bsecConstants": ModuleType("bsecConstants"),
    }
    stubs["bme68x"].BME68X = FakeBME68X
    stubs["bme68xConstants"].BME68X_ENABLE = 1
    stubs["bme68xConstants"].BME68X_PARALLEL_MODE = 1
    stubs["bsecConstants"].BSEC_SAMPLE_RATE_LP = 0.5
    patcher = patch.dict(sys.modules, stubs)
    patcher.start()
    return patcher


patcher = install_native_stubs()
from drivers.sensors.BME688 import BME688  # noqa: E402


def build_driver(env=None):
    with patch.dict("os.environ", env or {}, clear=True):
        driver = BME688()
    # testing=True makes DriverBase.getEvent() read raw events instead of [event, callback]
    driver.testing = True
    driver.data = driver.createDataDict()
    return driver


def test_vendor_debug_output_is_off_by_default():
    driver = build_driver()
    assert driver.debug_mode == 0

    driver.initialize()

    assert driver.sensor.debug_mode == 0


def test_debug_output_is_opt_in_through_the_environment():
    driver = build_driver({"BME688_DEBUG_MODE": "1"})

    driver.initialize()

    assert driver.sensor.debug_mode == 1


def test_only_the_exact_value_one_enables_debug_output():
    driver = build_driver({"BME688_DEBUG_MODE": "true"})

    driver.initialize()

    assert driver.sensor.debug_mode == 0


def test_sensor_address_is_still_passed_positionally():
    driver = build_driver()
    driver.initialize()

    assert driver.sensor.i2c_address == 0x77


def test_measure_maps_bsec_data_onto_the_shared_dict():
    driver = build_driver()

    driver.initialize()
    driver.measure()

    assert driver.data["initialized"].value == 1
    assert driver.data["temperature(c)"].value == 19.61
    assert driver.data["pressure(kpa)"].value == pytest.approx(102.096)
    assert driver.data["humidity(%rh)"].value == 46.77
    assert driver.data["gas_resistance(ohms)"].value == pytest.approx(25376.685)
    assert driver.data["iaq"].value == 25.0
    assert driver.data["sIAQ"].value == 25.0
    assert driver.data["CO2-eq"].value == 500.0
    assert driver.data["bVOC-eq"].value == 0.5


def test_calibration_state_is_restored_on_initialize():
    driver = build_driver()
    driver._readState = Mock(return_value=[1, 2, 3])

    driver.initialize()

    assert driver.sensor.set_bsec_state_calls == [[1, 2, 3]]
    assert driver.data["calibrated"].value == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
