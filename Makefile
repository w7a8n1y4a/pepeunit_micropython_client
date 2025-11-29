.PHONY: help install esp8266-build-micropython esp8266-full-update esp8266-full-update esp32-full-update add-rules-tty connect-with-screen clean

help:
	@echo "Pepeunit Micropython Client - Commands:"
	@echo ""
	@echo "install:                    Install packages ampy and esptool to system"
	@echo "esp8266-build-micropython:  Make micropython with freeze pepeunit library for esp8266" 
	@echo "esp8266-full-update:        Generate micropython esp8266 binary and write example to unit"
	@echo "esp32-build-micropython:    Make micropython with freeze pepeunit library for esp32" 
	@echo "esp32-full-update:          Generate micropython esp32 binary and write example to unit"
	@echo "add-rules-tty:              Add rules for connect unit tty"
	@echo "connect-with-screen:        Connect with screen to unit tty"
	@echo "clean:                      Clean micropython binary"

install:
	@echo "Install packages ampy and esptool to system..."
	pip install esptool --break-system-packages
	pip install adafruit-ampy --break-system-packages

add-rules-tty:
	@echo "Add rules for connect unit tty..."
	sudo chmod 777 /dev/ttyUSB0

esp8266-build-micropython:
	@echo "Make micropython with freeze pepeunit library for esp8266..."
	./build_esp8266.sh

esp8266-full-update:
	@echo "Generate micropython esp8266 binary and write example to unit..."
	./esp8266_rewrite.sh

esp32-build-micropython:
	@echo "Make micropython with freeze pepeunit library for esp32..."
	./build_esp32.sh

esp32-full-update:
	@echo "Generate micropython esp32 binary and write example to unit..."
	./esp32_rewrite.sh

connect-with-screen:
	@echo "Connect with screen to unit tty..."
	screen -XS pts quit || true
	screen /dev/ttyUSB0 115200

clean:
	@echo "Clean micropython binary..."
	rm -rf ESP8266_GENERIC*
	rm -rf ESP32_GENERIC*
