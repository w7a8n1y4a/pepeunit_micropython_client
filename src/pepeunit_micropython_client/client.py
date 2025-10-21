import ujson as json
import ubinascii as binascii
import time

from .settings import Settings
from .file_manager import FileManager
from .logger import Logger
from .schema_manager import SchemaManager
from .pepeunit_mqtt_client import PepeunitMqttClient
from .pepeunit_rest_client import PepeunitRestClient
from .enums import BaseInputTopicType, BaseOutputTopicType, RestartMode


class PepeunitClient:
    def __init__(
        self,
        env_file_path,
        schema_file_path,
        log_file_path,
        enable_mqtt=False,
        enable_rest=False,
        mqtt_client=None,
        rest_client=None,
        cycle_speed=0.1,
        restart_mode=RestartMode.ENV_SCHEMA_ONLY
    ):
        self.env_file_path = env_file_path
        self.schema_file_path = schema_file_path
        self.log_file_path = log_file_path
        self.enable_mqtt = enable_mqtt
        self.enable_rest = enable_rest
        self.cycle_speed = cycle_speed
        self.restart_mode = restart_mode

        self.settings = Settings(env_file_path)
        self.schema = SchemaManager(schema_file_path)

        self.logger = Logger(log_file_path, None, self.schema, self.settings)

        self.mqtt_client = (mqtt_client if mqtt_client else self._get_default_mqtt_client()) if enable_mqtt else None
        self.rest_client = (rest_client if rest_client else self._get_default_rest_client()) if enable_rest else None

        if self.mqtt_client:
            self.logger.mqtt_client = self.mqtt_client

        self.mqtt_input_handler = None
        self.mqtt_output_handler = None
        self.custom_update_handler = None

        self._running = False
        self._last_state_send = 0

    def _get_default_mqtt_client(self):
        return PepeunitMqttClient(self.settings, self.schema, self.logger)

    def _get_default_rest_client(self):
        return PepeunitRestClient(self.settings)

    @property
    def unit_uuid(self):
        token_parts = self.settings.PEPEUNIT_TOKEN.split('.')
        if len(token_parts) != 3:
            raise ValueError('Invalid JWT token format')
        payload = token_parts[1]
        # MicroPython: add padding for base64 urlsafe
        while len(payload) % 4 != 0:
            payload += '='
        # urlsafe base64 decode
        try:
            data = binascii.a2b_base64(payload.replace('-', '+').replace('_', '/'))
        except Exception:
            data = binascii.a2b_base64(payload)
        payload_data = json.loads(data)
        return payload_data['uuid']

    def set_cycle_speed(self, speed):
        if speed <= 0:
            raise ValueError('Cycle speed must be greater than 0')
        self.cycle_speed = speed

    def update_device_program(self, archive_path):
        # On MicroPython we avoid process restart; only update env/schema/data
        unit_directory = self._dirname(self.env_file_path) or '/'
        FileManager.extract_tar_gz(archive_path, unit_directory)
        try:
            import os
            os.remove(archive_path)
        except Exception:
            pass
        if self.restart_mode == RestartMode.ENV_SCHEMA_ONLY:
            self._update_env_schema_only()

    def _update_env_schema_only(self):
        try:
            self.settings.load_from_file()
            self.schema.update_from_file()
            if self.enable_mqtt and self.mqtt_client:
                self.subscribe_all_schema_topics()
            self.logger.info('Environment and schema updated successfully')
        except Exception as e:
            self.logger.error('Failed to update env and schema: ' + str(e))
            raise

    def get_system_state(self):
        return {
            'millis': int(time.time() * 1000),
            'mem_free': 0,
            'mem_alloc': 0,
            'freq': 0,
            'commit_version': self.settings.COMMIT_VERSION,
        }

    def set_mqtt_input_handler(self, handler):
        self.mqtt_input_handler = handler
        if self.mqtt_client:
            def combined_handler(msg):
                self._base_mqtt_input_func(msg)
                if self.mqtt_input_handler:
                    self.mqtt_input_handler(self, msg)
            self.mqtt_client.set_input_handler(combined_handler)

    def _base_mqtt_input_func(self, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode()) if hasattr(msg.payload, 'decode') else json.loads(msg.payload)
        except Exception:
            payload = {}
        try:
            for topic_key in self.schema.input_base_topic:
                if topic in self.schema.input_base_topic[topic_key]:
                    if topic_key == BaseInputTopicType.UPDATE_PEPEUNIT:
                        self._handle_update(payload)
                    elif topic_key == BaseInputTopicType.ENV_UPDATE_PEPEUNIT:
                        self._handle_env_update()
                    elif topic_key == BaseInputTopicType.SCHEMA_UPDATE_PEPEUNIT:
                        self._handle_schema_update()
                    elif topic_key == BaseInputTopicType.LOG_SYNC_PEPEUNIT:
                        self._handle_log_sync()
                    break
        except Exception as e:
            self.logger.error('Error in base MQTT input handler: ' + str(e))

    def download_update(self, archive_path):
        if not self.enable_rest or not self.rest_client:
            raise RuntimeError('REST client is not enabled or available')
        self.rest_client.download_update(self.unit_uuid, archive_path)
        self.logger.info('Update archive downloaded to ' + archive_path)

    def download_env(self, file_path):
        if not self.enable_rest or not self.rest_client:
            raise RuntimeError('REST client is not enabled or available')
        self.rest_client.download_env(self.unit_uuid, file_path)
        self.settings.load_from_file()
        self.logger.info('Environment file downloaded and updated from ' + file_path)

    def download_schema(self, file_path):
        if not self.enable_rest or not self.rest_client:
            raise RuntimeError('REST client is not enabled or available')
        self.rest_client.download_schema(self.unit_uuid, file_path)
        self.schema.update_from_file()
        self.logger.info('Schema file downloaded and updated from ' + file_path)

    def set_state_storage(self, state):
        if not self.enable_rest or not self.rest_client:
            raise RuntimeError('REST client is not enabled or available')
        self.rest_client.set_state_storage(self.unit_uuid, state)
        self.logger.info('State uploaded to Pepeunit Unit Storage')

    def get_state_storage(self):
        if not self.enable_rest or not self.rest_client:
            raise RuntimeError('REST client is not enabled or available')
        state = self.rest_client.get_state_storage(self.unit_uuid)
        self.logger.info('State retrieved from Pepeunit Unit Storage')
        return state

    def perform_update(self):
        if not (self.enable_mqtt and self.enable_rest):
            raise RuntimeError('Both MQTT and REST clients must be enabled for perform_update')
        try:
            tmp = '/update_' + self.unit_uuid + '.tar.gz'
            self.download_update(tmp)
            self.update_device_program(tmp)
            self.logger.info('Full update cycle completed successfully')
        except Exception as e:
            self.logger.error('Update failed: ' + str(e))
            raise

    def _handle_update(self, payload):
        self.logger.info('Update request received via MQTT')
        if self.enable_rest and self.rest_client:
            try:
                if self.custom_update_handler:
                    self.custom_update_handler(self, payload)
                else:
                    self.perform_update()
            except Exception as e:
                self.logger.error('Failed to perform update: ' + str(e))
        else:
            self.logger.warning('REST client not available for update')

    def _handle_env_update(self):
        self.logger.info('Env update request received via MQTT')
        if self.enable_rest and self.rest_client:
            try:
                self.download_env(self.env_file_path)
            except Exception as e:
                self.logger.error('Failed to update env: ' + str(e))
        else:
            self.logger.warning('REST client not available for env update')

    def _handle_schema_update(self):
        self.logger.info('Schema update request received via MQTT')
        if self.enable_rest and self.rest_client:
            try:
                self.download_schema(self.schema_file_path)
                if self.enable_mqtt and self.mqtt_client:
                    self.subscribe_all_schema_topics()
            except Exception as e:
                self.logger.error('Failed to update schema: ' + str(e))
        else:
            self.logger.warning('REST client not available for schema update')

    def _handle_log_sync(self):
        try:
            if BaseOutputTopicType.LOG_PEPEUNIT in self.schema.output_base_topic:
                topic = self.schema.output_base_topic[BaseOutputTopicType.LOG_PEPEUNIT][0]
                log_data = self.logger.get_full_log()
                if self.mqtt_client:
                    import ujson as json
                    self.mqtt_client.publish(topic, json.dumps(log_data))
                self.logger.info('Log sync completed')
        except Exception as e:
            self.logger.error('Error during log sync: ' + str(e))

    def subscribe_all_schema_topics(self):
        if not self.enable_mqtt or not self.mqtt_client:
            raise RuntimeError('MQTT client is not enabled or available')
        topics = []
        for topic_list in self.schema.input_base_topic.values():
            topics.extend(topic_list)
        for topic_list in self.schema.input_topic.values():
            topics.extend(topic_list)
        self.mqtt_client.subscribe_topics(topics)

    def publish_to_topics(self, topic_key, message):
        if not self.enable_mqtt or not self.mqtt_client:
            raise RuntimeError('MQTT client is not enabled or available')
        topics = []
        if topic_key in self.schema.output_topic:
            topics.extend(self.schema.output_topic[topic_key])
        elif topic_key in self.schema.output_base_topic:
            topics.extend(self.schema.output_base_topic[topic_key])
        for topic in topics:
            self.mqtt_client.publish(topic, message)

    def _base_mqtt_output_handler(self):
        current_time = time.time()
        if BaseOutputTopicType.STATE_PEPEUNIT in self.schema.output_base_topic:
            if current_time - self._last_state_send >= self.settings.STATE_SEND_INTERVAL:
                topic = self.schema.output_base_topic[BaseOutputTopicType.STATE_PEPEUNIT][0]
                state_data = self.get_system_state()
                import ujson as json
                if self.mqtt_client:
                    self.mqtt_client.publish(topic, json.dumps(state_data))
                self._last_state_send = current_time

    def run_main_cycle(self, output_handler=None):
        self._running = True
        if output_handler:
            self.mqtt_output_handler = output_handler
        try:
            while self._running:
                if self.mqtt_client:
                    self.mqtt_client.check_msg()
                self._base_mqtt_output_handler()
                if self.mqtt_output_handler:
                    self.mqtt_output_handler(self)
                time.sleep(self.cycle_speed)
        except Exception as e:
            self.logger.error('Error in main cycle: ' + str(e))
        finally:
            self._running = False

    def set_output_handler(self, output_handler):
        self.mqtt_output_handler = output_handler

    def set_custom_update_handler(self, custom_update_handler):
        self.custom_update_handler = custom_update_handler

    def stop_main_cycle(self):
        self.logger.info('Stop main cycle')
        self._running = False

    def _dirname(self, path):
        i = path.rfind('/')
        return path[:i] if i > 0 else '/'

