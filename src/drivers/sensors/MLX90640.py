""""
Will Richards, Oregon State University, 2023

Abstraction layer for the MLX90640 
"""

from mlx90640 import MLX90640 as mlx90640
from multiprocessing import Event
import logging
import cv2
import numpy as np
from scipy import ndimage
from time import time, strftime, gmtime
from enum import Enum
import cmapy

from drivers.DriverBase import DriverBase

"""
Enum to map readable camera refresh rates to there integer values
"""
class CameraRefreshRate(Enum):
    RATE_05 = 0x00,
    RATE_1 = 0x01,
    RATE_2 = 0x02,
    RATE_4 = 0x03,
    RATE_8 = 0x04,
    RATE_16 = 0x05,
    RATE_32 = 0x06,
    RATE_64 = 0x07


"""
Class used to convert the data from the IR matrix into a thermal camera of sorts
"""
class ThermalCam():
    
    # Heatmap generation parameters 
    _colormap_list=['jet','bwr','seismic','coolwarm','PiYG_r','tab10','tab20','gnuplot2','brg']
    _interpolation_list =[cv2.INTER_NEAREST,cv2.INTER_LINEAR,cv2.INTER_AREA,cv2.INTER_CUBIC,cv2.INTER_LANCZOS4,5,6]
    _interpolation_list_name = ['Nearest','Inter Linear','Inter Area','Inter Cubic','Inter Lanczos4','Pure Scipy', 'Scipy/CV2 Mixed']

    """
    Create a new "Thermal camera" 

    :param width: The width of the resulting image
    :param height: The height of the resulting image
    :param refreshRate: The refresh rate of the MLX90640
    """
    def __init__(self, width=1200, height=900, refreshRate=CameraRefreshRate.RATE_4):
        self.imageHeight = height
        self.imageWidth = width
        self._colormap_index = 0

        # Setup the camera
        self.mlx = mlx90640()
        self.mlx.i2c_init("/dev/i2c-1")
        self.mlx.set_refresh_rate(refreshRate.value[0])

    """
    Scale temperature values to create an accurate heatmap

    :param currentTemp: The current temperature matrix
    :param Tmin: The minimum temperature recorded
    :param Tmax: The maximum temperature recorded
    """
    def _rescaleTemps(self, currentTemp, Tmin, Tmax):
        f = np.nan_to_num(currentTemp)
        norm = np.uint8(((f - Tmin) / (Tmax-Tmin))*255)
        norm.shape = (24,32)
        return norm

    """
    Capture the current readings from the MLX90640
    """
    def _captureRaw(self):

        # Hardcoded values, we don't really care about a super accurate heatmap
        emissivity = 0.95
        ta = 23.15

        # Read the matrix out
        self.mlx.dump_eeprom()
        self.mlx.extract_parameters()
        self.mlx.get_frame_data()
        ta = self.mlx.get_ta() - 8.0
        heats = self.mlx.calculate_to(emissivity, ta)
        heats = np.array(heats)

        # Normalize values
        self._tempMin = np.min(heats)
        self._tempMax = np.max(heats)
        heats = self._rescaleTemps(heats, self._tempMin, self._tempMax)
        return heats

    """
    Create a heatmap image from the given temperature data

    :param raw_data: The normalized temperature data
    """
    def _createHeatmap(self, raw_data):

        # Scale the image so that we have a higher resolution and apply colormap
        image = ndimage.zoom(raw_data, 10)
        image = cv2.applyColorMap(image, cmapy.cmap(self._colormap_list[self._colormap_index]))
        image = cv2.resize(image, (800,600), interpolation=cv2.INTER_CUBIC)

        # Flip image and filter to get smooth upright image
        image = cv2.flip(image, 0)
        image = cv2.bilateralFilter(image,15,80,80)
        return image
    
    """
    Take several captures before the actual one so the sensor has data to average
    """
    def _preloadImage(self):
        for _ in range(5):
            self._captureRaw()

    """
    Capture the data, generate a heatmap from the data and write the heatmap image to a file
    """
    def capture(self) -> str:
        self._preloadImage()
        heats = self._captureRaw()
        heatmap = self._createHeatmap(heats)
        currentTime = time()
        name = self._formatFileName("heatmap.jpg", currentTime)
        cv2.imwrite(name, heatmap)
        logging.info("Succsessfully captured heatmap")
        return name
        

    """
    Close the current I2C communication channel
    """
    def close(self):
        self.mlx.i2c_tear_down()
    
    """
    Given a generic file name like colorImage.jpg format it to be saved in ../data/colorImage_2024-04-16--19--00-12.jpg
    """
    def _formatFileName(self, fileName: str, currentTime):
        fileNameSplit = fileName.split(".")
        outputFile = strftime(f"../data/{fileNameSplit[0]}_%Y-%m-%d--%H-%M-%S.{fileNameSplit[1]}",gmtime(currentTime))
        return outputFile
        
class MLX90640(DriverBase):

    """
    Construct a new instance of the camera
    """
    def __init__(self, controllerPipe):
        super().__init__("MLX90640")
        self.controllerConnection = controllerPipe
        self.mlx = None
        self.events = {
            "CAPTURE": Event()
        }

    """
    Initialzize a new instance of our "thermal camera"
    """
    def initialize(self):
        self.mlx = ThermalCam()
        logging.info("Succsessfully initialized!")
        self.data["initialized"].value = 1
    
    """
    If a measurement is requested in the form of the CAPTURE event then capture a new image from the camera
    """
    def measure(self) -> None:
        if self.mlx is None:
            return
            
        if(self.getEvent("CAPTURE").is_set()):
            fileName = self.mlx.capture()
            self.controllerConnection.send({'heatmapImage': fileName})
            self.getEvent("CAPTURE").clear()

    """
    Clean up hardware for shutdown
    """
    def kill(self):
        if self.mlx:
            self.mlx.close()


        