import time
import network
import uasyncio as asyncio
import sys

import utils

from .settings import Settings
from .logger import Logger


class WifiManager:
    _PLATFORM = sys.platform

    def __init__(self, settings: Settings, logger: Logger):
        self.logger = logger
        self.settings = settings
        self._sta = None

    @staticmethod
    def _decode_ssid(value):
        return utils.to_str(value)

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

    def is_connected(self):
        return bool(self.get_sta().isconnected())

    def get_connected_ssid(self):
        sta = self.get_sta()
        return self._decode_ssid(sta.config("essid"))

    async def _force_sta_reset(self):
        self.logger.info("WiFi station prepare", file_only=True)
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
        scan = sta.scan()
        for idx, ap in enumerate(scan, 1):
            ap_ssid = ap[0]
            ap_ssid = self._decode_ssid(ap_ssid)
            if ap_ssid == self.settings.PUC_WIFI_SSID:
                return True
            await utils.ayield(idx, every=8, do_gc=False)
        return False

    async def connect_once(self, timeout_ms=10000):
        sta = self.get_sta()

        if sta.isconnected():
            connected_ssid = self.get_connected_ssid()
            if self.settings.PUC_WIFI_SSID and connected_ssid == self.settings.PUC_WIFI_SSID:
                return True
            self.logger.warning(
                'WiFi connected to "{}" but target ssid is "{}" - forcing reconnect'.format(
                    connected_ssid, self.settings.PUC_WIFI_SSID
                ),
                file_only=True
            )
            await self._force_sta_reset()

        await self._force_sta_reset()

        self.logger.warning("Attempting connect to WiFi", file_only=True)
        sta.connect(str(self.settings.PUC_WIFI_SSID), str(self.settings.PUC_WIFI_PASS))

        started = time.ticks_ms()
        while not sta.isconnected():
            if time.ticks_diff(time.ticks_ms(), started) >= int(timeout_ms):
                return False
            await asyncio.sleep_ms(200)

        return True

    async def connect_forever(self, connect_timeout_ms=10000):
        attempt = 0
        while True:
            if self.is_connected():
                connected_ssid = self.get_connected_ssid()
                if self.settings.PUC_WIFI_SSID and connected_ssid and connected_ssid != self.settings.PUC_WIFI_SSID:
                    self.logger.warning(
                        'WiFi unexpected cached connection to "{}"; need "{}" - disconnecting'.format(
                            connected_ssid, self.settings.PUC_WIFI_SSID
                        ),
                        file_only=True
                    )
                    await self._force_sta_reset()
                    attempt += 1
                    continue
                self.logger.warning("WiFi connected: " + str(self.get_sta().ifconfig()), file_only=True)
                return True

            wait_ms = utils.backoff_interval_ms(
                attempt,
                5000,
                self.settings.PUC_MAX_RECONNECTION_INTERVAL,
            )

            try:
                found = await self.scan_has_target_ssid()
                if found:
                    ok = await self.connect_once(timeout_ms=connect_timeout_ms)
                    if ok:
                        continue
                    self.logger.warning("WiFi connect timeout, next try in {} ms".format(wait_ms), file_only=True)
                else:
                    self.logger.warning(
                        'WiFi ssid "{}" not found, next scan in {} ms'.format(self.settings.PUC_WIFI_SSID, wait_ms),
                        file_only=True
                    )
            except Exception as e:
                self.logger.error("WiFi error: {}, next try in {} ms".format(str(e), wait_ms), file_only=True)

            if wait_ms > 0:
                await asyncio.sleep_ms(int(wait_ms))
            attempt += 1

    async def ensure_connected(self, connect_timeout_ms=10000):
        if not self.is_connected():
            return await self.connect_forever(connect_timeout_ms=connect_timeout_ms)
        return True
