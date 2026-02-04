import ujson as json
import time
import gc
import machine
import os
import uasyncio as asyncio

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
    ):
        self.env_file_path = env_file_path
        self.schema_file_path = schema_file_path
        self.log_file_path = log_file_path
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
                ff_console_log_enable
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
        self._in_mqtt_callback = False
        self._resubscribe_requested = False
        self._last_mqtt_ping_ms = time.ticks_ms()
    
    def get_system_state(self):
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
                    res = self.mqtt_input_handler(self, msg)


                    if res is not None and hasattr(res, "send"):
                        asyncio.create_task(res)
            finally:
                self._last_state_send = time.ticks_ms()
                self._in_mqtt_callback = False
        self.mqtt_client.set_input_handler(combined_handler)

    def _base_mqtt_input_func(self, msg):
        try:
            for topic_key in self.schema.input_base_topic:
                if msg.topic in self.schema.input_base_topic[topic_key]:
                    self.logger.info(f'Get base MQTT command: {topic_key}')

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

    def set_state_storage(self, state):
        self.rest_client.set_state_storage(state)

    def get_state_storage(self):
        return self.rest_client.get_state_storage()

    def _handle_update(self, msg):
        payload = json.loads(msg.payload) if msg.payload else {}

        if self.custom_update_handler:
            res = self.custom_update_handler(self, payload)
            if res is not None and hasattr(res, "send"):
                asyncio.create_task(res)
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

        try:
            asyncio.create_task(_do_update())
        except Exception as e:
            self.logger.error("Failed to schedule update task: {}".format(e), file_only=True)

    async def perform_update(self):
        tmp = '/update_' + self.settings.unit_uuid + '.tgz'
        await self.rest_client.download_update(tmp)
        self.logger.info('Success download update archive', file_only=True)

        unit_directory = self.env_file_path[: self.env_file_path.rfind('/')] if '/' in self.env_file_path else ''
        await FileManager.extract_tar_gz(tmp, unit_directory, copy_chunk=128, yield_every=8)
        self.logger.info('Success extract archive', file_only=True)
        gc.collect()

        try:
            os.remove(tmp)
        except Exception as e:
            self.logger.warning("Failed to remove update archive: {}".format(e), file_only=True)

    def _handle_log_sync(self):
        async def _trim_and_send(topic):
            try:
                await FileManager.trim_ndjson(self.logger.log_file_path, self.settings.PU_MAX_LOG_LENGTH)
            except Exception as e:
                self.logger.warning("Log trim failed: {}".format(e), file_only=True)

            async def on_line(line):
                await self.mqtt_client.publish(topic, line)
                if gc.mem_free() < 8000:
                    gc.collect()
                await asyncio.sleep_ms(50)

            await FileManager.iter_lines_bytes_cb(self.logger.log_file_path, on_line, yield_every=32)

        topic = self.schema.output_base_topic[BaseOutputTopicType.LOG_PEPEUNIT][0]

        asyncio.create_task(_trim_and_send(topic))
        self.logger.info('Scheduled log sync to MQTT')


    def _subscribe_all_schema_topics_now(self):
        self.mqtt_client.subscribe_all_schema_topics()

    def subscribe_all_schema_topics(self):
        if self._in_mqtt_callback:
            self._resubscribe_requested = True
            return
        self._subscribe_all_schema_topics_now()

    async def publish_to_topics(self, topic_key, message):

        topics = self.schema.output_topic.get(topic_key, None)
        if topics is None:
            topics = self.schema.output_base_topic.get(topic_key, None)
        if not topics:
            self.logger.warning("No MQTT topics for key: {}".format(topic_key), file_only=True)
            return
        for topic in topics:
            await self.mqtt_client.publish(topic, message)

    def _base_mqtt_output_handler(self):
        current_time = self.time_manager.get_epoch_ms()
        if self.mqtt_client and BaseOutputTopicType.STATE_PEPEUNIT in self.schema.output_base_topic:
            if (current_time - self._last_state_send) / 1000 >= self.settings.PU_STATE_SEND_INTERVAL:
                topic = self.schema.output_base_topic[BaseOutputTopicType.STATE_PEPEUNIT][0]
                state_payload = self.get_system_state()

                if gc.mem_free() < 6000:
                    self._last_state_send = current_time
                    return
                asyncio.create_task(self.mqtt_client.publish(topic, json.dumps(state_payload)))
                self._last_state_send = current_time

    async def run_main_cycle(self, cycle_ms=20):

        self._running = True
        try:
            while self._running:
                if not self._in_mqtt_callback:
                    await self.mqtt_client.ensure_connected()
                    if self.mqtt_client.consume_reconnected():
                        self._resubscribe_requested = True
                if self._resubscribe_requested and not self._in_mqtt_callback:
                    try:

                        subscribe_all = getattr(self.mqtt_client, "subscribe_all_schema_topics", None)
                        if subscribe_all:
                            if self.mqtt_client.is_connected():
                                res = subscribe_all()
                                if res is not None:
                                    await res
                    finally:
                        self._resubscribe_requested = False

                if self.mqtt_output_handler:
                    res = self.mqtt_output_handler(self)


                    if res is not None and hasattr(res, "send"):
                        await res

                self._base_mqtt_output_handler()

                await asyncio.sleep_ms(int(cycle_ms))
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
            self.logger.warning("Restart: I`ll be back", file_only=True)
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

