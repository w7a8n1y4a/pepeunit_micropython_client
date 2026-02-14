import ujson as json
import time
import gc
import machine
import os
import uasyncio as asyncio
import utils

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
        restart_mode=RestartMode.RESTART_EXEC,
        ntp_host='pool.ntp.org',
        sta=None,
        ff_version_check_enable=True,
        ff_wifi_manager_enable=False,
        ff_console_log_enable=True,
        ff_mqtt_log_enable=True,
        ff_file_log_enable=True,
    ):
        self.env_file_path = env_file_path
        self.schema_file_path = schema_file_path
        self.restart_mode = restart_mode
        self.ff_version_check_enable = ff_version_check_enable
        self.sta = sta

        self.time_manager = TimeManager(ntp_host=ntp_host)
        self.settings = Settings(env_file_path)
        self.schema = SchemaManager(schema_file_path)
        self.logger = Logger(
                log_file_path,
                None,
                self.schema,
                self.settings,
                self.time_manager,
                ff_console_log_enable,
                ff_mqtt_log_enable,
                ff_file_log_enable,
            )
        self.mqtt_client = PepeunitMqttClient(self.settings, self.schema, self.logger)
        self.logger.mqtt_client = self.mqtt_client
        self.rest_client = PepeunitRestClient(self.settings)

        if ff_wifi_manager_enable:
            from .wifi_manager import WifiManager
            self.wifi_manager = WifiManager(settings=self.settings, logger=self.logger)
        else:
            self.wifi_manager = None
        self.mqtt_client.set_wifi_manager(self.wifi_manager)

        self.mqtt_input_handler = None
        self.mqtt_output_handler = None
        self.custom_update_handler = None

        self._running = False
        self._last_state_send = 0
        self._resubscribe_requested = False

    def get_system_state(self):
        state = {
            'millis': self.time_manager.get_epoch_ms(),
            'mem_free': gc.mem_free(),
            'mem_alloc': gc.mem_alloc(),
            'freq': machine.freq(),
            'statvfs': os.statvfs('/'),
            'pu_commit_version': self.settings.PU_COMMIT_VERSION
        }

        if self.wifi_manager:
            state['ifconfig'] = self.wifi_manager.get_sta().ifconfig()
        elif self.sta is not None:
            state['ifconfig'] = self.sta.ifconfig()

        return state

    def set_mqtt_input_handler(self, handler):
        self.mqtt_input_handler = handler
        async def combined_handler(msg):
            try:
                self._base_mqtt_input_func(msg)
                if self.mqtt_input_handler:
                    await self.mqtt_input_handler(self, msg)
            except Exception as e:
                self.logger.error('Error in MQTT handler: ' + str(e))
            finally:
                self._last_state_send = self.time_manager.get_epoch_ms()
        self.mqtt_client.set_input_handler(combined_handler)

    def _base_mqtt_input_func(self, msg):
        try:
            for topic_key in self.schema.input_base_topic:
                if msg.topic in self.schema.input_base_topic[topic_key]:
                    self.logger.info('Get base MQTT command: {}'.format(topic_key))

                    if topic_key == BaseInputTopicType.ENV_UPDATE_PEPEUNIT:
                        asyncio.create_task(self.download_env(self.env_file_path))
                    elif topic_key == BaseInputTopicType.SCHEMA_UPDATE_PEPEUNIT:
                        asyncio.create_task(self.download_schema(self.schema_file_path))
                    elif topic_key == BaseInputTopicType.UPDATE_PEPEUNIT:
                        self._handle_update(msg)
                    elif topic_key == BaseInputTopicType.LOG_SYNC_PEPEUNIT:
                        self._handle_log_sync()
                    break
        except Exception as e:
            self.logger.error('Error in base MQTT command: ' + str(e))

    async def download_env(self, file_path):
        await self.rest_client.download_env(file_path)
        self.settings.load_from_file()
        self.logger.info('Success update env')

    async def download_schema(self, file_path):
        await self.rest_client.download_schema(file_path)
        self.schema.update_from_file()
        self._resubscribe_requested = True
        self.logger.info('Success update schema')

    async def set_state_storage(self, state):
        await self.rest_client.set_state_storage(state)

    async def get_state_storage(self):
        return await self.rest_client.get_state_storage()

    def _handle_update(self, msg):
        payload = json.loads(msg.payload) if msg.payload else {}

        if self.custom_update_handler:
            utils.spawn(self.custom_update_handler(self, payload))
            return

        async def _do_update():
            if self.ff_version_check_enable and self.settings.PU_COMMIT_VERSION == payload.get('PU_COMMIT_VERSION'):
                self.logger.info('No update needed: current version = target version')
                return

            if self.restart_mode == RestartMode.RESTART_EXEC:
                try:
                    await self.mqtt_client.disconnect()
                except Exception as e:
                    self.logger.warning("MQTT disconnect failed before update: {}".format(e), file_only=True)
                await self.perform_update()

            if self.restart_mode != RestartMode.NO_RESTART:
                self.restart_device()

        asyncio.create_task(_do_update())

    async def perform_update(self):
        tmp = '/update_' + self.settings.unit_uuid + '.tgz'
        await self.rest_client.download_update(tmp)
        self.logger.info('Success download update archive', file_only=True)

        unit_directory = utils.dirname(self.env_file_path)
        await FileManager.extract_tar_gz(tmp, unit_directory, copy_chunk=128, yield_every=8)
        self.logger.info('Success extract archive', file_only=True)
        gc.collect()

        try:
            os.remove(tmp)
        except Exception as e:
            self.logger.warning("Failed to remove update archive: {}".format(e), file_only=True)

    def _handle_log_sync(self):
        if not self.logger.ff_file_log_enable:
            return
        topic = self.schema.output_base_topic[BaseOutputTopicType.LOG_PEPEUNIT][0]

        async def _trim_and_send():
            try:
                await FileManager.trim_ndjson(self.logger.log_file_path, self.settings.PU_MAX_LOG_LENGTH)
            except Exception as e:
                self.logger.warning("Log trim failed: {}".format(e), file_only=True)

            async def on_line(line):
                await self.mqtt_client.publish(topic, line)
                utils.ensure_memory(8000)
                await asyncio.sleep_ms(50)

            await FileManager.iter_lines_bytes_cb(self.logger.log_file_path, on_line, yield_every=32)

        asyncio.create_task(_trim_and_send())
        self.logger.info('Scheduled log sync to MQTT')

    def subscribe_all_schema_topics(self):
        self._resubscribe_requested = True

    async def publish_to_topics(self, topic_key, message):
        topics = self.schema.output_topic.get(topic_key) or self.schema.output_base_topic.get(topic_key)
        if not topics:
            self.logger.warning("No MQTT topics for key: {}".format(topic_key), file_only=True)
            return False
        ok = True
        for topic in topics:
            if not await self.mqtt_client.publish(topic, message):
                ok = False
        return ok

    def _base_mqtt_output_handler(self):
        current_time = self.time_manager.get_epoch_ms()
        if BaseOutputTopicType.STATE_PEPEUNIT not in self.schema.output_base_topic:
            return None
        if (current_time - self._last_state_send) // 1000 < self.settings.PU_STATE_SEND_INTERVAL:
            return None
        self._last_state_send = current_time
        if not utils.ensure_memory(6000):
            return None
        topic = self.schema.output_base_topic[BaseOutputTopicType.STATE_PEPEUNIT][0]
        return self.mqtt_client.publish(topic, json.dumps(self.get_system_state()))

    async def run_main_cycle(self, cycle_ms=20):
        self._running = True
        try:
            while self._running:
                await self.mqtt_client.ensure_connected()
                if self.mqtt_client.consume_reconnected():
                    self._resubscribe_requested = True
                if self._resubscribe_requested and self.mqtt_client.is_connected():
                    try:
                        await self.mqtt_client.subscribe_all_schema_topics()
                    finally:
                        self._resubscribe_requested = False

                if self.mqtt_output_handler:
                    await utils.maybe_await(self.mqtt_output_handler(self))

                await utils.maybe_await(self._base_mqtt_output_handler())

                utils.ensure_memory()
                await asyncio.sleep_ms(int(cycle_ms))
        finally:
            self._running = False

    def set_output_handler(self, output_handler):
        self.mqtt_output_handler = output_handler

    def set_custom_update_handler(self, custom_update_handler):
        self.custom_update_handler = custom_update_handler

    def stop_main_cycle(self):
        self.logger.info('Main cycle stopped', file_only=True)
        self._running = False

    def restart_device(self):
        try:
            gc.collect()
            self.logger.warning("Restart: I`ll be back", file_only=True)
        except Exception:
            pass
        time.sleep(1)
        machine.reset()
