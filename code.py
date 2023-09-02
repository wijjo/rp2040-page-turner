"""
Page Turner
"""

import board
import digitalio
import neopixel
import storage
import supervisor
import time
import usb_hid
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from analogio import AnalogIn

# Pins.
PULSE_LAMP_PIN = board.LED
STATUS_LAMP_PIN = board.NEOPIXEL
PGDN_LAMP_PIN = board.D2
PGUP_LAMP_PIN = board.D3
USB_DISK_SWITCH_PIN = board.D7
USB_DISK_LAMP_PIN = board.D8
TAP_INPUT_PIN = board.A0

# Parameters.
PULSE_SECS = .02
PULSE_LAMP_FLASH_SECS = .5
TAP_VALUE_THRESHOLD = 1000
TAP_MIN_SECS = .05
TAP_CAPTURE_SECS = 0.5
STATUS_BRIGHTNESS = 0.1
STATUS_COLOR_SINGLE_TAP = (255, 0, 0)
STATUS_COLOR_DOUBLE_TAP = (0, 255, 0)
STATUS_LAMP_ON_SECS = 1.0
PGXX_LAMP_ON_SECS = 1.0


class Tap:
    def __init__(self, start):
        self.start = start
        self.end = None


class TapInput:

    def __init__(self, pin):
        self.device = AnalogIn(pin)
        self.taps = None

    def check_released(self, current_time):
        tapped = self.device.value < TAP_VALUE_THRESHOLD

        # Wait for an initial tap to release when starting up.
        if self.taps is None:
            if not tapped:
                self.taps = []
            return False

        if tapped:
            # Add new Tap if handling first one or previous one was finalized.
            if not self.taps or self.taps[-1].end is not None:
                self.taps.append(Tap(current_time))
            # Nothing for caller to do while tapped.
            return False

        # Finalize unfinished last tap or remove short tap as appropriate.
        if self.taps and self.taps[-1].end is None:
            if current_time - self.taps[-1].start >= TAP_MIN_SECS:
                self.taps[-1].end = current_time
            else:
                print('short tap ignored')
                self.taps.pop()

        # Nothing to do if no taps are saved.
        if not self.taps:
            return False

        # Wait for end of capture window before checking taps.
        if current_time - self.taps[0].start < TAP_CAPTURE_SECS:
            return False

        # Caller can continue tap processing when released.
        return True

    def check_taps(self):
        # More than 2 pending taps is handled as double tap.
        tap_count = min(len(self.taps), 2)
        self.taps = []
        return tap_count


class LampBase:

    def __init__(self, device, on_secs=None, off_secs=None, is_on=False):
        self.device = device
        self.on_secs = on_secs
        self.off_secs = off_secs
        self.is_on = is_on
        self.on_time = None
        self.off_time = None

    def update(self, current_time):
        if self.is_on:
            if self.off_time and current_time >= self.off_time:
                self.turn_off(current_time)
        else:
            if self.on_time and current_time >= self.on_time:
                self.turn_on(current_time)

    def turn_on(self, current_time):
        self.on_turn_on()
        self.is_on = True
        if self.on_secs is not None:
            self.off_time = current_time + self.on_secs
        else:
            self.off_time = None

    def turn_off(self, current_time):
        self.on_turn_off()
        self.is_on = False
        if self.off_secs is not None:
            self.on_time = current_time + self.off_secs
        else:
            self.on_time = None

    def on_turn_on(self):
        raise NotImplementedError

    def on_turn_off(self):
        raise NotImplementedError


class Lamp(LampBase):

    def __init__(self, pin, on_secs=None, off_secs=None):
        device = digitalio.DigitalInOut(pin)
        device.direction = digitalio.Direction.OUTPUT
        super().__init__(device, on_secs=on_secs, off_secs=off_secs, is_on=device.value)

    def on_turn_on(self):
        self.device.value = True

    def on_turn_off(self):
        self.device.value = False


class MulticolorLamp(LampBase):

    def __init__(self, pin, brightness=1.0, on_secs=None, off_secs=None, color=None):
        device = neopixel.NeoPixel(pin, 1, brightness=brightness, auto_write=True)
        super().__init__(device, on_secs=on_secs, off_secs=off_secs)
        self.color = color

    def set_color(self, color):
        self.color = color

    def on_turn_on(self):
        if self.color is not None:
            self.device.fill(self.color)

    def on_turn_off(self):
        self.device.fill(0)


class PageTurner:

    def __init__(self):
        self.pulse_lamp = Lamp(PULSE_LAMP_PIN,
                               on_secs=PULSE_SECS,
                               off_secs=PULSE_SECS)
        self.status_lamp = MulticolorLamp(STATUS_LAMP_PIN,
                                          brightness=STATUS_BRIGHTNESS,
                                          on_secs=STATUS_LAMP_ON_SECS)
        self.pgdn_lamp = Lamp(PGDN_LAMP_PIN,
                              on_secs=PGXX_LAMP_ON_SECS)
        self.pgup_lamp = Lamp(PGUP_LAMP_PIN,
                              on_secs=PGXX_LAMP_ON_SECS)
        self.usb_drive_lamp = Lamp(USB_DISK_LAMP_PIN)
        self.keyboard_output = None
        self.tap_input = TapInput(board.A0)

    def loop(self):
        mount = storage.getmount('/')
        if mount.readonly:
            self.usb_drive_lamp.turn_on(time.monotonic())
        while True:
            time.sleep(PULSE_SECS)
            self.poll()

    def poll(self):
        current_time = time.monotonic()
        # Host may be disconnected at startup. Connect USB HID keyboard when host connects.
        if self.keyboard_output is None and supervisor.runtime.usb_connected:
            print('USB host connected')
            self.keyboard_output = Keyboard(usb_hid.devices)
            self.pgdn_lamp.turn_on(current_time)
            self.pgup_lamp.turn_on(current_time)
        # Update lamps.
        self.pgdn_lamp.update(current_time)
        self.pgup_lamp.update(current_time)
        self.pulse_lamp.update(current_time)
        self.status_lamp.update(current_time)
        # Handle tap input. Look for finalized single/double taps when released.
        if self.tap_input.check_released(current_time):
            tap_count = self.tap_input.check_taps()
            if tap_count == 1:
                print('page down')
                if self.keyboard_output is not None:
                    self.keyboard_output.send(Keycode.PAGE_DOWN)
                self.pgdn_lamp.turn_on(current_time)
                self.status_lamp.set_color(STATUS_COLOR_SINGLE_TAP)
                self.status_lamp.turn_on(current_time)
            elif tap_count == 2:
                print('page up')
                if self.keyboard_output is not None:
                    self.keyboard_output.send(Keycode.PAGE_UP)
                self.pgup_lamp.turn_on(current_time)
                self.status_lamp.set_color(STATUS_COLOR_DOUBLE_TAP)
                self.status_lamp.turn_on(current_time)


PageTurner().loop()
