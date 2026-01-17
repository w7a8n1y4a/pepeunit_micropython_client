from .settings import Settings
from .schema_manager import SchemaManager
from .logger import Logger

from umqtt.simple import MQTTClient, MQTTException


class PepeunitMqttClient:
    def __init__(self, settings: Settings, schema_manager: SchemaManager, logger: Logger):
        self.settings = settings
        self.schema_manager = schema_manager
        self.logger = logger
        self._client = None
        self._input_handler = None

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
        self.logger.info('Disconnected from MQTT Broker', file_only=True)

    def _reconnect(self):
        self.disconnect()
        self.connect()
        self.subscribe_all_schema_topics()
        self.logger.info('Reconnected to MQTT Broker')

    def set_input_handler(self, handler):
        self._input_handler = handler

    def _get_all_schema_topics(self):
        topics_set = set()
        for topic_list in self.schema_manager.input_base_topic.values():
            topics_set.update(topic_list)
        for topic_list in self.schema_manager.input_topic.values():
            topics_set.update(topic_list)
        return list(topics_set)

    def subscribe_all_schema_topics(self):
        topics = self._get_all_schema_topics()
        self.logger.info('Need a subscription for {} topics'.format(len(topics)))
        if topics:
            self.subscribe_topics(topics)

    def subscribe_topics(self, topics):
        topics = topics or []
        try:
            for topic in topics:
                self._client.subscribe(topic)
            self.logger.info('Success subscribed to {} topics'.format(len(topics)))
        except MQTTException as e:
            self._reconnect()

    def publish(self, topic, message):
        try:
            self._client.publish(topic, message)
        except MQTTException as e:
            self._reconnect()

    def ping(self):
        try:
            self._client.ping()
        except MQTTException as e:
            self._reconnect()

    def _on_message(self, topic, msg):
        class Msg:
            pass
        m = Msg()
        m.topic = topic.decode('utf-8') if isinstance(topic, bytes) else topic
        m.payload = msg.decode('utf-8') if isinstance(msg, bytes) else msg

        if self._input_handler:
            self._input_handler(m)

    def check_msg(self):
        try:
            return self._client.check_msg()
        except MQTTException as e:
            self._reconnect()
