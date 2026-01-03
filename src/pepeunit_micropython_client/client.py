import ujson as json
import time
import gc
import machine
import os

from .time_manager import TimeManager
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
        cycle_speed=0.1,
        restart_mode=RestartMode.RESTART_EXEC,
        skip_version_check=False,
        ntp_host='pool.ntp.org',
        ff_wifi_manager_enable=False,
        sta=None,
    ):
        self.env_file_path = env_file_path
        self.schema_file_path = schema_file_path
        self.log_file_path = log_file_path
        self.cycle_speed = cycle_speed
        self.restart_mode = restart_mode
        self.skip_version_check = skip_version_check
        self.sta = sta

        self.time_manager = TimeManager(ntp_host=ntp_host)
        self.settings = Settings(env_file_path)
        self.schema = SchemaManager(schema_file_path)
        self.logger = Logger(log_file_path, None, self.schema, self.settings, self.time_manager)
        self.mqtt_client = PepeunitMqttClient(self.settings, self.schema, self.logger)
        self.logger.mqtt_client = self.mqtt_client
        self.rest_client = PepeunitRestClient(self.settings)

        if ff_wifi_manager_enable:
            from .wifi_manager import WifiManager
            self.wifi_manager = WifiManager(settings=self.settings, logger=self.logger)
        else:
            self.wifi_manager = None

        self.mqtt_input_handler = None
        self.mqtt_output_handler = None
        self.custom_update_handler = None

        self._running = False
        self._last_state_send = 0
        self._in_mqtt_callback = False
        self._resubscribe_requested = False

    def get_system_state(self):
        gc.collect()
        state = {
            'millis': self.time_manager.get_epoch_ms(),
            'mem_free': gc.mem_free(),
            'mem_alloc': gc.mem_alloc(),
            'freq': machine.freq(),
            'statvfs': os.statvfs('/'),
            'pu_commit_version': self.settings.PU_COMMIT_VERSION
        }

        try:
            if self.wifi_manager:
                state['ifconfig'] = self.wifi_manager.get_sta().ifconfig()
            else:
                state['ifconfig'] = self.sta.ifconfig()
        except Exception:
            pass

        return state

    def set_mqtt_input_handler(self, handler):
        self.mqtt_input_handler = handler
        def combined_handler(msg):
            self._in_mqtt_callback = True
            try:
                self._base_mqtt_input_func(msg)
                if self.mqtt_input_handler:
                    self.mqtt_input_handler(self, msg)
            finally:
                self._in_mqtt_callback = False
        self.mqtt_client.set_input_handler(combined_handler)

    def _base_mqtt_input_func(self, msg):
        try:
            for topic_key in self.schema.input_base_topic:
                if msg.topic in self.schema.input_base_topic[topic_key]:
                    self.logger.info(f'Get base MQTT command: {topic_key}')

                    if topic_key == BaseInputTopicType.ENV_UPDATE_PEPEUNIT:
                        self.download_env(self.env_file_path)
                    elif topic_key == BaseInputTopicType.SCHEMA_UPDATE_PEPEUNIT:
                        self.download_schema(self.schema_file_path)
                    elif topic_key == BaseInputTopicType.UPDATE_PEPEUNIT:
                        self._handle_update(msg)
                    elif topic_key == BaseInputTopicType.LOG_SYNC_PEPEUNIT:
                        self._handle_log_sync()
                    break
        except Exception as e:
            self.logger.error('Error in base MQTT command: ' + str(e))

    def download_env(self, file_path):
        self.rest_client.download_env(file_path)
        self.settings.load_from_file()
        self.logger.info('Success update env')

    def download_schema(self, file_path):
        self.rest_client.download_schema(file_path)
        self.schema.update_from_file()
        self._resubscribe_requested = True
        self.logger.info('Success update schema')

    def set_state_storage(self, state):
        self.rest_client.set_state_storage(state)

    def get_state_storage(self):
        return self.rest_client.get_state_storage()

    def _handle_update(self, msg):
        gc.collect()
        payload = json.loads(msg.payload) if msg.payload else {}

        if self.custom_update_handler:
            self.custom_update_handler(self, payload)
        else:
            if not self.skip_version_check and self.settings.PU_COMMIT_VERSION == payload.get('PU_COMMIT_VERSION'):
                self.logger.info('No update needed: current version = target version')
                return
            if self.restart_mode == RestartMode.RESTART_EXEC:
                self.mqtt_client.disconnect()

                self.perform_update()

            if self.restart_mode != RestartMode.NO_RESTART:
                self.restart_device()

    def perform_update(self):
        tmp = '/update_' + self.settings.unit_uuid + '.tgz'
        self.rest_client.download_update(tmp)
        self.logger.info('Success download update archive', file_only=True)
        
        unit_directory = FileManager.dirname(self.env_file_path)
        FileManager.extract_tar_gz(tmp, unit_directory)
        self.logger.info('Success extract archive', file_only=True)

        gc.collect()

        try:
            os.remove(tmp)
        except Exception:
            pass

    def _handle_log_sync(self):
        try:
            FileManager.trim_ndjson(self.logger.log_file_path, self.settings.PU_MAX_LOG_LENGTH)
        except Exception:
            pass

        mem = gc.mem_free()
        batch_size = 8 if mem >= 6000 else (4 if mem >= 3000 else 2)
        topic = self.schema.output_base_topic[BaseOutputTopicType.LOG_PEPEUNIT][0]

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
        except Exception:
            pass

    def _subscribe_all_schema_topics_now(self):
        topics_set = set()
        for topic_list in self.schema.input_base_topic.values():
            topics_set.update(topic_list)
        for topic_list in self.schema.input_topic.values():
            topics_set.update(topic_list)

        self.logger.info(f'Need a subscription for {len(topics_set)} topics')

        if topics_set:
            self.mqtt_client.subscribe_topics(list(topics_set))

    def subscribe_all_schema_topics(self):
        if self._in_mqtt_callback:
            self._resubscribe_requested = True
            return
        self._subscribe_all_schema_topics_now()

    def publish_to_topics(self, topic_key, message):
        topics = []
        if topic_key in self.schema.output_topic:
            topics.extend(self.schema.output_topic[topic_key])
        elif topic_key in self.schema.output_base_topic:
            topics.extend(self.schema.output_base_topic[topic_key])
        for topic in topics:
            self.mqtt_client.publish(topic, message)

    def _base_mqtt_output_handler(self):
        current_time = self.time_manager.get_epoch_ms()
        if BaseOutputTopicType.STATE_PEPEUNIT in self.schema.output_base_topic:
            if (current_time - self._last_state_send) / 1000 >= self.settings.PU_STATE_SEND_INTERVAL:
                topic = self.schema.output_base_topic[BaseOutputTopicType.STATE_PEPEUNIT][0]
                state_data = self.get_system_state()
                self.mqtt_client.publish(topic, json.dumps(state_data))
                self._last_state_send = current_time

    def run_main_cycle(self):
        self._running = True
        try:
            while self._running:
                if self._resubscribe_requested and not self._in_mqtt_callback:
                    try:
                        self._subscribe_all_schema_topics_now()
                    finally:
                        self._resubscribe_requested = False
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
        self.logger.info(f'Main cycle stopped', file_only=True)
        self._running = False

    def restart_device(self):
        try:
            text = "I'll be back"
            print(text)
            self.logger.info(f'Restart planned: {text}', file_only=True)
        except Exception:
            pass
        try:
            time.sleep(1)
        except Exception:
            pass
        try:
            machine.reset()
        except Exception:
            pass
