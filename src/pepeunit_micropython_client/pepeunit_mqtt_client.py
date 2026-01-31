import time
import uasyncio as asyncio

from mqtt_as import MQTTClient


class _Msg:
    __slots__ = ("topic", "payload", "retained", "properties")


class PepeunitMqttClient:
    def __init__(self, settings, schema_manager, logger):
        self.settings = settings
        self.schema_manager = schema_manager
        self.logger = logger

        self._input_handler = None

        self._client = None
        self._wifi_manager = None
        self._reconnect_attempt = 0
        self._next_reconnect_ms = 0
        self._reconnect_in_progress = False
        self._just_reconnected = False
        self._last_error = None

    def _to_bytes(self, v):
        if v is None:
            return b""
        if isinstance(v, bytes):
            return v
        return str(v).encode("utf-8")

    def set_wifi_manager(self, wifi_manager):
        self._wifi_manager = wifi_manager

    def is_connected(self):
        cli = self._client
        if cli is None:
            return False
        isconn = getattr(cli, "isconnected", None)
        if not isconn:
            return False
        try:
            return bool(isconn())
        except Exception:
            return False

    def get_last_rx_ms(self):
        cli = self._client
        if cli is None:
            return None
        return getattr(cli, "last_rx", None)

    def get_ping_interval_ms(self):
        cli = self._client
        if cli is None:
            return int(self.settings.PU_MQTT_PING_INTERVAL) * 1000
        val = getattr(cli, "_ping_interval", None)
        if val is None:
            return int(self.settings.PU_MQTT_PING_INTERVAL) * 1000
        return val

    def mark_disconnected(self, reason=None):
        cli = self._client
        if cli is None:
            return
        try:
            reconnect = getattr(cli, "_reconnect", None)
            if reconnect:
                reconnect()
            close = getattr(cli, "_close", None)
            if close:
                close()
        except Exception:
            pass
        self._client = None
        self._just_reconnected = False
        if reason:
            self._last_error = reason
        if reason:
            self.logger.warning("MQTT force disconnect: {}".format(reason), file_only=True)

    def get_last_error(self):
        return self._last_error

    def _reconnect_interval_ms(self, attempt):
        if attempt <= 0:
            return 0
        base = 5000
        interval = base * (2 ** (attempt - 1))
        max_wait = getattr(self.settings, "PUC_MAX_RECONNECTION_INTERVAL", 60000)
        if interval > max_wait:
            return max_wait
        return int(interval)

    def consume_reconnected(self):
        if not self._just_reconnected:
            return False
        self._just_reconnected = False
        return True

    async def ensure_connected(self):
        if self._reconnect_in_progress:
            return False

        now = time.ticks_ms()
        if self.is_connected():
            last_rx = self.get_last_rx_ms()
            ping_ms = self.get_ping_interval_ms()
            if last_rx is None or not ping_ms:
                self._reconnect_attempt = 0
                return True
            stale_ms = int(ping_ms) * 4
            if time.ticks_diff(now, last_rx) <= stale_ms:
                self._reconnect_attempt = 0
                return True
            self.mark_disconnected("stale rx > {} ms".format(stale_ms))
            self._next_reconnect_ms = 0

        if self._next_reconnect_ms and time.ticks_diff(now, self._next_reconnect_ms) < 0:
            return False

        self._reconnect_in_progress = True
        try:
            if self._wifi_manager and not self._wifi_manager.is_connected():
                await self._wifi_manager.ensure_connected()
            await self.connect()
            self._reconnect_attempt = 0
            self._next_reconnect_ms = 0
            self._just_reconnected = True
            self.logger.warning("MQTT reconnected", file_only=True)
            return True
        except Exception as e:
            self._last_error = e
            self._reconnect_attempt += 1
            wait_ms = self._reconnect_interval_ms(self._reconnect_attempt)
            self._next_reconnect_ms = time.ticks_add(now, wait_ms)
            self.logger.warning(
                "MQTT reconnect failed: {}, next try in {} ms".format(e, wait_ms),
                file_only=True
            )
            return False
        finally:
            self._reconnect_in_progress = False

    def _on_message(self, topic, msg, retained=False, properties=None):
        if self._input_handler is None:
            return
        m = _Msg()
        try:
            m.topic = topic.decode("utf-8") if isinstance(topic, (bytes, bytearray, memoryview)) else topic
        except Exception:
            m.topic = str(topic)
        m.payload = msg
        m.retained = retained
        m.properties = properties

        try:
            self._input_handler(m)
        except Exception as e:
            self.logger.error("MQTT input handler error: {}".format(e), file_only=True)

    def set_input_handler(self, handler):
        self._input_handler = handler

    async def connect(self):
        if self.is_connected():
            return
        self._client = MQTTClient(
            server=self.settings.PU_MQTT_HOST,
            port=self.settings.PU_MQTT_PORT,
            user=self._to_bytes(self.settings.PU_AUTH_TOKEN),
            password=b"",
            keepalive=self.settings.PU_MQTT_KEEPALIVE,
            ping_interval=self.settings.PU_MQTT_PING_INTERVAL,
            client_id=self._to_bytes(self.settings.unit_uuid),
            subs_cb=self._on_message,
        )
        await self._client.connect()

        self.logger.info("Connected to MQTT Broker (mqtt_as)")

    async def disconnect(self):
        if self._client is None:
            return
        try:
            await self._client.disconnect()
        finally:
            self._client = None

    def _get_all_schema_topics(self):
        raise NotImplementedError("Use subscribe_all_schema_topics() streaming implementation.")

    async def subscribe_all_schema_topics(self):
        if not self.is_connected():
            return False
        try:
            idx = 0
            for topic_list in self.schema_manager.input_base_topic.values():
                for topic in topic_list:
                    await self._client.subscribe(self._to_bytes(topic), qos=0)
                    idx += 1
                    if (idx & 0x0F) == 0:
                        await asyncio.sleep_ms(0)
            for topic_list in self.schema_manager.input_topic.values():
                for topic in topic_list:
                    await self._client.subscribe(self._to_bytes(topic), qos=0)
                    idx += 1
                    if (idx & 0x0F) == 0:
                        await asyncio.sleep_ms(0)
            return True
        except Exception as e:
            self._last_error = e
            self.mark_disconnected("subscribe all failed: {}".format(e))
            return False

    async def subscribe_topics(self, topics):
        if not self.is_connected():
            return False
        try:
            topics = topics or ()
            idx = 0
            for topic in topics:
                await self._client.subscribe(self._to_bytes(topic), qos=0)
                idx += 1
                if (idx & 0x0F) == 0:
                    await asyncio.sleep_ms(0)
            return True
        except Exception as e:
            self._last_error = e
            self.mark_disconnected("subscribe failed: {}".format(e))
            return False

    async def publish(self, topic, message, retain=False, qos=0):
        if not self.is_connected():
            self._last_error = "publish while disconnected"
            return False
        try:
            await self._client.publish(self._to_bytes(topic), self._to_bytes(message), retain=retain, qos=qos)
            return True
        except Exception as e:
            self._last_error = e
            self.mark_disconnected("publish failed: {}".format(e))
            return False

