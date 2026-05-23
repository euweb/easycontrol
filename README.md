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

When the physical EasyControl remote is used to operate a shutter, the ESP32 detects the activity by monitoring the channel-select LEDs:

- The device polls `check_channel()` every loop tick (~1 s).
- If the active channel changes **without** the ESP32 having triggered it, the **previous** channel was operated by the remote.
- The tracked position for that channel is reset to 50 (`stopped`) and published to Home Assistant.
- The updated position is also persisted to flash.

> **Note:** The invalidation happens when the remote **switches away** from a channel, not at the moment the button is pressed. This is the best resolution possible without additional hardware.

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