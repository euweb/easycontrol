import machine
from machine import Pin
import time
import ubinascii
from umqtt.simple import MQTTClient

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

# 0 if all channels selected, greater than 0 otherwise
selected = None

up_pin = None
down_pin = None
stop_pin = None
select_pin = None

ch1_pin = None
ch2_pin = None
ch3_pin = None
ch4_pin = None
ch5_pin = None

ch_map = {}

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

def channel_on(pin):
  global selected, ch_map
  if((selected is not None) and (selected > 0)):
    selected = 0
  else:
    selected = ch_map.get(pin)
  print(f"Pin: {pin} Selected: {selected}")

def init():
  global select_pin, ch1_pin, ch2_pin, ch3_pin, ch4_pin, ch5_pin, ch_map, up_pin, down_pin, stop_pin
  select_pin = Pin(CONFIG['select_pin'], mode=Pin.OPEN_DRAIN, value=1)
  up_pin = Pin(CONFIG['up_pin'], mode=Pin.OPEN_DRAIN, value=1)
  stop_pin = Pin(CONFIG['stop_pin'], mode=Pin.OPEN_DRAIN, value=1)
  down_pin = Pin(CONFIG['down_pin'], mode=Pin.OPEN_DRAIN, value=1)
  
  ch1_pin = Pin(CONFIG['ch1_pin'], Pin.IN)
  ch2_pin = Pin(CONFIG['ch2_pin'], Pin.IN)
  ch3_pin = Pin(CONFIG['ch3_pin'], Pin.IN)
  ch4_pin = Pin(CONFIG['ch4_pin'], Pin.IN)
  ch5_pin = Pin(CONFIG['ch5_pin'], Pin.IN)

  ch_map[ch1_pin]=1
  ch_map[ch2_pin]=2
  ch_map[ch3_pin]=3
  ch_map[ch4_pin]=4
  ch_map[ch5_pin]=5
  
  
  ch1_pin.irq(trigger=Pin.IRQ_FALLING, handler=channel_on)
  ch2_pin.irq(trigger=Pin.IRQ_FALLING, handler=channel_on)
  ch3_pin.irq(trigger=Pin.IRQ_FALLING, handler=channel_on)
  ch4_pin.irq(trigger=Pin.IRQ_FALLING, handler=channel_on)
  ch5_pin.irq(trigger=Pin.IRQ_FALLING, handler=channel_on)
  

def sub_cb(topic, msg):
  global select_pin
  print((topic, msg))
  if(msg == b'up'):
    print('up click')
    up_pin.off()
    time.sleep(1)
    up_pin.on()
  elif(msg == b'down'):
    print('down click')
    down_pin.off()
    time.sleep(1)
    down_pin.on()
  elif(msg == b'stop'):
    print('stop click')
    stop_pin.off()
    time.sleep(1)
    stop_pin.on()
  else:
    print('select click')
    select_pin.off()
    time.sleep(1)
    select_pin.on()
  

def main():
    client = MQTTClient(CONFIG['client_id'], CONFIG['broker'])
    client.connect()
    print("Connected to {}".format(CONFIG['broker']))
    client.set_callback(sub_cb)
    client.connect()
    client.subscribe(b"easycontrol/channel")
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
    init()
    main()