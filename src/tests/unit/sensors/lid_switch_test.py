"""
Unit test of the lid switch logic
"""

from gpiod.line import Value as GPIOValue
from drivers.sensors.LidSwitch import LidSwitch
from tests.unit.common.FakeGPIO import FakeGPIO


# Build LidSwitch with fake GPIO state and initialized shared data
def build_driver(last_state, current_reading):
    driver = LidSwitch()
    driver.testing = True
    driver.data = driver.createDataDict()
    driver.lastState = last_state
    driver.request = FakeGPIO(current_reading)
    return driver


# Closed-to-open transitions should update state and emit only LID_OPENED
def test_lid_closed_to_open_transition():
    driver = build_driver(GPIOValue.INACTIVE, GPIOValue.ACTIVE)

    driver.measure()

    assert driver.lidOpen is True
    assert driver.data["Lid_State"].value == 1
    assert driver.events["LID_OPENED"].is_set()
    assert not driver.events["LID_CLOSED"].is_set()


# Open-to-closed transitions should update state and emit only LID_CLOSED
def test_lid_open_to_closed_transition():
    driver = build_driver(GPIOValue.ACTIVE, GPIOValue.INACTIVE)

    driver.measure()

    assert driver.lidOpen is False
    assert driver.data["Lid_State"].value == 0
    assert not driver.events["LID_OPENED"].is_set()
    assert driver.events["LID_CLOSED"].is_set()


# Open-to-open readings should refresh Lid_State without raising transition events
def test_lid_open_to_open_no_change_updates_state_without_events():
    driver = build_driver(GPIOValue.ACTIVE, GPIOValue.ACTIVE)

    driver.measure()

    assert driver.lidOpen is True
    assert driver.data["Lid_State"].value == 1
    assert not driver.events["LID_OPENED"].is_set()
    assert not driver.events["LID_CLOSED"].is_set()
    assert driver.lastState == GPIOValue.ACTIVE


# Closed-to-closed readings should refresh Lid_State without raising transition events
def test_lid_closed_to_closed_no_change_updates_state_without_events():
    driver = build_driver(GPIOValue.INACTIVE, GPIOValue.INACTIVE)

    driver.measure()

    assert driver.lidOpen is False
    assert driver.data["Lid_State"].value == 0
    assert not driver.events["LID_OPENED"].is_set()
    assert not driver.events["LID_CLOSED"].is_set()
    assert driver.lastState == GPIOValue.INACTIVE
