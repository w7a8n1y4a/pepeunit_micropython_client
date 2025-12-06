#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")" && pwd)
MPY_DIR="$ROOT_DIR/micropython"
BOARD="ESP8266_GENERIC"
TAG="v1.26.1"
OUTPUT_NAME="${OUTPUT_NAME:-ESP8266_GENERIC-v1.26.1-PEPEUNIT-v1.0.0.bin}"
DEFAULT_MANIFEST="$ROOT_DIR/manifests/esp8266_manifest_2MiB.py"
# Allow override via env; otherwise use our project manifest
FROZEN_MANIFEST="${FROZEN_MANIFEST:-$DEFAULT_MANIFEST}"

echo "==> Using MicroPython tag: $TAG"
git -C "$MPY_DIR" fetch --tags --quiet || true
git -C "$MPY_DIR" checkout -q "$TAG"

echo "==> Building mpy-cross"
make -C "$MPY_DIR/mpy-cross" -j"$(nproc)"

# Ensure Xtensa toolchain for ESP8266 is available
TOOLCHAIN_DIR="$MPY_DIR/xtensa-lx106-elf"
if [[ ! -x "$TOOLCHAIN_DIR/bin/xtensa-lx106-elf-gcc" ]]; then
  echo "==> Installing xtensa-lx106 toolchain (first run only)"
  cd "$MPY_DIR"
  wget -q https://micropython.org/resources/xtensa-lx106-elf-standalone.tar.gz
  tar xzf xtensa-lx106-elf-standalone.tar.gz
  rm -f xtensa-lx106-elf-standalone.tar.gz
fi

# Avoid any esptool.py in the toolchain shadowing the pip one
rm -f "$TOOLCHAIN_DIR/bin/esptool.py" 2>/dev/null || true

# Ensure esptool 3.3.1 (compatible with ESP8266 build) without touching system packages
export PATH="$HOME/.local/bin:$PATH"
ESPTOOL_BIN="esptool.py"
if ! python3 -c "import esptool,sys; sys.exit(0 if getattr(esptool,'__version__','')=='3.3.1' else 1)" >/dev/null 2>&1; then
  echo "==> Preparing esptool==3.3.1 (pipx or local venv)"
  if command -v pipx >/dev/null 2>&1; then
    pipx install --force "esptool==3.3.1" >/dev/null
    ESPTOOL_BIN="$HOME/.local/bin/esptool.py"
  else
    VENV_DIR="$ROOT_DIR/.venv_esptool"
    if [[ ! -x "$VENV_DIR/bin/python" ]]; then
      python3 -m venv "$VENV_DIR"
    fi
    "$VENV_DIR/bin/pip" install --upgrade "pip<24" >/dev/null || true
    "$VENV_DIR/bin/pip" install "esptool==3.3.1" >/dev/null
    ESPTOOL_BIN="$VENV_DIR/bin/esptool.py"
  fi
else
  # Prefer calling esptool.py explicitly to avoid wrapper issues
  if [[ -x "$HOME/.local/bin/esptool.py" ]]; then
    ESPTOOL_BIN="$HOME/.local/bin/esptool.py"
  fi
fi

# Build the ESP8266 port
export PATH="$TOOLCHAIN_DIR/bin:$PATH"
ESP8266_DIR="$MPY_DIR/ports/esp8266"

echo "==> Updating submodules for esp8266"
make -C "$ESP8266_DIR" submodules

echo "==> Cleaning previous build and frozen content"
make -C "$ESP8266_DIR" clean-modules || true
make -C "$ESP8266_DIR" clean || true

echo "==> Building firmware"
echo "==> Using manifest: $FROZEN_MANIFEST"
make -C "$ESP8266_DIR" BOARD="$BOARD" ESPTOOL="$ESPTOOL_BIN" FROZEN_MANIFEST="$FROZEN_MANIFEST" -j"$(nproc)"

SRC_BIN="$ESP8266_DIR/build-$BOARD/firmware.bin"
DST_BIN="$ROOT_DIR/$OUTPUT_NAME"
cp -f "$SRC_BIN" "$DST_BIN"

echo "==> Done: $(du -h "$DST_BIN" | cut -f1)  $DST_BIN"

