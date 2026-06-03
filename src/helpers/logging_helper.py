import logging
import sys


"""
General wrapper for initializing logging formats and file storage
"""


class Logging:
    """
    Configure logging format and output type based on arguments passed to the program

    :param path: The current file path of the module creating our logging module
    :param verbose: Determines wether or not we should be printing all of the info messages or just warning and higher
    """

    def __init__(self, verbose=True):
        FORMAT = "%(asctime)s [%(filename)s:%(funcName)s:%(lineno)d] [%(levelname)s] %(message)s"

        loggingLevel = logging.INFO
        if not verbose:
            loggingLevel = logging.WARNING

        # Check if we want to specify an output file for the logging
        if len(sys.argv) < 2:
            logging.basicConfig(format=FORMAT, level=loggingLevel)
            logging.info(
                "No output file specified file logging will be disabled to enable: ./main.py <outputfilepath>"
            )
        else:
            logging.basicConfig(
                format=FORMAT,
                level=logging.INFO,
                handlers=[logging.FileHandler(sys.argv[1]), logging.StreamHandler()],
            )
