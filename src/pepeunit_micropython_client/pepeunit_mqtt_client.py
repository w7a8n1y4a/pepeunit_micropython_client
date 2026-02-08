import time
import utils

from mqtt_as import MQTTClient


class _Msg:
    __slots__ = ("topic", "payload", "retained", "properties")


class _InputDropContext:
    __slots__ = ("_client",)

    def __init__(self, client):
        self._client = client

    def __enter__(self):
        self._client._drop_input_refcount += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        cnt = self._client._drop_input_refcount - 1
        self._client._drop_input_refcount = cnt if cnt > 0 else 0
        return False

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc, tb):
        return self.__exit__(exc_type, exc, tb)


class PepeunitMqttClient:
    DISCONNECTED = 0
    RECONNECTING = 1
    CONNECTED = 2

    def __init__(self, settings, schema_manager, logger):
        self.settings = settings
        self.schema_manager = schema_manager
        self.logger = logger

        self._input_handler = None
        self._drop_input_refcount = 0
        self._msg = _Msg()

        self._client = None
        self._wifi_manager = None
        self._reconnect_attempt = 0
        self._next_reconnect_ms = 0
        self._state = self.DISCONNECTED
        self._just_reconnected = False

    def set_wifi_manager(self, wifi_manager):
        self._wifi_manager = wifi_manager

    def get_state(self):
        if self._state >= self.CONNECTED and not (self._client and self._client.is_connected()):
            self._state = self.DISCONNECTED
        return self._state

    def is_connected(self):
        return self.get_state() >= self.CONNECTED

    def mark_disconnected(self, reason=None):
        self._state = self.DISCONNECTED
        self._just_reconnected = False

        if self._client:
            self._client._reconnect()
            self._client = None

        if reason:
            self.logger.warning("MQTT force disconnect: {}".format(reason), file_only=True)

    def consume_reconnected(self):
        if not self._just_reconnected:
            return False
        self._just_reconnected = False
        return True

    def _should_attempt_reconnect(self, now):
        state = self.get_state()

        if state == self.RECONNECTING:
            return False

        if state >= self.CONNECTED:
            ping_ms = self.settings.PU_MQTT_PING_INTERVAL * 1000
            last_rx = self._client.last_rx if self._client else None

            if last_rx is None or not ping_ms:
                self._reconnect_attempt = 0
                return False

            stale_ms = ping_ms * 2
            if time.ticks_diff(now, last_rx) <= stale_ms:
                self._reconnect_attempt = 0
                return False

            self.mark_disconnected("stale rx > {} ms".format(stale_ms))
            self._next_reconnect_ms = 0

        if self._next_reconnect_ms and time.ticks_diff(now, self._next_reconnect_ms) < 0:
            return False

        return True

    async def _attempt_reconnect(self, now):
        self._state = self.RECONNECTING
        try:
            if self._wifi_manager:
                await self._wifi_manager.ensure_connected()

            await self.connect()

            self._reconnect_attempt = 0
            self._next_reconnect_ms = 0
            self._just_reconnected = True

            self.logger.warning("MQTT reconnected", file_only=True)
        except Exception as e:
            self._reconnect_attempt += 1

            wait_ms = utils.backoff_interval_ms(
                self._reconnect_attempt,
                500,
                2000,
            )

            if wait_ms >= 2000:
                raise e

            self._next_reconnect_ms = time.ticks_add(now, wait_ms)
            self.logger.warning(
                "MQTT reconnect failed: {}, next try in {} ms".format(e, wait_ms),
                file_only=True
            )
        finally:
            if self._state == self.RECONNECTING:
                self._state = self.DISCONNECTED

    async def ensure_connected(self):
        now = time.ticks_ms()
        if self._should_attempt_reconnect(now):
            await self._attempt_reconnect(now)

    def _on_message(self, topic, msg, retained=False, properties=None):
        if not self._drop_input_refcount or self._input_handler:
            m = self._msg
            m.topic = utils.to_str(topic)
            m.payload = msg
            m.retained = retained
            m.properties = properties

            try:
                self._input_handler(m)
            except Exception as e:
                self.logger.error("MQTT input handler error: {}".format(e), file_only=True)

    def set_input_handler(self, handler):
        self._input_handler = handler

    def drop_input(self):
        return _InputDropContext(self)

    async def connect(self):
        if not self.is_connected():
            self._client = MQTTClient(
                server=self.settings.PU_MQTT_HOST,
                port=self.settings.PU_MQTT_PORT,
                user=utils.to_bytes(self.settings.PU_AUTH_TOKEN),
                password=b"",
                keepalive=self.settings.PU_MQTT_KEEPALIVE,
                ping_interval=self.settings.PU_MQTT_PING_INTERVAL,
                client_id=utils.to_bytes(self.settings.unit_uuid),
                subs_cb=self._on_message,
            )
            await self._client.connect()
            self._state = self.CONNECTED

            self.logger.info("Connected to MQTT Broker")

    async def disconnect(self):
        if self._client:
            try:
                await self._client.disconnect()
            finally:
                self._client = None
                self._state = self.DISCONNECTED
                self._just_reconnected = False

    async def subscribe_all_schema_topics(self):
        if self.is_connected():
            try:
                idx = 0
                for topic_list in self.schema_manager.input_base_topic.values():
                    for topic in topic_list:
                        await self._client.subscribe(utils.to_bytes(topic), qos=0)
                        idx += 1
                        if (idx & 0x0F) == 0:
                            await utils.ayield(idx, every=16, do_gc=False)
                for topic_list in self.schema_manager.input_topic.values():
                    for topic in topic_list:
                        await self._client.subscribe(utils.to_bytes(topic), qos=0)
                        idx += 1
                        if (idx & 0x0F) == 0:
                            await utils.ayield(idx, every=16, do_gc=False)

                self.logger.info("Success subscribed to {} topics".format(idx))
            except Exception as e:
                self.mark_disconnected("subscribe all failed: {}".format(e))

    async def publish(self, topic, message, retain=False, qos=0):
        if self.is_connected():
            try:
                await self._client.publish(utils.to_bytes(topic), utils.to_bytes(message), retain=retain, qos=qos)
            except Exception as e:
                self.mark_disconnected("publish failed: {}".format(e))
