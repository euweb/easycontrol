import machine
import ubinascii
import ure as re
from umqtt.simple import MQTTClient
from easycontrol import Easycontrol
#import easycontrol

CONFIG = {
    "broker": "192.168.1.16",
    "sensor_pin": 0,
    "client_id": b"esp8266_" + ubinascii.hexlify(machine.unique_id()),
    "topic": b"easycontrol",
    "select_pin": 21, 
    "up_pin": 0,
    "down_pin": 0,
    "stop_pin": 0,
    "ch1_pin": 0,
    "ch2_pin": 0,
    "ch3_pin": 0,
    "ch4_pin": 0,
    "ch5_pin": 0,
}

HA_CONFIG = {}

ec = None

def load_config():
    import ujson as json
    try:
        with open("/config.json") as f:
            config = json.loads(f.read())
    except (OSError, ValueError):
        print("Couldn't load /config.json")
        save_config()
    else:
        CONFIG.update(config)
        print("Loaded config from /config.json")

def save_config():
    import ujson as json
    try:
        with open("/config.json", "w") as f:
            f.write(json.dumps(CONFIG))
    except OSError:
        print("Couldn't save /config.json")

def parse_string(s):
    pattern = r'^(.*?)(?:/(\d+))?/([^/]+)$'
    match = re.match(pattern, s)
    
    if match:
        part1 = match.group(1)
        id = match.group(2)
        command = match.group(3)
        return part1, id, command
    else:
        raise ValueError("String does not match the expected format")

def sub_cb(topic_raw, msg_raw):
  global ec
  msg = msg_raw.decode('utf-8')
  topic = topic_raw.decode('utf-8')
  try:
    part1, id, command = parse_string(topic)
    print(f"Topic: {part1}, channel: {id}, command: {command}")
  except ValueError as e:
    print(e)
  print((topic, msg))
  if(command == HA_CONFIG['command_topic']):
    if(msg == HA_CONFIG['payload_open']):
      print('up click')
      ec.up(id)
    elif(msg == HA_CONFIG['payload_close']):
      print('down click')
      ec.down(id)
    elif(msg == HA_CONFIG['payload_stop']):
      print('stop click')
      ec.stop(id)


def main():
    global ec, HA_CONFIG
    ec = Easycontrol(CONFIG["easycontrol"])
    ec.init()
    MQTT_CONFIG = CONFIG['mqtt']
    HA_CONFIG = CONFIG['ha']
    client = MQTTClient(MQTT_CONFIG['client_id'], MQTT_CONFIG['broker'])
    client.connect()
    print("Connected to {}".format(MQTT_CONFIG['broker']))
    
    client.set_callback(sub_cb)
    client.connect()
    print("publish availability message")
    client.publish(MQTT_CONFIG['basic_topic']+"/" + HA_CONFIG['availability_topic'], HA_CONFIG['payload_available'], qos=1)
    
    print("subscribe to topic")
    client.subscribe(MQTT_CONFIG['basic_topic']+"/#")
    
    while True:
        if True:
            # Blocking wait for message
            client.wait_msg()
        else:
            # Non-blocking wait for message
            client.check_msg()
            # Then need to sleep to avoid 100% CPU usage (in a real
            # app other useful actions would be performed instead)
            time.sleep(1)

    c.disconnect()

if __name__ == '__main__':
    load_config()
    main()