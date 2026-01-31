import ujson as json
import time
import gc
import machine
import os
try:
    import uasyncio as asyncio  # MicroPython
except ImportError:  # CPython
    import asyncio

from .time_manager import TimeManager
from .settings import Settings
from .file_manager import FileManager
from .logger import Logger
from .schema_manager import SchemaManager

from .pepeunit_mqtt_as_client import PepeunitMqttAsClient
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
        self.mqtt_client = PepeunitMqttAsClient(self.settings, self.schema, self.logger)
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
        self._last_mqtt_ping_ms = time.ticks_ms()

    def get_system_state(self):
        # Keep this as small as possible: low-RAM boards can crash on the
        # temporary allocations caused by building a large dict + json.dumps().
        state = {
            "millis": self.time_manager.get_epoch_ms(),
            "mem_free": gc.mem_free(),
        }

        if getattr(self.settings, "PU_STATE_INCLUDE_MEM_ALLOC", False):
            state["mem_alloc"] = gc.mem_alloc()
        if getattr(self.settings, "PU_STATE_INCLUDE_FREQ", False):
            state["freq"] = machine.freq()
        if getattr(self.settings, "PU_STATE_INCLUDE_STATVFS", False):
            # This can be relatively “fat” in JSON.
            try:
                state["statvfs"] = os.statvfs("/")
            except Exception:
                pass
        if getattr(self.settings, "PU_STATE_INCLUDE_IFCONFIG", False):
            try:
                if self.wifi_manager:
                    state["ifconfig"] = self.wifi_manager.get_sta().ifconfig()
                else:
                    state["ifconfig"] = self.sta.ifconfig()
            except Exception:
                pass

        # Keep version behind a flag too: strings increase JSON size and RAM peak.
        if getattr(self.settings, "PU_STATE_INCLUDE_VERSION", False):
            state["pu_commit_version"] = self.settings.PU_COMMIT_VERSION

        return state

    def set_mqtt_input_handler(self, handler):
        self.mqtt_input_handler = handler
        def combined_handler(msg):
            self._in_mqtt_callback = True
            try:
                self._base_mqtt_input_func(msg)
                if self.mqtt_input_handler:
                    res = self.mqtt_input_handler(self, msg)
                    # In mqtt_as callback we can't await; schedule if user returns a coroutine.
                    # MicroPython coroutines don't always expose __await__ reliably.
                    if res is not None and hasattr(res, "send"):
                        try:
                            asyncio.create_task(res)
                        except Exception:
                            pass
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
                        try:
                            asyncio.create_task(self.download_env_async(self.env_file_path))
                        except Exception:
                            pass
                    elif topic_key == BaseInputTopicType.SCHEMA_UPDATE_PEPEUNIT:
                        try:
                            asyncio.create_task(self.download_schema_async(self.schema_file_path))
                        except Exception:
                            pass
                    elif topic_key == BaseInputTopicType.UPDATE_PEPEUNIT:
                        self._handle_update(msg)
                    elif topic_key == BaseInputTopicType.LOG_SYNC_PEPEUNIT:
                        self._handle_log_sync()
                    break
        except Exception as e:
            self.logger.error('Error in base MQTT command: ' + str(e))

    def download_env(self, file_path):
        # Deprecated (sync). Use download_env_async() or schedule it from callbacks.
        raise NotImplementedError("download_env() is sync; use download_env_async() with uasyncio.")

    def download_schema(self, file_path):
        # Deprecated (sync). Use download_schema_async() or schedule it from callbacks.
        raise NotImplementedError("download_schema() is sync; use download_schema_async() with uasyncio.")

    async def download_env_async(self, file_path):
        await self.rest_client.download_env(file_path)
        self.settings.load_from_file()
        self.logger.info('Success update env')

    async def download_schema_async(self, file_path):
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
            self.custom_update_handler(self, payload)
        else:
            if self.ff_version_check_enable and self.settings.PU_COMMIT_VERSION == payload.get('PU_COMMIT_VERSION'):
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
        
        # FileManager is async-only; update is sync, so keep a local sync extractor here.
        unit_directory = self.env_file_path[: self.env_file_path.rfind('/')] if '/' in self.env_file_path else ''
        self._extract_tar_gz_sync(tmp, unit_directory)
        self.logger.info('Success extract archive', file_only=True)
        gc.collect()

        try:
            os.remove(tmp)
        except Exception:
            pass

    def _handle_log_sync(self):
        async def _trim_and_send(topic):
            try:
                await FileManager.trim_ndjson(self.logger.log_file_path, self.settings.PU_MAX_LOG_LENGTH)
            except Exception:
                pass

            async def on_line(line):
                await self.mqtt_client.publish(topic, line)
                if gc.mem_free() < 8000:
                    gc.collect()
                await asyncio.sleep_ms(50)

            await FileManager.iter_lines_bytes_cb(self.logger.log_file_path, on_line, yield_every=32)

        topic = self.schema.output_base_topic[BaseOutputTopicType.LOG_PEPEUNIT][0]

        try:
            asyncio.create_task(_trim_and_send(topic))
            self.logger.info('Scheduled log sync to MQTT')
        except Exception:
            pass

    # --- internal sync-only helper for update extraction (avoid FileManager sync API) ---
    def _extract_tar_gz_sync(self, tgz_path, dest_root):
        import tarfile
        import deflate
        from shutil import shutil as shutil

        def _ensure_dir(path):
            if not path:
                return
            parts = []
            if path.startswith('/'):
                base = '/'
                rest = path[1:]
            else:
                base = ''
                rest = path
            for p in rest.split('/'):
                parts.append(p)
                cur = (base + '/'.join(parts)) if base else '/'.join(parts)
                try:
                    os.mkdir(cur)
                except OSError:
                    pass

        _ensure_dir(dest_root)
        with open(tgz_path, 'rb') as tgz:
            tar_file = deflate.DeflateIO(tgz, deflate.AUTO, 9)
            unpack_tar = tarfile.TarFile(fileobj=tar_file)
            for unpack_file in unpack_tar:
                if unpack_file.type == tarfile.DIRTYPE or '@PaxHeader' in unpack_file.name:
                    continue
                out_path = dest_root + '/' + unpack_file.name[2:]
                _ensure_dir(out_path[: out_path.rfind('/')])
                subf = unpack_tar.extractfile(unpack_file)
                try:
                    with open(out_path, 'wb') as outf:
                        shutil.copyfileobj(subf, outf, length=256)
                        outf.close()
                finally:
                    try:
                        if subf:
                            subf.close()
                    except Exception:
                        pass

    def _subscribe_all_schema_topics_now(self):
        self.mqtt_client.subscribe_all_schema_topics()

    def subscribe_all_schema_topics(self):
        if self._in_mqtt_callback:
            self._resubscribe_requested = True
            return
        self._subscribe_all_schema_topics_now()

    async def publish_to_topics(self, topic_key, message):
        # Low-RAM: avoid building intermediate lists on every publish.
        topics = self.schema.output_topic.get(topic_key, None)
        if topics is None:
            topics = self.schema.output_base_topic.get(topic_key, None)
        if not topics:
            try:
                self.logger.warning("No MQTT topics for key: {}".format(topic_key), file_only=True)
            except Exception:
                pass
            return
        for topic in topics:
            await self.mqtt_client.publish(topic, message)

    def _base_mqtt_output_handler(self):
        current_time = self.time_manager.get_epoch_ms()
        if BaseOutputTopicType.STATE_PEPEUNIT in self.schema.output_base_topic:
            if (current_time - self._last_state_send) / 1000 >= self.settings.PU_STATE_SEND_INTERVAL:
                topic = self.schema.output_base_topic[BaseOutputTopicType.STATE_PEPEUNIT][0]
                state_data = self.get_system_state()
                # This is called from async main loop; schedule to avoid blocking if needed.
                try:
                    # Don't allocate tasks if MQTT isn't connected or RAM is low.
                    if gc.mem_free() < getattr(self.settings, "PU_STATE_MQTT_MIN_FREE", 6000):
                        self._last_state_send = current_time
                        return
                    cli = getattr(self.mqtt_client, "_client", None)
                    if cli is None:
                        self._last_state_send = current_time
                        return
                    isconn = getattr(cli, "isconnected", None)
                    if isconn and not isconn():
                        self._last_state_send = current_time
                        return
                    asyncio.create_task(self.mqtt_client.publish(topic, json.dumps(state_data)))
                except Exception:
                    pass
                self._last_state_send = current_time

    def run_main_cycle(self):
        raise NotImplementedError("Synchronous run_main_cycle() is not supported with mqtt_as. Use run_main_cycle_async().")

    async def run_main_cycle_async(self, cycle_ms=20):
        """
        Async variant of `run_main_cycle()` intended for use with `mqtt_as`.
        Incoming messages are handled by mqtt_as internal tasks; this loop only
        drives periodic publish handlers and resubscribe requests.
        """
        try:
            import uasyncio as asyncio  # MicroPython
        except ImportError:
            import asyncio

        self._running = True
        try:
            while self._running:
                if self._resubscribe_requested and not self._in_mqtt_callback:
                    try:
                        # For mqtt_as client: subscribe is async.
                        subscribe_all = getattr(self.mqtt_client, "subscribe_all_schema_topics", None)
                        if subscribe_all:
                            res = subscribe_all()
                            if res is not None:
                                await res
                    finally:
                        self._resubscribe_requested = False

                if self.mqtt_output_handler:
                    res = self.mqtt_output_handler(self)
                    # Allow async output handlers.
                    # MicroPython coroutines don't always expose __await__ reliably.
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
