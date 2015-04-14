#!/usr/bin/env python

"""
Scans through the USB busses and devices to detect a CM19a X10 USB Transceiver
If a CM19a is found it prints out the device information

Andrew Cuddon August 2009

Uses: pyUSB which can be found at http://sourceforge.net/projects/pyusb/

Development environment: Ubuntu 9.04 (Jaunty).

NOTES:
- Requires: pyUSB module
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
"""

import usb

ENDPOINT_TYPE = ["Control", "ISOCHRONOUS",  "BULK",  "INTERRUPT"  ]
DEVICE_CLASS = ["Vendor Specific"] * 256
DEVICE_CLASS [0] = "Per Interface"
DEVICE_CLASS [1] = "Audio"
DEVICE_CLASS [2] = "Comm"
DEVICE_CLASS [3] = "HID"
DEVICE_CLASS [7] = "Printer"
DEVICE_CLASS [8] = "Mass Storage"
DEVICE_CLASS [9] = "Hub"
DEVICE_CLASS [10] = "Data"

busses = usb.busses()               # busses is a tuple/list of USB buses (bus objects) on the machine

print "Extracting info..."
for bus in busses:                  # bus is a bus object
    print "\nBus number (bus.dirname): %s" % bus.dirname
    # print "  Bus Location (bus.location): %s" % bus.location

    devices = bus.devices           # devices is a tuple/list of the devices on a bus
    for dev in devices: # dev is a device object
        if dev.idVendor <> 0x0bc7:
            print "No CM19a found on this USB bus."
            break

        print "CM19a found:"
        print "  Device Number(dev.filename):", dev.filename
        print "    Device class: %d (%s)" % (dev.deviceClass,  DEVICE_CLASS[dev.deviceClass])
        print "    Device sub class: %d (%s)" % (dev.deviceSubClass,  DEVICE_CLASS[dev.deviceSubClass])
        print "    Device protocol:",dev.deviceProtocol
        print "    Max packet size for Endpoint 0:", dev.maxPacketSize
        print "    Vendor ID (dev.idVendor): %d (%04x hex)" % (dev.idVendor, dev.idVendor)
        print "    Product ID (dev.idProduct): %d (%04x hex)" % (dev.idProduct, dev.idProduct)
        print "    Device Version:",dev.deviceVersion
        #print "    Manufacturer (dev.iManufacturer): %d, %s" %  (dev.iManufacturer,  dev.open().getString(dev.iManufacturer,50))
        #print "    Product (dev.iProduct): %d, %s" %  (dev.iProduct,  dev.open().getString(dev.iProduct,50))
        #print "    SerialNumber (dev.iSerialNumber):  %d, %s" %  (dev.iSerialNumber,  dev.open().getString(dev.iSerialNumber,50))
        print "    usbVersion: ",  dev.usbVersion
        print "    Number of Configurations: ",  len(dev.configurations)
        for config in dev.configurations:
            print "    Configuration:", config.value
            print "      Total length:", config.totalLength
            print "      selfPowered:", config.selfPowered
            print "      remoteWakeup:", config.remoteWakeup
            print "      maxPower:", config.maxPower
            print "      Configuration Description: ",  config.iConfiguration
            print "      Number of Interfaces: ",  len(config.interfaces)
            print "      Interface tuple: ",  config.interfaces             # --> Tupe of a tuple of interface objects
            for intf in config.interfaces:
                # intf is a tuple where each item is a tuple of alternative settings (which are actually interface objects)
                for alt in intf:
                    # alt is an interface object
                    print "      Interface Number: ", alt.interfaceNumber
                    print "      Alternate Setting Number:",alt.alternateSetting
                    print "        Interface class: %d (%s)" % (alt.interfaceClass,  DEVICE_CLASS[alt.interfaceClass])
                    print "        Interface sub class: %d (%s)" % (alt.interfaceSubClass,  DEVICE_CLASS[alt.interfaceSubClass])
                    print "        Interface protocol:",alt.interfaceProtocol
                    print "        Number of end points: ",  len(alt.endpoints)
                    print "        Endpoint tuple: ",  alt.endpoints
                    for ep in alt.endpoints:
                        print "        Endpoint address: %d (%04x hex)" % (ep.address,  ep.address)
                        print "          Type: %d (%s):" % (ep.type, ENDPOINT_TYPE[ep.type])
                        print "          Max packet size: %d bytes" % ep.maxPacketSize
                        print "         Interval:",ep.interval

raw_input("Press Enter to finish")
