"""
RP2040 utility classes, etc..

Common code for managing a gadget and its connected components.
"""

# noinspection PyUnresolvedReferences
import board
import digitalio
import neopixel
import storage
import supervisor
import time
import usb_hid
from adafruit_hid.keyboard import Keyboard
# noinspection PyUnresolvedReferences
from adafruit_hid.keycode import Keycode
from analogio import AnalogIn

TAP_VALUE_THRESHOLD = 1000
TAP_MIN_SECS = .05
TAP_CAPTURE_SECS = 0.5


class Heartbeat:

    def __init__(self):
        self.time = time.monotonic()

    def tick(self):
        self.time = time.monotonic()


class TimedDevice:

    def __init__(self, heartbeat):
        self.heartbeat = heartbeat


class Tap:
    def __init__(self, start):
        self.start = start
        self.end = None


class TapInput(TimedDevice):

    def __init__(self, pin, heartbeat):
        self.device = AnalogIn(pin)
        self.taps = None
        super().__init__(heartbeat)

    def check_released(self):
        tapped = self.device.value < TAP_VALUE_THRESHOLD

        # Wait for an initial tap to release when starting up.
        if self.taps is None:
            if not tapped:
                self.taps = []
            return False

        if tapped:
            # Add new Tap if handling first one or previous one was finalized.
            if not self.taps or self.taps[-1].end is not None:
                self.taps.append(Tap(self.heartbeat.time))
            # Nothing for caller to do while tapped.
            return False

        # Finalize unfinished last tap or remove short tap as appropriate.
        if self.taps and self.taps[-1].end is None:
            if self.heartbeat.time - self.taps[-1].start >= TAP_MIN_SECS:
                self.taps[-1].end = self.heartbeat.time
            else:
                print('short tap ignored')
                self.taps.pop()

        # Nothing to do if no taps are saved.
        if not self.taps:
            return False

        # Wait for end of capture window before checking taps.
        if self.heartbeat.time - self.taps[0].start < TAP_CAPTURE_SECS:
            return False

        # Caller can continue tap processing when released.
        return True

    def check_taps(self):
        # More than 2 pending taps is handled as double tap.
        tap_count = min(len(self.taps), 2)
        self.taps = []
        return tap_count


class LampBase(TimedDevice):

    def __init__(self, device, heartbeat, on_secs=None, off_secs=None, is_on=False):
        self.device = device
        self.on_secs = on_secs
        self.off_secs = off_secs
        self.is_on = is_on
        self.on_time = None
        self.off_time = None
        super().__init__(heartbeat)

    def update(self):
        if self.is_on:
            if self.off_time and self.heartbeat.time >= self.off_time:
                self.turn_off()
        else:
            if self.on_time and self.heartbeat.time >= self.on_time:
                self.turn_on()

    def turn_on(self):
        self.on_turn_on()
        self.is_on = True
        if self.on_secs is not None:
            self.off_time = self.heartbeat.time + self.on_secs
        else:
            self.off_time = None

    def turn_off(self):
        self.on_turn_off()
        self.is_on = False
        if self.off_secs is not None:
            self.on_time = self.heartbeat.time + self.off_secs
        else:
            self.on_time = None

    def on_turn_on(self):
        raise NotImplementedError

    def on_turn_off(self):
        raise NotImplementedError


class Lamp(LampBase):

    def __init__(self, pin, heartbeat, on_secs=None, off_secs=None):
        device = digitalio.DigitalInOut(pin)
        device.direction = digitalio.Direction.OUTPUT
        super().__init__(device, heartbeat, on_secs=on_secs, off_secs=off_secs, is_on=device.value)

    def on_turn_on(self):
        self.device.value = True

    def on_turn_off(self):
        self.device.value = False


class MulticolorLamp(LampBase):

    def __init__(self, pin, heartbeat, brightness=1.0, on_secs=None, off_secs=None, color=None):
        device = neopixel.NeoPixel(pin, 1, brightness=brightness, auto_write=True)
        super().__init__(device, heartbeat, on_secs=on_secs, off_secs=off_secs)
        self.color = color

    def set_color(self, color):
        self.color = color

    def on_turn_on(self):
        if self.color is not None:
            self.device.fill(self.color)

    def on_turn_off(self):
        self.device.fill(0)


class HIDKeyboard:

    def __init__(self):
        self.device = None

    def check_connected(self):
        if self.device is None and supervisor.runtime.usb_connected:
            print('USB host connected')
            self.device = Keyboard(usb_hid.devices)
        return self.device is not None

    def send_keys(self, *keycodes):
        if self.check_connected():
            self.device.send(*keycodes)


class Controller:

    def __init__(self, heartbeat):
        self.heartbeat = heartbeat
        self.lamps = []

    def lamp(self, pin, on_secs=None, off_secs=None):
        self.lamps.append(
            Lamp(pin,
                 self.heartbeat,
                 on_secs=on_secs,
                 off_secs=off_secs),
        )
        return self.lamps[-1]

    def multicolor_lamp(self, pin, brightness=1.0, on_secs=None, off_secs=None, color=None):
        self.lamps.append(
            MulticolorLamp(pin,
                           self.heartbeat,
                           brightness=brightness,
                           on_secs=on_secs,
                           off_secs=off_secs,
                           color=color),
        )
        return self.lamps[-1]

    def tap_input(self, pin):
        return TapInput(pin, self.heartbeat)

    @staticmethod
    def is_circuitpy_mounted():
        return storage.getmount('/').readonly


class Gadget:

    def __init__(self, controller):
        self.controller = controller

    def init(self):
        raise NotImplementedError

    def poll(self):
        raise NotImplementedError


def gadget_main(sleep_secs, gadget_class, *gadget_args, **gadget_kwargs):
    heartbeat = Heartbeat()
    controller = Controller(heartbeat)
    gadget = gadget_class(controller, *gadget_args, **gadget_kwargs)
    gadget.init()
    while True:
        time.sleep(sleep_secs)
        heartbeat.tick()
        for lamp in controller.lamps:
            lamp.update()
        gadget.poll()
