"""
Page Turner
"""

from rp2040_util import (
    Gadget,
    HIDKeyboard,
    Keycode,
    board,
    gadget_main,
)

# Pins.
PULSE_LAMP_PIN = board.LED
STATUS_LAMP_PIN = board.NEOPIXEL
PGDN_LAMP_PIN = board.D2
PGUP_LAMP_PIN = board.D3
USB_DISK_SWITCH_PIN = board.D7
USB_DISK_LAMP_PIN = board.D8
TAP_INPUT_PIN = board.A0

# Parameters.
SLEEP_SECS = .02
PULSE_LAMP_FLASH_SECS = .5
STATUS_BRIGHTNESS = 0.1
STATUS_COLOR_SINGLE_TAP = (255, 0, 0)
STATUS_COLOR_DOUBLE_TAP = (0, 255, 0)
STATUS_LAMP_ON_SECS = 1.0
PGXX_LAMP_ON_SECS = 1.0


class PageTurner(Gadget):

    def __init__(self, controller):
        super().__init__(controller)
        self.pulse_lamp = self.controller.lamp(
            PULSE_LAMP_PIN,
            on_secs=PULSE_LAMP_FLASH_SECS,
            off_secs=PULSE_LAMP_FLASH_SECS,
        )
        self.status_lamp = self.controller.multicolor_lamp(
            STATUS_LAMP_PIN,
            brightness=STATUS_BRIGHTNESS,
            on_secs=STATUS_LAMP_ON_SECS,
        )
        self.pgdn_lamp = self.controller.lamp(
            PGDN_LAMP_PIN,
            on_secs=PGXX_LAMP_ON_SECS,
        )
        self.pgup_lamp = self.controller.lamp(
            PGUP_LAMP_PIN,
            on_secs=PGXX_LAMP_ON_SECS,
        )
        self.usb_drive_lamp = self.controller.lamp(
            USB_DISK_LAMP_PIN,
        )
        self.hid_keyboard = HIDKeyboard()
        self.tap_input = self.controller.tap_input(board.A0)

    def init(self):
        # Indicate that the CIRCUITPY drive is mounted.
        if self.controller.is_circuitpy_mounted():
            self.usb_drive_lamp.turn_on()
        # Host may be disconnected at startup. Connect USB HID keyboard when host connects.
        if self.hid_keyboard.check_connected():
            self.pgdn_lamp.turn_on()
            self.pgup_lamp.turn_on()

    def poll(self):
        # Handle tap input. Look for finalized single/double taps when released.
        if self.tap_input.check_released():
            tap_count = self.tap_input.check_taps()
            if tap_count == 1:
                print('page down')
                self.hid_keyboard.send_keys(Keycode.PAGE_DOWN)
                self.pgdn_lamp.turn_on()
                self.status_lamp.set_color(STATUS_COLOR_SINGLE_TAP)
                self.status_lamp.turn_on()
            elif tap_count == 2:
                print('page up')
                self.hid_keyboard.send_keys(Keycode.PAGE_UP)
                self.pgup_lamp.turn_on()
                self.status_lamp.set_color(STATUS_COLOR_DOUBLE_TAP)
                self.status_lamp.turn_on()


gadget_main(SLEEP_SECS, PageTurner)
