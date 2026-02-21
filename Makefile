BOARD   ?= ESP32_GENERIC
TAG     ?= v1.27.0
VERSION ?= v1.1.1
PORT    ?= /dev/ttyUSB0

.PHONY: help install build full-update add-rules-tty connect-with-screen clean

help:
	@echo "Pepeunit Micropython Client - Commands:"
	@echo ""
	@echo "  make build                         Build firmware (default: $(BOARD))"
	@echo "  make full-update                   Build + flash + upload example files"
	@echo "  make install                       Install ampy and esptool to system"
	@echo "  make add-rules-tty                 chmod 777 on PORT device"
	@echo "  make connect-with-screen           Open screen session on PORT"
	@echo "  make clean                         Remove generated binaries"
	@echo ""
	@echo "Variables (override with VAR=value):"
	@echo "  BOARD    $(BOARD)"
	@echo "  TAG      $(TAG)"
	@echo "  VERSION  $(VERSION)"
	@echo "  PORT     $(PORT)"
	@echo ""
	@echo "Supported boards: ESP8266_GENERIC  ESP32_GENERIC  ESP32_GENERIC_S3  ESP32_GENERIC_C3"
	@echo ""
	@echo "Examples:"
	@echo "  make build BOARD=ESP32_GENERIC_S3"
	@echo "  make full-update BOARD=ESP32_GENERIC_C3 PORT=/dev/ttyACM0"

install:
	@echo "Install packages ampy and esptool to system..."
	pip install esptool --break-system-packages
	pip install adafruit-ampy --break-system-packages

add-rules-tty:
	@echo "Add rules for connect unit tty..."
	sudo chmod 777 $(PORT)

build:
	@echo "Building firmware for $(BOARD)..."
	./micropython_pepeunit_build.sh $(BOARD) $(TAG) $(VERSION)

full-update:
	@echo "Build + flash $(BOARD) via $(PORT)..."
	./micropython_pepeunit_build.sh $(BOARD) $(TAG) $(VERSION)
	./micropython_pepeunit_rewrite.sh $(BOARD) $(TAG) $(VERSION) $(PORT)

connect-with-screen:
	@echo "Connect with screen to $(PORT)..."
	screen -XS pts quit || true
	screen $(PORT) 115200

clean:
	@echo "Clean micropython binaries..."
	rm -rf ESP8266_GENERIC*
	rm -rf ESP32_GENERIC*
