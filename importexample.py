#!/usr/bin/env python

"""
    importexample.py

    This script:
        * demonstrates how to import the CM19a driver module and use it to send and receive commands via the CM19a; and
        * provides an example of a simple macro that runs when a particular command is received from an RF remote

    Version 3.0
    Sept 2011

    Andrew Cuddon
    www.cuddon.net
"""

# *************** CONFIGURATION ***************
POLLFREQ = 1     # Polling Frequency - Check for inbound commands every 1 second


# *************** CODE ***************
VERSION = "3.00 (Beta)"

# Std Python modules
import sys, time, re

# CM19a module
import cm19aDriver

# Start logging
log = cm19aDriver.startLogging()        # log is an instance of the logger class

# Configure the CM19a and start polling for inbound commands from a remote
# Initialise device. Note: auto polling/receiving in a thread is turned ON
cm19a = cm19aDriver.CM19aDevice(POLLFREQ, log, polling = True)            # cm19a is an instance of the CM19aDevice class

if cm19a.initialised:
    # Firstly some simple send commands
    # Send the command 'ON' to X10 device A1 wirelessly via the CM19a (and a receiver of course)
    print "Turning ON A1..."
    result = cm19a.send("A", "1", "ON")     # True if the command was sent OK
    if result:
        print "...Success"
    else:
        print  >> sys.stderr, "Command failed"

    print "Waiting 5 seconds (so we can check that the device has turned on)..."
    time.sleep(5)

    print "Now turning OFF A1..."
    result = cm19a.send("a", "1", "OFf")            # notice that this is case insensitive
    if result:
        print "...Success"
    else:
        print  >> sys.stderr, "Command failed"

    # Now a simple macro
    print '\n\n---- Basic Macros initiated by a key press on an X10 remote control ----'
    print 'Press any button on the remote. A4ON will run a macro, A4OFF will exit this programme'
    alive = True
    lasthouse = ''
    lastunit = ''
    while alive:
        # Check for any button presses from an X10 remote
        buttonpresses = cm19a.getReceiveQueue()         # -> List
        if buttonpresses:
            # One or more button presses were received so loop through the list of button presses
            for button in buttonpresses:
                print "Actioning button press: %s" % button
                # Use a regular expression to extract the house code, unit number, and command
                b = re.search(r'^(.)(\d+)(.+)', button)     # start of string, 1 character (house code), 1 or more digits (unit number), 1 or more characters (command)
                if b:
                    house = b.group(1).upper()
                    unit = b.group(2).upper()
                    command = b.group(3).upper()
                else:
                    print  >> sys.stderr, "Could not extract house code etc from %s" % button

                if button == "A4ON":
                    # Really simple macro
                    # When A4ON is pressed on the remote, turn on E1, dim it by 5% (assuming it is a lamp module) and turn off E2
                    print "\nRunning macro (A4ON) to turn ON E1, dimming it by 5%, and then turn OFF E2"
                    result = cm19a.send("E", "1", "ON")     # True if the command was sent OK
                    if not result:
                        print  >> sys.stderr, "Command failed"
                    result = cm19a.send("E", "1", "DIM")        # True if the command was sent OK
                    if not result:
                        print  >> sys.stderr, "Command failed"
                    result = cm19a.send("E", "2", "OFF")        # True if the command was sent OK
                    if not result:
                        print  >> sys.stderr, "Command failed"
                    lasthouse = 'E'
                    lastunit = '2'
                    print "Macro for A4ON completed."
                elif button == "A4OFF":
                    # exit the program
                    print "Stopping checking for button presses."
                    alive = False
                    break
                else:
                    # Other button pressess
                    if command.find('BRIGHTBUTTONPRESSED')>= 0:
                        print 'Bright button was pressed => Brightening the last used device..'
                        result = cm19a.send(lasthouse, lastunit, 'bright')       # True if the command was sent OK
                        if not result:
                            print  >> sys.stderr, "Command failed"
                    elif command.find('DIMBUTTONPRESSED')>= 0:
                        print 'Dim button was pressed => Dimming the last used device...'
                        result = cm19a.send(lasthouse, lastunit, 'dim')       # True if the command was sent OK
                        if not result:
                            print  >> sys.stderr, "Command failed"
                    else:
                        # Just retransmit any other command recevied
                        result = cm19a.send(house, unit, command)       # True if the command was sent OK
                        if not result:
                            print  >> sys.stderr, "Command failed"
                        lasthouse = house
                        lastunit = unit
            #end for loop
        else:
            # No buttons pressed so do just wait a bit (2 seconds in this case) before checking again
            time.sleep(2)
    # end while alive loop

    cm19a.finish()
else:
    print "Error initialising the CM19a...exiting..."
    sys.exit(1)

print "...All done"

# End of example

