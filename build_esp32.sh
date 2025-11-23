#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")" && pwd)
MPY_DIR="$ROOT_DIR/micropython"
BOARD="ESP32_GENERIC"
TAG="v1.26.1"
IDF_VERSION="${IDF_VERSION:-v5.4.2}"
OUTPUT_NAME="${OUTPUT_NAME:-ESP32_GENERIC-v1.26.1-PEPEUNIT-v0.10.0.bin}"
DEFAULT_MANIFEST="$ROOT_DIR/manifests/esp32_manifest.py"
if [[ -z "${FROZEN_MANIFEST:-}" && -f "$DEFAULT_MANIFEST" ]]; then
  FROZEN_MANIFEST="$DEFAULT_MANIFEST"
fi

echo "==> Using MicroPython tag: $TAG"
git -C "$MPY_DIR" fetch --tags --quiet || true
git -C "$MPY_DIR" checkout -q "$TAG"

echo "==> Building mpy-cross"
make -C "$MPY_DIR/mpy-cross" -j"$(nproc)"

# Ensure ESP-IDF is available (prefer system IDF if provided)
IDF_DIR="$MPY_DIR/esp-idf"
if [[ -n "${IDF_PATH:-}" && -f "${IDF_PATH}/export.sh" ]]; then
  echo "==> Using system ESP-IDF from IDF_PATH: ${IDF_PATH}"
  # shellcheck disable=SC1091
  source "${IDF_PATH}/export.sh"
elif command -v idf.py >/dev/null 2>&1 && [[ -n "${IDF_TOOLS_EXPORT_CMD:-}" ]]; then
  echo "==> Using existing ESP-IDF from environment"
  eval "${IDF_TOOLS_EXPORT_CMD}"
else
  echo "==> Ensuring ESP-IDF locally: $IDF_VERSION (with submodules)"
  if [[ ! -d "$IDF_DIR" ]]; then
    git clone -q -b "$IDF_VERSION" --recursive https://github.com/espressif/esp-idf.git "$IDF_DIR"
  else
    git -C "$IDF_DIR" fetch -q origin "$IDF_VERSION" || true
    git -C "$IDF_DIR" checkout -q "$IDF_VERSION"
    git -C "$IDF_DIR" submodule update --init --recursive -q
  fi
  echo "==> Installing ESP-IDF tools (first run only) ... (this may take several minutes)"
  pushd "$IDF_DIR" >/dev/null
  # Use tools dir local to repo to avoid conflicting with existing ~/.espressif installs
  export IDF_TOOLS_PATH="$MPY_DIR/.espressif"
  export IDF_INSTALL_TARGETS="esp32"
  : "${IDF_GITHUB_ASSETS:=dl.espressif.com/github_assets}"
  export IDF_GITHUB_ASSETS
  ./install.sh esp32
  popd >/dev/null
  # Source ESP-IDF environment (adds idf.py and toolchains to PATH)
  # shellcheck disable=SC1091
  source "$IDF_DIR/export.sh"
  idf.py --version >/dev/null
  # Verify xtensa dynconfig exists; reinstall targets=esp32 if missing
  if TOOL_BIN="$(command -v xtensa-esp32-elf-gcc 2>/dev/null)"; then
    TOOL_ROOT="$(cd "$(dirname "$TOOL_BIN")/.." && pwd)"
    if [[ ! -f "$TOOL_ROOT/lib/xtensa_esp32.so" ]]; then
      echo "==> Missing xtensa dynconfig for esp32; reinstalling toolchain..."
      pushd "$IDF_DIR" >/dev/null
      python3 tools/idf_tools.py install --targets esp32
      popd >/dev/null
    fi
  fi
fi

# Build the ESP32 port
ESP32_DIR="$MPY_DIR/ports/esp32"

echo "==> Updating submodules for esp32"
make -C "$ESP32_DIR" submodules

echo "==> Cleaning previous build and frozen content"
make -C "$ESP32_DIR" clean-modules || true
make -C "$ESP32_DIR" clean || true

echo "==> Building firmware"
if [[ -n "${FROZEN_MANIFEST:-}" ]]; then
  echo "==> Using frozen manifest: $FROZEN_MANIFEST"
  make -C "$ESP32_DIR" BOARD="$BOARD" FROZEN_MANIFEST="$FROZEN_MANIFEST" -j"$(nproc)"
else
  make -C "$ESP32_DIR" BOARD="$BOARD" -j"$(nproc)"
fi

SRC_BIN="$ESP32_DIR/build-$BOARD/firmware.bin"
DST_BIN="$ROOT_DIR/$OUTPUT_NAME"
cp -f "$SRC_BIN" "$DST_BIN"

echo "==> Done: $(du -h "$DST_BIN" | cut -f1)  $DST_BIN"


