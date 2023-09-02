"""
Page turner boot handler.

Disables CIRCUITPY USB disk, unless switch is engaged.

https://learn.adafruit.com/customizing-usb-devices-in-circuitpython/circuitpy-midi-serial
"""

import board
import digitalio
import storage

# Pins.
USB_DISK_SWITCH_PIN = board.D7


def boot_main():
    switch = digitalio.DigitalInOut(USB_DISK_SWITCH_PIN)
    switch.pull = digitalio.Pull.UP
    if switch.value:
        storage.disable_usb_drive()


boot_main()
