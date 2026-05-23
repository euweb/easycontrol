"""
stubs/easycontrol.py – Easycontrol hardware simulation
=======================================================
Replaces the real easycontrol.py when running on a PC.

Channel rotation (simulates the select button):
  1 → 2 → 3 → 4 → 5 → 0 (all simultaneously) → 1 → 2 → …

up/down/stop print the action to the console
instead of driving GPIO pins.
"""

# Sequence the real controller cycles through when clicking select
_SEQUENCE = [1, 2, 3, 4, 5, 0]


def _label(channel: int) -> str:
    return "ALL" if channel == 0 else f"ch{channel}"


class Easycontrol:

    def __init__(self, config):
        self._config = config
        self._idx = 0          # current index in _SEQUENCE → channel 1 is active

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def init(self):
        self._idx = 0
        print(f"[ec]  init  (simulated)  –  active: {_label(_SEQUENCE[self._idx])}")

    # ── Interne Helfer ────────────────────────────────────────────────────────

    def check_channel(self) -> int:
        """Returns the currently active channel (0 = all)."""
        return _SEQUENCE[self._idx]

    def _click_select(self):
        """Simulates one press of the select button."""
        self._idx = (self._idx + 1) % len(_SEQUENCE)
        print(f"[ec]  select click  →  {_label(_SEQUENCE[self._idx])} active")

    def select(self, channel):
        """Clicks select until the desired channel is active."""
        if channel is None:
            channel = 0
        channel = int(channel)

        attempts = 0
        while self.check_channel() != channel and attempts < len(_SEQUENCE):
            self._click_select()
            attempts += 1

        if self.check_channel() == channel:
            print(f"[ec]  selected: {_label(channel)}")
        else:
            print(f"[ec]  WARNING: {_label(channel)} not reachable")

    # ── Befehle ───────────────────────────────────────────────────────────────

    def up(self, channel):
        self.select(channel)
        print(f"[ec]  {_label(int(channel or 0))}: UP   ▲")

    def down(self, channel):
        self.select(channel)
        print(f"[ec]  {_label(int(channel or 0))}: DOWN ▼")

    def stop(self, channel):
        self.select(channel)
        print(f"[ec]  {_label(int(channel or 0))}: STOP ■")

    def check_command_pins(self):
        """Stub: physical remote buttons are never pressed in simulation."""
        return set()

    def get_and_clear_remote_press(self):
        """Stub: no physical remote in simulation."""
        return None
