#!/usr/bin/env python

"""
importexample.py

This script shows you how to import the CM19a module and use it to send and receive commands via the CM19a

Version 0.12
Sep 2011

Andrew Cuddon
www.cuddon.net
"""

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
    # Sends the command 'ON' to device X10 device A1 wirelessly via the CM19a (and recevier of course)
    result = cm19aDriver.cm19a.send("A", "1", "ON")     # True if the command was sent OK
    if result:
        print "...Success"
    else:
        print  >> sys.stderr, "Command failed"
        
    print "Waiting 5 seconds (so we can check that the device has turned on)..."
    time.sleep(5)

    print "Now turning OFF A1..."
    result = cm19aDriver.cm19a.send("a", "1", "OFf")            # notice that this is case insensitive
    if result:
        print "...Success"
    else:
        print  >> sys.stderr, "Command failed"

    print "\nPress one or more keys on the x10 remote within the next 30 seconds"
    time.sleep(30)
    print "Receive Queue:",  cm19aDriver.cm19a.getReceiveQueue()

    print "\nAgain, press one or more keys on the x10 remote within the next 30 seconds"
    time.sleep(30)
    print "Receive Queue (since the last time we requested the queue):",  cm19aDriver.cm19a.getReceiveQueue()

    # Close the device and tidy up
    cm19aDriver.tidyUp()
    print "Tests complete."
else:
    print "Error initialising the CM19a...exiting..."
    sys.exit(1)

# End of example

