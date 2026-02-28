# Freeze core modules for the ESP32 port (minimal base, no bundle-networking)
freeze("$(PORT_DIR)/modules")

# asyncio (useful for many apps)
include("$(MPY_DIR)/extmod/asyncio")

# Minimal required micropython-lib deps
require("ssl")
require("upysh")
# NTP time sync for TimeManager
require("ntptime")
# 1-Wire support
require("onewire")
# DS18x20 temperature sensors
require("ds18x20")
# Optional: display driver, remove if not needed
require("ssd1306")

# Freeze all project modules from the external src directory so they are
# available as a built-in package in the firmware.
import os
freeze(os.environ["PEPEUNIT_SRC_DIR"])
