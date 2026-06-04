"""
Will Richards, Daniel Lau, Oregon State University, 2024

WiFi/Bluetooh driver for handling device-to-device communication with the bucket
"""

import asyncio
from genericpath import isfile
import json
import logging
import subprocess
import uuid
from time import sleep, time
from typing import Union
import re
import os
from multiprocessing import Event, Value

from bluez_peripheral.advert import Advertisement
from bluez_peripheral.agent import NoIoAgent
from bluez_peripheral.gatt.characteristic import CharacteristicFlags as CharFlags
from bluez_peripheral.gatt.characteristic import characteristic
from bluez_peripheral.gatt.service import Service, ServiceCollection
from bluez_peripheral.util import Adapter, get_message_bus

from drivers.DriverBase import DriverBase
from helpers import RequestHandler

"""
Provides interaction between our device and the network we are connected or attempting to connect to
"""


class WiFiManager:
    def __init__(self):
        self.requests = RequestHandler()
        self.lastConnectionResult = {"success": False, "message": "", "timestamp": 0}
        self.lastWiFiScan = {}
        self.scanNetworks()
        self.isConnectedBool = False

    """
    Run a given command as a list of arguments ["ping", "8.8.8.8"]
    """

    def _runCommand(self, cmd: list[str]):
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return process.returncode, process

    """
    Given the result from nmcli we want to pull out the network name and the signal strength and return them as dict of the two SSID: Signal Strength
    """

    def _parseNetworkList(self, cmdOutput: str):
        resultNetworks = {}
        output = cmdOutput.split("\n")

        # For each network that we discovered during our scan we want to split and remove all duplicates so we have a list of network names mapped to signal strengths
        for network in output:
            try:
                network = network.strip()

                # Allow for networks with ":" in them
                splitNetworkName = re.split(r'(?<!\\):', network)
                splitNetworkName[0] = splitNetworkName[0].replace("\\:", ":")

                if len(splitNetworkName[0]) > 0 and (
                    splitNetworkName[0] not in resultNetworks
                ):
                    resultNetworks[splitNetworkName[0]] = {
                        "strength": int(splitNetworkName[1]),
                        "security": (
                            splitNetworkName[2]
                            if len(splitNetworkName[2]) > 1
                            else "Open"
                        ),
                    }
            except ValueError as e:
                continue

        # Prune network list down to less than 512 characters
        while len(str(resultNetworks)) > 512:
            networks = list(resultNetworks.keys())
            del resultNetworks[networks[len(networks) - 1]]
        return resultNetworks

    """
    Scan for available networks
    """

    def scanNetworks(self):
        _, _ = self._runCommand(["iwlist", "wlan0", "scan"])
        returnCode, process = self._runCommand(
            ["nmcli", "-g", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"]
        )
        if returnCode == 0:
            # Create a dict of network names to signals to avoid duplicate networks
            discoveredNetworks = self._parseNetworkList(process.stdout.decode("utf-8"))
            self.lastWiFiScan = discoveredNetworks
            return True
        else:
            logging.error("Failed to scan WiFi networks!")
            return False

    """
    Get the results from the last WiFi scan
    """

    def getLastScanResults(self):
        return self.lastWiFiScan

    """
    Get the results from the last attempted connection
    """

    def getLastConnectionResults(self):
        return self.lastConnectionResult

    """
    Connect to a specified network

    :param ssid: The network name to connect to
    :param password: The password to connect to the network with
    """

    def connectToNetwork(self, ssid, password):
        returnCode, process = self._runCommand(
            ["nmcli", "device", "wifi", "connect", ssid, "password", password]
        )

        # If we succsessfully exited the program that means we were able to connect to the network
        if returnCode == 0:
            logging.info(f"Successfully connected to network: {ssid}")

            # Enable unlimited reconnection attempts for the given network
            _, process = self._runCommand(
                ["nmcli", "c", "modify", ssid, "connection.autoconnect-retries", "0"]
            )

            self.lastConnectionResult = {
                "message": "Wi-Fi configuration successful",
                "success": True,
                "timestamp": time(),
            }
            return True
        else:
            logging.error(f"Failed to connect to network: {ssid}")
            self.lastConnectionResult = {
                "message": "Wi-Fi configuration failed",
                "log": process.stderr.decode("utf-8").strip(),
                "success": False,
                "timestamp": time(),
            }
            return False

    """
    Check if we are actually connected to the internet by sending a heartbeat request to our API
    """

    def checkConnection(self):
        returnCode, process = self._runCommand(
            ["nmcli", "-t", "-f", "NAME", "c", "show", "--active"]
        )

        # If we got a 0 return code attempt to parse out the active network name
        if returnCode == 0:
            activeNetwork = process.stdout.decode("utf-8").split("\n")[0].strip()

            # If we do show up as being connected to an actual network we want to send a heartbeat to see if we have an actual internet connection
            hasInternet = self.requests.checkNetworkConnection()

            # If we have internet we want to set is connected equal to true
            if hasInternet:
                self.isConnectedBool = True
            return {
                "message": f"Connected to {activeNetwork}",
                "success": True,
                "internet_access": hasInternet,
            }
        else:
            self.isConnectedBool = False
            return {"message": "Not connected to Wi-Fi", "success": False}
        

    """
    Disconnect from the given network by name
    """
    def disconnectFromNetwork(self, ssid):
        returnCode, process = self._runCommand(["nmcli", "connection", "delete", ssid])
        if returnCode == 0:
            self.isConnectedBool = False
            return True
        else:
            return False
        
    def isConnected(self):
        return self.isConnectedBool


"""
Provides interfaces for communicating with bluetooth devices such as phones or laptops
"""


class BluetoothDriver(DriverBase):
    """
    Provides bluetooth service descriptor for the WiFi setup procedure
    """

    class WiFiSetupSerivce(Service):
        """
        Start the bluetooth service with the unique indentifier
        """

        def __init__(self):
            super().__init__(str(31415924535897932384626433832790), True)
            self.wifi = WiFiManager()

        """
        Return the current status of our connection, are we connected to a network and if so are we also connected to the internet
        """

        @characteristic(str(31415924535897932384626433832790 + 1), CharFlags.READ)
        def getConnectionStatus(self, options):
            return json.dumps(self.wifi.checkConnection()).encode("utf-8")

        """
        Returns the result of the last Wi-Fi connection attempt
        """

        @characteristic(
            str(31415924535897932384626433832790 + 2),
            CharFlags.WRITE | CharFlags.READ | CharFlags.WRITE_WITHOUT_RESPONSE,
        )
        def setWIFiArgs(self, options):
            return json.dumps(self.wifi.lastConnectionResult).encode("utf-8")

        """
        Takes the Wi-Fi credentials recieved from a remote device and attempts to connect to the network provided in the request
        """

        @setWIFiArgs.setter
        def setWIFIArgs(self, value, options):
            ssid = ""
            password = ""
            decodedValue = str(value.decode("utf-8"))

            try:
                data = json.loads(decodedValue)
                ssid = data["ssid"]
                password = data["password"]

            except Exception as e:
                logging.error(f"An error occurred when setting WiFi credentials: {e}")
                self.lastConnectionResult = {
                    "success": False,
                    "message": e,
                    "timestamp": time(),
                }

            self.wifi.connectToNetwork(ssid, password)
            return json.dumps(self.wifi.lastConnectionResult).encode("utf-8")

        """
        Returns a JSON document with the list of in range access points, their strength and security type
        """

        @characteristic(
            str(31415924535897932384626433832790 + 3), CharFlags.NOTIFY | CharFlags.READ
        )
        def getScannedNetworks(self, options):
            return json.dumps(self.wifi.lastWiFiScan).encode("utf-8")


        """
        Disconnects from a given WiFi network
        """
        @characteristic(
            str(31415924535897932384626433832790 + 4),
            CharFlags.WRITE | CharFlags.WRITE_WITHOUT_RESPONSE
        ).setter
        def disconnectFromNetwork(self,value, options):
            decodedValue = str(value.decode('utf-8'))
            try:
                data = json.loads(decodedValue)
            except Exception as e:
                logging.error(f"An error occurred when disconnecting from WiFi network: {e}")
    
            if "ssid" in data:
                if self.wifi.disconnectFromNetwork(data["ssid"]):
                   logging.info("Succsessfully disconnected from WiFi network!")
                else:
                    logging.error(f"Failed to disconnect from WiFi netowrk: {data['ssid']}")
            else:
                logging.error("SSID not supplied in request!")
                
            
            

    """
    Handles the transmission and valididation of API keys
    """

    class APISetupService(Service):
        def __init__(self):
            super().__init__("ABC0", True)
            self.requests = RequestHandler()
            

        def checkAPIConnection(self):
            return self.requests.sendSecureHeartbeat()

        @characteristic(
            "ABC1", CharFlags.WRITE | CharFlags.READ | CharFlags.WRITE_WITHOUT_RESPONSE
        )
        def setAPIKey(self, options):
            return str(self.checkAPIConnection()).encode("utf-8")

        @setAPIKey.setter
        def setAPIKey(self, value, options):
            try:
                decodedValue = str(value.decode("utf-8")).strip()
                data = json.loads(decodedValue)
                print("Decoded JSON!")
            except Exception as e:
                print(f"An error occurred: {e}")
                return False
           
            # Formulate new FastAPI credentials based on the incoming data
            creds = {
                "FASTAPI_CREDS": {
                    "apiKey": data["apiKey"],
                    "endpoint": data["endpoint"],
                    "port": int(data["port"]),
                }
            }

            jsonString = json.dumps(creds)
            # Write the new credentials to the config.secret file
            with open("config.secret", "w") as file:
                file.write(jsonString)

            # Then have the requests library update the credentials currently loaded into the system
            self.requests.updateAPICreds()
            print("Written to file and updated credentials!")

        @characteristic("ABC2", CharFlags.READ)
        def getAPIKey(self, options):
            response = {"apiKey": self.requests.getAPIKey(), "deviceID": self.requests.serial}

            return json.dumps(response).encode("utf-8")

    """
    Handles requests to test specific components 
    """

    class DebugService(Service):
        def __init__(self, muted):
            super().__init__("BEEF", True)
            self.isMuted = muted
        
        def _clearCache(self):
            try:
                filesInDir = os.listdir("../data")
                for file in filesInDir:
                    file_path = os.path.join("../data", file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)

                return True
            except OSError as e:
                logging.error(f"Failed to clear cache: {e}")
                return False
                
        @characteristic(
            "BEF0", CharFlags.WRITE | CharFlags.READ | CharFlags.WRITE_WITHOUT_RESPONSE
        )
        def setMuted(self, options):
            return str(self.isMuted).encode("utf-8")

        @setMuted.setter
        def setMuted(self, value, options):
            try:
                decodedValue = str(value.decode('utf-8'))
                if decodedValue == "True":
                    self.isMuted = True
                else:
                    self.isMuted = False
            except Exception as e:
                print(f"An error occurred: {e}")
                return False
            
        @characteristic(
            "BEF1",
            CharFlags.WRITE | CharFlags.WRITE_WITHOUT_RESPONSE
        ).setter
        def clearCache(self, value, options):
            try:
                decodedValue = str(value.decode('utf-8'))
                if decodedValue == "True":
                    self._clearCache()
            except Exception as e:
                logging.error(f"An error occurred: {e}")
                return False

    """
    Construct a new instance of the bluetooth driver
    """

    def __init__(self, muted):
        super().__init__("BluetoothDriver")
        self.muted = muted
        self.events = {
            "LOST_WIFI_CONNECTION": Event(),
            "GOT_WIFI_CONNECTION": Event(),
            "BLUETOOTH_STOPPED": Event(),
            "BLUETOOTH_RESTARTED": Event(),
        }

    """
    Start the Bluetooth server
    """
    def startServer(self):
        async def run_server():
            await self.setupBus()
            await self.controlLoop()
        asyncio.run(run_server())

    def initialize(self):
        self.wifiService = self.WiFiSetupSerivce()
        self.apiService = self.APISetupService()
        self.debugService = self.DebugService(self.muted)
        self.isServerRunning = False
        self.wifi = self.wifiService.wifi
        self.lastConnectionStatus = bool(self.wifi.checkConnection()["internet_access"])
        self.data["muted"].value = self.muted
        self.loopTime = 20
        self.startServer()
        

    """
    Check once every 20 seconds to see if our connection is still alive and if not we want to inform the controller that we have lost connection
    """
    def updateConnectionState(self):
        connectionStatus =  bool(self.wifi.checkConnection()["internet_access"])

        # Check if in between the current sample and now we have lost the connection
        if connectionStatus == False and self.lastConnectionStatus == True:
            self.getEvent("LOST_WIFI_CONNECTION").set()

        elif connectionStatus == True and self.lastConnectionStatus == False:
            self.getEvent("GOT_WIFI_CONNECTION").set()

        self.lastConnectionStatus = connectionStatus
   
    """
    Handle updating our connection state
    """
    def measure(self):
       self.updateConnectionState()

    def createDataDict(self):
        self.data = {
            "initialized": Value('i', 0),
            "muted": Value('i', 0)
        }
        return self.data
    
    # While the server is running we want to refersh the list of WiFi networks every 10 seconds
    async def controlLoop(self):
        while True:
            self.updateConnectionState()
            self.data["muted"].value = int(self.debugService.isMuted)

            if not self.wifi.isConnected():
                self.wifi.scanNetworks()
                self.lastConnectionStatus = False
                
            await asyncio.sleep(10)

    async def setupBus(self):
        bus = await get_message_bus()

        # Register our services with a service collection so we can run several at the same time
        serviceCollection = ServiceCollection()
        serviceCollection.add_service(self.wifiService)
        serviceCollection.add_service(self.apiService)
        serviceCollection.add_service(self.debugService)

        await serviceCollection.register(bus)
        logging.info("Registered services.")

        agent = NoIoAgent()
        await agent.register(bus)

        adapter = await Adapter.get_first(bus)
        bluetoothName = "Binsight Compost Bin"
        await adapter.set_alias(bluetoothName)
        advert = Advertisement(
            bluetoothName, [str(31415924535897932384626433832790), "ABC0"], 0x0, 0
        )

        try:
            await advert.register(bus, adapter)
            self.initialized = True
            self.data["initialized"].value = 1
            logging.info("Advertising Bluetooth Device")

        except:
            pass

    """
    Run a given command as a complete string like "ping 8.8.8.8"

    :param cmd: The command to run as one contigious string
    """

    def _runCommand(self, cmd: Union[str, list[str]]):
        final_cmd = cmd.split(" ") if isinstance(cmd, str) else cmd
        process = subprocess.run(
            final_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return process.returncode, process
