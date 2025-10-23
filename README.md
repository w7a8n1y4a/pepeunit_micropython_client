# Pepeunit MicroPython Client (ESP8266)

## Install Micropython on esp8266 board

```bash
pip install esptool --break-system-packages
sudo chmod 777 /dev/ttyUSB0
esptool.py --port /dev/ttyUSB0 erase_flash
wget https://micropython.org/resources/firmware/ESP8266_GENERIC-20250911-v1.26.1.bin
esptool.py --port /dev/ttyUSB0 --baud 460800 write_flash --flash_size=detect 0 ESP8266_GENERIC-20250911-v1.26.1.bin

```

Minimal MicroPython client mirroring the Python client's public API, adapted for constrained boards (ESP8266/ESP32).

- MQTT: `umqtt.simple`
- HTTP/REST: `mrequests`
- Archive: `uzlib` + simple tar reader (no `tarfile`)
- FS: basic file ops

## Quick start (ESP8266)

1. Copy `src/pepeunit_micropython_client` to the board (`/lib/pepeunit_micropython_client`) and put your `env.json`, `schema.json`, `log.json` in `/`.
2. Use `example/basic.py` as a template.

```python
import network, time
from pepeunit_micropython_client.client import PepeunitClient

sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.connect('SSID', 'PASSWORD')
while not sta.isconnected():
    time.sleep(0.2)

client = PepeunitClient(
    env_file_path='/env.json',
    schema_file_path='/schema.json',
    log_file_path='/log.json',
    enable_mqtt=True,
    enable_rest=False,
)

client.mqtt_client.connect()
client.subscribe_all_schema_topics()
client.run_main_cycle()
```

See `example/basic.py`.

