#!/usr/bin/env bash
screen -XS pts quit || true
esptool.py --port /dev/ttyUSB0 erase_flash
bash build_esp32.sh
esptool.py --port /dev/ttyUSB0 --baud 460800 write_flash 0x1000 ESP32_GENERIC-v1.26.1-PEPEUNIT-v1.0.0.bin

echo "Run sync example files"
ampy -p /dev/ttyUSB0 -b 115200 put ./example/ .