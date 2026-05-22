"""
MicroPython `machine` stub for CPython (desktop/test)
======================================================
Pin is a silent no-op stub – the actual simulation
runs in stubs/easycontrol.py.
Only Timer and reset() are still required.
"""

import threading


def reset():
    print("[hw]  machine.reset() (stub, no-op)")


class Pin:
    """Silent stub – no longer used by stubs/easycontrol.py,
    kept for any direct Pin imports in main.py."""
    OPEN_DRAIN = "OPEN_DRAIN"
    IN = "IN"
    OUT = "OUT"

    def __init__(self, id, mode=None, value=None):
        self._value = value if value is not None else 0

    def off(self):
        self._value = 0

    def on(self):
        self._value = 1

    def value(self, v=None):
        if v is None:
            return self._value
        self._value = v


class Timer:
    PERIODIC = "PERIODIC"
    ONE_SHOT = "ONE_SHOT"

    def __init__(self, id=-1):
        self._id = id
        self._stop = threading.Event()
        self._thread = None

    def init(self, period, mode=None, callback=None):
        if mode is None:
            mode = Timer.PERIODIC
        self._stop.clear()
        interval = period / 1000.0

        def _loop():
            while not self._stop.wait(interval):
                if callback:
                    callback(self)
                if mode == Timer.ONE_SHOT:
                    break

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def deinit(self):
        self._stop.set()
