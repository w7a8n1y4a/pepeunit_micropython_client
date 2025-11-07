import ujson as json
import gc
import ubinascii as binascii

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
    MIN_LOG_LEVEL = 'Debug'
    MAX_LOG_LENGTH = 64

    def __init__(self, env_file_path=None, **kwargs):
        self.env_file_path = env_file_path
        if env_file_path:
            self.load_from_file()
        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def unit_uuid(self):
        data = self.PEPEUNIT_TOKEN.split('.')[1].encode()
        gc.collect()
        uuid = json.loads(binascii.a2b_base64(data + (len(data) % 4) * b'=').decode('utf-8'))['uuid']
        gc.collect()
        return uuid

    def load_from_file(self):
        if not self.env_file_path or not FileManager.file_exists(self.env_file_path):
            return
        with open(self.env_file_path, 'r') as f:
            data = json.load(f)

        gc.collect()
        for k, v in data.items():
            setattr(self, k, v)
