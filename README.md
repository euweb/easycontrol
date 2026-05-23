# easycontrol

Control Roto roof window covers using an Arduino Nano ESP32 and an EasyControl remote.  
The ESP32 connects to a MQTT broker via Wi-Fi and can be integrated into Home Assistant.

Background information on wiring the remote control:  
https://wiki.fhem.de/wiki/Dachfenster-Roll%C3%A4den_von_Roto_%C3%BCber_Handsender_ansteuern

## Requirements

- Arduino Nano ESP32 with MicroPython firmware
- MQTT broker (e.g. Mosquitto running as an LXC container on Proxmox)
- Home Assistant (optional)

## Files

| File | Description |
|---|---|
| `boot.py` | Runs on boot, establishes the Wi-Fi connection |
| `main.py` | Main logic: MQTT connection and command handling |
| `easycontrol.py` | Class for controlling the GPIO pins of the remote |
| `config.json.template` | MQTT and Home Assistant configuration |
| `wlan_config.py.template` | Wi-Fi credentias |

## Installation

1. **Configure Wi-Fi**  
   Copy `wlan_config.py.template` to `wlan_config.py` and enter your credentials:
   ```python
   WIFI_SSID = "your-network"
   WIFI_PASSWORD = "your-password"
   ```

2. **Configure MQTT**  
   Copy `config.json.template` to `config.json` and adjust the values:
   ```json
   "mqtt": {
       "client_id": "esp32_my_device",
       "basic_topic": "home-assistant/cover",
       "broker": "mqtt01.example.com",
       "username": "mqtt_user",
       "password": "mqtt_password"
   }
   ```

3. **Upload files to the ESP32**  
   Use [Arduino Lab for MicroPython](https://labs.arduino.cc/en/labs/micropython) to copy all `.py` files and `config.json` to the device.

4. **Restart the device** — `boot.py` connects to Wi-Fi, then `main.py` establishes the MQTT connection.

## Configuration

### `config.json`

```json
{
    "mqtt": {
        "client_id": "esp32_my_device",     // unique client ID
        "basic_topic": "home-assistant/cover",
        "broker": "mqtt01.example.com",      // FQDN or IP of the broker
        "username": "mqtt_user",
        "password": "mqtt_password"
    },
    "ha": {
        "state_topic": "state",
        "command_topic": "set",
        "payload_open": "OPEN",
        "payload_close": "CLOSE",
        "payload_stop": "STOP",
        "availability_topic": "availability",
        "payload_available": "online",
        "payload_not_available": "offline"
    },
    "easycontrol": {
        "select_pin": 8,
        "up_pin": 5,
        "down_pin": 7,
        "stop_pin": 6,
        "ch1_pin": 9,
        "ch2_pin": 10,
        "ch3_pin": 17,
        "ch4_pin": 18,
        "ch5_pin": 21
    }
}
```

### MQTT Topics

The device subscribes to `<basic_topic>/#`. Commands are sent to the following topics:

| Topic | Description |
|---|---|
| `home-assistant/cover/<channel>/set` | Command for a specific channel (OPEN / CLOSE / STOP) |
| `home-assistant/cover/set` | Command for all channels |
| `home-assistant/cover/availability` | Availability heartbeat (online / offline, every minute) |

## Testing MQTT

```bash
# Listen to all messages
mosquitto_sub -h <broker> -p 1883 -t "home-assistant/#" -u <user> -P <password> -v

# Send a command (open channel 1)
mosquitto_pub -h <broker> -p 1883 -t "home-assistant/cover/1/set" -u <user> -P <password> -m "OPEN"
```

## Position tracking

The ESP32 tracks the estimated position (0 = fully closed, 100 = fully open) of each channel based on the configured travel time.

### Persistence across reboots

Positions are saved to `/positions.json` on the ESP32 flash whenever a motor movement finishes or is stopped.  
On the next boot the saved positions are restored and published to Home Assistant — no manual re-calibration needed.

**First boot (no saved file):** all channels are reported as `stopped` at position 50, so both OPEN and CLOSE commands always work regardless of the actual shutter position.

### Physical remote detection

The UP, DOWN, and STOP pins are shared open-drain lines between the ESP32 and the EasyControl remote — no additional wiring is needed.  
Falling-edge interrupts (IRQs) fire the instant the remote pulls a line low, which is much faster and more reliable than polling.

| Remote action | ESP32 behaviour |
|---|---|
| UP pressed | Publishes `opening`, tracks position toward 100 using `travel_time` |
| DOWN pressed | Publishes `closing`, tracks position toward 0 using `travel_time` |
| STOP pressed | Cancels tracking, estimates intermediate position, publishes `stopped` |
| Timer expires (motor at end stop) | Sends STOP command (harmless if motor has already stopped), publishes `open`/`closed` |

To prevent the ESP32's own SELECT cycling from triggering spurious IRQs, all three IRQs are suppressed for the entire duration of `select() + command()` and re-enabled afterwards.

> **Limitation:** If the remote is already on the same channel the ESP32 last used and a button is pressed without first pressing SELECT, the position will still be tracked — UP always targets 100, DOWN always targets 0. A manual STOP will produce the correct intermediate position estimate.

### Travel time calibration

The travel time (seconds for a full open/close cycle) can be set per channel via MQTT — the value is retained by the broker and restored automatically on reconnect:

| Topic | Payload | Effect |
|---|---|---|
| `home-assistant/cover/config/travel_time` | `30` | Default for all channels |
| `home-assistant/cover/config/<ch>/travel_time` | `25` | Override for channel `<ch>` |

## MQTT reconnect

If the broker drops the connection (e.g. due to a network hiccup or broker restart), the ESP32 automatically reconnects:

1. Waits 5 seconds, then calls `client.connect()` and re-subscribes.
2. Re-publishes the availability message and the current state/position of all channels so Home Assistant is immediately up to date.
3. If the reconnect itself fails, the device performs a soft reset (`machine.reset()`).

### Travel time calibration

The travel time (seconds for a full open/close cycle) can be set per channel via MQTT — the value is retained by the broker and restored automatically on reconnect:

| Topic | Payload | Effect |
|---|---|---|
| `home-assistant/cover/config/travel_time` | `30` | Default for all channels |
| `home-assistant/cover/config/<ch>/travel_time` | `25` | Override for channel `<ch>` |

## Home Assistant configuration

Add one `cover` entry per channel to your `configuration.yaml`.  
Replace `<ch>` with the channel number (1–5) and adjust `basic_topic` to match your `config.json`.

```yaml
mqtt:
  cover:
    - name: "Rolladen Kanal 1"
      unique_id: easycontrol_cover_1
      command_topic: "home-assistant/cover/1/set"
      state_topic: "home-assistant/cover/1/state"
      position_topic: "home-assistant/cover/1/position"
      set_position_topic: "home-assistant/cover/1/set_position"
      availability_topic: "home-assistant/cover/availability"
      payload_open: "OPEN"
      payload_close: "CLOSE"
      payload_stop: "STOP"
      state_open: "open"
      state_closed: "closed"
      state_opening: "opening"
      state_closing: "closing"
      state_stopped: "stopped"
      payload_available: "online"
      payload_not_available: "offline"
      position_open: 100
      position_closed: 0
      optimistic: false
      retain: false
      device_class: shutter

    - name: "Rolladen Kanal 2"
      unique_id: easycontrol_cover_2
      command_topic: "home-assistant/cover/2/set"
      state_topic: "home-assistant/cover/2/state"
      position_topic: "home-assistant/cover/2/position"
      set_position_topic: "home-assistant/cover/2/set_position"
      availability_topic: "home-assistant/cover/availability"
      payload_open: "OPEN"
      payload_close: "CLOSE"
      payload_stop: "STOP"
      state_open: "open"
      state_closed: "closed"
      state_opening: "opening"
      state_closing: "closing"
      state_stopped: "stopped"
      payload_available: "online"
      payload_not_available: "offline"
      position_open: 100
      position_closed: 0
      optimistic: false
      retain: false
      device_class: shutter

    # Repeat for channels 3–5 …
```

> **Tip:** For a cleaner setup, extract the shared fields into a [MQTT cover package](https://www.home-assistant.io/integrations/cover.mqtt/) or use `!include` anchors to avoid repetition.