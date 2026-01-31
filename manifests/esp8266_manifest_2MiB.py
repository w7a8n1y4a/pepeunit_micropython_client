# base modules
include("$(PORT_DIR)/boards/manifest.py")

# asyncio
include("$(MPY_DIR)/extmod/asyncio")

# drivers
require("ssd1306")

# micropython-lib: file utilities
require("upysh")

# Freeze all project modules from the external src directory
freeze("/home/w7a8n1y4a/Documents/gitlab/pepe/pepeunit/libs/pepeunit_micropython_client/src")
