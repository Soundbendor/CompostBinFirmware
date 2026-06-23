import json
import logging
import os
import smtplib
import socket
import sys
import uuid
from csv import excel_tab
from email.mime.text import MIMEText
from time import time

import botocore
import httpx
from aws_secretsmanager_caching import SecretCache, SecretCacheConfig
from botocore.exceptions import NoCredentialsError, PartialCredentialsError


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


"""
Handles requests to remote APIs (S3 and FastAPI)
"""


class RequestHandler:
    def __init__(self, dataDir="../data", secret_file="config.secret"):
        self.secret_file = secret_file
        self.dataDir = dataDir
        self.apiKey, self.endpoint, self.port = self.loadFastAPICredentials(secret_file)
        self.appPassword, self.emailAddress = self.loadEmailCredentials()

        # Check if the app password is equal to FAILED then we know it didn't get the email credentials and should retry when we have a network connection
        if self.appPassword == "FAILED":
            self.gotEmailCreds = False
        else:
            self.gotEmailCreds = True

        self.endpoint = f"https://{self.endpoint}:{self.port}"
        self.serial = self._getSerial()

        logging.basicConfig(
            format="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            level=logging.DEBUG,
        )

    """
    Check to see if our bucket can communicate with the internet at all, effictvely ping 8.8.8.8
    """

    def checkNetworkConnection(self, host="8.8.8.8", port=53, timeout=3) -> bool:
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            return True
        except socket.error as ex:
            logging.error(f"Failed to connect to {host}: {ex}")
            return False

    """
    Get the currently set API key
    """

    def getAPIKey(self):
        return self.apiKey

    """
    Test method to verify our API key is functioning

    :param apiKey: Our API Key used to authenticate with our API
    """

    def sendHeartbeat(self):
        endpoint = self.endpoint + "/api/health/heartbeat"
        client = httpx.Client(verify=False)

        # Attempt to send the packet
        failed = False
        try:
            response = client.get(endpoint).json()
        except Exception as e:
            logging.error(f"Exception occurred while sending hearbeat: {e}")
            return False
            client.close()
        finally:
            client.close()

        if "is_alive" in response and response["is_alive"] == True:
            logging.info("Succsessfully recieved hearbeat!")

            # If we weren't able to get the email creds last time now that we for sure have network we should try again
            if not self.gotEmailCreds:
                self.appPassword, self.emailAddress = self.loadEmailCredentials()

                # Check if the app password is equal to FAILED then we know it didn't get the email credentials and should retry when we have a network connection
                if self.appPassword == "FAILED":
                    self.gotEmailCreds = False
                else:
                    self.gotEmailCreds = True

            return True
        else:
            logging.error("Failed to recieive heartbeat from server!")
            return False

    """
    Request that the API credentials be updated to the most recent ones stored in the file
    """

    def updateAPICreds(self):
        self.apiKey, self.endpoint, self.port = self.loadFastAPICredentials(
            self.secret_file
        )
        self.endpoint = f"https://{self.endpoint}:{self.port}"

    """
    Send a secure heartbeat request to the API
    """

    def sendSecureHeartbeat(self):
        endpoint = self.endpoint + "/api/health/secure_heartbeat"
        headers = {
            "token": self.apiKey,
        }
        client = httpx.Client(verify=False)
        try:
            response = client.get(endpoint, headers=headers).json()
        except Exception as e:
            logging.error(f"Exception occurred while sending hearbeat: {e}")
            client.close()
            return False
        finally:
            client.close()

        if "is_alive" in response and response["is_alive"] == True:
            logging.info("Succsessfully recieved hearbeat!")
            return True
        else:
            logging.error("Failed to recieive heartbeat from server!")
            return False

    def sendAPIRequest(self, fileNames: dict, data: dict):
        endpoint = self.endpoint + "/api/scan"

        # Get current timestamp
        # Create file names for colorImage, depthImage, heatmapImage, topologyMap, and voiceRecording

        basenames = {k: os.path.basename(v) for k, v in fileNames.items()}
        headers = {
            "token": self.apiKey,
            "accept": "application/json",
        }

        payload = {
            "colorImage": str(basenames["colorImage"]),
            "depthImage": str(basenames["depthImage"]),
            "heatmapImage": str(basenames["heatmapImage"]),
            "topologyMap": str(basenames["topologyMap"]),
            "voiceRecording": str(basenames["voiceRecording"]),
            "total_weight": float(data["NAU7802"]["data"]["weight"]),
            "weight_delta": float(data["NAU7802"]["data"]["weight_delta"]),
            "temperature": float(data["BME688"]["data"]["temperature(c)"]),
            "pressure": float(data["BME688"]["data"]["pressure(kpa)"]),
            "humidity": float(data["BME688"]["data"]["humidity(%rh)"]),
            "iaq": float(data["BME688"]["data"]["iaq"]),
            "co2_eq": float(data["BME688"]["data"]["CO2-eq"]),
            "tvoc": float(data["BME688"]["data"]["bVOC-eq"]),
            "transcription": str(data["SoundController"]["data"]["TranscribedText"]),
            "userTrigger": bool(data["DriverManager"]["data"]["userTrigger"]),
            "deviceID": str(self.serial),
        }
        data = {"data": json.dumps(payload)}

        file_keys = [
            "colorImage",
            "depthImage",
            "heatmapImage",
            "topologyMap",
            "voiceRecording",
        ]
        files = [("files", open(fileNames[k], "rb")) for k in file_keys]

        with httpx.Client(headers=headers, timeout=60, verify=False) as client:
            try:
                response = client.post(
                    endpoint,
                    files=files,
                    data=data,
                )
                response_json = response.json()
                print(f"DEBUG: {response}")
            except Exception as e:
                logging.error(f"Exception occurred while sending API request: {e}")
                return (False, -1, str(e))

            if "status" in response_json and response_json["status"] == True:
                logging.info("Data successfully uploaded!")
                return (True, response.status_code, response.text)
            else:
                logging.error("Failed to upload data to API.")
                return (False, response.status_code, response.text)

    """
    Sends an email to our support server when an error occurs when attempting to upload a packer

    :param error_code: The code that was returned from the request
    :param error_message: The exception or the error that was returned by the request
    """

    def sendErrorEmail(self, error_code, error_message):
        subject = f"[Bucket Upload Error] Device: {self.serial} encountered a {error_code} error code."
        body = f"The following was returned as the error in question:\t{error_message}"

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self.emailAddress
        msg["To"] = self.emailAddress

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp_server:
                smtp_server.login(self.emailAddress, self.appPassword)
                smtp_server.sendmail(
                    self.emailAddress, self.emailAddress, msg.as_string()
                )
                return True
        except Exception as e:
            logging.error("Error occurred sending email: {e}")
            return False

    """
    Load and return our Fast API credentials

    :param file: The file our credentials are stored in
    """

    def loadFastAPICredentials(self, file):
        secretFile = open(file, "r")
        credsJson = json.load(secretFile)
        secretFile.close()
        return (
            credsJson["FASTAPI_CREDS"]["apiKey"],
            credsJson["FASTAPI_CREDS"]["endpoint"],
            credsJson["FASTAPI_CREDS"]["port"],
        )

    """
    Load a Gmail app password from a file

    :param file: The file the credentials are stored in
    """

    def loadEmailCredentials(self):
        try:
            client = botocore.session.get_session().create_client(
                "secretsmanager", region_name="us-west-2"
            )
            cache_config = SecretCacheConfig()
            cache = SecretCache(config=cache_config, client=client)
            email = cache.get_secret_string("sb_notification_email")
            pword = cache.get_secret_string("sb_notification_password")
            return pword, email
        except Exception as e:
            logging.error(f"Failed to retrieve email credentials: {e}")
            return "FAILED", "FAILED"

        # secretFile = open(file, "r")
        # credsJson = json.load(secretFile)
        # secretFile.close()
        # return (
        #     credsJson["EMAIL_LOGGING"]["appCode"],
        #     credsJson["EMAIL_LOGGING"]["email"],
        # )

    """
    Get the serial number of this specific raspberry Pi by querying /proc/cpuinfo
    """

    def _getSerial(self):
        # Extract serial from cpuinfo file
        cpuserial = "0000000000000000"
        try:
            f = open("/proc/cpuinfo", "r")
            for line in f:
                if line[0:6] == "Serial":
                    cpuserial = line[10:26]
            f.close()
        except:
            cpuserial = "ERROR000000000"

        return cpuserial
