import network
import time
import gc
import ujson as json

print('\n')

def _read_wifi_from_env(path):
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        ssid = data.get('WIFI_SSID', '')
        password = data.get('WIFI_PASS', '')
        return ssid, password
    except Exception:
        return '', ''


ssid, password = _read_wifi_from_env('/env.json')
print('wifi:', ssid, password)

sta = network.WLAN(network.STA_IF)

if not sta.active():
    sta.active(True)

if not sta.isconnected():
    sta.connect(ssid, password)
    # Wait for connection
    for _ in range(50):
        if sta.isconnected():
            break
        time.sleep(0.2)

if sta.isconnected():
    try:
        print('network:', sta.ifconfig())
    except Exception:
        pass

gc.collect()

print('free_mem:',  gc.mem_free(), 'alloc_mem:',  gc.mem_alloc())
print('Boot Success')
