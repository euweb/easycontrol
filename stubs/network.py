# MicroPython `network` stub – included only for import compatibility on PC
class WLAN:
    STA_IF = "STA_IF"
    AP_IF = "AP_IF"

    def __init__(self, interface=None):
        pass

    def active(self, val=None):
        return True

    def isconnected(self):
        return True

    def connect(self, ssid, password):
        print(f"[net]  WLAN.connect({ssid}) (stub, no-op)")

    def ifconfig(self):
        return ("127.0.0.1", "255.255.255.0", "127.0.0.1", "127.0.0.1")
