from machine import Pin
import time


class Easycontrol:

    CONFIG = None

    # 0 if all channels selected, greater than 0 otherwise
    selected = None

    up_pin = None
    down_pin = None
    stop_pin = None
    select_pin = None

    channels = None

    # Set by falling-edge IRQ handlers when the physical remote presses a button.
    # Values: 'up', 'down', 'stop', or None.  Cleared by get_and_clear_remote_press().
    _remote_pressed = None

    # ── IRQ handlers (must be static – no heap allocation in interrupt context) ───

    @staticmethod
    def _irq_up(pin):
        Easycontrol._remote_pressed = 'up'

    @staticmethod
    def _irq_down(pin):
        Easycontrol._remote_pressed = 'down'

    @staticmethod
    def _irq_stop(pin):
        Easycontrol._remote_pressed = 'stop'

    def __init__(self, config):
        self.CONFIG = config

    def init(self):
        self.select_pin = Pin(self.CONFIG['select_pin'], mode=Pin.OPEN_DRAIN, value=1)
        self.up_pin = Pin(self.CONFIG['up_pin'], mode=Pin.OPEN_DRAIN, value=1)
        self.stop_pin = Pin(self.CONFIG['stop_pin'], mode=Pin.OPEN_DRAIN, value=1)
        self.down_pin = Pin(self.CONFIG['down_pin'], mode=Pin.OPEN_DRAIN, value=1)

        ch1_pin = Pin(self.CONFIG['ch1_pin'], Pin.IN)
        ch2_pin = Pin(self.CONFIG['ch2_pin'], Pin.IN)
        ch3_pin = Pin(self.CONFIG['ch3_pin'], Pin.IN)
        ch4_pin = Pin(self.CONFIG['ch4_pin'], Pin.IN)
        ch5_pin = Pin(self.CONFIG['ch5_pin'], Pin.IN)

        self.channels = [ch1_pin, ch2_pin, ch3_pin, ch4_pin, ch5_pin]

        # Attach falling-edge IRQs: fires the instant the line goes low (button pressed).
        # The ESP32's own 100 ms pulses are suppressed in _up()/_down()/_stop() below.
        self.up_pin.irq(trigger=Pin.IRQ_FALLING, handler=Easycontrol._irq_up)
        self.down_pin.irq(trigger=Pin.IRQ_FALLING, handler=Easycontrol._irq_down)
        self.stop_pin.irq(trigger=Pin.IRQ_FALLING, handler=Easycontrol._irq_stop)

    def _suppress_irqs(self):
        """Disable all command-pin IRQs and clear any pending event.
        Called before select() so noise during channel cycling is ignored.
        """
        Easycontrol._remote_pressed = None
        self.up_pin.irq(handler=None)
        self.down_pin.irq(handler=None)
        self.stop_pin.irq(handler=None)

    def _restore_irqs(self):
        """Re-enable all command-pin IRQs after the command is complete."""
        self.up_pin.irq(trigger=Pin.IRQ_FALLING, handler=Easycontrol._irq_up)
        self.down_pin.irq(trigger=Pin.IRQ_FALLING, handler=Easycontrol._irq_down)
        self.stop_pin.irq(trigger=Pin.IRQ_FALLING, handler=Easycontrol._irq_stop)

    def _up(self):
        self.up_pin.off()
        time.sleep(0.1)
        self.up_pin.on()

    def _down(self):
        self.down_pin.off()
        time.sleep(0.1)
        self.down_pin.on()

    def _stop(self):
        self.stop_pin.off()
        time.sleep(0.1)
        self.stop_pin.on()

    def up(self, channel):
        self._suppress_irqs()
        self.select(channel)
        self._up()
        self._restore_irqs()

    def down(self, channel):
        self._suppress_irqs()
        self.select(channel)
        self._down()
        self._restore_irqs()

    def stop(self, channel):
        self._suppress_irqs()
        self.select(channel)
        self._stop()
        self._restore_irqs()

    def get_and_clear_remote_press(self):
        """Return the button the physical remote last pressed ('up'/'down'/'stop'),
        then clear the flag.  Returns None if no press was recorded."""
        pressed = Easycontrol._remote_pressed
        Easycontrol._remote_pressed = None
        return pressed

    def check_channel(self):
        """Funktion zum Überprüfen der LED-Zustände"""
        states = [channel.value() for channel in self.channels]
        print(states)
        
        if all(state == 1 for state in states):
            return 0  # all channels are selected
        elif all(state == 0 for state in states):
            return -1  # no channel is selected, should not occur
        else:
            # find the selected channel and return its nubmer
            for i, state in enumerate(states):
                if state == 1:
                    return i+1
        return -1  # catch all, should not occur

    def select(self, channel):
        if(channel == None):
            channel = 0
        channel = int(channel)
        self.selected = self.check_channel()
        print(f"select channel: {channel}")
        i=0
        while( ( self.selected != channel ) and (i < 10) ):
            self.select_pin.off()
            time.sleep(0.1)
            self.select_pin.on()
            time.sleep(0.02)
            self.selected = self.check_channel()
            print(f"desired: {channel}, got: {self.selected}, i: {i}")
            time.sleep(1)
            i = i + 1

        

    