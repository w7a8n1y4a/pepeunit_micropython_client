.PHONY: help install build-micropython-esp8266 build-micropython-esp32 write-update-to-unit add-rules-tty connect-with-screen clean

help:
	@echo "Pepeunit Micropython Client - Commands:"
	@echo ""
	@echo "install:              Install packages to system"
	@echo "build-micropython-esp8266:    Make micropython with freeze pepeunit library for esp8266" 
	@echo "build-micropython-esp32:    Make micropython with freeze pepeunit library for esp32" 
	@echo "write-update-to-unit: Write micropython and example files to unit"
	@echo "add-rules-tty:        Add rules for connect unit tty"
	@echo "connect-with-screen:  Connect with screen to unit tty"
	@echo "clean:                Clean micropython binary"

install:
	@echo "Install packages to system..."
	pip install esptool --break-system-packages
	pip install adafruit-ampy --break-system-packages

add-rules-tty:
	@echo "Add rules for connect unit tty..."
	sudo chmod 777 /dev/ttyUSB0

build-micropython-esp8266:
	@echo "Make micropython with freeze pepeunit library for esp8266..."
	./build_esp8266.sh

build-micropython-esp32:
	@echo "Make micropython with freeze pepeunit library for esp32..."
	./build_esp32.sh

write-update-to-unit:
	@echo "Write micropython and example files to unit..."
	./rewrite.sh

connect-with-screen:
	@echo "Connect with screen to unit tty..."
	screen -XS pts quit || true
	screen /dev/ttyUSB0 115200

clean:
	@echo "Clean micropython binary..."
	rm -rf ESP8266_GENERIC*
