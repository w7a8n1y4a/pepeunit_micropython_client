import ujson as json
import ubinascii as binascii
import time
import gc
import machine
import os

from .settings import Settings
from .file_manager import FileManager
from .logger import Logger
from .schema_manager import SchemaManager
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
        restart_mode=RestartMode.ENV_SCHEMA_ONLY,
        sta=None
    ):
        self.env_file_path = env_file_path
        self.schema_file_path = schema_file_path
        self.log_file_path = log_file_path
        self.enable_mqtt = enable_mqtt
        self.enable_rest = enable_rest
        self.cycle_speed = cycle_speed
        self.restart_mode = restart_mode
        self.sta = sta

        self.settings = Settings(env_file_path)
        self.schema = SchemaManager(schema_file_path)

        self.logger = Logger(log_file_path, None, self.schema, self.settings)

        self.mqtt_client = (mqtt_client if mqtt_client else self._get_default_mqtt_client()) if enable_mqtt else None
        gc.collect()
        self.rest_client = (rest_client if rest_client else self._get_default_rest_client()) if enable_rest else None

        if self.mqtt_client:
            self.logger.mqtt_client = self.mqtt_client

        self.mqtt_input_handler = None
        self.mqtt_output_handler = None
        self.custom_update_handler = None

        self._running = False
        self._last_state_send = 0

    def _get_default_mqtt_client(self):
        from .pepeunit_mqtt_client import PepeunitMqttClient
        return PepeunitMqttClient(self.settings, self.schema, self.logger)

    def _get_default_rest_client(self):
        from .pepeunit_rest_client import PepeunitRestClient
        return PepeunitRestClient(self.settings)

    @property
    def unit_uuid(self):
        data = self.settings.PEPEUNIT_TOKEN.split('.')[1].encode()
        return json.loads(binascii.a2b_base64(data + (len(data) % 4) * b'=').decode('utf-8'))['uuid']

    def set_cycle_speed(self, speed):
        if speed <= 0:
            raise ValueError('Cycle speed must be greater than 0')
        self.cycle_speed = speed

    def update_device_program(self, archive_path):
        unit_directory = self._dirname(self.env_file_path) or '/'
        FileManager.extract_tar_gz(archive_path, unit_directory)

        try:
            os.remove(archive_path)
        except Exception:
            pass
        
        if self.restart_mode == RestartMode.ENV_SCHEMA_ONLY:
            self._update_env_schema_only()

    def _update_env_schema_only(self):
        self.settings.load_from_file()
        self.schema.update_from_file()
        if self.enable_mqtt and self.mqtt_client:
            self.subscribe_all_schema_topics()

    def get_system_state(self):
        gc.collect()
        state = {
            'millis': time.ticks_ms(),
            'mem_free': gc.mem_free(),
            'mem_alloc': gc.mem_alloc(),
            'freq': machine.freq(),
            'statvfs': os.statvfs('/'),
            'commit_version': self.settings.COMMIT_VERSION
        }

        try:
            state['ifconfig'] = self.sta.ifconfig()
        except Exception as e:
            pass

        return state

    def set_mqtt_input_handler(self, handler):
        self.mqtt_input_handler = handler
        if self.mqtt_client:    
            def combined_handler(msg):
                self._base_mqtt_input_func(msg)
                if self.mqtt_input_handler:
                    self.mqtt_input_handler(self, msg)
            self.mqtt_client.set_input_handler(combined_handler)

    def _base_mqtt_input_func(self, msg):
        try:
            for topic_key in self.schema.input_base_topic:
                if msg.topic in self.schema.input_base_topic[topic_key]:
                    self.logger.info(f'Input base topic: {msg.payload}')
                    if topic_key == BaseInputTopicType.UPDATE_PEPEUNIT:
                        self._handle_update(msg)
                    elif topic_key == BaseInputTopicType.ENV_UPDATE_PEPEUNIT:
                        self.download_env(self.env_file_path)
                    elif topic_key == BaseInputTopicType.SCHEMA_UPDATE_PEPEUNIT:
                        self._handle_schema_update()
                    elif topic_key == BaseInputTopicType.LOG_SYNC_PEPEUNIT:
                        self._handle_log_sync()
                    break
        except Exception as e:
            self.logger.error('Error in base MQTT input handler: ' + str(e))

    def download_update(self, archive_path):
        if self.enable_rest:
            self.rest_client.download_update(self.unit_uuid, archive_path)

    def download_env(self, file_path):
        self.rest_client.download_env(self.unit_uuid, file_path)
        self.settings.load_from_file()

    def download_schema(self, file_path):
        if self.enable_rest:
            self.rest_client.download_schema(self.unit_uuid, file_path)
            self.schema.update_from_file()

    def set_state_storage(self, state):
        if self.enable_rest:
            self.rest_client.set_state_storage(self.unit_uuid, state)

    def get_state_storage(self):
        if self.enable_rest:
            return self.rest_client.get_state_storage(self.unit_uuid)

    def perform_update(self):
        if self.enable_mqtt and self.enable_rest:
            tmp = '/update_' + self.unit_uuid + '.tar.gz'
            self.download_update(tmp)
            self.update_device_program(tmp)

    def _handle_update(self, msg):
        try:
            payload = json.loads(msg.payload)
            gc.collect()
        except Exception:
            payload = {}

        if self.enable_rest and self.rest_client:
            if self.custom_update_handler:
                self.custom_update_handler(self, payload)
            else:
                self.perform_update()

    def _handle_schema_update(self):
        if self.enable_rest and self.rest_client:
            self.download_schema(self.schema_file_path)
            if self.enable_mqtt and self.mqtt_client:
                self.subscribe_all_schema_topics()

    def _handle_log_sync(self):
        if not self.mqtt_client or BaseOutputTopicType.LOG_PEPEUNIT not in self.schema.output_base_topic:
            return
        topic = self.schema.output_base_topic[BaseOutputTopicType.LOG_PEPEUNIT][0]
        try:
            FileManager.trim_ndjson(self.logger.log_file_path, self.settings.LOG_LENGTH)
        except Exception:
            pass

        mem = gc.mem_free()
        batch_size = 8 if mem >= 6000 else (4 if mem >= 3000 else 2)

        def flush_batch_bytes(batch):
            if not batch:
                return
            payload = b'[' + b','.join(batch) + b']'
            self.mqtt_client.publish(topic, payload)
            
            batch.clear()
            gc.collect()

        batch = []
        try:
            for line in FileManager.iter_lines_bytes(self.logger.log_file_path):
                batch.append(line)
                if len(batch) >= batch_size:
                    flush_batch_bytes(batch)
            flush_batch_bytes(batch)
        except Exception as e:
            self.logger.error('Log sync failed: ' + str(e))

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
        if self.enable_mqtt or self.mqtt_client:
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
        finally:
            self._running = False

    def set_output_handler(self, output_handler):
        self.mqtt_output_handler = output_handler

    def set_custom_update_handler(self, custom_update_handler):
        self.custom_update_handler = custom_update_handler

    def stop_main_cycle(self):
        self._running = False

    def _dirname(self, path):
        i = path.rfind('/')
        return path[:i] if i > 0 else '/'
