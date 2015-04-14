#!/usr/bin/env python

"""
A Python driver for the CM19a X10 RF Transceiver (USB)
This is a user space driver so a kernel driver for the CM19a does not need to be installed.

Functionality
 - Use a CM19a to send any X10 on/off command (eg A1 OFF, C16 DIM) wirelessly to a lamp or appliance module (requires an X10 receiver module).
 - Use a CM19a to automatically receive and log to a queue any command received from an X10 RF remote control.

Coded by: Andrew Cuddon (www.cuddon.net)

Version 3.0
September 2011

Changelog 0.20 - 3.0
- Added basic command line argument functionality
    * e.g. cm19a_X10_USB.py A1 ON
    * Send only, you cannot receive commands via this approach becuase the device does not maintain a queue of commands received.
    * Relatively slow because the driver must initialise the device each time and then exit.
    * This is the default mode of operation: MODE = 'Command Line'
- Added in-built HTTP server
    * Send and receive commands via a web browser, any app that supports http, or even the command line (using cURL)
    * e.g. http://192.168.1.3:8008/?house=A&unit=1&command=ON
    * The driver starts and remains running so it can monitor and respond to http requests and capture inbound RF commands received by the CM19a
    * Faster than the basic command line interface becuase the device needs to be initilaised only once (at startup)
    * You need to set MODE = 'HTTP Server' to use the driver this way. You also need to set the IP address and port you wish to use.
- Fixed several bugs relating to bright/dim functionality
    * Added in missing bright/dim commands to the protocol file
    * Modified approach to decode bright/dim button presses from a X10 RF remote
    * Now identifies the house code as well as the button pressessed (bright or dim) on the RF keychain remote

Changelog 0.11 - 0.20
- Added Bright/Dim functionality
- Added Python Logging
- Bug fixes
- When searching for a CM19a exits the search when it finds the first matching device
- Added flag to control whether to start the receiving thread automatically (default is to start)
- Some methods renamed so they are not exposed as an XML-RPC call (via a separate programme)

Changelog 0.1 - 0.11
- Add saving error messages to an object attribute so they can be utilised by a separate UI app
- Fixed a couple of coding errors

Requires:
    pyUSB
    libusb 0.1 series

NOTES:
- You need to disable any other driver that attempts to attach to this device:
    On Ubuntu 11.04:
        sudo nano  /etc/modprobe.d/blacklist.conf  (may just be blacklist (without the .conf) on other distros)
        Add in the follow text and save
            # To enable CM19a X10 Transceiver to work
            blacklist lirc_atiusb
            blacklist ati_remote
        reboot

- To claim control of the USB device you may find you need to run this as the root user
- On Ubuntu you could use:
    sudo python CM19a_X10_USB.py
- But this is not very good practice

It is better to set permissions via udev
1. Create a udev permissions files so that when udev creates a device file when the transceiver is connected, the correct permissions are set
    sudo nano /etc/udev/rules.d/cm19a.rules
        Note that I did not number this file so it runs after all other permissions are set.
2. Add in the following text and save
    # Allow all users to read and write to the CM19a X10 Transceiver (USB)
    SYSFS{idVendor}=="0bc7", SYSFS{idProduct}=="0002", MODE="666"
3. If your CM19a is plugged in, then remove, wait a sec or two and then plug it back in again. The correct permissions should now be set.
4. Any user should now be able to run the driver without using sudo.
    eg. From a terminal: ./CM19aDriver.py

TTDs
    * Web graphical interface
    * Identifying and detaching any pre-existing kernel driver
    * Run as a daemon
    * User Privileges

"""

# *************** CONFIGURATION ***************

LOGFILE = './cm19a.log'             # Path and filename for the logfile

#MODE = 'Command Line'              # Mode of operation: either 'Command Line', 'HTTP Server'
MODE = 'HTTP Server'

# Required only if MODE == 'HTTP Server'
SERVER_IP_ADDRESS = '192.168.1.3'              # Set SERVERIP to the IP address of the server
SERVER_PORT = 8008                             # Consider firewall rules if any

# Required only for HTTP Server and importing into another script
REFRESH = 1.0               # Refresh rate (seconds) for polling the transceiver for inbound commands


# *************** CODE ***************
VERSION = "3.00"

# Standard modules
import sys, time, os, threading, types
import socket, BaseHTTPServer, httplib

# pyUSB 1.0 (for libUSB 1.0 series)
import usb

# Code Modules
import logger

# Globals
global cm19a, log, server

class USBdevice:
    def __init__(self, vendor_id, product_id) :
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.bus = None
        self.device = None
        self._find_device()

    def _find_device(self):
        # Search across all USB busses for the nominated device
        # Finishes searching when the first matching device is found
        buses = usb.busses()
        for bus in buses :
            for device in bus.devices :
                if device.idVendor == self.vendor_id and device.idProduct == self.product_id:
                    self.bus = bus
                    self.device = device
                    break
            #end for loop
            if self.device:
                # A device was found so look no further
                break
        #end for loop

    def get_device(self):
        return self.device

    def print_device_info(self):
        "Prints out the device information"
        if not self.device:
            print "Device (%r, %r) not found" % (self.vendor_id, self.product_id)
            return

        print "  Vendor ID (dev.idVendor): %d (%04x hex)" % (self.device.idVendor, self.device.idVendor)
        print "  Product ID (dev.idProduct): %d (%04x hex)" % (self.device.idProduct, self.device.idProduct)
        print "  Device Version:",self.device.deviceVersion
        print "  usbVersion: ",  self.device.usbVersion
        print "  Number of Configurations: ",  len(self.device.configurations)
#end of class


class CM19aDevice(threading.Thread):
    # subclasses the Thread class from the threading module

    # Class constants (run once only when the module is loaded)
    VENDOR_ID = 0x0bc7              # Vendor Id: X10 Wireless Technology, Inc.
    PRODUCT_ID = 0x0002             # Product Id: Firecracker Interface (ACPI-compliant)
    CONFIGURATION_ID = 1            # Use configuration #1 (This device has only 1 configuration)
    INTERFACE_ID = 0                # The interface we use to talk to the device (This is the only configuration available for this device)
    ALTERNATE_SETTING_ID = 0        # The alternate setting to use on the selected interface
    READ_EP_ADDRESS   = 0x081       # Endpoint for reading from the device: 129 (decimal)
    WRITE_EP_ADDRESS  = 0x002       # Endpoint for writing to the device: 2  (decimal)
    PACKET_LENGTH = 8               # Maximum packet length is 8 bytes (possibly 5 for std X10 remotes)
    ACK = 0x0FF                     # Bit string received on CM19a send success = 11111111 (binary) = 255 (decimal)

    SEND_TIMEOUT = 1000             # 1000 ms = 1s
    RECEIVE_TIMEOUT = 100           # 100 ms
    PROTOCOL_FILE = "./CM19aProtocol.ini"

    def __init__(self, refresh=1, loginstance=None, polling=False):
        # Initialise the object and create the device driver
        threading.Thread.__init__(self)     # initialise the thread for automatic monitoring
        self.refresh = refresh
        self.polling = polling
        self.alive = False                  # Set to false to permanently stop the thread that automatic monitors for received commands
        self.paused = False                 # Set to True to temporarily stop automatic monitoring of receive commands
        self.initialised = False            # True when the device has been opened and the driver initialised successfully
        self.device = False                 # USB device class instance
        self.receivequeue = []              # Queue of commands received automatically
        self.receivequeuecount = 0          # Number of items in the receive queue
        self.protocol = {}                  # Dict containing the communications protocol for the CM19a

        # Set up logging
        if loginstance:
            self.log = loginstance
        else:
            # No logger instance provided so create one
            import logger
            self.log = logger.start_logging("CM19a_X10_USB", "./CM19a.log")

        # Find the correct USB device
        self.USB_device = USBdevice(self.VENDOR_ID, self.PRODUCT_ID)
        # save the USB instance that points to the CM19a
        self.device = self.USB_device.device
        if not self.device:
            print >> sys.stderr, "The CM19a is probably not plugged in or is being controlled by another USB driver."
            self.log.error('The CM19a is probably not plugged in or is being controlled by another USB driver.')
            return

        # Open the device for send/receive
        if not self._open_device():
            # Device was not opened successfully
            return

        self.print_device_info()

        # Load the communications protocol
        self._load_protocol()

        # Initialise the device to read the remote controls
        self._initialise_remotes()

        # Start the thread for automatically polling for inbound commands
        # If you just send commands via the CM19a and do not need to check for incoming commands from a remote control
        # then set 'start' to False when the class instance is created
        if self.polling:
            self.start()


    def _open_device(self) :
        """ Open the device, claim the interface, and create a device handle """

        if not self.device:
            # no device object
            return False

        self.handle = None      # file-like handle
        try:
            # Open the device and create a handle
            self.handle = self.device.open()                    # --> DeviceHandle object

            # Select the active configuration
            self.handle.setConfiguration(self.CONFIGURATION_ID)

            # detach any other kernel drivers that are currently attached to the required interface
            #self.handle.detachKernelDriver(self.INTERFACE_ID)

            # Claim control of the interface
            self.handle.claimInterface(self.INTERFACE_ID)

            # Set the alternative setting for this interface
            self.handle.setAltInterface(self.ALTERNATE_SETTING_ID)

            print "Cm19a opened and interface claimed."
            self.log.info("Cm19a opened and interface claimed")
            self.initialised = True
        except usb.USBError, err:
            print >> sys.stderr, err
            self.log.error(err)
            print >> sys.stderr, "Unable to open and claim the CM19a interface."
            self.log.error("Unable to open and claim the CM19a interface.")
            self.initialised = False
            return False

        return True


    def _initialise_remotes(self):
        # Initilises the CM19a for wireless remote controls
        sequence=[]
        sequence.append([0x020,0x034,0x0cb,0x058,0x0a7])       # 5 byte sequence (interestingly this is the same sequence as P16 ON)
        sequence.append([0x080,0x001,0x000,0x020,0x014])       # 5 byte sequence
        sequence.append([0x080,0x001,0x000,0x000,0x014,0x024,0x020,0x020])     # 8 byte sequence

        for s in sequence:
            result = self._write_bytes(s)
            if not result:
                self.log.error("Error initialising the CM19a for wireless remote controls")
                print  >> sys.stderr, "Error initialising the CM19a for wireless remote controls"


    def run(self):
        """
            This is the main function that will run in the thread when start() is issued
            Check for an incoming command received via the CM19a
            If a command is found, it is decoded and added to the receive queue
            Rechecks the device every refresh seconds
            set 'self.alive' to False to halt checking
        """
        self.alive = True
        while self.alive:
            # continues to run the following code in a separate thread until alive is set to false
            if self.paused:
                # Device is paused (eg during a send command) so do not read
                pass
            else:
                # Device is not paused so check for incoming commands
                self.receive()

            # wait for 'refresh' seconds before checking the device again
            time.sleep(self.refresh)


    def receive(self):
        """ Receive any available data from the Cm19a
            Append it to the queue
        """
        if not self.initialised:
            return

        # Raw read any data from the device
        data = None
        try:
            data = self.handle.interruptRead(self.READ_EP_ADDRESS, self.PACKET_LENGTH, self.RECEIVE_TIMEOUT)
        except:
            # error or simply nothing in the buffer to read
            pass

        # Decode the data and add any commands to the receive queue
        if data:
            # something read so add it the the receive queue
            result = self._decode(data)     # decode the byte stream
            if result == str(self.ACK):
                # Ignore any send command acknowledgements
                pass
            else:
                self.receivequeue.append(result)
                self.receivequeuecount = self.receivequeuecount + 1
                #print "Command %s received via the cm19a and added to the receive queue." % result
                self.log.info("Command %s received via the cm19a and added to the receive queue." % result)


    def getReceiveQueue(self):
        """ 
            Returns the queue (list) of incoming commands
            Clears it ready for receiving more
        """

        if self.receivequeuecount > 0:
            # Pause receiving so the receive thread does not add items just before we clear to queue
            self.paused = True
            # Temporarily store the queue because we clear it before we return it the the calling routine
            tmp = self.receivequeue

            # clear the queue
            self.receivequeue = []
            self.receivequeuecount = 0
            self.paused = False
            return tmp
        else:
            # no commands so return an empty queue (list)
            return []


    def send(self, house_code, unit_number, function):
        """
            Sends a command request to the device
            Tries to send just once
            Returns False if an error occurs
        """
        if not self.initialised:
            return False

        self.log.info("Sending %s%s %s" % (house_code.upper(), unit_number, function.upper()))
        print "Sending %s%s %s" % (house_code.upper(), unit_number, function.upper())

        # Encode the command to the X10 protocol
        command_sequence = self._encode(house_code, unit_number, function)        # -> list
        if not command_sequence:
            # encoding error
            self.log.error("Unable to send command; encoding error occurred.")
            return False

        # Pause automatic receiving while we send
        if self.polling:
            self.paused = True
            time.sleep(int(self.refresh/2))

        # Flush the device before we send anything so we do not lose any incoming requests
        self.receive()

        # Write the command sequence to the device
        result = self._write_bytes(command_sequence)
        self.log.info("Result %s%s %s: %r" % (house_code.upper(), unit_number, function.upper(), result))
        print "Result %s%s %s: %r" % (house_code.upper(), unit_number, function.upper(), result)

        # Restart automatic receiving and return
        self.paused = False
        return result


    def _write_bytes(self, bytesequence):
        # Write the bytes to the device
        # bytesequence is a list of bytes to be written
        if len(bytesequence) == 0:
            return False

        try:
            chars_written = self.handle.interruptWrite(self.WRITE_EP_ADDRESS, bytesequence, self.SEND_TIMEOUT)
            returnval = True
        except Exception, err:
            print >> sys.stderr, err
            self.log.error(str(err))
            chars_written = 0
            returnval = False

        if chars_written != len(bytesequence):
            # Incorrect number of bytes written
            print  >> sys.stderr, "Incorrect number of bytes written."
            self.log.error("Incorrect number of bytes written.")
            returnval = False

        return returnval


    def _encode(self, house_code,  unit_number,  on_off):
        """
            Looks up the X10 protocol for the appropriate byte command sequence
        """
        key = house_code.upper() + unit_number + on_off.upper()
        if key in self.protocol:
            return self.protocol[key]
        else:
            print >> sys.stderr, "Unable to encode the requested action: %s" %  key
            self.log.error("Unable to encode the requested action: %s" %  key)
            return False


    def _decode(self, receive_sequence):
        """
            Uses the X10 protocol to decode a command received by the CM19a
            'receive_sequence' is a list of decimal values
            returns the command (housecode, unit number, on/off) that the sequence represents
            If it cannot decode the sequence then the sequence is simply returned
        """

        if not (self.protocol and self.protocol_remote):
            # the protocol has not been loaded
            self.log.error("Cannot decode in inbound command since the protocol is not loaded")
            return ""

        return_value = None

        # Convert the inbound command sequence (bytes) to a string to it can be compared to the protocol values
        # the received command sequence is a list of decimal values (not text)
        # Note: cannot use Python sets for comparing the lists because there may be duplicate values in each list (esp zeros)
        receive_string = ""
        for i in range(len(receive_sequence)):
            receive_string += str(receive_sequence[i])

        # Now search for the string in the protocol
        for cmd, seq in self.protocol.iteritems():
            # Protocol is a dict of command:command_sequence pairs
            # cmd is the command (eg A1OFF)
            # seq is a list of the command bytes
            protocol_string = ""
            for i in range(len(seq)):
                protocol_string += str(seq[i])
            if receive_string == protocol_string:
                # protocol match found
                return_value = cmd
                break

        # Now search for the string in the RF remote protocol (this overrides anything found in the above std x10 protocol)
        for cmd, seq in self.protocol_remote.iteritems():
            # Protocol is a dict of command:command_sequence pairs
            # cmd is the command (eg A1OFF)
            # seq is a list of the command bytes
            protocol_string = ""
            for i in range(len(seq)):
                protocol_string += str(seq[i])
            if receive_string == protocol_string:
                # protocol match found
                return_value = cmd
                break

        if not return_value:
            # The byte string was not found in the protocol so return the bytes
            receive_string = ""
            for i in range(len(receive_sequence)):
                receive_string += str(receive_sequence[i])+" "
            return_value = receive_string

        return return_value.strip()


    def _load_protocol(self):
        # Loads the X10 protocol into a dict

        if not self.device:
            print >> sys.stderr, "Cannot load X10 Protocol since the CM19a is not plugged in."
            self.log.error("Cannot load X10 Protocol since the CM19a is not plugged in.")
            return

        self.protocol = {}  # empty dictionary
        self.protocol_remote = {}  # empty dictionary

        # Open the configuration file
        fname = self.PROTOCOL_FILE
        if not os.path.isfile(fname):
            print >> sys.stderr, "**ERROR**", "Protocol file missing %s" % fname
            self.log.error("**ERROR**", "Protocol file missing %s" % fname)
            self.initialised = False
            return None
        f = open(fname, "r")

        section=None
        for aline in f.readlines():
            aline = aline.strip()
            if not aline or aline[0] == "#":
                # comment or blank line so ignore
                pass
            elif aline[0] == "[":
                # new section
                section = aline
            else:
                # extract the data using regular expressions
                if section == "[CM19A X10 CODES]":
                    aline = aline.replace(" ", "")  # remove any whitespace
                    data = aline.split(',', 3)     # Comma separate data but keep the command sequence as a single string
                    house_code = data[0].upper()
                    unit_number = data[1]
                    on_off_dim = data[2].upper()
                    command_sequence = data[3].split(',')
                    for i in range(len(command_sequence)):
                        command_sequence[i] = int(command_sequence[i], 16)      # Convert the list items from text to values (the text representation is hex)
                    if data:
                        # add the command to the list (which is actually a dictionary in the form:
                        #{key : command_sequence}   command_sequence is a list of the bytes
                        key = house_code + unit_number + on_off_dim
                        self.protocol[key] =  command_sequence
                elif section == "[X10 RF REMOTE DIM/BRIGHT CODES]":
                    aline = aline.replace(" ", "")  # remove any whitespace
                    data = aline.split(',', 3)     # Comma separate data but keep the command sequence as a single string
                    house_code = data[0].upper()
                    unit_number = data[1]
                    on_off_dim = data[2].upper()
                    command_sequence = data[3].split(',')
                    for i in range(len(command_sequence)):
                        command_sequence[i] = int(command_sequence[i], 16)      # Convert the list items from text to values (the text representation is hex)
                    if data:
                        # add the command to the list (which is actually a dictionary in the form:
                        #{key : command_sequence}   command_sequence is a list of the bytes
                        key = house_code + unit_number + on_off_dim
                        self.protocol_remote[key] =  command_sequence
                elif section == "[OTHER]":
                    # Not required
                    pass
                #endif
            # endif
        #end for

        f.close()
    #endsub


    def finish(self):
        """ Close everything and release device interface """
        self.alive = False
        self.paused = True
        try:
            #self.handle.reset()
            self.handle.releaseInterface()
        except Exception, err:
            print >> sys.stderr, err
            self.log.error(str(err))
        self.handle, self.device = None, None


    def print_device_info(self):
        self.USB_device.print_device_info()

#End class


class HTTPServer(BaseHTTPServer.HTTPServer):
    """
        Subclasses the BaseHTTPServer and overrides the serve_forever method so that we can interrupt it and quit gracefully
    """
    def serve_forever(self):
        # override the std serve_forever method which can be stopped only by a Ctrl-C
        self.alive = True
        while self.alive:
            # Continue to respond to HTTP requests until self.alive is set to False
            self.handle_request()
        print "HTTP server is shutting down due to a user request"


class HTTPhandler(BaseHTTPServer.BaseHTTPRequestHandler):
    """
        Processes HTTP requests
        Subclasses the BaseHTTPServer and adds additional functionality

        HTTP reponse codes
            200 OK
            400 Bad Request
            500 Error
    """

    server_version= "MyHandler/1.1"

    def do_GET(self):
        #self.log_message("Command: %s Path: %s Headers: %r" % (self.command, self.path, self.headers.items()))
        self.processRequest(None)


    def do_POST(self):
        # A form is posted via a HTML post
        self.sendPage(400, "text/html", "HTML forms/web pages not yet implemnted")
        return
        #self.log_message("Command: %s Path: %s Headers: %r" % ( self.command, self.path, self.headers.items()))
        #if self.headers.has_key('content-length'):
        #    length= int(self.headers['content-length'])
        #    self.dumpReq(self.rfile.read(length))
        #else:
        #    self.processRequest(None)


    def processRequest(self, formInput=None):
        # Example client calls
        # http://192.168.1.3:8008/?house=A&unit=1&command=ON
        # http://192.168.1.3:8008/?house=A&unit=1&command=DIM
        # http://192.168.1.3:8008?command=getqueue
        # http://192.168.1.3:8008?command=getlog
        # http://192.168.1.3:8008?command=quit

        # remove leading gumph
        qmarkpos = self.path.find('?')
        self.path = self.path[qmarkpos+1:]

        # replace any escaped spaces with a real space
        self.path = self.path.replace('%20',  " ")
        respcode = 200

        # extract the arguments
        argsdict = {}
        for arg in self.path.split('&'):
            if arg.find('=') >= 0:
                key = arg.split('=')[0]
                value = arg.split('=')[1]
                argsdict[key] = value

        house = ""
        unit = ""
        command = ""

        if 'house' in argsdict:
            house = argsdict['house'].lower()
        if 'unit' in argsdict:
            unit = argsdict['unit']
        if 'command' in argsdict:
            command = argsdict['command'].lower()

        if command in ['on', 'off', 'dim', 'bright', 'allon', 'alloff']:
            # Valid command request
            try:
                response = cm19a.send(house, unit, command)     # True if the command was sent OK
            except:
                response = False
        elif command in ['getqueue', 'receive', 'getreceivequeue']:
            response = cm19a.getReceiveQueue()
            if len(response) > 0:
                response = ','.join(response)
            else:
                response = "Receive queue is empty"
        elif command in ['clearqueue',]:
            # clear the queue
            cm19a.paused = True
            cm19a.receivequeue = []
            cm19a.receivequeuecount = 0
            cm19a.paused = False
            response = "Receive queue emptied successfully"
        elif command in ['quit', 'shutdown', 'exit']:
            response = "Shutting down the server..."
            # Do a fake call so that the server can terminate
            global server
            if server.alive:
                server.alive = False
                conn = httplib.HTTPConnection("%s:%s" % (SERVER_IP_ADDRESS, SERVER_PORT))
                conn.request("GET", '?command=nothing')
        elif command in ['getversion', 'version']:
            response = VERSION
        elif command in ['getlogs',  'getlog']:
            # Returns the Logs (text only)
            if not os.path.isfile(LOGFILE):
                log.error("%s log file missing %s" % LOGFILE)
                response = ''
            else:
                respcode = 200
                response = "CM19a Device Driver Log\n"
                f = open(LOGFILE, "r")
                for aline in f.readlines():
                    response += aline
                f.close()
        elif command in ['getformattedlog',]:
            # Returns the Logs with HTML formatting for display purposes
            if not os.path.isfile(LOGFILE):
                log.error("%s log file missing %s" % LOGFILE)
                response = ''
            else:
                respcode = 200
                response = "<html><body><p style='font-family:Arial;font-size:14pt;font-weight:bold;color:navy;line-height:100%%'>CM19a Device Driver Log</p>"
                f = open(LOGFILE, "r")
                for aline in f.readlines():
                    if aline.lower().find('critical') >= 0:
                        response +=  "<p style='font-family:Arial;font-size:10pt;font-weight:bold;color:white;background-color:red;line-height:100%%'>%s</p>" % aline
                    elif aline.lower().find('error') >= 0:
                        response +=  "<p style='font-family:Arial;font-size:10pt; font-weight:normal;color:white;background-color:red;line-height:100%%'>%s</p>" % aline
                    elif aline.lower().find('warning') >= 0:
                        response +=  "<p style='font-family:Arial;font-size:10pt; font-weight:bold;color:olive;background-color:yellow;line-height:100%%'>%s</p>" % aline
                    else:
                        response +=  "<p style='font-family:Arial;font-size:10pt; font-weight:normal;color:gray;background-color:white;line-height:30%%'>%s</p>" % aline
                f.close()
                response += "</body></html>"
        else:
            # error no command request
            respcode = 400
            response = "NAK: Invalid 'command' value"

        if type(response) == types.BooleanType:
            if response:
                respcode = 200
                response = "ACK"
            else:
                reposcode = 500
                response = "NAK"

        self.sendPage(respcode, "text/html", str(response))

    def sendPage(self, code,  type, body):
        body+= "\n\r"
        self.send_response(code)
        self.send_header("Content-type", type)
        self.send_header("Content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
# End Class

def startLogging(progname="CM19a_X10_USB", logfile='./cm19a.log'):
    return logger.start_logging(progname, logfile)

def processcommandline():
    """Process the command line
        Command line usage:
           cm19aDriver.py  house&unitcode ON/OFF
           e.g. cm19aDriver.py A 1 ON     # Turns on device A1, returns 1 if OK, 0 if not
           You can only send a command via the command line, you cannot read/receive a wireless command form anX10 remote"
        Returns 0 is OK, 1 if failure
    """

    # Get the command line arguments
    try:
        house = sys.argv[1]     # First command line argument after the program name
        unit = sys.argv[2]      # 2nd argument
        cmd = sys.argv[3]       # 3rd argument
        print "Doing %s%s %s..." % (house, unit, cmd)
        result = cm19a.send(house, unit, cmd)     # True if the command was sent OK
        if result:
            print "Result: %r" % result
            returnval = 0
        else:
            print  >> sys.stderr, "Command failed: %s%s %s" % (house, unit, cmd)
            returnval = 1
    except:
        print  >> sys.stderr, "Invalid command line"
        returnval = 1

    return returnval


#Main
if __name__ == '__main__':

    # Configure logging
    log = startLogging(LOGFILE)

    if MODE.lower() == 'command line':
        # Process the command line (send commands only)
        # Exits with an error level of 0 if successful
        if len(sys.argv) <= 1 :
            # no command line arguments given
            print "Command line usage:"
            print "   cm19a_X10_USB.py  house&unitcode ON/OFF"
            print "   e.g. cm19a_X10_USB.py A 1 ON     # Turns on device A1, returns 1 if OK, 0 if not"
            print "   You can only send a command via the command line, you cannot read/receive a wireless command form an X10 remote"
            sys.exit(2)
        else:
            print "\nInitialising..."
            log.info('Initialising...')
            cm19a = CM19aDevice(REFRESH, log, polling = False)       # Initialise device. Note: auto receiving in a thread is turned off for this example
            if cm19a.initialised:
                result = processcommandline()
                cm19a.finish()
                sys.exit(result)
            else:
                print "Error initialising the CM19a...exiting..."
                log.error("Error initialising the CM19a...exiting...")
                cm19a.finish()
                sys.exit(1)

        #***** Example command line (Linux/Bash) *****
        # Note: $? is the exit status/error level. Zero means success
        #    sudo ./cm19aDriver.py A 1 ON
        #    echo "Result: $?"

    elif MODE.lower() in ['http server', 'web server']:
        # Accept commands via http (eg a Web Browser)
        print "\nInitialising..."
        log.info('Initialising...')
        cm19a = CM19aDevice(REFRESH, log, polling = True)       # Initialise device. Note: auto polling/receviing in a thread is turned ON
        if cm19a.initialised:
            log.info("Configuring the HTTP server on %s:%s" % (SERVER_IP_ADDRESS, SERVER_PORT))
            print "Configuring the HTTP server on %s:%s" % (SERVER_IP_ADDRESS, SERVER_PORT)
            server = HTTPServer((SERVER_IP_ADDRESS, SERVER_PORT,), HTTPhandler)
            log.info("Starting the HTTP server...")
            print "Starting the HTTP server..."
            server.serve_forever()
            # Finish and tidy up
            server = None
            log.info("All done")
            cm19a.finish()
            sys.exit(0)
        else:
            print "Error initialising the CM19a...exiting..."
            log.error("Error initialising the CM19a...exiting...")
            cm19a.finish()
            sys.exit(1)

        # Example client calls from a web browser
        #   http://192.168.1.3:8008/?house=A&unit=1&command=ON
        #   http://192.168.1.3:8008?command=getqueue              Returns a comma separated list of the commands received since the last getqueue call
        #   http://192.168.1.3:8008?command=clearqueue
        #   http://192.168.1.3:8008?command=getlog
        #   http://192.168.1.3:8008?command=getformattedlog
        #   http://192.168.1.3:8008?command=getversion
        #   http://192.168.1.3:8008?command=quit                  Gracefully shuts down the driver

        # Example command line using the cURL (a command line URL client that send the command via http)
        #   sudo ./cm19aDriver.py (ensure MODE = 'HTTP SERVER')
        #   result=`curl --silent http://192.168.1.3:8008/?house=A\&unit=1\&command=ON`     NOTE THAT THE AMPERSAND NEEDS TO BE ESCAPED WITH A BACK SLASH
        #   echo $result
        #   result=`curl --silent http://192.168.1.3:8008/?command=getqueue`                NOTE the use of the ` character - this is not a single quote
        #   echo $result
        #   curl --silent http://192.168.1.3:8008/?command=quit
    else:
        print "Please set the MODE of operation."


# End of module

