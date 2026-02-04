import ujson as json
import gc
import utils

from .enums import LogLevel, BaseOutputTopicType
from .file_manager import FileManager

import uasyncio as asyncio


class Logger:
    def __init__(self, log_file_path, mqtt_client=None, schema_manager=None, settings=None, time_manager=None, ff_console_log_enable=True):
        self.log_file_path = log_file_path
        self.mqtt_client = mqtt_client
        self.schema_manager = schema_manager
        self.settings = settings
        self.time_manager = time_manager
        self.ff_console_log_enable = ff_console_log_enable

    def _should_log(self, level_str):
        if not self.settings:
            return True
        return LogLevel.get_int_level(level_str) >= LogLevel.get_int_level(self.settings.PU_MIN_LOG_LEVEL)

    def _log(self, level_str, message, file_only=False):
        if not self._should_log(level_str):
            return

        create_datetime = self.time_manager.get_epoch_ms()
        free_mem = gc.mem_free()
        log_entry = '{"level":"%s","text":%s,"create_datetime":%d,"free_mem":%d}' % (
            level_str,
            json.dumps(message),
            create_datetime,
            free_mem,
        )

        if self.ff_console_log_enable:
            print(log_entry)
        asyncio.create_task(
            FileManager.append_ndjson_with_limit(self.log_file_path, log_entry, self.settings.PU_MAX_LOG_LENGTH)
        )

        if not file_only and self.mqtt_client and BaseOutputTopicType.LOG_PEPEUNIT in self.schema_manager.output_base_topic:
            if utils.should_collect_memory(8192):
                return
            topic = self.schema_manager.output_base_topic[BaseOutputTopicType.LOG_PEPEUNIT][0]
            asyncio.create_task(self.mqtt_client.publish(topic, log_entry))

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

    def reset_log(self):
        with open(self.log_file_path, 'w') as f:
            pass
