"""
Unit test for the BME688 sensor module. Mock data obtained from tests/requestTest.py
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from drivers.sensors.BME688 import BME688


class FakeBME680:
    """
    Fake BME680 library. Imitates bme680.BME680.
    """
    def __init__(self):
        self.data = SimpleNamespace(
            temperature=19.61,
            pressure=1020.96,
            humidity=46.77,
            gas_resistance=25376.685170499604,
            heat_stable=True,
        )
        self._i2c = Mock()

    def set_humidity_oversample(self, value): pass
    def set_pressure_oversample(self, value): pass
    def set_temperature_oversample(self, value): pass
    def set_filter(self, value): pass
    def set_gas_status(self, value): pass
    def set_gas_heater_temperature(self, value): pass
    def set_gas_heater_duration(self, value): pass
    def select_gas_heater_profile(self, value): pass

    def get_sensor_data(self):
        return True


class FakeBSECLib:
    """
    Fake BSEC library. Imitates bsec_python.so loaded by CDLL
    """
    def proccess_bme_data(self, ts, temp, pressure, humidity, gas, arr_c):
        arr_c[0] = 25.0
        arr_c[4] = 25.0
        arr_c[5] = 500.0
        arr_c[6] = 0.4999999403953552


@patch("drivers.sensors.BME688.cdll.LoadLibrary", return_value=FakeBSECLib())
@patch("drivers.sensors.BME688.bme680.BME680", return_value=FakeBME680())
def test_bme688_measure_updates_data(mock_bme_ctor, mock_loadlib):
    driver = BME688()
    driver.data = driver.createDataDict()

    driver.initialize()
    driver.measure()

    assert driver.data["initialized"].value == 1
    assert driver.data["temperature(c)"].value == 19.61
    assert driver.data["pressure(kpa)"].value == 102.096
    assert driver.data["humidity(%rh)"].value == 46.77
    assert driver.data["gas_resistance(ohms)"].value == 25376.685170499604
    assert driver.data["iaq"].value == 25.0
    assert driver.data["sIAQ"].value == 25.0
    assert driver.data["CO2-eq"].value == 500.0
    assert driver.data["bVOC-eq"].value == 0.4999999403953552
