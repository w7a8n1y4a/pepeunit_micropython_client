try:
    import uasyncio as asyncio  # MicroPython
except ImportError:  # CPython
    import asyncio

from mqtt_as import MQTTClient, config as mqtt_as_config


class _Msg:
    __slots__ = ("topic", "payload", "retained", "properties")


class PepeunitMqttAsClient:
    """
    Thin adapter around `mqtt_as.MQTTClient` to match the subset of the
    `PepeunitMqttClient` API used by `PepeunitClient` and examples.
    """

    def __init__(self, settings, schema_manager, logger):
        self.settings = settings
        self.schema_manager = schema_manager
        self.logger = logger

        self._input_handler = None

        self._client = None

    # ---- Internal helpers
    def _to_bytes(self, v):
        if v is None:
            return b""
        if isinstance(v, bytes):
            return v
        return str(v).encode("utf-8")

    def _on_message(self, topic, msg, retained=False, properties=None):
        # mqtt_as passes `topic` and `msg` as bytes.
        if self._input_handler is None:
            return
        m = _Msg()
        try:
            m.topic = topic.decode("utf-8") if isinstance(topic, (bytes, bytearray, memoryview)) else topic
        except Exception:
            m.topic = str(topic)
        # Do NOT copy payload: mqtt_as can provide memoryview for efficiency.
        m.payload = msg
        # keep compat with old code which doesn't care about retain/props
        m.retained = retained
        m.properties = properties

        try:
            self._input_handler(m)
        except Exception as e:
            try:
                self.logger.error("MQTT input handler error: {}".format(e), file_only=True)
            except Exception:
                pass

    # ---- Public API (compat)
    def set_input_handler(self, handler):
        self._input_handler = handler

    async def connect(self):
        cfg = mqtt_as_config.copy()
        cfg["server"] = self.settings.PU_MQTT_HOST
        cfg["port"] = self.settings.PU_MQTT_PORT
        # mqtt_as expects bytes for all MQTT strings sent on-wire.
        cfg["user"] = self._to_bytes(self.settings.PU_AUTH_TOKEN)
        cfg["password"] = b""
        cfg["keepalive"] = self.settings.PU_MQTT_KEEPALIVE
        # mqtt_as expects bytes for client_id in many ports
        cfg["client_id"] = self._to_bytes(self.settings.unit_uuid)
        cfg["subs_cb"] = self._on_message
        # Let mqtt_as handle Wi-Fi too (safe even if already connected)
        cfg["ssid"] = getattr(self.settings, "PUC_WIFI_SSID", None) or None
        cfg["wifi_pw"] = getattr(self.settings, "PUC_WIFI_PASS", None) or None
        # callback mode (not queue/event mode)
        cfg["queue_len"] = 0

        self._client = MQTTClient(cfg)
        await self._client.connect()

        try:
            self.logger.info("Connected to MQTT Broker (mqtt_as)")
        except Exception:
            pass

    async def disconnect(self):
        if self._client is None:
            return
        try:
            await self._client.disconnect()
        finally:
            self._client = None

    def _get_all_schema_topics(self):
        # Intentionally removed in low-RAM build: building a full set/list can OOM.
        raise NotImplementedError("Use subscribe_all_schema_topics() streaming implementation.")

    async def subscribe_all_schema_topics(self):
        # Stream subscriptions to avoid allocating a huge set/list.
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

    async def subscribe_topics(self, topics):
        # Accept any iterable without forcing a list allocation.
        topics = topics or ()
        idx = 0
        for topic in topics:
            await self._client.subscribe(self._to_bytes(topic), qos=0)
            idx += 1
            if (idx & 0x0F) == 0:
                await asyncio.sleep_ms(0)

    async def publish(self, topic, message, retain=False, qos=0):
        if self._client is None:
            return
        await self._client.publish(self._to_bytes(topic), self._to_bytes(message), retain=retain, qos=qos)


