import time
import network

from .settings import Settings
from .logger import Logger


class WifiManager:
    def __init__(self, settings: Settings, logger: Logger):
        self.logger = logger
        self.settings = settings
        self._sta = None

    @staticmethod
    def _decode_ssid(value):
        if isinstance(value, bytes):
            try:
                return value.decode()
            except Exception:
                return ""
        if value is None:
            return ""
        return str(value)

    def get_sta(self):
        if self._sta is None:
            self.logger.warning("WiFi station run create", file_only=True)
            sta = network.WLAN(network.STA_IF)
            if not sta.active():
                sta.active(True)
            try:
                sta.config(reconnects=0)
            except Exception:
                pass
            self._sta = sta
        return self._sta

    def is_connected(self):
        return bool(self.get_sta().isconnected())

    def get_connected_ssid(self):
        sta = self.get_sta()
        for key in ("essid", "ssid"):
            try:
                return self._decode_ssid(sta.config(key))
            except Exception:
                pass
        return ""

    def _force_sta_reset(self):
        self.logger.info("WiFi station prepare", file_only=True)
        sta = self.get_sta()
        try:
            sta.disconnect()
        except Exception:
            pass
        try:
            sta.active(False)
        except Exception:
            pass
        time.sleep_ms(200)
        try:
            sta.active(True)
        except Exception:
            pass
        try:
            sta.config(reconnects=0)
        except Exception:
            pass
        time.sleep_ms(200)

    def scan_has_target_ssid(self):
        sta = self.get_sta()
        self.logger.info("WiFi run scan existing ssid`s", file_only=True)
        scan = sta.scan()
        for ap in scan:
            ap_ssid = ap[0]
            ap_ssid = self._decode_ssid(ap_ssid)
            if ap_ssid == self.settings.PUC_WIFI_SSID:
                return True
        return False

    def connect_once(self, timeout_ms=10000):
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
            self._force_sta_reset()

        self._force_sta_reset()

        self.logger.warning("Attempting connect to WiFi", file_only=True)
        sta.connect(str(self.settings.PUC_WIFI_SSID), str(self.settings.PUC_WIFI_PASS))

        started = time.ticks_ms()
        while not sta.isconnected():
            if time.ticks_diff(time.ticks_ms(), started) >= int(timeout_ms):
                return False
            time.sleep_ms(200)

        return True

    def connect_forever(self, connect_timeout_ms=10000):
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
                    self._force_sta_reset()
                    attempt += 1
                    continue
                try:
                    self.logger.warning("WiFi connected: " + str(self.get_sta().ifconfig()), file_only=True)
                except Exception:
                    self.logger.warning("WiFi connected", file_only=True)
                return True

            wait_ms = self._reconnection_interval_ms(attempt)

            try:
                if self.scan_has_target_ssid():
                    ok = self.connect_once(timeout_ms=connect_timeout_ms)
                    if ok:
                        continue
                    self.logger.warning("WiFi connect timeout, next try in {} ms".format(wait_ms), file_only=True)
                else:
                    self.logger.warning('WiFi ssid "{}" not found, next scan in {} ms'.format(self.settings.PUC_WIFI_SSID, wait_ms), file_only=True)
            except Exception as e:
                self.logger.error("WiFi error: {}, next try in {} ms".format(str(e), wait_ms), file_only=True)

            if wait_ms > 0:
                time.sleep_ms(wait_ms)
            attempt += 1

    def ensure_connected(self):
        if not self.is_connected():
            return self.connect_forever()
        return True

    def _reconnection_interval_ms(self, attempt):
        if attempt <= 0:
            return 0
        base = 5000
        interval = base * (2 ** (attempt - 1))
        if interval > self.settings.PUC_MAX_RECONNECTION_INTERVAL:
            return self.settings.PUC_max_reconnection_interval
        return int(interval)
