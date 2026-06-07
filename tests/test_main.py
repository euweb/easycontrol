"""Unit tests for main.py – ESP32 EasyControl shutter controller.

Run:
    python -m pytest tests/
    python -m unittest discover -s tests/
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, call, mock_open, patch

# ── sys.path: stubs first so MicroPython modules are found ───────────────────
_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(_ROOT, "stubs"))
sys.path.insert(0, _ROOT)

import main  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Base class: resets module-level globals before every test
# ─────────────────────────────────────────────────────────────────────────────

class _Base(unittest.TestCase):
    """Resets all module-level globals before every test."""

    _MQTT_CFG = {"basic_topic": "ha/cover", "broker": "127.0.0.1"}
    _HA_CFG = {
        "state_topic": "state",
        "command_topic": "set",
        "set_position_topic": "set_position",
        "position_topic": "position",
        "payload_open": "OPEN",
        "payload_close": "CLOSE",
        "payload_stop": "STOP",
        "availability_topic": "availability",
        "payload_available": "online",
        "payload_not_available": "offline",
    }

    def setUp(self):
        main._positions = {}
        main._active_moves = {}
        main._pending_mqtt_messages = []
        main._pending_positions = {}
        main._last_position_flush = 0
        main._log_enabled = True
        main._travel_time_default = 30.0
        main._travel_times = {}
        main._CONFIG_PREFIX = "ha/cover/config/"
        main.MQTT_CONFIG = dict(self._MQTT_CFG)
        main.HA_CONFIG = dict(self._HA_CFG)

        main.ec = MagicMock()
        main.ec.get_and_clear_remote_press.return_value = (None, None)
        main.client = MagicMock()

        # Suppress real file I/O in most tests
        patcher = patch("main._save_positions")
        self.mock_save = patcher.start()
        self.addCleanup(patcher.stop)


# ─────────────────────────────────────────────────────────────────────────────
# Position helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestPositionHelpers(_Base):
    def test_get_pos_unknown_channel_returns_50(self):
        self.assertEqual(main._get_pos(1), 50)

    def test_set_and_get_pos(self):
        main._set_pos(1, 75)
        self.assertEqual(main._get_pos(1), 75)

    def test_set_pos_clamps_above_100(self):
        main._set_pos(2, 150)
        self.assertEqual(main._get_pos(2), 100)

    def test_set_pos_clamps_below_0(self):
        main._set_pos(3, -10)
        self.assertEqual(main._get_pos(3), 0)

    def test_set_pos_exactly_0_allowed(self):
        main._set_pos(1, 0)
        self.assertEqual(main._get_pos(1), 0)

    def test_set_pos_exactly_100_allowed(self):
        main._set_pos(1, 100)
        self.assertEqual(main._get_pos(1), 100)


# ─────────────────────────────────────────────────────────────────────────────
# Channel resolution
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveChannels(_Base):
    def test_none_returns_all(self):
        self.assertEqual(main._resolve_channels(None), [1, 2, 3, 4, 5])

    def test_int_zero_returns_all(self):
        self.assertEqual(main._resolve_channels(0), [1, 2, 3, 4, 5])

    def test_str_zero_returns_all(self):
        self.assertEqual(main._resolve_channels("0"), [1, 2, 3, 4, 5])

    def test_specific_int_channel(self):
        self.assertEqual(main._resolve_channels(3), [3])

    def test_specific_str_channel(self):
        self.assertEqual(main._resolve_channels("2"), [2])

    def test_channel_5(self):
        self.assertEqual(main._resolve_channels(5), [5])


# ─────────────────────────────────────────────────────────────────────────────
# Topic parsing
# ─────────────────────────────────────────────────────────────────────────────

class TestParseString(_Base):
    def test_with_channel(self):
        base, ch, cmd = main.parse_string("home-assistant/cover/1/set")
        self.assertEqual(base, "home-assistant/cover")
        self.assertEqual(ch, "1")
        self.assertEqual(cmd, "set")

    def test_without_channel(self):
        base, ch, cmd = main.parse_string("home-assistant/cover/set")
        self.assertEqual(base, "home-assistant/cover")
        self.assertIsNone(ch)
        self.assertEqual(cmd, "set")

    def test_set_position_topic(self):
        _, ch, cmd = main.parse_string("ha/cover/3/set_position")
        self.assertEqual(ch, "3")
        self.assertEqual(cmd, "set_position")

    def test_availability_topic(self):
        base, ch, cmd = main.parse_string("ha/cover/availability")
        self.assertIsNone(ch)
        self.assertEqual(cmd, "availability")

    def test_empty_string_raises_value_error(self):
        with self.assertRaises(ValueError):
            main.parse_string("")


# ─────────────────────────────────────────────────────────────────────────────
# Travel time configuration
# ─────────────────────────────────────────────────────────────────────────────

class TestTravelTime(_Base):
    def test_default_travel_time(self):
        self.assertEqual(main._get_travel_time(1), 30.0)

    def test_per_channel_overrides_default(self):
        main._travel_times[2] = 45.0
        self.assertEqual(main._get_travel_time(2), 45.0)
        self.assertEqual(main._get_travel_time(1), 30.0)  # others unchanged

    def test_set_global_travel_time(self):
        main._set_travel_time(None, "60")
        self.assertEqual(main._travel_time_default, 60.0)

    def test_set_per_channel_travel_time(self):
        main._set_travel_time(2, "25")
        self.assertEqual(main._get_travel_time(2), 25.0)

    def test_set_below_minimum_ignored(self):
        main._set_travel_time(1, "3")   # minimum is 5 s
        self.assertEqual(main._get_travel_time(1), 30.0)

    def test_set_above_maximum_ignored(self):
        main._set_travel_time(1, "999")  # maximum is 300 s
        self.assertEqual(main._get_travel_time(1), 30.0)

    def test_set_invalid_string_ignored(self):
        main._set_travel_time(1, "abc")
        self.assertEqual(main._get_travel_time(1), 30.0)


# ─────────────────────────────────────────────────────────────────────────────
# Timed moves
# ─────────────────────────────────────────────────────────────────────────────

class TestTimedMoves(_Base):
    def test_open_calls_ec_up(self):
        main._set_pos(1, 0)
        with patch("time.time", return_value=1000.0):
            main._start_timed_move(1, 100)
        main.ec.up.assert_called_once_with(1)
        self.assertIn(1, main._active_moves)
        self.assertEqual(main._active_moves[1]["target"], 100)
        self.assertEqual(main._active_moves[1]["direction"], 1)

    def test_close_calls_ec_down(self):
        main._set_pos(1, 100)
        with patch("time.time", return_value=1000.0):
            main._start_timed_move(1, 0)
        main.ec.down.assert_called_once_with(1)
        self.assertEqual(main._active_moves[1]["direction"], -1)

    def test_opening_state_uses_qos0(self):
        main._set_pos(1, 0)
        with patch("time.time", return_value=1000.0):
            main._start_timed_move(1, 100)
        state_call = main.client.publish.call_args_list[0]
        self.assertEqual(state_call.args[1], "opening")
        self.assertEqual(state_call.kwargs["qos"], 0)

    def test_no_move_when_already_at_target(self):
        main._set_pos(1, 100)
        main._start_timed_move(1, 100)
        main.ec.up.assert_not_called()
        self.assertNotIn(1, main._active_moves)

    def test_duration_proportional_to_remaining_distance(self):
        """A half-open cover must take exactly half the travel time to fully open."""
        main._set_pos(1, 50)
        with patch("time.time", return_value=0.0):
            main._start_timed_move(1, 100)
        self.assertAlmostEqual(main._active_moves[1]["end_time"], 15.0)

    def test_cancel_estimates_intermediate_position(self):
        """After 15 s of a 30 s travel the estimated position must be 50 %."""
        main._set_pos(1, 0)
        with patch("time.time", return_value=1000.0):
            main._start_timed_move(1, 100)
        with patch("time.time", return_value=1015.0):
            main._cancel_timed_move(1)
        self.assertEqual(main._get_pos(1), 50)
        self.assertNotIn(1, main._active_moves)

    def test_cancel_inactive_channel_does_not_raise(self):
        main._cancel_timed_move(99)  # must not raise
        self.assertNotIn(99, main._active_moves)

    def test_auto_stop_after_end_time(self):
        """An expired full-close move must NOT send hardware STOP."""
        main._set_pos(1, 100)
        with patch("time.time", return_value=1000.0):
            main._start_timed_move(1, 0)    # end_time = 1030
        main.ec.down.reset_mock()
        main.client.publish.reset_mock()

        with patch("time.time", return_value=1031.0):
            main._check_timed_moves()

        main.ec.stop.assert_not_called()
        self.assertEqual(main._get_pos(1), 0)
        self.assertNotIn(1, main._active_moves)
        payloads = [c.args[1] for c in main.client.publish.call_args_list]
        self.assertIn("closed", payloads)

    def test_auto_stop_intermediate_target_sends_hardware_stop(self):
        """Intermediate target requires hardware STOP to halt movement."""
        main._set_pos(1, 0)
        with patch("time.time", return_value=1000.0):
            main._start_timed_move(1, 50)  # end_time = 1015
        main.ec.up.reset_mock()
        main.client.publish.reset_mock()

        with patch("time.time", return_value=1016.0):
            main._check_timed_moves()

        main.ec.stop.assert_called_once_with(1)
        self.assertEqual(main._get_pos(1), 50)
        self.assertNotIn(1, main._active_moves)

    def test_auto_stop_open_publishes_open(self):
        """An expired open move publishes 'open'."""
        main._set_pos(1, 0)
        with patch("time.time", return_value=1000.0):
            main._start_timed_move(1, 100)
        with patch("time.time", return_value=1031.0):
            main._check_timed_moves()
        payloads = [c.args[1] for c in main.client.publish.call_args_list]
        self.assertIn("open", payloads)

    def test_intermediate_position_published(self):
        """An in-progress move buffers the current position and does not call ec.stop."""
        main._set_pos(1, 0)
        with patch("time.time", return_value=1000.0):
            main._start_timed_move(1, 100)
        main.client.publish.reset_mock()

        with patch("time.time", return_value=1015.0):
            main._check_timed_moves()

        main.ec.stop.assert_not_called()
        self.assertIn(1, main._active_moves)
        # Position is buffered, not yet published to MQTT
        self.assertEqual(main._pending_positions.get(1), 50)
        # No position publish should have been issued directly
        position_calls = [
            c for c in main.client.publish.call_args_list
            if c.args[0].endswith("/position")
        ]
        self.assertEqual(position_calls, [])

    def test_channel_removed_from_active_moves_on_publish_error(self):
        """Channel is removed from _active_moves even when publish raises OSError.
        Guards the try/finally fix that prevents an infinite ec.stop loop."""
        main._set_pos(1, 100)
        with patch("time.time", return_value=1000.0):
            main._start_timed_move(1, 0)
        main.client.publish.reset_mock()
        main.client.publish.side_effect = OSError("ECONNRESET")

        with patch("time.time", return_value=1031.0):
            with self.assertRaises(OSError):
                main._check_timed_moves()

        # try/finally must have cleaned up despite the publish error
        self.assertNotIn(1, main._active_moves)

    def test_two_concurrent_moves_both_completed(self):
        """Two simultaneously active moves are both finalised correctly."""
        main._set_pos(1, 100)
        main._set_pos(2, 0)
        with patch("time.time", return_value=1000.0):
            main._start_timed_move(1, 0)
            main._start_timed_move(2, 100)

        with patch("time.time", return_value=1031.0):
            main._check_timed_moves()

        self.assertNotIn(1, main._active_moves)
        self.assertNotIn(2, main._active_moves)
        self.assertEqual(main._get_pos(1), 0)
        self.assertEqual(main._get_pos(2), 100)


# ─────────────────────────────────────────────────────────────────────────────
# External activity (physical remote via IRQ)
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckExternalActivity(_Base):
    def test_up_press_starts_external_move(self):
        main._set_pos(1, 0)
        main.ec.get_and_clear_remote_press.return_value = ("up", 1)
        with patch("time.time", return_value=1000.0):
            main._check_external_activity()
        self.assertIn(1, main._active_moves)
        self.assertEqual(main._active_moves[1]["target"], 100)

    def test_down_press_starts_external_move(self):
        main._set_pos(1, 100)
        main.ec.get_and_clear_remote_press.return_value = ("down", 1)
        with patch("time.time", return_value=1000.0):
            main._check_external_activity()
        self.assertIn(1, main._active_moves)
        self.assertEqual(main._active_moves[1]["target"], 0)

    def test_external_move_start_uses_qos0(self):
        main._set_pos(1, 0)
        main.ec.get_and_clear_remote_press.return_value = ("up", 1)
        with patch("time.time", return_value=1000.0):
            main._check_external_activity()
        state_calls = [
            c for c in main.client.publish.call_args_list
            if c.args[0].endswith("/state")
        ]
        self.assertEqual(state_calls[0].args[1], "opening")
        self.assertEqual(state_calls[0].kwargs["qos"], 0)

    def test_stop_press_cancels_active_move(self):
        main._set_pos(2, 0)
        with patch("time.time", return_value=1000.0):
            main._start_external_move(2, 100)
        main.ec.get_and_clear_remote_press.return_value = ("stop", 2)
        with patch("time.time", return_value=1015.0):
            main._check_external_activity()
        self.assertNotIn(2, main._active_moves)
        self.assertEqual(main._get_pos(2), 50)

    def test_stop_press_publishes_stopped(self):
        main._set_pos(1, 0)
        with patch("time.time", return_value=0.0):
            main._start_external_move(1, 100)
        main.client.publish.reset_mock()
        main.ec.get_and_clear_remote_press.return_value = ("stop", 1)
        with patch("time.time", return_value=15.0):
            main._check_external_activity()
        payloads = [c.args[1] for c in main.client.publish.call_args_list]
        self.assertIn("stopped", payloads)

    def test_stop_without_active_move_publishes_nothing(self):
        """FB STOP when the cover is already stopped must not publish state/position."""
        main.ec.get_and_clear_remote_press.return_value = ("stop", 1)
        main._check_external_activity()
        # Log topic may be published; state/position must not be
        non_log_calls = [
            c for c in main.client.publish.call_args_list
            if not c.args[0].endswith("/log")
        ]
        self.assertEqual(non_log_calls, [])

    def test_irq_channel_takes_priority_over_software_channel(self):
        """A valid IRQ channel must override the current software-tracked channel."""
        main.ec.check_channel.return_value = 3
        main._set_pos(2, 0)
        main.ec.get_and_clear_remote_press.return_value = ("up", 2)
        with patch("time.time", return_value=0.0):
            main._check_external_activity()
        self.assertIn(2, main._active_moves)
        self.assertNotIn(3, main._active_moves)
        self.assertEqual(main.ec._selected_ch, 2)

    def test_irq_channel_minus1_falls_back_to_check_channel(self):
        """irq_ch == -1 (undetermined) → software-tracked channel is used."""
        main.ec.check_channel.return_value = 1
        main._set_pos(1, 0)
        main.ec.get_and_clear_remote_press.return_value = ("up", -1)
        with patch("time.time", return_value=0.0):
            main._check_external_activity()
        self.assertIn(1, main._active_moves)

    def test_no_press_does_nothing(self):
        main.ec.get_and_clear_remote_press.return_value = (None, None)
        main._check_external_activity()
        main.client.publish.assert_not_called()

    def test_up_press_channel_0_starts_all_channels(self):
        """Channel 0 means all channels selected → all 5 moves are started."""
        for ch in range(1, 6):
            main._set_pos(ch, 0)
        main.ec.get_and_clear_remote_press.return_value = ("up", 0)
        with patch("time.time", return_value=0.0):
            main._check_external_activity()
        for ch in range(1, 6):
            self.assertIn(ch, main._active_moves)


# ─────────────────────────────────────────────────────────────────────────────
# MQTT callback (sub_cb)
# ─────────────────────────────────────────────────────────────────────────────

class TestSubCb(_Base):
    def _call(self, topic: str, payload: str):
        main.sub_cb(topic.encode(), payload.encode())
        main._process_pending_mqtt_messages()

    def test_sub_cb_only_queues_message(self):
        main.sub_cb(b"ha/cover/1/set", b"OPEN")
        self.assertEqual(main._pending_mqtt_messages, [("ha/cover/1/set", "OPEN")])
        main.ec.up.assert_not_called()
        main._process_pending_mqtt_messages()
        main.ec.up.assert_called_once_with(1)

    def test_open_command(self):
        main._set_pos(1, 0)
        with patch("time.time", return_value=0.0):
            self._call("ha/cover/1/set", "OPEN")
        main.ec.up.assert_called_once_with(1)
        self.assertIn(1, main._active_moves)

    def test_close_command(self):
        main._set_pos(1, 100)
        with patch("time.time", return_value=0.0):
            self._call("ha/cover/1/set", "CLOSE")
        main.ec.down.assert_called_once_with(1)
        self.assertIn(1, main._active_moves)

    def test_stop_command_calls_ec_stop(self):
        main._set_pos(1, 50)
        with patch("time.time", return_value=0.0):
            main._start_timed_move(1, 100)
        self._call("ha/cover/1/set", "STOP")
        main.ec.stop.assert_called_with(1)
        self.assertNotIn(1, main._active_moves)

    def test_stop_command_also_fires_without_active_move(self):
        """HA STOP always triggers hardware stop – shutter may run from physical remote."""
        main._set_pos(1, 0)
        self._call("ha/cover/1/set", "STOP")
        main.ec.stop.assert_called_with(1)
        self.assertNotIn(1, main._active_moves)

    def test_set_position_command(self):
        main._set_pos(1, 0)
        with patch("time.time", return_value=0.0):
            self._call("ha/cover/1/set_position", "75")
        self.assertIn(1, main._active_moves)
        self.assertEqual(main._active_moves[1]["target"], 75)

    def test_set_position_out_of_range_ignored(self):
        self._call("ha/cover/1/set_position", "150")
        self.assertNotIn(1, main._active_moves)

    def test_set_position_invalid_string_ignored(self):
        self._call("ha/cover/1/set_position", "abc")
        self.assertNotIn(1, main._active_moves)

    def test_own_state_topic_filtered(self):
        self._call("ha/cover/1/state", "open")
        main.ec.up.assert_not_called()

    def test_own_position_topic_filtered(self):
        self._call("ha/cover/1/position", "80")
        main.ec.up.assert_not_called()

    def test_own_availability_topic_filtered(self):
        self._call("ha/cover/availability", "online")
        main.ec.up.assert_not_called()

    def test_log_topic_filtered(self):
        self._call("ha/cover/log", "some message")
        main.ec.up.assert_not_called()

    def test_open_all_channels(self):
        """A command without a channel number targets all 5 channels."""
        for ch in range(1, 6):
            main._set_pos(ch, 0)
        with patch("time.time", return_value=0.0):
            self._call("ha/cover/set", "OPEN")
        for ch in range(1, 6):
            self.assertIn(ch, main._active_moves)

    def test_stop_command_publishes_stopped(self):
        """HA STOP publishes 'stopped' and the current position."""
        main._set_pos(1, 50)
        with patch("time.time", return_value=0.0):
            main._start_timed_move(1, 100)
        main.client.publish.reset_mock()
        self._call("ha/cover/1/set", "STOP")
        payloads = [c.args[1] for c in main.client.publish.call_args_list]
        self.assertIn("stopped", payloads)

    def test_stop_command_without_active_move_publishes_stopped(self):
        """Idle HA STOP must still publish state=stopped."""
        main._set_pos(1, 0)
        main.client.publish.reset_mock()
        self._call("ha/cover/1/set", "STOP")
        state_calls = [
            c for c in main.client.publish.call_args_list
            if c.args[0].endswith("/state")
        ]
        self.assertEqual(len(state_calls), 1)
        self.assertEqual(state_calls[0].args[1], "stopped")


# ─────────────────────────────────────────────────────────────────────────────
# Config messages
# ─────────────────────────────────────────────────────────────────────────────

class TestHandleConfigMessage(_Base):
    def test_global_travel_time(self):
        main._handle_config_message("ha/cover/config/travel_time", "45")
        self.assertEqual(main._travel_time_default, 45.0)

    def test_per_channel_travel_time(self):
        main._handle_config_message("ha/cover/config/3/travel_time", "20")
        self.assertEqual(main._get_travel_time(3), 20.0)
        self.assertEqual(main._get_travel_time(1), 30.0)  # others unchanged

    def test_unknown_key_ignored(self):
        main._handle_config_message("ha/cover/config/unknown", "value")
        self.assertEqual(main._travel_time_default, 30.0)  # no crash, no change

    def test_log_enabled_on(self):
        main._log_enabled = False
        main._handle_config_message("ha/cover/config/log_enabled", "on")
        self.assertTrue(main._log_enabled)

    def test_log_enabled_off(self):
        main._log_enabled = True
        main._handle_config_message("ha/cover/config/log_enabled", "off")
        self.assertFalse(main._log_enabled)


# ─────────────────────────────────────────────────────────────────────────────
# Position persistence (direct I/O tests – no _save_positions mock)
# ─────────────────────────────────────────────────────────────────────────────

class TestPositionPersistence(unittest.TestCase):
    """Tests _load_positions / _save_positions directly against mocked file I/O."""

    def setUp(self):
        main._positions = {}

    def test_load_returns_none_when_file_missing(self):
        with patch("builtins.open", side_effect=OSError("no file")):
            result = main._load_positions()
        self.assertIsNone(result)

    def test_load_returns_none_on_invalid_json(self):
        with patch("builtins.open", mock_open(read_data="not valid json %%")):
            result = main._load_positions()
        self.assertIsNone(result)

    def test_load_clamps_out_of_range_values(self):
        data = json.dumps({"1": 150, "2": -20, "3": 50})
        with patch("builtins.open", mock_open(read_data=data)):
            result = main._load_positions()
        self.assertEqual(result["1"], 100)
        self.assertEqual(result["2"], 0)
        self.assertEqual(result["3"], 50)

    def test_load_returns_correct_values(self):
        data = json.dumps({"1": 75, "5": 0})
        with patch("builtins.open", mock_open(read_data=data)):
            result = main._load_positions()
        self.assertEqual(result["1"], 75)
        self.assertEqual(result["5"], 0)

    def test_save_writes_valid_json(self):
        main._set_pos(1, 75)
        main._set_pos(2, 0)
        m = mock_open()
        with patch("builtins.open", m):
            main._save_positions()
        handle = m()
        written = "".join(c.args[0] for c in handle.write.call_args_list)
        data = json.loads(written)
        self.assertEqual(data["1"], 75)
        self.assertEqual(data["2"], 0)

    def test_save_does_not_raise_on_write_error(self):
        """An OSError during write must not crash the application."""
        main._set_pos(1, 50)
        with patch("builtins.open", side_effect=OSError("flash full")):
            main._save_positions()  # must not raise


if __name__ == "__main__":
    unittest.main()

