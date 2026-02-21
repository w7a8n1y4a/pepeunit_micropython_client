#!/usr/bin/env bash
set -euo pipefail

BOARD="${1:?Usage: $0 <BOARD> <TAG> <VERSION> <PORT>
Supported boards: ESP8266_GENERIC  ESP32_GENERIC  ESP32_GENERIC_S3  ESP32_GENERIC_C3
Example: $0 ESP32_GENERIC v1.27.0 v1.1.1 /dev/ttyUSB0}"
TAG="${2:?Usage: $0 <BOARD> <TAG> <VERSION> <PORT>}"
VERSION="${3:?Usage: $0 <BOARD> <TAG> <VERSION> <PORT>}"
PORT="${4:?Usage: $0 <BOARD> <TAG> <VERSION> <PORT>}"
BIN_NAME="${BOARD}-${TAG}-PEPEUNIT-${VERSION}.bin"

case "$BOARD" in
  ESP8266_GENERIC)    FLASH_ARGS=(--flash_size=detect 0) ;;
  ESP32_GENERIC)      FLASH_ARGS=(0x1000) ;;
  ESP32_GENERIC_S3)   FLASH_ARGS=(0x0) ;;
  ESP32_GENERIC_C3)   FLASH_ARGS=(0x0) ;;
  *)
    echo "Error: unsupported board '$BOARD'"
    echo "Supported: ESP8266_GENERIC  ESP32_GENERIC  ESP32_GENERIC_S3  ESP32_GENERIC_C3"
    exit 1
    ;;
esac

screen -XS pts quit || true
esptool.py --port "$PORT" erase_flash
esptool.py --port "$PORT" --baud 460800 write_flash "${FLASH_ARGS[@]}" "$BIN_NAME"

echo "Run sync example files"
ampy -p "$PORT" -b 115200 put ./example/ .
