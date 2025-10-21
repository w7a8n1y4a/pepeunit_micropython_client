import ujson as json
import os


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
        if not self.env_file_path or not self.file_exists(self.env_file_path):
            return
        with open(self.env_file_path, 'r') as f:
            data = json.load(f)
        for k, v in data.items():
            setattr(self, k, v)

    def get_env_values(self):
        if not self.env_file_path or not self.file_exists(self.env_file_path):
            return {}
        with open(self.env_file_path, 'r') as f:
            return json.load(f)

    def update_env_file(self, new_env_file_path):
        if not self.env_file_path:
            raise ValueError('env_file_path not set')
        self.copy_file(new_env_file_path, self.env_file_path)
        self.load_from_file()

    def update(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    @staticmethod
    def file_exists(path):
        try:
            s = os.stat(path)
            return s[6] >= 0 if isinstance(s, tuple) else True
        except OSError:
            return False

    @staticmethod
    def copy_file(src, dst):
        with open(src, 'rb') as s, open(dst, 'wb') as d:
            while True:
                b = s.read(1024)
                if not b:
                    break
                d.write(b)
