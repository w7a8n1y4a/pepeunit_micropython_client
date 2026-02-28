# base modules
include("$(PORT_DIR)/boards/manifest.py")

# asyncio
include("$(MPY_DIR)/extmod/asyncio")

# drivers
require("ssd1306")

# micropython-lib: file utilities
require("upysh")

# Freeze all project modules from the external src directory
import os
freeze(os.environ["PEPEUNIT_SRC_DIR"])
