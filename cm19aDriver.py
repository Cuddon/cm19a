#!/usr/bin/env python

"""
cm19aDriver.py

A Python driver for the CM19a X10 RF Transceiver (USB)
This is a user space driver so a kernel driver for the CM19a does not need to be installed.

Functionality
 - Use the CM19a to send any X10 on/off command (eg A1OFF, C16ON) wirelessly to a lamp or appliance module (requires an X10 receiver module).
 - Use the CM19a to automatically receive and log to a queue any command received from an X10 remote control.

Version 0.12
Sep 2011

Changelog v0.12
- Added functionality to accept command line arguments for sending an x10 command
    e.g. sudo ./cm19aDriver.py A1 ON
- Added argument to Configure to state whether polling for inbound commands should be started
    Default is 'start=False' (this is the correct setting for command line processing)

Changelog 0.1 - 0.11
- Add saving error messages to an object attribute so they can be utilised by a separate UI app
- Fixed a couple of coding errors


Coded by: Andrew Cuddon (www.cuddon.net)

Notes:
- Requires pyUSB, (based on libusb 0.1 series)
- You need to disable any other driver that attempts to attach to this device:
    On Ubuntu 11.04:
        sudo nano  /etc/modprobe.d/blacklist.conf  (may just be blacklist (without the .conf) on other distros)
        Add in the follow text and save
            # To enable CM19a X10 Transceiver to work
            blacklist lirc_atiusb
            blacklist ati_remote
        reboot
- You may need to run this as the root user
- On Ubuntu I use:   sudo python cm19aDriver.py (or set permissions via udev rules)


Many ideas gleaned from the following:
    Jan Roberts Java user space driver for CM19a (search for this on google)
    Neil Cherry's Linux Home Automation site:  http://www.linuxha.com/USB/cm19a.html

Current Isues/Bugs
     - Bright/Dim functionality does not work
     - Requires root privileges to access the USB device

TTDs
     - Identifying and detaching any pre-existing kernel driver
     - More error checking
     - Logging
     - X10 security controllers/modules
"""

# Standard modules
import sys, time, os
import threading

# pyUSB
import usb

# Globals
global cm19a

VERSION = "0.12"

class USBdevice:
    def __init__(self, vendor_id, product_id) :
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.bus = None
        self.device = None

        buses = usb.busses()
        for bus in buses :
            for device in bus.devices :
                if device.idVendor == self.vendor_id and device.idProduct == self.product_id:
                    self.bus = bus
                    self.device = device
                #endif
            #endfor
        #endfor

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
#endclass


class CM19aDevice(threading.Thread):
    # subclasses the Thread class from the threading module

    # Class constants (run only when the module is loaded)
    VENDOR_ID = 0x0bc7          # Vendor Id: X10 Wireless Technology, Inc.
    PRODUCT_ID = 0x0002         # Product Id: Firecracker Interface (ACPI-compliant)
    CONFIGURATION_ID = 1        # Use configuration #1 (This device has only 1 configuration)
    INTERFACE_ID = 0            # The interface we use to talk to the device (This is the only configuration available for this device)
    ALTERNATE_SETTING_ID = 0    # The alternate setting to use on the selected interface

    READ_EP_ADDRESS   = 0x081       # Endpoint 129 (decimal)
    WRITE_EP_ADDRESS  = 0x002       # Endpoint 2  (decimal)
    PACKET_LENGTH = 8                   # Maximum packet length is 8 bytes

    SEND_TIMEOUT = 1000             # 1000 ms = 1s
    RECEIVE_TIMEOUT = 100               # 100 ms

    PROTOCOL_FILE = "./CM19aProtocol.txt"

    def __init__(self,  refresh):
        # Initialise the object and create the device driver

        threading.Thread.__init__(self)     # initialise the thread for automatic monitoring

        self.refresh = refresh
        self.alive = False                  # Set to false to halt automatic monitoring of receive commands
        self.paused = False             # Set to True to temportarily stop automatic monitoring of receive commands
        self.initialised = False            # True when the device has been opened and the driver initialised successfully
        self.device = False             # USB device object
        self.receivequeue = []          # Queue of commands received automtically
        self.receivequeuecount = 0  # Number of items in the receive queue
        self.errormessages = ""
        self.errors = 0

        # Find the correct USB device
        self.USB_device = USBdevice(self.VENDOR_ID, self.PRODUCT_ID)
        self.device = self.USB_device.get_device()          # --> Device object that points to the CM19a
        if not self.device:
            print >> sys.stderr, "The CM19a is not plugged in."
            self.errormessages += "\nThe CM19a is not plugged in."
            self.errors += 1
            return

        if self.open():
            print "CM19a found and opened"
            self.print_device_info()
            self.initialised = True
        else:
            print >> sys.stderr, "Unable to open the CM19a."
            self.errormessages += "\nUnable to open the CM19a."
            self.errors += 1
            return

        self.loadProtocol()


    def open(self) :
        # Open the device, claim the interface, and create a device handle
        self.handle = None      # file-like handle
        if not self.device:
            print >> sys.stderr, "The CM19a is not plugged in"
            self.errormessages += "\nThe CM19a is not plugged in."
            self.errors += 1
            return False

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
        except usb.USBError, err:
            print >> sys.stderr, err
            self.errormessages = str(err)
            self.errors += 1
            return False

        return True


    def run(self):
        """
            This is the main function that will run in the thread when start() is issued
            Check for an incoming command received via the CM19a
            If a command is found, it is decoded and added to the receive queue
            Rechecks the device every refresh seconds
            set alive to False to halt checking
        """
        self.alive = True
        while self.alive:
            # continues to run the following code until alive is set to false
            #self.counter += 1
            if not self.paused:
                # Only check if the device is not paused (eg during a send)
                data = self.receive()
                if data:
                    # something read so add it the the receive queue
                    result = self.decode(data)      # decode the byte stream
                    if result:
                        self.receivequeue.append(result)
                        self.receivequeuecount = self.receivequeuecount + 1
                        print "Command %s received via cm19a" % result

            # wait for 'refresh' seconds before checking the device again
            time.sleep(self.refresh)


    def print_device_info(self):
        self.USB_device.print_device_info()


    def loadProtocol(self):
        # Loads the X10 protocol into a dictonary

        if not self.device:
            print >> sys.stderr, "Cannot load X10 Protocol. The CM19a is not plugged in."
            self.errormessages += "\nCannot load X10 Protocol. The CM19a is not plugged in."
            self.errors += 1
            return

        self.protocol = {}  # empty dictionary

        # Open the configuration file
        fname = self.PROTOCOL_FILE
        if not os.path.isfile(fname):
            print >> sys.stderr, "**ERROR**", "Protocol file missing %s" % fname
            self.errormessages += "\nProtocol file missing %s" % fname
            self.errors += 1
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
                # extract the comma separated values
                if section == "[BASIC REMOTE CODES]":
                    aline = aline.replace(" ", "")  # remove any whitespace
                    data = aline.split(',',  3)     # Comma separate data but keep the command sequence as a single string
                    house_code = data[0].upper()
                    device_number = data[1]
                    on_off = data[2].upper()
                    command_sequence = data[3].split(',')
                    for i in range(len(command_sequence)):
                        command_sequence[i] = int(command_sequence[i], 16)      # Convert the list items from text to values (the text representation is hex)

                    if data:
                        # add the command to the list (which is actually a dictionary in the form:
                        #{key : command_sequence}   command_sequence is a list of the bytes
                        key = house_code + device_number + on_off
                        self.protocol[key] =  command_sequence
                elif section == "[FIXED STATUS RESPONSES]":
                    pass
                elif section == "[VARIABLE STATUS RESPONSES]":
                    pass
                #endif
            # endif
        #end for

        f.close()
    #endsub


    def encode(self, house_code,  device_number,  on_off):
        """
            Looks up the X10 protocol for the appropriate byte command sequence
        """
        key = house_code.upper() + device_number.upper() + on_off.upper()
        if key in self.protocol:
            return self.protocol[key]
        else:
            print >> sys.stderr, "Unable to encode the requested action: %s" %  key
            self.errormessages += "\nUnable to encode the requested action: %s" %  key
            self.errors += 1
            return False


    def decode(self, receive_sequence):
        """
            Uses the X10 protocol to decode a command received by the CM19a
            receive_sequence is a list of decimal values
            returns the command (housecode, device number, on/off) that the sequence represents
        """

        if not self.protocol:
            # the protocol has not been loaded
            return ""

        return_value = ""

        # Convert the inbound command sequence to a string to it can be compared to the protocol values
        # the receied comand sequence is a list of decimal values (not text)
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

        return return_value


    def finish(self):
        """ Close everything and release device interface """
        self.alive = False
        try:
            #self.handle.reset()
            self.handle.releaseInterface()
        except Exception, err:
            print >> sys.stderr, err
            self.errormessages = str(err)
            self.errors += 1
        self.handle, self.device = None, None


    def receive(self, numbytes=0, timeout=0):
        """
            Checks the device for an inbound command and adds it to the queue if found
            numbytes is the maximum number of bytes to read
            For std X10 remotes this is 5 bytes, but some others may be 8
            Returns the data (list) read from the device (not decoded)
            Returns an empty list if not data received
        """
        data = None
        if numbytes == 0:
            numbytes =self.PACKET_LENGTH
        if timeout ==0:
            timeout = self.RECEIVE_TIMEOUT

        try:
            data = self.handle.interruptRead(self.READ_EP_ADDRESS, numbytes, timeout)
        except Exception, err:
            # error or simply nothing in the buffer to read
            #print >> sys.stderr, err
            pass        # Ignore any errors

        return data

    def getReceiveQueue(self):
        # returns the queue (list) of incoming commands and clears it ready for receiving more

        if self.receivequeuecount > 0:
            # Pause receiving so the recieve thread does not add items just before we clear to queue
            self.paused = True
            # Temporarily store the queue becuase we clear it before we return it the the calling rountine
            tmp = self.receivequeue

            # clear the queue
            self.receivequeue = []
            self.receivequeuecount = 0
            self.paused = False
            return tmp
        else:
            # no commands so return an empty queue (list)
            return []
        #endif


    def send(self, house_code,  device_number,  on_off):
        """
            Sends a command request to the device
            Tries to send just once
            Returns False if an error occurs
        """

        # Get the command codes from the X10 protocol
        command_sequence = self.encode(house_code,  device_number,  on_off)     # -> list
        if not command_sequence:
            # encoding error
            return False

        # Pause automtic receiving while we send
        self.paused = True
        time.sleep(self.refresh)

        # Write the command sequence to the device
        try:
            chars_written = self.handle.interruptWrite(self.WRITE_EP_ADDRESS, command_sequence, self.SEND_TIMEOUT)
        except Exception, err:
            print >> sys.stderr, err
            self.errormessages = str(err)
            self.errors += 1
            chars_written = 0

        # Unpause automatic receiving
        self.paused = False

        if chars_written != len(command_sequence):
            # Incorrect number of bytes written
            print  >> sys.stderr, "Incorrect number of bytes written."
            self.errormessages += "\nIncorrect number of bytes written."
            self.errors += 1
            return False

        return True


#End class

def processcommandline():
    """Process the command line
        Command line usage:
           cm19aDriver_v0.12.py  house&unitcode ON/OFF
           e.g. cm19aDriver_v0.12.py A1 ON     # Turns on device A1, returns 1 if OK, 0 if not
           You can only send a command via the command line, you cannot read/receive a wireless command form anX10 remote"
        Returns 0 is OK, 1 if failure
    """

    # Get args
    try:
        house = sys.argv[1][0]      # First char of the 2nd command line argument (the 1st argument (index=0) is just the name of the program
        unit = sys.argv[1][1:]          # 2nd and subsequent chars of the first command line argument
        cmd = sys.argv[2]           # the 3rd command line argument
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


def configure(start=False):
    global cm19a            # Use the global value

    cm19a = CM19aDevice(refresh=1)      # Initialise device with 1s refresh/polling rate

    if start and cm19a.initialised:
        # start automatic monitoring
        print "Monitoring of inbound commands started..."
        cm19a.start()


def tidyUp():
    # Close the device and release the cm19a object
    global cm19a

    cm19a.finish()
    cm19a = None


# Main
if __name__ == '__main__':
    # The following code executes only when this module is run standalone. See below for how to import this into another Python module

        if len(sys.argv) <= 1 :
            # no command line arguments given
            print "Command line usage:"
            print "   cm19aDriver.py  house&unitcode ON/OFF"
            print "   e.g. cm19aDriver.py A1 ON     # Turns on device A1, returns 1 if OK, 0 if not"
            print "   You can only send a command via the command line, you cannot read/receive a wireless command form anX10 remote"
            sys.exit(2)
        else:
            print "\nConfiguring..."
            configure()
            if cm19a.initialised:
                result = processcommandline()
                tidyUp()
                sys.exit(result)
            else:
                print "Error initialising the CM19a...exiting..."
                sys.exit(1)

"""

***** Example command line (Linux/Bash) *****
        Notes: $? is the exit status/error level. Zero means success
               This is very slow because the device must be initialised each time
               You do not the correct USB permissions
            sudo ./cm19aDriver.py A1 ON
            echo "Result: $?"

***** Example when importing this driver into another module *****
#!/usr/bin/env python

# Std Python modules
import sys,  time

# CM19a module
import cm19aDriver

# Main Programme
# this is what executes with this example is run

# Configure the CM19a and start polling for inbound commands
cm19aDriver.configure(start=True)

if cm19aDriver.cm19a.initialised:
    print "Turning ON A1..."
    # Sends the command 'ON' to device X10 device A1 wirelessly via the CM19a (and a receivier module of course)
    result = cm19aDriver.cm19a.send("A", "1", "ON")     # True if the command was sent OK
    if result:
        print "...Success"
    else:
        print  >> sys.stderr, "Command failed"

    print "\nPress one or more keys on the x10 remote within the next 30 seconds"
    time.sleep(30)
    print "Receive Queue:",  cm19aDriver.cm19a.getReceiveQueue()

    # Close the device and tidy up
    cm19aDriver.tidyUp()
    print "Tests complete."
else:
    print "Error initialising the CM19a...exiting..."
    sys.exit(1)
"""

# End of module

