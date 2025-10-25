# Pepeunit MicroPython Client (ESP8266)

## Install Micropython on esp8266 board

```bash
pip install esptool --break-system-packages
sudo chmod 777 /dev/ttyUSB0
esptool.py --port /dev/ttyUSB0 erase_flash
wget https://micropython.org/resources/firmware/ESP8266_GENERIC-20250911-v1.26.1.bin
esptool.py --port /dev/ttyUSB0 --baud 460800 write_flash --flash_size=detect 0 ESP8266_GENERIC-20250911-v1.26.1.bin

```

## ampy

```bash
pip install adafruit-ampy --break-system-packages
ampy -p /dev/ttyUSB0 -b 115200 put ./ .
screen /dev/ttyUSB0 115200
screen -XS name quit

```

## mpy gen

```bash
git clone https://github.com/micropython/micropython.git
cd micropython/mpy-cross
make -j
```

```bash
set SRC /home/w7a8n1y4a/Documents/gitlab/pepe/pepeunit/libs/pepeunit_micropython_client/src/pepeunit_micropython_client
set DST /home/w7a8n1y4a/Documents/gitlab/pepe/pepeunit/libs/pepeunit_micropython_client/example/lib/pepeunit_micropython_client

for f in $SRC/*.py
    set base (basename $f .py)
    micropython/mpy-cross/build/mpy-cross -O2 -o $DST/$base.mpy $f
end
```


