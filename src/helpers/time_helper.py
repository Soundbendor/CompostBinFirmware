from time import time


TWO_HOURS_SECONDS = 7200
# TWO_HOURS_SECONDS = 20


class TimeHelper:
    def __init__(self):
        self.lastTime = time()

    """
    Check to see if we have reached the two hour interval and should trigger the collection

    :return A bool representing if our 2 hour interval is up
    """

    def twoHourInterval(self) -> bool:
        currentTime = int(time())
        if (currentTime % TWO_HOURS_SECONDS) == 0 and currentTime != self.lastTime:
            self.lastTime = currentTime
            return True
        return False
