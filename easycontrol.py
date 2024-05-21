from machine import Pin
import time


class Easycontrol:

    CONFIG = None
    
    # 0 if all channels selected, greater than 0 otherwise
    selected = None

    up_pin = None
    down_pin = None
    stop_pin = None
    select_pin = None

    channels = None

    def __init__(self, config):
        self.CONFIG = config

    def init(self):
        self.select_pin = Pin(self.CONFIG['select_pin'], mode=Pin.OPEN_DRAIN, value=1)
        self.up_pin = Pin(self.CONFIG['up_pin'], mode=Pin.OPEN_DRAIN, value=1)
        self.stop_pin = Pin(self.CONFIG['stop_pin'], mode=Pin.OPEN_DRAIN, value=1)
        self.down_pin = Pin(self.CONFIG['down_pin'], mode=Pin.OPEN_DRAIN, value=1)
        
        ch1_pin = Pin(self.CONFIG['ch1_pin'], Pin.IN)
        ch2_pin = Pin(self.CONFIG['ch2_pin'], Pin.IN)
        ch3_pin = Pin(self.CONFIG['ch3_pin'], Pin.IN)
        ch4_pin = Pin(self.CONFIG['ch4_pin'], Pin.IN)
        ch5_pin = Pin(self.CONFIG['ch5_pin'], Pin.IN)

        self.channels = [ch1_pin, ch2_pin, ch3_pin, ch4_pin, ch5_pin]

    def _up(self):
        self.up_pin.off()
        time.sleep(0.1)
        self.up_pin.on()

    def _down(self):
        self.down_pin.off()
        time.sleep(0.1)
        self.down_pin.on()

    def _stop(self):
        self.stop_pin.off()
        time.sleep(0.1)
        self.stop_pin.on()

    def up(self, channel):
        self.select(channel)
        self._up()

    def down(self, channel):
        self.select(channel)
        self._down()

    def stop(self, channel):
        self.select(channel)
        self._stop()

    def check_channel(self):
        """Funktion zum Überprüfen der LED-Zustände"""
        states = [channel.value() for channel in self.channels]
        print(states)
        
        if all(state == 1 for state in states):
            return 0  # all channels are selected
        elif all(state == 0 for state in states):
            return -1  # no channel is selected, should not occur
        else:
            # find the selected channel and return its nubmer
            for i, state in enumerate(states):
                if state == 1:
                    return i+1
        return -1  # catch all, should not occur

    def select(self, channel):
        if(channel == None):
            channel = 0
        channel = int(channel)
        self.selected = None
        print(f"select channel: {channel}")
        i=0
        while( ( self.selected != channel ) and (i < 10) ):
            self.select_pin.off()
            time.sleep(0.1)
            self.select_pin.on()
            time.sleep(0.02)
            self.selected = self.check_channel()
            print(f"desired: {channel}, got: {self.selected}, i: {i}")
            time.sleep(1)
            i = i + 1

        

    