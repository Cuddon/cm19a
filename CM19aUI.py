#!/usr/bin/env python

"""
A simple and not very pretty user interface for my Python driver for the CM19a X10 RF Transceiver (USB)

Functionality
 - Send ON/OFF/DIM/BRIGHT commands wirelessly to any X10 device via the CM19a (requires a transceiver)
 - Displays some basic info about the device

Requires my CM19a driver version 0.11 or above

Version 3.00
Sept 2011

Uses Tkinter UI libraries provided with Python so should run on any Python installation.

Requires tkinter 8.4 or later (on Ubuntu: sudo apt-get install python-tk)

"""

import time

from Tkinter import *
import tkMessageBox

import CM19aDriver

class App:
    def __init__(self, master):
        # Construct the App object

        self.statusText = StringVar()
        self.statusText.set("Starting up...")

        # Add a label frame widget to group the x10 commands
        group1 = LabelFrame(master, text="Commands", padx=5, pady=5,  height=50,  width=60)
        group1.pack(padx=10, pady=10)

        # X10 device selection entry
        self.house = Entry(group1,  width=5)
        self.house.insert(0, "A")
        self.house.pack(side=LEFT)
        self.unit = Entry(group1,  width=10)
        self.unit.insert(0, "1")
        self.unit.pack(side=LEFT)

        # comand buttons
        self.onButton = Button(group1, text="On", command=lambda: self.x10command("ON"))
        self.onButton.pack(side=LEFT)
        self.offButton = Button(group1, text="Off", command=lambda: self.x10command("OFF"))
        self.offButton.pack(side=LEFT)
        self.brightButton = Button(group1, text="Brighter", command=lambda: self.x10command("BRIGHT"))
        self.brightButton.pack(side=LEFT)
        self.dimButton = Button(group1, text="Dimmer", command=lambda: self.x10command("DIM"))
        self.dimButton.pack(side=LEFT)

        # Add another frame widget for the status messeages
        group2 = LabelFrame(master, text="Status", padx=5, pady=5,  height=10,  width=300)
        group2.pack()

        # Status information
        self.statusTextLabel = Label(group2,  textvariable=self.statusText, anchor=W, justify=LEFT,  relief=FLAT,  fg="blue",  width=60)
        self.statusTextLabel.pack(side=LEFT)

        # Add another (invisible) frame widget for the quit and queue buttons
        group3 = Frame(master)
        group3.pack()

        # Listen Button (Waits from an inbound command from the X10
        self.listenButton = Button(group3, text="Receive Queue...", fg="black", command=self.cm19aGetReceiveQueue)
        self.listenButton.pack(side=LEFT)

        # Quit button
        self.quitButton = Button(group3, text="QUIT", fg="red", command=master.quit)
        self.quitButton.pack(side=BOTTOM)

        # Add another frame widget
        group4 = LabelFrame(master, text="Device Information", padx=5, pady=5,  height=10,  width=300)
        group4.pack()
        # retrieve the USB device info
        self.deviceInfoText = StringVar()
        self.deviceInfoText.set("Vendor ID: %d" % cm19a.device.idVendor +
        "\nProduct ID: %d" % cm19a.device.idProduct +
        #"\nProduct: %s" % cm19a.device.open().getString(cm19a.device.iProduct,50) +
        #"\nManufacturer: %r" % cm19a.device.iManufacturer +
        "\nUSB version: %r" % cm19a.device.usbVersion)

        self.deviceInfoTextLabel = Label(group4,  textvariable=self.deviceInfoText, anchor=W, justify=LEFT,  relief=FLAT,  bg="gray")
        self.deviceInfoTextLabel.pack()

        self.statusText.set("Ready.. Select a house code, unit and then click an action button.")


    def x10command(self,  cmd):
        print "Doing command %s on %s%s" % (cmd, self.house.get(), self.unit.get())
        result = cm19a.send(self.house.get(), self.unit.get(), cmd)       # True if the command was sent OK
        if not result:
            tkMessageBox.showerror("Cm19a UI","Command Failed:\n")
            self.statusText.set("Command %s on %s%s FAILED!" % (cmd, self.house.get(), self.unit.get()))
        else:
            self.statusText.set("Command %s on %s%s sent OK!" % (cmd, self.house.get(), self.unit.get()))

    def cm19aGetReceiveQueue(self):
        queue = cm19a.getReceiveQueue()
        if queue == []:
            tkMessageBox.showinfo("Cm19a UI","No commands received.\nPress a button on an RF remote.")
        else:
            tkMessageBox.showinfo("Cm19a UI","Commands Received:\n%r" % queue)

# endclass


# MAIN
VERSION = "3.00"
POLLFREQ = 1
WINDOW_WIDTH = 600
WINDOW_HEIGHT = 300

# Create the root widget for the application
root = Tk()
root.withdraw()

try:
    if CM19aDriver.VERSION < 3.00:
        tkMessageBox.showerror("Cm19a Driver","The app requires version 3.00 of the driver or above. You are using version %r." % cm19aDriver.VERSION)
except:
        tkMessageBox.showerror("Cm19a Driver","The app requires version 3.00 of the driver or above. Please download a leter version from www cuddon.net")

# Start logging
log = CM19aDriver.startLogging()        # log is an instance of the logger class

# Open the device and  configure
cm19a = CM19aDriver.CM19aDevice(POLLFREQ, log, polling = True)

if not cm19a.initialised > 0:
    tkMessageBox.showerror("Cm19a Driver","Error initialising the Cm19a device.\n See log for more info.")
else:
    # Set up the root window
    root.title(string="CM19a driver example front end (v%s) - Driver version: %s" % (VERSION,  CM19aDriver.VERSION))
    root.resizable(width=None, height=None)
    # get screen width and height
    ws = root.winfo_screenwidth()
    hs = root.winfo_screenheight()
    # calculate position x, y
    x = (ws/2) - (WINDOW_WIDTH/2)
    y = (hs/2) - (WINDOW_HEIGHT/2)
    root.geometry('%dx%d+%d+%d' % (WINDOW_WIDTH, WINDOW_HEIGHT, x, y))
    root.deiconify()

    # create the app object and initialise
    app = App(root)

    # Run the app
    root.mainloop()

    cm19a.finish()

root.destroy()
print "Done."

