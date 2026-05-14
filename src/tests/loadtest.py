#!../../venv/bin/python
from time import sleep, time
import os

from helpers import Logging, CalibrationLoader
from drivers.DriverManager import DriverManager
from drivers.sensors.NAU7802 import NAU7802
from drivers.sensors.LidSwitch import LidSwitch

if __name__ == "__main__":
    # Change our current working directory to this file so our relative paths still work no matter where this file was called from
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    logger = Logging()
    calibration = CalibrationLoader("../CalibrationDetails.json")
    manager = DriverManager(NAU7802(calibration.get("NAU7802_CALIBRATION_FACTOR")), LidSwitch())
    with open("../../data/weightTest.csv", 'w') as output:
        output.write("time, human_avg_weight(g), load_cell_average, raw_adc, lid_state\n")
    
    while True:
        try:
            with open("../../data/weightTest.csv", 'a') as output:
                lidState = "0"
                
                # Check the state of the LidSwitch
                if manager.getEvent("LidSwitch.LID_CLOSED"):
                    lidState = "-250"
                    manager.clearEvent("LidSwitch.LID_CLOSED")

                # Check the state of the LidSwitch
                elif manager.getEvent("LidSwitch.LID_OPENED"):
                    lidState = "250"
                    manager.clearEvent("LidSwitch.LID_OPENED")

                jsonOut = manager.getJSON()   
                output.write(f"{time()},{jsonOut['NAU7802']['data']['weight']},{jsonOut['NAU7802']['data']['nau_average']},{jsonOut['NAU7802']['data']['raw_adc']}, {lidState}\n")         
            sleep(0.1)
        except KeyboardInterrupt:
            manager.kill()
            break
