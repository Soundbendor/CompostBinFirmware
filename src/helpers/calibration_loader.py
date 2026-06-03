import json
import logging


"""
Load sensor calibration details from a given file
"""


class CalibrationLoader:
    """
    Create a new instance of our calibration data loader

    :param file: The name of the JSON file our calibration data is stored in
    """

    def __init__(self, file="CalibrationDetails.json"):
        logging.info(f"Retrieving calibration details from file: {file}")

        # Attempt to open the file and convert the contents to JSON object
        with open(file, "r") as f:
            self.data = json.load(f)
            logging.info("Succsessfully loaded calibration details!")

    """
    Retrieve the given calibration data

    :param field: The key name where the calibration data is stored
    """

    def get(self, field):
        return self.data[field]
