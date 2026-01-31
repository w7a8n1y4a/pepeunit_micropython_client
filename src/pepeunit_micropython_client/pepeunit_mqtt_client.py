from .settings import Settings
from .schema_manager import SchemaManager
from .logger import Logger

import utils

from umqtt.simple import MQTTClient, MQTTException


class PepeunitMqttClient:
    def __init__(self, settings: Settings, schema_manager: SchemaManager, logger: Logger):
        self.settings = settings
        self.schema_manager = schema_manager
        self.logger = logger
        self._client = None
        self._input_handler = None
        self._inbox = None
        self._outbox = None
        self._ping_pending = False
        self.dropped_in = 0
        self.dropped_out = 0
        self.replaced_in = 0

    def _get_client(self):
        c = MQTTClient(
            client_id=self.settings.unit_uuid,
            server=self.settings.PU_MQTT_HOST,
            port=self.settings.PU_MQTT_PORT,
            user=self.settings.PU_AUTH_TOKEN,
            password="",
            keepalive=self.settings.PU_MQTT_KEEPALIVE,
            socket_timeout=5,
        )
        c.set_callback(self._on_message)
        return c

    def connect(self):
        self._client = self._get_client()
        self._client.connect()
        self.logger.info('Connected to MQTT Broker')

    def disconnect(self):
        if not self._client:
            return
        self._client.disconnect()
        self._client = None
        self._inbox = None
        self._outbox = None
        self._ping_pending = False
        self.logger.info('Disconnected from MQTT Broker', file_only=True)

    def _format_mqtt_exception(self, action, error):
        try:
            cause = getattr(error, "cause", None)
            errno = getattr(error, "errno", None)
            transport = getattr(error, "transport", None)
            return "MQTT error during {}: {} (transport={}, errno={}, cause={})".format(
                action, error, transport, errno, repr(cause)
            )
        except Exception:
            return "MQTT error during {}: {}".format(action, error)

    def _reconnect(self, reason=None):
        if reason:
            self.logger.warning(reason, file_only=True)
        self.disconnect()
        self.connect()
        self.subscribe_all_schema_topics()
        self.logger.info('Reconnected to MQTT Broker')

    def set_input_handler(self, handler):
        self._input_handler = handler

    @staticmethod
    def _topic_depth(topic):
        try:
            if isinstance(topic, bytes):
                topic = topic.decode('utf-8')
            if not topic:
                return 0
            return topic.count('/') + 1
        except Exception:
            return 0

    def _enqueue_incoming(self, msg):
        if self._inbox is None:
            self._inbox = msg
            return

        old = self._inbox
        new_is_5 = self._topic_depth(getattr(msg, "topic", "")) == 5
        old_is_5 = self._topic_depth(getattr(old, "topic", "")) == 5

        if new_is_5 and not old_is_5:
            self._inbox = msg
            self.replaced_in += 1
        else:
            self.dropped_in += 1

    def _get_all_schema_topics(self):
        topics_set = set()
        idx = 0
        for topic_list in self.schema_manager.input_base_topic.values():
            topics_set.update(topic_list)
            idx += 1
            utils._yield(idx, every=8)
        for topic_list in self.schema_manager.input_topic.values():
            topics_set.update(topic_list)
            idx += 1
            utils._yield(idx, every=8)
        return list(topics_set)

    def subscribe_all_schema_topics(self):
        topics = self._get_all_schema_topics()
        self.logger.info('Need a subscription for {} topics'.format(len(topics)))
        if topics:
            self.subscribe_topics(topics)

    def subscribe_topics(self, topics):
        topics = topics or []
        try:
            for idx, topic in enumerate(topics, 1):
                self._client.subscribe(topic)
                utils._yield(idx, every=8)
            self.logger.info('Success subscribed to {} topics'.format(len(topics)))
        except MQTTException as e:
            self._reconnect(self._format_mqtt_exception("subscribe", e))

    def publish(self, topic, message):
        if self._client is None:
            return
        if self._outbox is None:
            self._outbox = (topic, message)
        else:
            self.dropped_out += 1

    def publish_now(self, topic, message):
        if self._client is None:
            return
        try:
            self._client.publish(topic, message)
        except MQTTException as e:
            self._reconnect(self._format_mqtt_exception("publish", e))

    def _can_write(self):
        try:
            can_write = getattr(self._client, "can_write", None)
            if can_write:
                return bool(can_write())
        except Exception:
            pass
        return True

    def flush_outbox_once(self):
        if self._client is None or self._outbox is None:
            return False
        if not self._can_write():
            return False
        topic, message = self._outbox
        try:
            self._client.publish(topic, message)
            self._outbox = None
            return True
        except MQTTException as e:
            self._outbox = None
            self._reconnect(self._format_mqtt_exception("publish", e))
            return False

    def ping(self):
        self._ping_pending = True

    def flush_ping_once(self):
        if not self._ping_pending or self._client is None:
            return False
        if not self._can_write():
            return False
        try:
            self._client.ping()
            self._ping_pending = False
            return True
        except MQTTException as e:
            self._ping_pending = False
            self._reconnect(self._format_mqtt_exception("ping", e))
            return False

    def _on_message(self, topic, msg):
        class Msg:
            pass
        m = Msg()
        m.topic = topic.decode('utf-8') if isinstance(topic, bytes) else topic
        m.payload = msg
        self._enqueue_incoming(m)

    def check_msg(self):
        try:
            return self._client.check_msg()
        except MQTTException as e:
            self._reconnect(self._format_mqtt_exception("check_msg", e))

    def dispatch_one(self):
        if self._inbox is None:
            return False
        m = self._inbox
        self._inbox = None
        if self._input_handler:
            self._input_handler(m)
        return True

    def service_io(self, budget_ms=5, max_in=16, max_out=1):
        if self._client is None:
            return
        import time
        start = time.ticks_ms()

        drained = 0
        while drained < max_in:
            res = self.check_msg()
            if res is None:
                break
            drained += 1
            if budget_ms is not None and time.ticks_diff(time.ticks_ms(), start) >= budget_ms:
                break
            utils._yield(drained, every=4, do_gc=False)

        self.flush_ping_once()

        sent = 0
        while sent < max_out:
            if not self.flush_outbox_once():
                break
            sent += 1
