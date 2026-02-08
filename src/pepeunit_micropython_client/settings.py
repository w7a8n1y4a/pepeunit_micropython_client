import ujson as json
import utils


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
        token = self.PU_AUTH_TOKEN
        dot1 = token.find(".")
        if dot1 < 0:
            return None
        dot2 = token.find(".", dot1 + 1)
        if dot2 < 0:
            return None
        try:
            seg = token[dot1 + 1:dot2]
            if '-' in seg or '_' in seg:
                seg = seg.replace("-", "+").replace("_", "/")
            raw = utils.b64decode_to_bytes(seg)
            i = raw.find(b'"uuid":"')
            if i < 0:
                return None
            i += 8
            j = raw.find(b'"', i)
            self._unit_uuid = raw[i:j].decode("utf-8") if j > i else None
        except Exception:
            return None
        return self._unit_uuid

    def load_from_file(self):
        if not self.env_file_path:
            return
        with open(self.env_file_path, "r") as f:
            data = json.load(f)
        for k, v in data.items():
            setattr(self, k, v)
        self._unit_uuid = None
