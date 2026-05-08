"""
Will Richards, Oregon State University, 2024

Provides a wrapper for the Neopixel LED Driver
"""

import enum
from drivers.DriverBase import DriverBase
from multiprocessing import Event
import logging
import neopixel_spi as neopixel
import board

"""
Device modes that the LED's are used to represent
CAMERA - The camera is currently taking an image, solid white
PROCCESSING - The bin is in the middle of computing results / taking measurements, Breathing yellow 
DONE - The bin has finished taking readings and is now idle, green
NONE - The device is currently idle, black
ERROR - Something went wrong, red
"""
class LEDMode(enum.Enum):
    CAMERA = 0,
    PROCESSING = 1,
    DONE = 2,
    NONE = 3,
    ERROR = 4


class LEDDriver(DriverBase):

    """
    LED Driver constructor

    :param isBootFromUpdaate: If the current initialization loop is caused by an update
    :param pixel_count: The number of LED "pixels" that are connected to the controller
    """
    def __init__(self, isBootFromUpdate, pixel_count = 16):
        super().__init__("LEDDriver")

        self.pixel_count = pixel_count
        self.pixels = None
        self.mode = LEDMode.PROCESSING if not isBootFromUpdate else LEDMode.NONE
        self.initialized = False
        self.events = {
            "CAMERA": Event(),
            "PROCESSING": Event(),
            "DONE": Event(),
            "NONE": Event(),
            "ERROR": Event()
        }
        self.currentLed = 0
        self.loopTime = 0.1
    
    """
    This doesn't do anything other than tell us the driver has been initialized succsessfully
    """
    def initialize(self):
        spi = board.SPI()
        self.pixels = neopixel.NeoPixel_SPI(
            spi, self.pixel_count, brightness=1, auto_write=True, pixel_order=neopixel.GRBW, bit0=0b10000000
        )   
        # Set the GPIO numbering to that of the board itself and then set the specified GPIO pin as an input
        logging.info("Succsessfully configured LED Driver!")
        self.data["initialized"].value = 1
    
    """
    Updates the LED's based on the given device mode
    """
    def measure(self):
        if self.pixels is None:
            return

        self.handleEvents()

        if(self.mode == LEDMode.CAMERA):
           self.cameraMode()
        elif(self.mode == LEDMode.PROCESSING):
            self.proccessingMode()
        elif(self.mode == LEDMode.DONE):
            self.doneMode()
        elif(self.mode == LEDMode.ERROR):
            self.errorMode()
        else:
            self.noneMode()
        
        self.pixels.show()

    """
    Handles mode switching depending on if an event was set or not
    """
    def handleEvents(self):
        if self.getEvent("CAMERA").is_set():
            self.mode = LEDMode.CAMERA
            self.getEvent("CAMERA").clear()
        
        elif self.getEvent("PROCESSING").is_set():
            self.noneMode()
            self.mode = LEDMode.PROCESSING
            self.getEvent("PROCESSING").clear()

        elif self.getEvent("DONE").is_set():
            self.mode = LEDMode.DONE
            self.getEvent("DONE").clear()

        elif self.getEvent("ERROR").is_set():
            self.mode = LEDMode.ERROR
            self.getEvent("ERROR").clear()
            
        elif self.getEvent("NONE").is_set():
            self.mode = LEDMode.NONE
            self.getEvent("NONE").clear()
        
    
    """
    Drives the LEDs to white for the camera to take a picture
    """
    def cameraMode(self):
        self.pixels.fill((0, 0, 0, 255))

    """
    Drives the LEDs to spin yellow while we are proccessing the data
    """
    def proccessingMode(self):
        self.pixels[self.currentLed] = (252,186,3,0)
        self.pixels[self.currentLed-1] = (252//2,186//2,3//2,0)
        self.pixels[self.currentLed-2] = (252//3,186//3,3//3,0)
        self.pixels[self.currentLed-3] = (0,0,0,0)
        self.currentLed += 1
        if(self.currentLed == 16):
            self.currentLed = 0
        

    """
    Drives the LEDs to solid green to signify we are done with the sample
    """
    def doneMode(self):
        self.pixels.fill((0,255,0,0))

    """
    Drives the LEDs to off to signify we are not doing anything
    """
    def noneMode(self):
        self.pixels.fill((0,0,0,0))
    
    """
    Informs the user something went wrong by turning all pixels to red
    """
    def errorMode(self):
        self.pixels.fill((255,0,0,0))

    def kill(self):
        if self.pixels:
            self.pixels.fill((0,0,0,0))
            self.pixels.show()

   