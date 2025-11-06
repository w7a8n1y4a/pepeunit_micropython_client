import ujson as json
import time
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

    def _log(self, level_str, message):
        print('log', level_str, message)
        if not self._should_log(level_str):
            return

        log_entry = {
            'level': level_str,
            'text': message,
            'create_datetime': str(int(time.time()))
        }
        FileManager.append_ndjson_with_limit(self.log_file_path, log_entry, self.settings.MAX_LOG_LENGTH)
        if self.mqtt_client and BaseOutputTopicType.LOG_PEPEUNIT in self.schema_manager.output_base_topic:
            topic = self.schema_manager.output_base_topic[BaseOutputTopicType.LOG_PEPEUNIT][0]
            self.mqtt_client.publish(topic, json.dumps(log_entry))

    def debug(self, message):
        self._log(LogLevel.DEBUG, message)

    def info(self, message):
        self._log(LogLevel.INFO, message)

    def warning(self, message):
        self._log(LogLevel.WARNING, message)

    def error(self, message):
        self._log(LogLevel.ERROR, message)

    def critical(self, message):
        self._log(LogLevel.CRITICAL, message)

    def reset_log(self):
        with open(self.log_file_path, 'w') as f:
            pass

    def iter_log(self):
        if not FileManager.file_exists(self.log_file_path):
            return
        for item in FileManager.iter_ndjson(self.log_file_path):
            yield item
