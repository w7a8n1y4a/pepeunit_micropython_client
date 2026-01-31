import ujson as json
import ubinascii as binascii

from .file_manager import FileManager


class Settings:

    PU_DOMAIN = ''
    PU_HTTP_TYPE = 'https'
    PU_APP_PREFIX = ''
    PU_API_ACTUAL_PREFIX = ''
    PU_MQTT_HOST = ''
    PU_MQTT_PORT = 1883
    PU_MQTT_PING_INTERVAL = 20
    PU_MQTT_KEEPALIVE = 60
    PU_AUTH_TOKEN = ''
    PU_SECRET_KEY = ''
    PU_ENCRYPT_KEY = ''
    PU_STATE_SEND_INTERVAL = 300
    PU_MIN_LOG_LEVEL = 'Debug'
    PU_MAX_LOG_LENGTH = 64
    PU_COMMIT_VERSION = ''
    PUC_WIFI_SSID = ''
    PUC_WIFI_PASS = ''
    PUC_MAX_RECONNECTION_INTERVAL = 60000

    def __init__(self, env_file_path=None, **kwargs):
        self.env_file_path = env_file_path
        self._unit_uuid = None
        if env_file_path:
            self.load_from_file()
        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def unit_uuid(self):
        if self._unit_uuid is not None:
            return self._unit_uuid
        data = self.PU_AUTH_TOKEN.split('.')[1].encode()
        uuid = json.loads(binascii.a2b_base64(data + (len(data) % 4) * b'=').decode('utf-8'))['uuid']
        self._unit_uuid = uuid
        return uuid

    def load_from_file(self):
        if not self.env_file_path or not FileManager.file_exists(self.env_file_path):
            return
        data = FileManager.read_json(self.env_file_path)

        for k, v in data.items():
            setattr(self, k, v)
        self._unit_uuid = None
