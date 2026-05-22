#!/usr/bin/env python3
"""
run_main.py – run main.py on a Mac/PC
=======================================
Injects MicroPython stubs (stubs/) into the module search path so that all
hardware-specific imports are intercepted.  GPIO operations are only printed
to the console; MQTT connects to the real broker from config-simulator.json.

Usage:
    python run_main.py

main.py is NOT modified by this script.
"""

import builtins
import os
import signal
import sys

# ── 1. Add stubs and project directory to sys.path ──────────────────────────

_ROOT = os.path.dirname(os.path.abspath(__file__))
_STUBS = os.path.join(_ROOT, "stubs")

sys.path.insert(0, _STUBS)   # stubs first so they shadow the real modules
sys.path.insert(1, _ROOT)    # so that easycontrol.py can be found

# ── 2. Redirect ESP32 absolute paths (/config.json) to local files ─────────

_real_open = builtins.open


def _patched_open(path, *args, **kwargs):
    """Redirects /config.json → <project folder>/config-simulator.json."""
    if isinstance(path, str) and path == "/config.json":
        path = os.path.join(_ROOT, "config-simulator.json")
    elif isinstance(path, str) and path.startswith("/") and not os.path.exists(path):
        local = os.path.join(_ROOT, path.lstrip("/"))
        if os.path.exists(local):
            path = local
    return _real_open(path, *args, **kwargs)


builtins.open = _patched_open

# ── 3. Load and run main.py ──────────────────────────────────────────────────

import main  # noqa: E402  (stubs must be set up first)

print("[sim]  Loading config …")
main.load_config()
# Ensure the client ID never collides with the real ESP32
if not main.CONFIG["mqtt"]["client_id"].endswith("_sim"):
    main.CONFIG["mqtt"]["client_id"] += "_sim"

print("[sim]  Starting main loop …  (Ctrl+C to quit)")
print()

try:
    main.main()
except KeyboardInterrupt:
    print("\n[sim]  Stopped.")
