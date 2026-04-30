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