from .settings import Settings
from .schema_manager import SchemaManager
from .logger import Logger

try:
    from umqtt.simple import MQTTClient
except ImportError:
    MQTTClient = None


class PepeunitMqttClient:
    def __init__(self, settings: Settings, schema_manager: SchemaManager, logger: Logger):
        self.settings = settings
        self.schema_manager = schema_manager
        self.logger = logger
        self._client = None
        self._input_handler = None

    def _get_client(self):
        if MQTTClient is None:
            raise ImportError('umqtt.simple is required')
        # Client id can be token tail to avoid collisions
        cid = self.settings.PEPEUNIT_TOKEN[-12:] if self.settings.PEPEUNIT_TOKEN else 'pepeunit'
        c = MQTTClient(client_id=cid, server=self.settings.MQTT_URL, port=self.settings.MQTT_PORT, user=self.settings.PEPEUNIT_TOKEN, password='')
        c.set_callback(self._on_message)
        return c

    def connect(self):
        if not self._client:
            self._client = self._get_client()
        try:
            self._client.connect()
            self.logger.info('Connected to MQTT Broker!')
        except Exception as e:
            self.logger.critical('Failed to connect to MQTT: ' + str(e))
            raise

    def disconnect(self):
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                pass

    def set_input_handler(self, handler):
        self._input_handler = handler

    def subscribe_topics(self, topics):
        if self._client:
            for topic in topics:
                try:
                    self._client.subscribe(topic)
                except Exception as e:
                    self.logger.error('Subscribe error: ' + str(e))

    def publish(self, topic, message):
        if self._client:
            try:
                self._client.publish(topic, message)
            except Exception as e:
                self.logger.error('Publish error: ' + str(e))

    def _on_message(self, topic, msg):
        class Msg:
            pass
        m = Msg()
        m.topic = topic.decode('utf-8') if isinstance(topic, bytes) else topic
        m.payload = msg
        try:
            if self._input_handler:
                self._input_handler(m)
        except Exception as e:
            self.logger.error('Error processing MQTT message: ' + str(e))

    def check_msg(self):
        # Non-blocking check for new messages (call in main loop)
        if self._client:
            try:
                self._client.check_msg()
            except Exception:
                pass

