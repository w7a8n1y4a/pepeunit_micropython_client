from .settings import Settings
from .schema_manager import SchemaManager
from .logger import Logger

from umqtt.simple import MQTTClient


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
            keepalive=self.settings.PU_MQTT_PING_INTERVAL,
            socket_timeout=5,
        )
        c.set_callback(self._on_message)
        return c

    def connect(self):
        self._client = self._get_client()
        self._client.connect()
        self.logger.info('Connected to MQTT Broker')

    def disconnect(self):
        if self._client:
            self._client.disconnect()
            self.logger.info('Disconnected from MQTT Broker', file_only=True)

    def set_input_handler(self, handler):
        self._input_handler = handler

    def subscribe_topics(self, topics):
        if self._client:
            for topic in topics:
                self._client.subscribe(topic)
            self.logger.info(f'Success subscribed to {len(topics)} topics')

    def publish(self, topic, message):
        if self._client:
            self._client.publish(topic, message)

    def _on_message(self, topic, msg):
        class Msg:
            pass
        m = Msg()
        m.topic = topic.decode('utf-8') if isinstance(topic, bytes) else topic
        m.payload = msg.decode('utf-8') if isinstance(msg, bytes) else msg

        if self._input_handler:
            self._input_handler(m)

    def check_msg(self):
        self._client.check_msg()
