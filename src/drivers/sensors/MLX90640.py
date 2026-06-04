""" "
Will Richards, Oregon State University, 2023

Abstraction layer for the MLX90640
"""

from multiprocessing import Event
import adafruit_mlx90640
import math
import board
import busio
import logging
import numpy as np
from time import time, strftime, gmtime
from PIL import Image

from drivers.DriverBase import DriverBase


class MLX90640(DriverBase):
    """
    Construct a new instance of the camera
    """

    def __init__(self, controllerPipe):
        super().__init__("MLX90640")
        self.controllerConnection = controllerPipe
        self.MIN_TEMP = 10.0
        self.MAX_TEMP = 50.0
        self.COLORDEPTH = 1000
        # Constant factor by which we scale the thermal image
        # In this case, take (32, 24) and scale to (800, 600)
        self.INTERPOLATE_FACTOR = 25
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
        if self.i2c:
            self.i2c.deinit()

    """
    Convert MLX raw sensor reading to image
    """

    def frame_to_image(self, frame: np.ndarray) -> Image:
        img = Image.new("RGB", (32, 24))
        # experimental: min-max based on sensor reading
        self.MIN_TEMP = np.min(frame)
        self.MAX_TEMP = np.max(frame)
        frame = self.map_color(frame)
        img.putdata(frame)
        img = img.resize(
            (32 * self.INTERPOLATE_FACTOR, 24 * self.INTERPOLATE_FACTOR), Image.BICUBIC
        )
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
            (frame - self.MIN_TEMP)
            * (self.COLORDEPTH - 1)
            / (self.MAX_TEMP - self.MIN_TEMP)
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
