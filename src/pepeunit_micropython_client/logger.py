import ujson as json
import time
import gc

from .enums import LogLevel, BaseOutputTopicType
from .file_manager import FileManager


class Logger:
    def __init__(self, log_file_path, mqtt_client=None, schema_manager=None, settings=None):
        self.log_file_path = log_file_path
        self.mqtt_client = mqtt_client
        self.schema_manager = schema_manager
        self.settings = settings

    def _should_log(self, level_str):
        if not self.settings:
            return True
        return LogLevel.get_int_level(level_str) >= LogLevel.get_int_level(self.settings.MIN_LOG_LEVEL)

    def _log(self, level_str, message, file_only=False):
        if not self._should_log(level_str):
            return

        log_entry = {
            'level': level_str,
            'text': message,
            'current_millis': time.ticks_ms(),
            'free_mem': gc.mem_free()
        }
        FileManager.append_ndjson_with_limit(self.log_file_path, log_entry, self.settings.MAX_LOG_LENGTH)
        if not file_only and self.mqtt_client and BaseOutputTopicType.LOG_PEPEUNIT in self.schema_manager.output_base_topic:
            topic = self.schema_manager.output_base_topic[BaseOutputTopicType.LOG_PEPEUNIT][0]
            try:
                self.mqtt_client.publish(topic, json.dumps(log_entry))
            except Exception:
                pass

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

    def iter_log(self):
        if not FileManager.file_exists(self.log_file_path):
            return
        for item in FileManager.iter_ndjson(self.log_file_path):
            yield item
