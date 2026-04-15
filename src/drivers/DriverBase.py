"""
Will Richards, Oregon State University, 2023

Provides a unified parent class that all sensor drivers can inherit from
"""

from multiprocessing import Event, Value

class DriverBase:
    """
    Driver base constructor takes in module name so we can make nice looking logs

    :param modName: Name of the module we are creating
    """
    def __init__(self, modName):
        self.moduleName = modName
        self.events = {}

        # The rate at which the thread this driver is running in will loop
        self.loopTime = 0.001
        self.initialized = False

        # Flag for testing mode. Allows driver to be used without DriverManager
        self.testing = False

    """
    Should be overloaded on all sub drivers so initialize can be called on all drivers at once
    """
    def initialize(self):
        pass
    
    """
    Should be overloaded on all sub drivers so initialize can be called on all drivers at once
    """
    def measure(self) -> None:
        pass

    """
    Should have the builtin functionality to calibrate a sensor if needed 
    """
    def calibrate(self):
        pass

    """
    Get the events that the driver has
    """
    def getEvents(self) -> dict:
        return self.events
    
    """
    Get a specific event from the dictionary
    """
    def getEvent(self, event) -> Event:
        if not self.testing:
            return self.events[event][0]
        else: 
            return self.events[event]

    """
    What to do when execution is ending
    """
    def kill(self):
        pass

    """
    Create a specified dictionary of values to create keys for the values we will update
    """
    def createDataDict(self):
        self.data = {
            "initialized": Value('i', 0)
        }
        return self.data

    """
    Sets the length of each loop of the driver
    """
    def setLoopTime(self, time):
        self.loopTime = time