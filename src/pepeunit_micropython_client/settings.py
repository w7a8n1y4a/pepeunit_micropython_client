import ujson as json
import gc

from .file_manager import FileManager


class Settings:

    PEPEUNIT_URL = ''
    PEPEUNIT_APP_PREFIX = ''
    PEPEUNIT_API_ACTUAL_PREFIX = ''
    HTTP_TYPE = 'https'
    MQTT_URL = ''
    MQTT_PORT = 1883
    PEPEUNIT_TOKEN = ''
    SYNC_ENCRYPT_KEY = ''
    SECRET_KEY = ''
    COMMIT_VERSION = ''
    PING_INTERVAL = 30
    STATE_SEND_INTERVAL = 300
    MINIMAL_LOG_LEVEL = 'Debug'

    def __init__(self, env_file_path=None, **kwargs):
        self.env_file_path = env_file_path
        if env_file_path:
            self.load_from_file()
        for k, v in kwargs.items():
            setattr(self, k, v)

    def load_from_file(self):
        if not self.env_file_path or not FileManager.file_exists(self.env_file_path):
            return
        with open(self.env_file_path, 'r') as f:
            data = json.load(f)

        gc.collect()
        for k, v in data.items():
            setattr(self, k, v)
