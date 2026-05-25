import machine
import time
import ure as re
from umqtt.simple import MQTTClient
from easycontrol import Easycontrol
from machine import Timer


CONFIG = {}
HA_CONFIG = {}
MQTT_CONFIG = {}

ec = None
client = None

# ── Position tracking ─────────────────────────────────────────────────────────

NUM_CHANNELS = 5

# Travel time per channel (seconds for full 0→100 % travel).
# _travel_time_default is the fallback when no per-channel value is set.
# Both are overridden live via MQTT config topics from Home Assistant.
_travel_time_default = 30.0
_travel_times = {}   # channel (int) → float

# Prefix for all config topics, e.g. "home-assistant/cover/config/"
# Global default : <prefix>travel_time
# Per channel    : <prefix><ch>/travel_time
_CONFIG_PREFIX = None


def _get_travel_time(channel):
    return _travel_times.get(channel, _travel_time_default)

# Estimated position per channel: 0 (closed) – 100 (open)
_positions = {}

POSITIONS_FILE = "/positions.json"

# Active timed moves: channel (int) → {end_time, target, start_pos, start_time, direction}
_active_moves = {}

# Last channel seen on hardware – used to detect physical remote activity
_last_channel = None


def _load_positions():
    """Load persisted positions from flash. Returns None if not available."""
    import ujson as json
    try:
        with open(POSITIONS_FILE) as f:
            data = json.loads(f.read())
            return {str(k): max(0, min(100, int(v))) for k, v in data.items()}
    except (OSError, ValueError):
        return None


def _save_positions():
    """Persist current positions to flash."""
    import ujson as json
    try:
        with open(POSITIONS_FILE, "w") as f:
            f.write(json.dumps(_positions))
    except OSError as e:
        print("Could not save positions: {}".format(e))


def _get_pos(channel):
    return _positions.get(str(channel), 50)


def _set_pos(channel, pos):
    _positions[str(channel)] = max(0, min(100, int(pos)))


def _resolve_channels(channel):
    """Return list of channel ints. None / '0' / 0 → all channels."""
    if channel is None or channel == 0 or channel == '0':
        return list(range(1, NUM_CHANNELS + 1))
    return [int(channel)]


# ── MQTT publish helpers ──────────────────────────────────────────────────────

def _pub_state(channel, state):
    topic = MQTT_CONFIG['basic_topic'] + "/" + str(channel) + "/" + HA_CONFIG['state_topic']
    client.publish(topic, state, qos=1)


def _pub_position(channel, pos):
    topic = MQTT_CONFIG['basic_topic'] + "/" + str(channel) + "/" + HA_CONFIG.get('position_topic', 'position')
    client.publish(topic, str(pos), qos=1)


# ── Timed movement ────────────────────────────────────────────────────────────

def _start_timed_move(channel, target):
    """Press UP/DOWN for a calculated duration, then auto-stop."""
    current = _get_pos(channel)
    delta = abs(target - current)
    if delta == 0:
        return
    direction = 1 if target > current else -1
    duration = _get_travel_time(channel) * delta / 100.0

    if direction > 0:
        ec.up(channel)
        _pub_state(channel, "opening")
    else:
        ec.down(channel)
        _pub_state(channel, "closing")

    now = time.time()
    _active_moves[channel] = {
        "end_time": now + duration,
        "target": target,
        "start_pos": current,
        "start_time": now,
        "direction": direction,
    }


def _cancel_timed_move(channel):
    """Cancel an active move and estimate the position reached so far."""
    if channel not in _active_moves:
        return
    move = _active_moves.pop(channel)
    elapsed = time.time() - move["start_time"]
    moved = int(elapsed / _get_travel_time(channel) * 100)
    estimated = move["start_pos"] + move["direction"] * moved
    _set_pos(channel, estimated)
    _save_positions()


def _check_timed_moves():
    """Call from main loop: auto-stop channels that have reached their target time,
    and publish intermediate position updates so Home Assistant shows movement animation."""
    done = []
    try:
        for ch, move in _active_moves.items():
            now = time.time()
            if now >= move["end_time"]:
                ec.stop(ch)
                _set_pos(ch, move["target"])
                # Mark as done BEFORE publishing so an OSError during publish
                # does not leave the channel stuck in _active_moves forever.
                done.append(ch)
                target = move["target"]
                if target >= 100:
                    final = "open"
                elif target <= 0:
                    final = "closed"
                else:
                    final = "stopped"
                _pub_state(ch, final)
                _pub_position(ch, target)
            else:
                # Publish current estimated position every loop tick → HA animation
                elapsed = now - move["start_time"]
                travel = _get_travel_time(ch)
                moved = elapsed / travel * 100.0
                current = max(0, min(100, int(move["start_pos"] + move["direction"] * moved)))
                _pub_position(ch, current)
    finally:
        # Always clean up completed channels, even if a publish raised an exception.
        for ch in done:
            _active_moves.pop(ch, None)
        if done:
            _save_positions()


def _start_external_move(channel, target):
    """Track a remote-initiated move and publish state/position to HA.
    Does NOT trigger any hardware – the motor is already running.
    """
    current = _get_pos(channel)
    delta = abs(target - current)
    if delta == 0:
        return
    direction = 1 if target > current else -1
    duration = _get_travel_time(channel) * delta / 100.0
    if direction > 0:
        _pub_state(channel, "opening")
    else:
        _pub_state(channel, "closing")
    now = time.time()
    _active_moves[channel] = {
        "end_time": now + duration,
        "target": target,
        "start_pos": current,
        "start_time": now,
        "direction": direction,
    }
    _log("External move ch{}: {} → {}".format(channel, current, target))


def _check_external_activity():
    """Detect physical remote usage via falling-edge IRQs on UP/DOWN/STOP pins.

    UP/DOWN start position tracking toward 100/0 without triggering hardware.
    STOP cancels any ongoing tracking and publishes the estimated position.
    The SELECT pin is intentionally ignored: browsing channels without pressing
    UP/DOWN/STOP causes no state change.
    """
    global _last_channel

    # ── IRQ-based button press ────────────────────────────────────────────────
    pressed, irq_ch = ec.get_and_clear_remote_press()
    if pressed is None:
        return

    # The IRQ reads the channel LED at the exact moment of the button press.
    # Fall back to _last_channel if the IRQ reading was indeterminate.
    if irq_ch is not None and irq_ch >= 0:
        ch_sel = irq_ch
        _last_channel = irq_ch  # keep _last_channel in sync
    else:
        ch_sel = _last_channel if (_last_channel is not None and _last_channel >= 0) else None

    _log("IRQ detected: {} ch={}".format(pressed, ch_sel))
    channels = _resolve_channels(ch_sel)
    if pressed == 'up':
        for ch in channels:
            _cancel_timed_move(ch)
            _start_external_move(ch, 100)
    elif pressed == 'down':
        for ch in channels:
            _cancel_timed_move(ch)
            _start_external_move(ch, 0)
    elif pressed == 'stop':
        stopped = []
        for ch in channels:
            if ch in _active_moves:
                _cancel_timed_move(ch)
                stopped.append(ch)
        for ch in stopped:
            _pub_state(ch, "stopped")
            _pub_position(ch, _get_pos(ch))
        if stopped:
            _save_positions()


# ── Config ────────────────────────────────────────────────────────────────────

def load_config():
    import ujson as json
    try:
        with open("/config.json") as f:
            config = json.loads(f.read())
    except (OSError, ValueError):
        print("Couldn't load /config.json")
    else:
        CONFIG.update(config)
        print("Loaded config from /config.json")


# ── Topic parsing ─────────────────────────────────────────────────────────────

def parse_string(s):
    pattern = r'^(.*?)(?:/(\d+))?/([^/]+)$'
    match = re.match(pattern, s)
    if match:
        return match.group(1), match.group(2), match.group(3)
    raise ValueError("String does not match the expected format")


# ── Travel time config ───────────────────────────────────────────────────────

def _set_travel_time(channel, msg):
    """Update travel time for one channel (int) or the global default (None)."""
    global _travel_time_default
    try:
        t = float(msg)
        if not (5 <= t <= 300):
            print("travel_time out of range (5-300): {}".format(msg))
            return
        if channel is None:
            _travel_time_default = t
            _log("travel_time default updated to {}s".format(t))
        else:
            _travel_times[channel] = t
            _log("travel_time ch{} updated to {}s".format(channel, t))
    except ValueError:
        _log("Invalid travel_time: {}".format(msg))


def _handle_config_message(topic, msg):
    """Dispatch config/... topics to the right handler."""
    suffix = topic[len(_CONFIG_PREFIX):]  # e.g. "travel_time" or "3/travel_time"
    if suffix == "travel_time":
        _set_travel_time(None, msg)
    else:
        parts = suffix.split("/")
        if len(parts) == 2 and parts[1] == "travel_time":
            try:
                ch = int(parts[0])
                if 1 <= ch <= NUM_CHANNELS:
                    _set_travel_time(ch, msg)
            except ValueError:
                pass


# ── MQTT callbacks ────────────────────────────────────────────────────────────

def sub_cb(topic_raw, msg_raw):
    msg = msg_raw.decode('utf-8')
    topic = topic_raw.decode('utf-8')

    # Ignore topics published by this device to avoid echo loops
    _outbound = (
        '/' + HA_CONFIG.get('state_topic', 'state'),
        '/' + HA_CONFIG.get('position_topic', 'position'),
        '/' + HA_CONFIG.get('availability_topic', 'availability'),
        '/log',
    )
    for suffix in _outbound:
        if topic.endswith(suffix):
            return

    # Config updates (not channel commands)
    if topic.startswith(_CONFIG_PREFIX):
        _handle_config_message(topic, msg)
        return

    try:
        part1, channel_str, command = parse_string(topic)
    except ValueError as e:
        print(e)
        return

    _log("topic: {}, channel: {}, command: {}, payload: {}".format(
        part1, channel_str, command, msg))

    channels = _resolve_channels(channel_str)

    if command == HA_CONFIG['command_topic']:
        if msg == HA_CONFIG['payload_open']:
            for ch in channels:
                _cancel_timed_move(ch)
                _start_timed_move(ch, 100)

        elif msg == HA_CONFIG['payload_close']:
            for ch in channels:
                _cancel_timed_move(ch)
                _start_timed_move(ch, 0)

        elif msg == HA_CONFIG['payload_stop']:
            for ch in channels:
                _cancel_timed_move(ch)
                ec.stop(ch)
                _pub_state(ch, "stopped")
                _pub_position(ch, _get_pos(ch))

    elif command == HA_CONFIG.get('set_position_topic', 'set_position'):
        try:
            target = int(msg)
            if 0 <= target <= 100:
                for ch in channels:
                    _cancel_timed_move(ch)
                    _start_timed_move(ch, target)
            else:
                print("Position out of range (0-100): {}".format(msg))
        except ValueError:
            _log("Invalid position payload: {}".format(msg))


def _log(msg):
    """Print to serial and publish to MQTT log topic (if connected)."""
    print(msg)
    if client is not None:
        try:
            client.publish(MQTT_CONFIG['basic_topic'] + "/log", msg, qos=0)
        except Exception:
            pass


def _mqtt_reconnect():
    """Reconnect to the MQTT broker and re-subscribe.
    Resets the device if the reconnect attempt fails.
    """
    print("MQTT connection lost, reconnecting ...")
    try:
        client.disconnect()
    except Exception:
        pass
    time.sleep(5)
    try:
        client.connect()
        client.set_callback(sub_cb)
        client.subscribe(MQTT_CONFIG['basic_topic'] + "/#")
        # Re-publish current state so HA is up to date.
        client.publish(
            MQTT_CONFIG['basic_topic'] + "/" + HA_CONFIG['availability_topic'],
            HA_CONFIG['payload_available'], qos=1)
        for ch in range(1, NUM_CHANNELS + 1):
            pos = _get_pos(ch)
            if pos >= 100:
                state = "open"
            elif pos <= 0:
                state = "closed"
            else:
                state = "stopped"
            _pub_state(ch, state)
            _pub_position(ch, pos)
        print("Reconnected to {}".format(MQTT_CONFIG['broker']))
    except Exception as e:
        print("Reconnect failed: {}".format(e))
        reset()


def send_heartbeat(t):
    print("publish availability message")
    try:
        client.publish(
            MQTT_CONFIG['basic_topic'] + "/" + HA_CONFIG['availability_topic'],
            HA_CONFIG['payload_available'], qos=1)
    except OSError:
        _mqtt_reconnect()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global ec, MQTT_CONFIG, HA_CONFIG, client, _travel_time_default, _CONFIG_PREFIX, _last_channel

    MQTT_CONFIG = CONFIG['mqtt']
    HA_CONFIG = CONFIG['ha']
    ec_cfg = CONFIG.get('easycontrol', {})

    # Load fallback travel times from config.json
    _travel_time_default = float(ec_cfg.get('travel_time', 30))
    for ch in range(1, NUM_CHANNELS + 1):
        key = 'travel_time_' + str(ch)
        if key in ec_cfg:
            _travel_times[ch] = float(ec_cfg[key])

    _CONFIG_PREFIX = MQTT_CONFIG['basic_topic'] + '/config/'

    ec = Easycontrol(CONFIG["easycontrol"])
    ec.init()
    _last_channel = ec.check_channel()  # baseline for remote-activity detection

    client = MQTTClient(
        MQTT_CONFIG['client_id'],
        MQTT_CONFIG['broker'],
        user=MQTT_CONFIG.get('username'),
        password=MQTT_CONFIG.get('password'),
    )
    client.set_callback(sub_cb)
    client.connect()
    _log("Connected to {}".format(MQTT_CONFIG['broker']))

    client.subscribe(MQTT_CONFIG['basic_topic'] + "/#")
    _log("Subscribed to {}/#".format(MQTT_CONFIG['basic_topic']))
    # _TRAVEL_TIME_TOPIC is already covered by the wildcard subscription above.
    # The retained value from the broker is delivered automatically on connect.

    # Restore persisted positions; fall back to 50 (unknown) so both OPEN and CLOSE always work
    send_heartbeat(None)
    saved = _load_positions()
    for ch in range(1, NUM_CHANNELS + 1):
        pos = saved.get(str(ch), 50) if saved is not None else 50
        _set_pos(ch, pos)
        if pos >= 100:
            state = "open"
        elif pos <= 0:
            state = "closed"
        else:
            state = "stopped"
        _pub_state(ch, state)
        _pub_position(ch, pos)

    tim1 = Timer(1)
    tim1.init(period=60000, mode=Timer.PERIODIC, callback=send_heartbeat)

    while True:
        try:
            client.check_msg()
            _check_timed_moves()
            _check_external_activity()
        except OSError as e:
            print("Connection error: {}".format(e))
            _mqtt_reconnect()
        time.sleep(1)


def reset():
    print("Resetting...")
    time.sleep(5)
    machine.reset()


if __name__ == '__main__':
    try:
        load_config()
        main()
    except OSError as e:
        print("Error: " + str(e))
        reset()
