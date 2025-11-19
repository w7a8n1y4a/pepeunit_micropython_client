.PHONY: help install build-micropython write-update-to-unit add-rules-tty connect-with-screen clean

help:
	@echo "Pepeunit Micropython Client - Commands:"
	@echo ""
	@echo "install:              Install packages to system"
	@echo "build-micropython:    Make micropython with freeze pepeunit library" 
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

build-micropython:
	@echo "Make micropython with freeze pepeunit library..."
	./build_esp8266.sh

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
