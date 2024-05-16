import network
import wlan_config

print('Easycontrol - ESP23 Module')
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
if not wlan.isconnected():
    print('Connecting to network...')
    wlan.connect(wlan_config.WIFI_SSID, wlan_config.WIFI_PASSWORD)
    while not wlan.isconnected():
        pass

print('Connected. Network config:', wlan.ifconfig())