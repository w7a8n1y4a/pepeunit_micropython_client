#!/usr/bin/env bash
screen -XS pts quit || true
esptool.py --port /dev/ttyUSB0 erase_flash
bash build_esp8266.sh
esptool.py --port /dev/ttyUSB0 --baud 460800 write_flash --flash_size=detect 0 ESP8266_GENERIC-v1.26.1-PEPEUNIT-v0.10.0.bin

echo "Run sync example files"
ampy -p /dev/ttyUSB0 -b 115200 put ./example/ .