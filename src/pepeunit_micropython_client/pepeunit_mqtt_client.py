import time
import uasyncio as asyncio
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

    def __exit__(self, *_):
        c = self._client._drop_input_refcount - 1
        self._client._drop_input_refcount = c if c > 0 else 0
        return False

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, *_):
        return self.__exit__()


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
        self._input_busy = False
        self._publish_lock = asyncio.Lock()

        self._client = None
        self._wifi_manager = None
        self._reconnect_attempt = 0
        self._next_reconnect_ms = 0
        self._state = self.DISCONNECTED
        self._just_reconnected = False

    def set_wifi_manager(self, wifi_manager):
        self._wifi_manager = wifi_manager

    @property
    def connection_state(self):
        return self._state

    def _can_publish(self):
        if self._wifi_manager and not self._wifi_manager.is_connected():
            return False
        if not self._client or not self._client.is_connected():
            return False
        return True

    def is_connected(self):
        return self._state == self.CONNECTED

    def _sync_state_from_client(self):
        if self._state >= self.CONNECTED and not (self._client and self._client.is_connected()):
            self.mark_disconnected("client disconnected")

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
        if not self.is_connected():
            if self._state == self.RECONNECTING:
                return False
            if self._next_reconnect_ms and time.ticks_diff(now, self._next_reconnect_ms) < 0:
                return False
            return True

        # Connected — check for stale rx
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
            wait_ms = utils.backoff_interval_ms(self._reconnect_attempt, 500, 2000)
            self._next_reconnect_ms = time.ticks_add(time.ticks_ms(), wait_ms)
            self.logger.warning(
                "MQTT reconnect failed: {}, next in {} ms".format(e, wait_ms), file_only=True
            )
            if wait_ms >= 2000:
                raise e
        finally:
            if self._state == self.RECONNECTING:
                self._state = self.DISCONNECTED

    async def ensure_connected(self):
        self._sync_state_from_client()
        now = time.ticks_ms()
        if self._should_attempt_reconnect(now):
            await self._attempt_reconnect(now)

    def drop_input(self):
        return _InputDropContext(self)

    def _on_message(self, topic, msg, retained=False, properties=None):
        if self._drop_input_refcount or not self._input_handler:
            return
        if self._input_busy:
            print("THROTTLE DROP MQTT INPUT")
            return
        m = _Msg()
        m.topic = utils.to_str(topic)
        m.payload = msg
        m.retained = retained
        m.properties = properties
        self._input_busy = True
        utils.spawn(self._run_input_handler(m))

    async def _run_input_handler(self, msg):
        try:
            await self._input_handler(msg)
        finally:
            self._input_busy = False

    def set_input_handler(self, handler):
        self._input_handler = handler

    async def connect(self):
        if self.is_connected():
            return
        self._client = MQTTClient(
            server=self.settings.PU_MQTT_HOST,
            port=self.settings.PU_MQTT_PORT,
            user=utils.to_bytes(self.settings.PU_AUTH_TOKEN),
            password=b"",
            keepalive=self.settings.PU_MQTT_KEEPALIVE,
            ping_interval=self.settings.PU_MQTT_PING_INTERVAL,
            client_id=utils.to_bytes(self.settings.unit_uuid),
            subs_cb=self._on_message,
            should_drop=lambda: bool(self._drop_input_refcount),
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
        if not self.is_connected():
            return
        try:
            idx = 0
            for section in (self.schema_manager.input_base_topic, self.schema_manager.input_topic):
                for topic_list in section.values():
                    for topic in topic_list:
                        await self._client.subscribe(utils.to_bytes(topic), qos=0)
                        idx += 1
                        await utils.ayield(idx, every=4, do_gc=True)
            self.logger.info("Subscribed to {} topics".format(idx))
        except Exception as e:
            self.mark_disconnected("subscribe failed: {}".format(e))

    async def publish(self, topic, message, retain=False, qos=0):
        if not self._can_publish():
            return False
        async with self._publish_lock:
            if not self._can_publish():
                return False
            try:
                await self._client.publish(utils.to_bytes(topic), utils.to_bytes(message), retain=retain, qos=qos)
                return True
            except Exception as e:
                self.mark_disconnected("publish failed: {}".format(e))
                return False
