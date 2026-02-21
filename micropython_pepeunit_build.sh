#!/usr/bin/env bash
set -euo pipefail

BOARD="${1:?Usage: $0 <BOARD> <TAG> <VERSION>
Supported boards: ESP8266_GENERIC  ESP32_GENERIC  ESP32_GENERIC_S3  ESP32_GENERIC_C3
Example: $0 ESP32_GENERIC v1.27.0 v1.1.1}"
TAG="${2:?Usage: $0 <BOARD> <TAG> <VERSION>}"
VERSION="${3:?Usage: $0 <BOARD> <TAG> <VERSION>}"
OUTPUT_NAME="${BOARD}-${TAG}-PEPEUNIT-${VERSION}.bin"

ROOT_DIR=$(cd "$(dirname "$0")" && pwd)
MPY_DIR="$ROOT_DIR/micropython"

case "$BOARD" in
  ESP8266_GENERIC)
    PORT_DIR="esp8266"
    DEFAULT_MANIFEST="$ROOT_DIR/manifests/esp8266_manifest_2MiB.py"
    ;;
  ESP32_GENERIC)
    PORT_DIR="esp32"
    IDF_TARGET="esp32"
    DEFAULT_MANIFEST="$ROOT_DIR/manifests/esp32_manifest.py"
    ;;
  ESP32_GENERIC_S3)
    PORT_DIR="esp32"
    IDF_TARGET="esp32s3"
    DEFAULT_MANIFEST="$ROOT_DIR/manifests/esp32_manifest.py"
    ;;
  ESP32_GENERIC_C3)
    PORT_DIR="esp32"
    IDF_TARGET="esp32c3"
    DEFAULT_MANIFEST="$ROOT_DIR/manifests/esp32_manifest.py"
    ;;
  *)
    echo "Error: unsupported board '$BOARD'"
    echo "Supported: ESP8266_GENERIC  ESP32_GENERIC  ESP32_GENERIC_S3  ESP32_GENERIC_C3"
    exit 1
    ;;
esac

if [[ -z "${FROZEN_MANIFEST:-}" && -f "$DEFAULT_MANIFEST" ]]; then
  FROZEN_MANIFEST="$DEFAULT_MANIFEST"
fi

echo "==> Board: $BOARD | Tag: $TAG | Output: $OUTPUT_NAME"

git -C "$MPY_DIR" fetch --tags --quiet || true
git -C "$MPY_DIR" checkout -q "$TAG"

echo "==> Building mpy-cross"
make -C "$MPY_DIR/mpy-cross" -j"$(nproc)"

# ── Toolchain setup ──────────────────────────────────────────────────────────

if [[ "$BOARD" == "ESP8266_GENERIC" ]]; then
  TOOLCHAIN_DIR="$MPY_DIR/xtensa-lx106-elf"
  if [[ ! -x "$TOOLCHAIN_DIR/bin/xtensa-lx106-elf-gcc" ]]; then
    echo "==> Installing xtensa-lx106 toolchain (first run only)"
    cd "$MPY_DIR"
    wget -q https://micropython.org/resources/xtensa-lx106-elf-standalone.tar.gz
    tar xzf xtensa-lx106-elf-standalone.tar.gz
    rm -f xtensa-lx106-elf-standalone.tar.gz
  fi
  rm -f "$TOOLCHAIN_DIR/bin/esptool.py" 2>/dev/null || true

  export PATH="$HOME/.local/bin:$PATH"
  if ! command -v esptool.py >/dev/null 2>&1; then
    echo "Error: esptool.py not found. Install with: pip install esptool"
    exit 1
  fi
  ESPTOOL_BIN="$(command -v esptool.py)"

  export PATH="$TOOLCHAIN_DIR/bin:$PATH"

else
  # ESP32 family — ESP-IDF
  IDF_VERSION="${IDF_VERSION:-v5.4.2}"
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
    echo "==> Installing ESP-IDF tools for $IDF_TARGET (first run only) ... (this may take several minutes)"
    pushd "$IDF_DIR" >/dev/null
    export IDF_TOOLS_PATH="$MPY_DIR/.espressif"
    export IDF_INSTALL_TARGETS="$IDF_TARGET"
    : "${IDF_GITHUB_ASSETS:=dl.espressif.com/github_assets}"
    export IDF_GITHUB_ASSETS
    ./install.sh "$IDF_TARGET"
    popd >/dev/null
    # shellcheck disable=SC1091
    source "$IDF_DIR/export.sh"
    idf.py --version >/dev/null

    # Xtensa-based targets: verify dynconfig library exists
    if [[ "$IDF_TARGET" == "esp32" || "$IDF_TARGET" == "esp32s3" ]]; then
      XTENSA_PREFIX="xtensa-${IDF_TARGET}-elf"
      if TOOL_BIN="$(command -v "${XTENSA_PREFIX}-gcc" 2>/dev/null)"; then
        TOOL_ROOT="$(cd "$(dirname "$TOOL_BIN")/.." && pwd)"
        if [[ ! -f "$TOOL_ROOT/lib/xtensa_${IDF_TARGET}.so" ]]; then
          echo "==> Missing xtensa dynconfig for $IDF_TARGET; reinstalling toolchain..."
          pushd "$IDF_DIR" >/dev/null
          python3 tools/idf_tools.py install --targets "$IDF_TARGET"
          popd >/dev/null
        fi
      fi
    fi
  fi
fi

# ── Build firmware ───────────────────────────────────────────────────────────

PORT_BUILD_DIR="$MPY_DIR/ports/$PORT_DIR"

echo "==> Updating submodules for $PORT_DIR"
make -C "$PORT_BUILD_DIR" submodules

echo "==> Cleaning previous build and frozen content"
make -C "$PORT_BUILD_DIR" clean-modules || true
make -C "$PORT_BUILD_DIR" clean || true

echo "==> Building firmware"
BUILD_ARGS=(BOARD="$BOARD")
if [[ -n "${FROZEN_MANIFEST:-}" ]]; then
  echo "==> Using frozen manifest: $FROZEN_MANIFEST"
  BUILD_ARGS+=(FROZEN_MANIFEST="$FROZEN_MANIFEST")
fi
if [[ "$BOARD" == "ESP8266_GENERIC" ]]; then
  BUILD_ARGS+=(ESPTOOL="$ESPTOOL_BIN")
fi

make -C "$PORT_BUILD_DIR" "${BUILD_ARGS[@]}" -j"$(nproc)"

SRC_BIN="$PORT_BUILD_DIR/build-$BOARD/firmware.bin"
DST_BIN="$ROOT_DIR/$OUTPUT_NAME"
cp -f "$SRC_BIN" "$DST_BIN"

echo "==> Done: $(du -h "$DST_BIN" | cut -f1)  $DST_BIN"
