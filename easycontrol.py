from machine import Pin
import time

# Channel cycle: matches physical remote select-button rotation.
_CHANNEL_SEQUENCE = [1, 2, 3, 4, 5, 0]

# Logger used by select() so messages reach MQTT at runtime.
_logger = print


def set_logger(fn):
    global _logger
    _logger = fn

# Give the controller a short moment to latch the new channel before sending
# the subsequent UP/DOWN/STOP pulse. Without this, the pulse may still hit the
# previously selected channel.
_SELECT_SETTLE_TIME = 0.5

# The selected channel LED is visible briefly after a SELECT pulse.
# Poll in small steps so we can detect the new channel without long blocking.
_SELECT_POLL_INTERVAL = 0.01   # 10 ms between reads
_SELECT_POLL_ATTEMPTS = 30     # up to 300 ms total polling window


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

    # Channel read at IRQ time (same moment the LED lights up).
    # -1 = undetermined, 0 = all channels, 1-5 = specific channel.
    _irq_channel = None

    # Pre-allocated reference to channel LED pins for IRQ-safe reading (no heap alloc).
    _ch_pins = None

    # ── IRQ helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _read_channel():
        """Read active channel from LED pins without heap allocation (IRQ-safe)."""
        p = Easycontrol._ch_pins
        if p is None:
            return -1
        c1 = p[0].value()
        c2 = p[1].value()
        c3 = p[2].value()
        c4 = p[3].value()
        c5 = p[4].value()
        if c1 and c2 and c3 and c4 and c5:
            return 0
        if c1: return 1
        if c2: return 2
        if c3: return 3
        if c4: return 4
        if c5: return 5
        return -1

    # ── IRQ handlers (must be static – no heap allocation in interrupt context) ───

    @staticmethod
    def _irq_up(pin):
        Easycontrol._remote_pressed = 'up'
        Easycontrol._irq_channel = Easycontrol._read_channel()

    @staticmethod
    def _irq_down(pin):
        Easycontrol._remote_pressed = 'down'
        Easycontrol._irq_channel = Easycontrol._read_channel()

    @staticmethod
    def _irq_stop(pin):
        Easycontrol._remote_pressed = 'stop'
        Easycontrol._irq_channel = Easycontrol._read_channel()

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
        # Make channel pins accessible to the static IRQ handler without heap allocation.
        Easycontrol._ch_pins = self.channels

        # Assume channel 1 is active after power-on (physical remote default).
        # Tracked in software because the LEDs are only briefly lit on button press.
        self._selected_ch = 1

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
        Easycontrol._irq_channel = None
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
        if self.select(channel):
            self._up()
        else:
            _logger("up: aborted, channel selection failed")
        self._restore_irqs()

    def down(self, channel):
        self._suppress_irqs()
        if self.select(channel):
            self._down()
        else:
            _logger("down: aborted, channel selection failed")
        self._restore_irqs()

    def stop(self, channel):
        self._suppress_irqs()
        if self.select(channel):
            self._stop()
        else:
            _logger("stop: aborted, channel selection failed")
        self._restore_irqs()

    def get_and_clear_remote_press(self):
        """Return (button, channel) captured at IRQ time, then clear both flags.
        button  : 'up' / 'down' / 'stop', or None if no press was recorded.
        channel : 0 = all channels, 1-5 = specific channel, -1 = undetermined."""
        pressed = Easycontrol._remote_pressed
        channel = Easycontrol._irq_channel
        Easycontrol._remote_pressed = None
        Easycontrol._irq_channel = None
        return pressed, channel

    def check_channel(self):
        """Read selected channel from LED inputs.

        Returns:
            0  -> all channels selected
            1..5 -> selected channel
            -1 -> indeterminate (no LED active)
        """
        states = [channel.value() for channel in self.channels]

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

    def _poll_selected_after_click(self, prev_channel):
        """Poll LED inputs for a new channel, ignoring prev_channel (afterglow).

        No initial delay – caller may invoke this both during and after the pulse
        to maximise the detection window.
        """
        for _ in range(_SELECT_POLL_ATTEMPTS):
            detected = self.check_channel()
            if detected >= 0 and detected != prev_channel:
                return detected
            time.sleep(_SELECT_POLL_INTERVAL)
        return -1

    def select(self, channel):
        if channel is None:
            channel = 0
        channel = int(channel)

        # Sync software state from hardware if LED is currently visible.
        hw_now = self.check_channel()
        if hw_now >= 0:
            self._selected_ch = hw_now

        _logger("select({}): sw_ch={}".format(channel, self._selected_ch))

        steps = 0            # number of SELECT pulses actually sent
        max_steps = len(_CHANNEL_SEQUENCE) * 2  # allow extra retries
        while self._selected_ch != channel and steps < max_steps:
            prev_channel = self._selected_ch

            # Send 100 ms pulse – log pin transitions so we can verify in MQTT.
            _logger("select: pulse start (select_pin LOW)")
            self.select_pin.off()
            time.sleep(0.1)
            self.select_pin.on()
            _logger("select: pulse end (select_pin HIGH)")

            # Wait a fixed 150 ms for the hardware to register the pulse and
            # light the new channel LED (original firmware used ~120 ms).
            time.sleep(0.15)
            detected = self.check_channel()

            steps += 1
            if detected >= 0 and detected != prev_channel:
                # LED confirmed new channel.
                self._selected_ch = detected
                _logger("select: LED ch={} after {} pulses".format(detected, steps))
            elif detected == channel:
                # LED shows target channel (may equal prev in some edge cases).
                self._selected_ch = detected
                _logger("select: LED ch={} (target) after {} pulses".format(detected, steps))
            elif detected == prev_channel:
                # Hardware acknowledged the pulse, but still reports old channel.
                # Observed behavior: first pulse can be a "priming" pulse.
                _logger("select: priming pulse (still ch={})".format(prev_channel))
            else:
                # No reliable LED confirmation -> do NOT advance software state.
                _logger("select: no LED confirmation (raw={}), retry".format(detected))

        if self._selected_ch == channel:
            if steps > 0:
                time.sleep(_SELECT_SETTLE_TIME)
            _logger("select: ch{} OK (pulses={})".format(channel, steps))
            return True
        else:
            _logger("select: WARNING ch{} not reached (sw_ch={})".format(channel, self._selected_ch))
            return False

