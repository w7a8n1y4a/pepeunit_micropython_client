import ujson as json
import gc
import utils

from .enums import LogLevel, BaseOutputTopicType
from .file_manager import FileManager

import uasyncio as asyncio


class Logger:
    def __init__(self, log_file_path, mqtt_client=None, schema_manager=None, settings=None, time_manager=None, ff_console_log_enable=True, ff_mqtt_log_enable=True, ff_file_log_enable=True):
        self.log_file_path = log_file_path
        self.mqtt_client = mqtt_client
        self.schema_manager = schema_manager
        self.settings = settings
        self.time_manager = time_manager
        self.ff_console_log_enable = ff_console_log_enable
        self.ff_mqtt_log_enable = ff_mqtt_log_enable
        self.ff_file_log_enable = ff_file_log_enable
        self._log_busy = False

    def _log(self, level_str, message, file_only=False):
        if self.settings and LogLevel.get_int_level(level_str) < LogLevel.get_int_level(self.settings.PU_MIN_LOG_LEVEL):
            return

        log_entry = '{"level":"%s","text":%s,"create_datetime":%d,"free_mem":%d}' % (
            level_str,
            json.dumps(message),
            self.time_manager.get_epoch_ms(),
            gc.mem_free(),
        )

        if self.ff_console_log_enable:
            print(log_entry)

        needs_file = self.ff_file_log_enable
        needs_mqtt = (
            not file_only
            and self.ff_mqtt_log_enable
            and self.mqtt_client
            and BaseOutputTopicType.LOG_PEPEUNIT in self.schema_manager.output_base_topic
            and utils.ensure_memory(8192)
        )

        if not (needs_file or needs_mqtt):
            return
        if self._log_busy:
            print("[throttle] log dropped")
            return
        self._log_busy = True
        asyncio.create_task(self._write_log(log_entry, needs_file, needs_mqtt))

    async def _write_log(self, log_entry, needs_file, needs_mqtt):
        try:
            if needs_file:
                await FileManager.append_ndjson_with_limit(self.log_file_path, log_entry, self.settings.PU_MAX_LOG_LENGTH)
            if needs_mqtt:
                topic = self.schema_manager.output_base_topic[BaseOutputTopicType.LOG_PEPEUNIT][0]
                await self.mqtt_client.publish(topic, log_entry)
        finally:
            self._log_busy = False

    def debug(self, message, file_only=False):
        self._log(LogLevel.DEBUG, message, file_only)

    def info(self, message, file_only=False):
        self._log(LogLevel.INFO, message, file_only)

    def warning(self, message, file_only=False):
        self._log(LogLevel.WARNING, message, file_only)

    def error(self, message, file_only=False):
        self._log(LogLevel.ERROR, message, file_only)

    def critical(self, message, file_only=False):
        self._log(LogLevel.CRITICAL, message, file_only)

    async def reset_log(self):
        if not self.ff_file_log_enable:
            return
        with open(self.log_file_path, 'w') as f:
            pass
        await utils.ayield(do_gc=False)
