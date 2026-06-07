import os
import sys
import types
import unittest
from unittest.mock import patch


_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, _ROOT)


class FakePin:
    OPEN_DRAIN = "OPEN_DRAIN"
    IN = "IN"
    IRQ_FALLING = "IRQ_FALLING"

    def __init__(self, pin_id, mode=None, value=None):
        self.pin_id = pin_id
        self.mode = mode
        self._value = value if value is not None else 0
        self._handler = None
        self.off_calls = 0
        self.on_calls = 0

    def off(self):
        self.off_calls += 1
        self._value = 0

    def on(self):
        self.on_calls += 1
        self._value = 1

    def value(self, value=None):
        if value is None:
            return self._value
        self._value = value

    def irq(self, trigger=None, handler=None):
        self._handler = handler


class FakeTimer:
    PERIODIC = "PERIODIC"
    ONE_SHOT = "ONE_SHOT"

    def __init__(self, id=-1):
        pass

    def init(self, period=0, mode=None, callback=None):
        pass

    def deinit(self):
        pass


machine = types.ModuleType("machine")
machine.Pin = FakePin
machine.Timer = FakeTimer
sys.modules["machine"] = machine

import easycontrol  # noqa: E402


class TestEasycontrolSelect(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "select_pin": 8,
            "up_pin": 5,
            "down_pin": 7,
            "stop_pin": 6,
            "ch1_pin": 9,
            "ch2_pin": 10,
            "ch3_pin": 17,
            "ch4_pin": 18,
            "ch5_pin": 21,
        }

    def test_select_advances_one_step_to_adjacent_channel(self):
        """One SELECT pulse sent to advance from ch1 to ch2."""
        with patch.object(easycontrol.time, "sleep", return_value=None):
            ec = easycontrol.Easycontrol(self.cfg)
            ec.init()
            # select(): first read (before loop) -> ch1, after first pulse -> ch2
            with patch.object(ec, "check_channel", side_effect=[1, 2]):
                ec.select(2)

        self.assertEqual(ec._selected_ch, 2)
        self.assertEqual(ec.select_pin.off_calls, 1)

    def test_select_sends_correct_number_of_pulses(self):
        """From ch1, exactly 2 pulses needed to reach ch3."""
        with patch.object(easycontrol.time, "sleep", return_value=None):
            ec = easycontrol.Easycontrol(self.cfg)
            ec.init()
            ec._selected_ch = 1
            # select(): first read -> ch1, then pulse confirmations ch2 and ch3
            with patch.object(ec, "check_channel", side_effect=[1, 2, 3]):
                ec.select(3)

        self.assertEqual(ec._selected_ch, 3)
        self.assertEqual(ec.select_pin.off_calls, 2)

    def test_select_does_not_pulse_when_already_on_target(self):
        """No pulse sent when software state already matches target."""
        with patch.object(easycontrol.time, "sleep", return_value=None):
            ec = easycontrol.Easycontrol(self.cfg)
            ec.init()
            ec._selected_ch = 2
            ec.select(2)

        self.assertEqual(ec._selected_ch, 2)
        self.assertEqual(ec.select_pin.off_calls, 0)


if __name__ == "__main__":
    unittest.main()