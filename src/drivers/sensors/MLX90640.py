""" "
Will Richards, Oregon State University, 2023

Abstraction layer for the MLX90640
"""

from mlx90640 import MLX90640 as mlx90640

from multiprocessing import Event
import adafruit_mlx90640
import math
import board
import busio
import logging
import cv2
import numpy as np
from scipy import ndimage
from time import time, strftime, gmtime
from enum import Enum
import cmapy
from PIL import Image

from drivers.DriverBase import DriverBase

"""
Enum to map readable camera refresh rates to there integer values
"""


class CameraRefreshRate(Enum):
    RATE_05 = (0x00,)
    RATE_1 = (0x01,)
    RATE_2 = (0x02,)
    RATE_4 = (0x03,)
    RATE_8 = (0x04,)
    RATE_16 = (0x05,)
    RATE_32 = (0x06,)
    RATE_64 = 0x07


"""
Class used to convert the data from the IR matrix into a thermal camera of sorts
"""


class ThermalCam:
    # Heatmap generation parameters
    _colormap_list = [
        "jet",
        "bwr",
        "seismic",
        "coolwarm",
        "PiYG_r",
        "tab10",
        "tab20",
        "gnuplot2",
        "brg",
    ]
    _interpolation_list = [
        cv2.INTER_NEAREST,
        cv2.INTER_LINEAR,
        cv2.INTER_AREA,
        cv2.INTER_CUBIC,
        cv2.INTER_LANCZOS4,
        5,
        6,
    ]
    _interpolation_list_name = [
        "Nearest",
        "Inter Linear",
        "Inter Area",
        "Inter Cubic",
        "Inter Lanczos4",
        "Pure Scipy",
        "Scipy/CV2 Mixed",
    ]

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
        norm = np.uint8(((f - Tmin) / (Tmax - Tmin)) * 255)
        norm.shape = (24, 32)
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
        image = cv2.applyColorMap(
            image, cmapy.cmap(self._colormap_list[self._colormap_index])
        )
        image = cv2.resize(image, (800, 600), interpolation=cv2.INTER_CUBIC)

        # Flip image and filter to get smooth upright image
        image = cv2.flip(image, 0)
        image = cv2.bilateralFilter(image, 15, 80, 80)
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
        outputFile = strftime(
            f"../data/{fileNameSplit[0]}_%Y-%m-%d--%H-%M-%S.{fileNameSplit[1]}",
            gmtime(currentTime),
        )
        return outputFile


class MLX90640(DriverBase):
    """
    Construct a new instance of the camera
    """

    def __init__(self, controllerPipe):
        super().__init__("MLX90640")
        self.controllerConnection = controllerPipe
        self.MIN_TEMP = 20.0
        self.MAX_TEMP = 50.0
        self.COLORDEPTH = 1000
        self.mlx = None
        self.i2c = None
        self.colormap = self._generate_cmap()
        self.events = {"CAPTURE": Event()}

    """
    Initialzize a new instance of our "thermal camera"
    """

    def initialize(self):
        self.i2c = busio.I2C(board.SCL, board.SDA, frequency=8000000)
        self.mlx = adafruit_mlx90640.MLX90640(self.i2c)
        self.mlx.refreshRate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ
        logging.info("Succsessfully initialized!")
        self.data["initialized"].value = 1

    """
    If a measurement is requested in the form of the CAPTURE event then capture a new image from the camera
    """

    def measure(self) -> None:
        if self.mlx is None:
            return

        if self.getEvent("CAPTURE").is_set():
            frame = np.zeros(768)
            for _ in range(3):
                try:
                    self.mlx.getFrame(frame)
                except ValueError:
                    continue
            # TODO: Should have an error handler here in case retries fail
            img = self.frame_to_image(frame)
            fname = self._formatFileName("heatmap.jpg")
            img.save(fname)
            self.controllerConnection.send({"heatmapImage": fname})
            self.getEvent("CAPTURE").clear()

    """
    Clean up hardware for shutdown
    """

    def kill(self):
        if self.mlx:
            self.mlx.close()

    """
    Convert MLX raw sensor reading to image
    """

    def frame_to_image(self, frame: np.ndarray) -> Image:
        img = Image.new("RGB", (32, 24))
        frame = self.map_color(frame)
        img.putdata(frame)
        return img

    """
    Helper functions for colormap
    """

    def constrain(self, val, min_val, max_val):
        return min(max_val, max(min_val, val))

    def map_value(self, x, in_min, in_max, out_min, out_max):
        return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

    def gaussian(self, x, a, b, c, d=0):
        return a * math.exp(-((x - b) ** 2) / (2 * c**2)) + d

    """
    Map MLX raw sensor reading to colorized values
    """

    def map_color(self, frame: np.ndarray) -> list:
        # Map temperatures to 0-999 range
        color_indices = (
            (frame - self.MIN_TEMP) * (self.COLORDEPTH - 1) / (self.MAX_TEMP - self.MIN_TEMP)
        )
        # Constrain to valid colormap range and convert to int
        color_indices = np.clip(color_indices, 0, self.COLORDEPTH - 1).astype(int)
        
        # Map indices to RGB tuples from self.colormap
        return [self.colormap[idx] for idx in color_indices]

    """
    Generate colormap used by map_color
    """

    def _generate_cmap(self):
        # the list of colors we can choose from
        heatmap = [
            (0.0, (0, 0, 0)),
            (0.20, (0, 0, 0.5)),
            (0.40, (0, 0.5, 0)),
            (0.60, (0.5, 0, 0)),
            (0.80, (0.75, 0.75, 0)),
            (0.90, (1.0, 0.75, 0)),
            (1.00, (1.0, 1.0, 1.0)),
        ]

        colormap = [0] * self.COLORDEPTH

        def gradient(x, width, cmap, spread=1):
            width = float(width)
            r = sum(
                self.gaussian(x, p[1][0], p[0] * width, width / (spread * len(cmap)))
                for p in cmap
            )
            g = sum(
                self.gaussian(x, p[1][1], p[0] * width, width / (spread * len(cmap)))
                for p in cmap
            )
            b = sum(
                self.gaussian(x, p[1][2], p[0] * width, width / (spread * len(cmap)))
                for p in cmap
            )
            r = int(self.constrain(r * 255, 0, 255))
            g = int(self.constrain(g * 255, 0, 255))
            b = int(self.constrain(b * 255, 0, 255))
            return r, g, b

        for i in range(self.COLORDEPTH):
            colormap[i] = gradient(i, self.COLORDEPTH, heatmap)

        return colormap

    """
    Generate timestamped file name for thermal image
    """

    def _formatFileName(self, fileName: str):
        currentTime = time()
        fileNameSplit = fileName.split(".")
        outputFile = strftime(
            f"../data/{fileNameSplit[0]}_%Y-%m-%d--%H-%M-%S.{fileNameSplit[1]}",
            gmtime(currentTime),
        )
        return outputFile
