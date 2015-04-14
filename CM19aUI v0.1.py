#!/usr/bin/env python

"""
A simple and not very pretty user interface for my Python driver for the CM19a X10 RF Transceiver (USB)

Functionality
 - Send ON/OFF/DIM/BRIGHT commands wirelessly to any X10 device via the CM19a (requires a transceiver)
 - Displays some basic info about the device

Requires my CM19a driver version 0.11 or above

Version 0.1
Dec 2009

Uses Tkinter libraries provided with Python so should run on any Python installation.

Requires tkinter 8.4 or later
"""

from Tkinter import *
import tkMessageBox

import cm19aDriver

class App:
    def __init__(self, master):
        # Construct the object

        self.statusText = StringVar()
        self.statusText.set("Starting up")

        # Add a label frame widget to group the x10 commands
        group1 = LabelFrame(master, text="Commands", padx=5, pady=5,  height=50,  width=60)
        group1.pack(padx=10, pady=10)

        # X10 device slection entry
        self.housecode = Entry(group1,  width=5)
        self.housecode.insert(0, "A")
        self.housecode.pack(side=LEFT)
        self.devicecode = Entry(group1,  width=10)
        self.devicecode.insert(0, "1")
        self.devicecode.pack(side=LEFT)

        # comand buttons
        self.onButton = Button(group1, text="On", command=lambda: self.x10command("ON"))
        self.onButton.pack(side=LEFT)
        self.offButton = Button(group1, text="Off", command=lambda: self.x10command("OFF"))
        self.offButton.pack(side=LEFT)
        self.brightButton = Button(group1, text="Brighter", command=lambda: self.x10command("BRIGHT"))
        self.brightButton.pack(side=LEFT)
        self.dimButton = Button(group1, text="Dimmer", command=lambda: self.x10command("DIM"))
        self.dimButton.pack(side=LEFT)

        # Add another frame widget
        group2 = LabelFrame(master, text="Status", padx=5, pady=5,  height=10,  width=300)
        group2.pack()

        # Status information
        self.statusTextLabel = Label(group2,  textvariable=self.statusText, anchor=W, justify=LEFT,  relief=FLAT,  fg="blue",  width=60)
        self.statusTextLabel.pack(side=LEFT)

        # Add another frame widget
        group3 = Frame(master)
        group3.pack()

        # Listen Button (Waits from an inbound command from the X10
        self.listenButton = Button(group3, text="Listen...", fg="green", command=self.cm19aListen, state=DISABLED)
        self.listenButton.pack(side=LEFT)

        # Quit button
        self.quitButton = Button(group3, text="QUIT", fg="red", command=master.quit)
        self.quitButton.pack(side=BOTTOM)

        # Add another frame widget
        group4 = LabelFrame(master, text="Device Information", padx=5, pady=5,  height=10,  width=300)
        group4.pack()
        # retrieve the USB device info
        self.deviceInfoText = StringVar()
        self.deviceInfoText.set("Vendor ID: %d" % cm19aDriver.cm19a.device.idVendor +
        "\nProduct ID: %d" % cm19aDriver.cm19a.device.idProduct +
        "\nProduct: %s" % cm19aDriver.cm19a.device.open().getString(cm19aDriver.cm19a.device.iProduct,50) +
        "\nManufacturer: %s" % cm19aDriver.cm19a.device.open().getString(cm19aDriver.cm19a.device.iManufacturer,50) +
        "\nDevice version: %r" % cm19aDriver.cm19a.device.deviceVersion +
        "\nUSB version: %r" % cm19aDriver.cm19a.device.usbVersion)

        self.deviceInfoTextLabel = Label(group4,  textvariable=self.deviceInfoText, anchor=W, justify=LEFT,  relief=FLAT,  bg="gray")
        self.deviceInfoTextLabel.pack()

        self.statusText.set("Ready.. Select a house code, device and then click an action button.")


    def x10command(self,  cmd):
        print "Doing command %s on %s%s" % (cmd, self.housecode.get(), self.devicecode.get())
        result = cm19aDriver.cm19a.send(self.housecode.get(), self.devicecode.get(), cmd)       # True if the command was sent OK
        if not result:
            tkMessageBox.showerror("Cm19a UI","Command Failed:\n" + cm19aDriver.cm19a.errormessages)
            self.statusText.set("Command %s on %s%s FAILED!" % (cmd, self.housecode.get(), self.devicecode.get()))
        else:
            self.statusText.set("Command %s on %s%s sent OK!" % (cmd, self.housecode.get(), self.devicecode.get()))

    def cm19aListen(self):
        print "Now listening (for 30 seconds) for x10 remote commands received via the Cm19a..."
        time.sleep(30)
        tkMessageBox.showinfo("Cm19a UI","Commands Received: " + cm19aDriver.cm19a.getReceiveQueue())
        print "Receive Queue:",  cm19aDriver.cm19a.getReceiveQueue()

# endclass


# MAIN
VERSION = "0.1"
WINDOW_WIDTH = 600
WINDOW_HEIGHT = 400

# Create the root widget for the application
root = Tk()
root.withdraw()

try:
    if cm19aDriver.VERSION < 0.11:
        tkMessageBox.showerror("Cm19a Driver","The app requires version 0.11 of the driver or above. You are using version %s." % cm19aDriver.VERSION)
except:
        tkMessageBox.showerror("Cm19a Driver","The app requires version 0.11 of the driver or above. Please download a leter version from www cuddon.net")

# Open the device and  configure
cm19aDriver.configure()
if cm19aDriver.cm19a.errors > 0:
    tkMessageBox.showerror("Cm19a Driver","Error initialising the Cm19a device:\n" + cm19aDriver.cm19a.errormessages)
else:
    # Set up the root window
    root.title(string="CM19a driver front end (v%s) - Driver version: %s" % (VERSION,  cm19aDriver.VERSION))
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

    cm19aDriver.tidyUp()

root.destroy()
print "Done."
