import machine
import time
import ubinascii
import ure as re
from umqtt.simple import MQTTClient
from easycontrol import Easycontrol
from machine import Timer


CONFIG = {}

HA_CONFIG = {}
MQTT_CONFIG = {}

ec = None
client = None

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


def send_heartbeat(t):
    global MQTT_CONFIG, HA_CONFIG, client
    print("publish availability message")
    client.publish(MQTT_CONFIG['basic_topic']+"/" + HA_CONFIG['availability_topic'], HA_CONFIG['payload_available'], qos=1)


def main():
    global ec, MQTT_CONFIG, HA_CONFIG, client
    ec = Easycontrol(CONFIG["easycontrol"])
    ec.init()
    MQTT_CONFIG = CONFIG['mqtt']
    HA_CONFIG = CONFIG['ha']
    client = MQTTClient(MQTT_CONFIG['client_id'], MQTT_CONFIG['broker'])
    client.connect()
    print("Connected to {}".format(MQTT_CONFIG['broker']))
    
    client.set_callback(sub_cb)
    client.connect()

    
    print("subscribe to topic")
    client.subscribe(MQTT_CONFIG['basic_topic']+"/#")

    send_heartbeat(None)    
    tim1 = Timer(1)
    tim1.init(period=60000, mode=Timer.PERIODIC, callback=send_heartbeat)
    
    try:
        while 1:
            # micropython.mem_info()
            client.check_msg()
            time.sleep(1)
    finally:
        client.disconnect()
        machine.reboot()


if __name__ == '__main__':
    load_config()
    main()