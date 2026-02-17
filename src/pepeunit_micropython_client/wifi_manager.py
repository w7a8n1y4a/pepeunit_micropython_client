import time
import network
import uasyncio as asyncio
import sys

import utils

from .settings import Settings
from .logger import Logger


class WifiManager:
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2

    _PLATFORM = sys.platform

    def __init__(self, settings: Settings, logger: Logger):
        self.logger = logger
        self.settings = settings
        self._sta = None
        self._state = self.DISCONNECTED

    @classmethod
    def _set_reconnects(cls, sta):
        if cls._PLATFORM in ("esp32", "rp2"):
            sta.config(reconnects=0)

    def get_sta(self):
        if self._sta is None:
            self.logger.warning("WiFi station run create", file_only=True)
            sta = network.WLAN(network.STA_IF)
            if not sta.active():
                sta.active(True)
            self._set_reconnects(sta)
            self._sta = sta
        return self._sta

    @property
    def connection_state(self):
        return self._state

    def is_wifi_linked(self):
        return bool(self.get_sta().isconnected())

    def _sync_state_from_hardware(self):
        if not self.is_wifi_linked() and self._state >= self.CONNECTED:
            self._state = self.DISCONNECTED

    def is_connected(self):
        return self._state == self.CONNECTED

    async def _force_sta_reset(self):
        self.logger.info("WiFi station prepare", file_only=True)
        self._state = self.DISCONNECTED
        sta = self.get_sta()
        sta.disconnect()
        sta.active(False)
        await asyncio.sleep_ms(200)
        sta.active(True)
        self._set_reconnects(sta)
        await asyncio.sleep_ms(200)

    async def scan_has_target_ssid(self):
        sta = self.get_sta()
        self.logger.info("WiFi run scan existing ssid`s", file_only=True)
        for idx, ap in enumerate(sta.scan(), 1):
            if utils.to_str(ap[0]) == self.settings.PUC_WIFI_SSID:
                return True
            await utils.ayield(idx, every=8, do_gc=False)
        return False

    async def connect_once(self, timeout_ms=10000):
        sta = self.get_sta()

        if sta.isconnected():
            if self.settings.PUC_WIFI_SSID and utils.to_str(sta.config("essid")) == self.settings.PUC_WIFI_SSID:
                self._state = self.CONNECTED
                return True
            self.logger.warning(
                'WiFi wrong SSID "{}"; need "{}"'.format(
                    utils.to_str(sta.config("essid")), self.settings.PUC_WIFI_SSID
                ),
                file_only=True
            )

        await self._force_sta_reset()

        self.logger.warning("Attempting connect to WiFi", file_only=True)
        self._state = self.CONNECTING
        sta.connect(str(self.settings.PUC_WIFI_SSID), str(self.settings.PUC_WIFI_PASS))

        started = time.ticks_ms()
        while not sta.isconnected():
            if time.ticks_diff(time.ticks_ms(), started) >= int(timeout_ms):
                self._state = self.DISCONNECTED
                return False
            await asyncio.sleep_ms(200)

        self._state = self.CONNECTED
        return True

    async def connect_forever(self, connect_timeout_ms=10000):
        attempt = 0
        while True:
            self._sync_state_from_hardware()
            if self.is_connected():
                ssid = utils.to_str(self.get_sta().config("essid"))
                if not self.settings.PUC_WIFI_SSID or ssid == self.settings.PUC_WIFI_SSID:
                    self.logger.warning("WiFi connected: " + str(self.get_sta().ifconfig()), file_only=True)
                    return True
                self.logger.warning(
                    'WiFi wrong SSID "{}"; need "{}"'.format(ssid, self.settings.PUC_WIFI_SSID),
                    file_only=True
                )
                await self._force_sta_reset()
                attempt += 1
                continue

            wait_ms = utils.backoff_interval_ms(attempt, 5000, self.settings.PUC_MAX_RECONNECTION_INTERVAL)

            try:
                self._state = self.CONNECTING
                if await self.scan_has_target_ssid():
                    if await self.connect_once(timeout_ms=connect_timeout_ms):
                        continue
                    self.logger.warning("WiFi timeout, retry in {} ms".format(wait_ms), file_only=True)
                else:
                    self.logger.warning(
                        'SSID "{}" not found, retry in {} ms'.format(self.settings.PUC_WIFI_SSID, wait_ms),
                        file_only=True
                    )
            except Exception as e:
                self.logger.error("WiFi error: {}, retry in {} ms".format(e, wait_ms), file_only=True)

            self._state = self.DISCONNECTED
            if wait_ms > 0:
                await asyncio.sleep_ms(int(wait_ms))
            attempt += 1

    async def ensure_connected(self, connect_timeout_ms=10000):
        self._sync_state_from_hardware()
        if not self.is_connected():
            return await self.connect_forever(connect_timeout_ms=connect_timeout_ms)
        return True
