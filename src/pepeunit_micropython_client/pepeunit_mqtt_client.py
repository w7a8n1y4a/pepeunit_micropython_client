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

    def _to_bytes(self, v):
        if v is None:
            return b""
        if isinstance(v, bytes):
            return v
        return str(v).encode("utf-8")

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

