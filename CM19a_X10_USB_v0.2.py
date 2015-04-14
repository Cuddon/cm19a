#!/usr/bin/env python

"""
A Python driver for the CM19a X10 RF Transceiver (USB)
This is a user space driver so a kernel driver for the CM19a does not need to be installed.

Functionality
 - Use a CM19a to send any X10 on/off command (eg A1OFF, C16ON) wirelessly to a lamp or appliance module (requires an X10 receiver module).
 - Use a CM19a to automatically receive and log to a queue any command received from an X10 remote control.

Version 0.20
June 2010

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


Coded by: Andrew Cuddon (www.cuddon.net)

Requires:
    pyUSB
    libusb 0.1 series
- You need to disable any other driver that attempts to attach to this device:
    On Ubuntu 11.04:
        sudo nano  /etc/modprobe.d/blacklist.conf  (may just be blacklist (without the .conf) on other distros)
        Add in the follow text and save
            # To enable CM19a X10 Transceiver to work
            blacklist lirc_atiusb
            blacklist ati_remote 
        reboot
- You may need to run this as the root user
- On Ubuntu I use:   sudo python CM19aUSBinfo.py (or set permissions via udev rules)

Many ideas gleaned from the following:
    Jan Roberts Java user space driver for CM19a (search for this on google)
    Neil Cherry's Linux Home Automation site:  http://www.linuxha.com/USB/cm19a.html


TTDs
     - Identifying and detaching any pre-existing kernel driver

NOTE:
- You may need to run this as the root user
- On Ubuntu you could use:
    sudo python CM19a_X10_USB.py

Or you could set permissions via udev
1. Create a udev permissions files so that when udev creates a device file when the transceiver is connected, the correct permissions are set
    sudo nano /etc/udev/rules.d/cm19a.rules
        Note that I did not number this file so it runs after all other permissions are set.
2. Add in the following text and save
    # Allow all users to read and write to the CM19a X10 Transceiver (USB)
    SYSFS{idVendor}=="0bc7", SYSFS{idProduct}=="0002", MODE="666"
3. If your CM19a is plugged in, then remove, wait a sec or two and then plug it back in again. The correct permissions should now be set.
4. Any user should now be able to run the driver without using sudo.
    eg. From a terminal
    ./CM19a_X10_USB.py

"""

# Standard modules
import sys
import time
import os
import threading

# pyUSB 1.0
import usb

# Globals
global cm19a, log

VERSION = "0.20"
REFRESH = 1.0               # Refresh rate (seconds) for polling the transceiver

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

    # Class constants (run only when the module is loaded)
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

    def __init__(self,  refresh, loginstance=None, startreceiving = True):
        # Initialise the object and create the device driver
        threading.Thread.__init__(self)     # initialise the thread for automatic monitoring
        self.refresh = refresh
        self.alive = False                  # Set to false to permanently stop the thread that automatic monitors for received commands
        self.paused = False                 # Set to True to temporarily stop automatic monitoring of receive commands
        self.initialised = False            # True when the device has been opened and the driver initialised successfully
        self.device = False                 # USB device class instance
        self.receivequeue = []              # Queue of commands received automatically
        self.receivequeuecount = 0          # Number of items in the receive queue
        self.protocol = {}                  # Dict containing the communications protocol for the CM19a
        
        # Set up logging.
        if loginstance:
            self.log = loginstance
        else:
            # No logger instance provided so create one
            import logger
            self.log = logger.start_logging("CM19a",  "./CM19a.log")

        # Find the correct USB device
        self.USB_device = USBdevice(self.VENDOR_ID, self.PRODUCT_ID)
        # save the USB instance that points to the CM19a
        self.device = self.USB_device.device
        if not self.device:
            print >> sys.stderr, "The CM19a is probably not plugged in or is being controlled by another USB driver."
            self.log.error('The CM19a is probably not plugged in or is being controlled by another USB driver.')
            return

        # Open the device for send/receive
        if self._open_device():
            self.print_device_info()
        else:
            # Device was not opened successfully
            return

        # Load the communications protocol
        self._load_protocol()
        
        # Start the thread for automatically receiving inbound commands
        # If you just send commands via the CM19a and do not need to check for incoming commands from a remote control
        # then set 'startreceving' to False when the class instance is created
        if startreceiving:
            self.start()


    def _open_device(self) :
        """ Open the device, claim the interface, and create a device handle """

        if not self.device:
            # not device object
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
        """ returns the queue (list) of incoming commands and clears it ready for receiving more """

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


    def send(self, house_code,  device_number,  function):
        """
            Sends a command request to the device
            Tries to send just once
            Returns False if an error occurs
        """
        if not self.initialised:
            return False


        self.log.info("Sending %s%s%s" % (house_code, device_number, function))

        # Encode the command to the X10 protocol
        command_sequence = self._encode(house_code, device_number, function)        # -> list
        if not command_sequence:
            # encoding error
            self.log.error("Unable to send command; encoding error occurred.")
            return False

        # Pause automatic receiving while we send
        self.paused = True
        time.sleep(self.refresh)

        # Flush the device before we send anything so we do not lose any incoming requests
        self.receive()
        
        # Write the command sequence to the device
        try:
            chars_written = self.handle.interruptWrite(self.WRITE_EP_ADDRESS, command_sequence, self.SEND_TIMEOUT)
        except Exception, err:
            print >> sys.stderr, err
            self.log.error(str(err))
            chars_written = 0
        
        if chars_written != len(command_sequence):
            # Incorrect number of bytes written
            print  >> sys.stderr, "Incorrect number of bytes written."
            self.log.error("Incorrect number of bytes written.")
            return False

        # Restart automatic receiving and return
        self.paused = False
        return True


    def _encode(self, house_code,  device_number,  on_off):
        """
            Looks up the X10 protocol for the appropriate byte command sequence
        """
        key = house_code.upper() + device_number.upper() + on_off.upper()
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
            returns the command (housecode, device number, on/off) that the sequence represents
            If it cannot decode the sequence then the sequence is just returned
        """
        
        if not self.protocol:
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
                    # Not required
                    pass
                elif section == "[VARIABLE STATUS RESPONSES]":
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


#Main
if __name__ == '__main__':
# Run this module standalone to do these simple tests
    LOGFILE = './DeviceManager.log'
    global log
    import logger
    log = logger.start_logging("CM19a_X10_USB",  LOGFILE)

    cm19a = CM19aDevice(REFRESH, log, startreceiving = False)       # Initialise device. Note: auto receiving in a thread is turned off for this example

    if not cm19a.initialised:
        print "Device not initialised so we did not doing anything."
        cm19a.finish()
        exit(1)
        
    print '\n---- Simple On/OFF Test ----'
    print "Turning ON A1..."
    result = cm19a.send("A", "1", "ON")     # True if the command was sent OK (does not mean the device responded though)
    if not result:
        print  >> sys.stderr, "Command failed"

    print "Waiting 2 seconds ..."
    time.sleep(2)

    print "Dimming A1 by 10%..."
    # Assumes A1 is a lamp module
    # Each Dim command dims the lamp module by 5%
    result = cm19a.send("A", "0", "DIM")        # notice that the unit code is zero (the last on device in for that house code is dimmed)
    if not result:
        print  >> sys.stderr, "Command failed"
    result = cm19a.send("A", "0", "DIM")
    if not result:
        print  >> sys.stderr, "Command failed"

    print "Waiting 2 seconds ..."
    time.sleep(2)

    print "Turning OFF A1..."
    result = cm19a.send("a", "1", "OFf")            # notice that this is case insensitive
    if not result:
        print  >> sys.stderr, "Command failed"


    print '\n\n---- Basic Macros initiated by a key press on an X10 remote control ----'
    print 'Press any button on the remote. A4ON will run a macro, A4OFF will exit'
    alive = True
    lasthousecode = "A"
    while alive:
        # Check for any button presses on the X10 remote
        cm19a.receive()                                 # We need to do this because is this example receive() is not running automatically in a thread
        buttonpresses = cm19a.getReceiveQueue()         # -> List
        if buttonpresses:
            # One or more button presses were received so loop through the list of button presses
            for button in buttonpresses:
                print "Actioning button press: %s" % button
                if button == 'Z0DIMBUTTONPRESSED':
                    # Dim button pressed (but not immediately after a house/unit button) so the house code is not identified
                    # Just dim the last used unit used
                    print "Dimming last used device on housecode: %s" % lasthousecode
                    result = cm19a.send(lasthousecode, "0", "DIM")      # True if the command was sent OK
                    if not result:
                        print  >> sys.stderr, "Command failed"
                elif button == 'Z0BRIGHTBUTTONPRESSED':
                    # Dim button pressed (but not immediately after a house/unit button) so the house code is not identified
                    # Just dim the last used unit used
                    print "Brightening last used device on housecode: %s" % lasthousecode
                    result = cm19a.send(lasthousecode, "0", "BRIGHT")       # True if the command was sent OK
                    if not result:
                        print  >> sys.stderr, "Command failed"
                elif button == 'A0DIM' or button == 'A0BRIGHT':
                    # Dim/Bright button pressed immediately after a house/unit button, so the housecode is identified
                    # So just do it
                    print "Dimming/Brightening: %s" % button[0]
                    result = cm19a.send(button[0], button[1], button[2:])       # True if the command was sent OK
                    if not result:
                        print  >> sys.stderr, "Command failed"
                    lasthousecode = button[0]
                elif button == "A4ON":
                    # Really simple macro
                    # When A4ON is pressed turn on E1, dim it by 10% (assuming it is a lamp module) and turn off E2
                    print "\nRunning macro (A4ON) to turn ON E1, dimming it by 10%, and then turn OFF E2"
                    result = cm19a.send("E", "1", "ON")     # True if the command was sent OK
                    if not result:
                        print  >> sys.stderr, "Command failed"
                    result = cm19a.send("E", "0", "DIM")        # True if the command was sent OK
                    if not result:
                        print  >> sys.stderr, "Command failed"
                    result = cm19a.send("E", "2", "OFF")        # True if the command was sent OK
                    if not result:
                        print  >> sys.stderr, "Command failed"
                    print "Macro for A4ON completed."
                    lasthousecode = button[0]
                elif button == "A4OFF":
                    # exit the for loop and checking for new button presses
                    print "Stopping checking for button presses."
                    alive = False
                    break
                else:
                    # Just re-transmit the button press
                    result = cm19a.send(button[0], button[1], button[2:])       # True if the command was sent OK
                    if not result:
                        print  >> sys.stderr, "Command failed"
                    lasthousecode = button[0]
            #end for loop
            
        # Wait for the device to refresh the receive queue
        time.sleep(REFRESH)
    #end while loop
    
    cm19a.finish()
    
    # Now an example of automatically receiving in a thread
    cm19a = CM19aDevice(REFRESH, log, startreceiving = True)        # Initialise device.
    print '\n\n---- Now demonstrate queueing up multiple key presses using a thread to continually check----'
    print "Press one or more keys on the x10 remote within the next 5 seconds..."
    time.sleep(5)
    print "The following buttons were pressed on the remote:",  cm19a.getReceiveQueue()

    

    print "\n\nTests complete."

# End of module
