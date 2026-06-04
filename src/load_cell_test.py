import logging
import time

import PyNAU7802
import smbus2

# Create the bus
bus = smbus2.SMBus(1)

# Create the scale and initialize it
scale = PyNAU7802.NAU7802()

if scale.begin(bus):
    print("Connected!\n")
else:
    print("Can't find the scale, exiting ...\n")
    exit()

# Calculate the zero offset
print("Calculating the zero offset...")
scale.setSampleRate(PyNAU7802.NAU7802_SPS_40)
scale.setGain(PyNAU7802.NAU7802_GAIN_16)
scale.setLDO(PyNAU7802.NAU7802_LDO_4V5)
scale.calibrateAFE()

scale.calculateZeroOffset()
print("The zero offset is : {0}\n".format(scale.getZeroOffset()))


scale.setCalibrationFactor(42.1825)
print("The calibration factor is : {0:0.3f}\n".format(scale.getCalibrationFactor()))

# data points to store in csv:
# timestamp
# raw adc value
while True:
    print("Mass is {0:0.3f} kg".format(scale.getWeight(True, 25)))
