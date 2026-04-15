"""
Unit test of the lid switch logic
"""

from gpiod.line import Value as GPIOValue
from drivers.sensors.LidSwitch import LidSwitch
from tests.unit.common.FakeGPIO import FakeGPIO

def test_lid_closed_to_open_transition():
    driver = LidSwitch()
    driver.testing = True

    driver.data = driver.createDataDict()
    driver.lastState = GPIOValue.INACTIVE
    driver.request = FakeGPIO(GPIOValue.ACTIVE)

    driver.measure()

    assert driver.lidOpen is True
    assert driver.data["Lid_State"].value is 1
    assert driver.events["LID_OPENED"].is_set()
    assert not driver.events["LID_CLOSED"].is_set()

def test_lid_open_to_closed_transition():
    driver = LidSwitch()
    driver.testing = True

    driver.data = driver.createDataDict()
    driver.lastState = GPIOValue.ACTIVE
    driver.request = FakeGPIO(GPIOValue.INACTIVE)

    driver.measure()

    assert driver.lidOpen is False
    assert driver.data["Lid_State"].value is 0
    assert not driver.events["LID_OPENED"].is_set()
    assert driver.events["LID_CLOSED"].is_set()