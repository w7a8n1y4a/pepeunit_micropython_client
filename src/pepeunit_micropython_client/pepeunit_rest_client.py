import gc
print('3free',  gc.mem_free())
from .file_manager import FileManager
print('4free',  gc.mem_free())
try:
    import mrequests as requests
except ImportError:
    requests = None
print('5free',  gc.mem_free())

class PepeunitRestClient:
    def __init__(self, settings):
        self.settings = settings
        if requests is None:
            raise ImportError('mrequests is required for REST functionality')

    def _get_auth_headers(self):
        return {
            'accept': 'application/json',
            'x-auth-token': self.settings.PEPEUNIT_TOKEN,
        }

    def _get_base_url(self):
        gc.collect()
        return (
            self.settings.HTTP_TYPE
            + '://'
            + self.settings.PEPEUNIT_URL
            + self.settings.PEPEUNIT_APP_PREFIX
            + self.settings.PEPEUNIT_API_ACTUAL_PREFIX
        )

    def download_update(self, unit_uuid, file_path):
        wbits = 9
        level = 9
        url = self._get_base_url() + '/units/firmware/tgz/' + unit_uuid + '?wbits=' + str(wbits) + '&level=' + str(level)
        headers = self._get_auth_headers()
        r = requests.get(url, headers=headers)
        if r.status_code >= 400:
            raise OSError('HTTP error ' + str(r.status_code))
        with open(file_path, 'wb') as f:
            f.write(r.content)
        r.close()

    def download_env(self, unit_uuid, file_path):
        url = self._get_base_url() + '/units/env/' + unit_uuid
        print('url', url)
        headers = self._get_auth_headers()
        print('headers', headers)
        r = requests.get(url, headers=headers)
        print('r', r)
        if r.status_code >= 400:
            raise OSError('HTTP error ' + str(r.status_code))
        data = r.json()
        if isinstance(data, str):
            try:
                import ujson as json
                data = json.loads(data)
            except Exception:
                pass
        FileManager.write_json(file_path, data)
        r.close()

    def download_schema(self, unit_uuid, file_path):
        url = self._get_base_url() + '/units/get_current_schema/' + unit_uuid
        headers = self._get_auth_headers()
        r = requests.get(url, headers=headers)
        if r.status_code >= 400:
            raise OSError('HTTP error ' + str(r.status_code))
        data = r.json()
        if isinstance(data, str):
            try:
                import ujson as json
                data = json.loads(data)
            except Exception:
                pass
        FileManager.write_json(file_path, data)
        r.close()

    def download_file_from_url(self, url, filepath):
        r = requests.get(url)
        if r.status_code >= 400:
            raise OSError('HTTP error ' + str(r.status_code))
        with open(filepath, 'wb') as f:
            f.write(r.content)
        r.close()

    def set_state_storage(self, unit_uuid, state):
        url = self._get_base_url() + '/unit/' + unit_uuid
        headers = self._get_auth_headers()
        headers['content-type'] = 'application/json'
        try:
            import ujson as json
            body = json.dumps(state)
        except Exception:
            body = '{}'
        r = requests.put(url, headers=headers, data=body)
        if r.status_code >= 400:
            raise OSError('HTTP error ' + str(r.status_code))
        r.close()

    def get_state_storage(self, unit_uuid):
        url = self._get_base_url() + '/unit/' + unit_uuid
        headers = self._get_auth_headers()
        r = requests.get(url, headers=headers)
        if r.status_code >= 400:
            raise OSError('HTTP error ' + str(r.status_code))
        data = r.json()
        r.close()
        return data

