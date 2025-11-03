import gc
import ujson as json

from .file_manager import FileManager


class PepeunitRestClient:
    def __init__(self, settings):
        self.settings = settings

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

    def _download_file(self, url, headers, file_path):
        from mrequests import get as m_get
        gc.collect()

        r = m_get(url=url, headers=headers)

        if r.status_code == 200:
            r.save(file_path, buf=bytearray(256))
        elif  r.status_code >= 400:
            raise OSError('HTTP error ' + str(r.status_code))
        r.close()
        gc.collect()


    def download_update(self, unit_uuid, file_path):
        url = self._get_base_url() + '/units/firmware/tgz/' + unit_uuid + '?wbits=9&level=9'
        headers = self._get_auth_headers()
        
        self._download_file(url, headers, file_path)

    def download_env(self, unit_uuid, file_path):
        url = self._get_base_url() + '/units/env/' + unit_uuid
        headers = self._get_auth_headers()
        self._download_file(url, headers, file_path)
        
        read_file = FileManager.read_json(file_path)
        json_load = json.loads(read_file)
        FileManager.write_json(file_path, json_load)

    def download_schema(self, unit_uuid, file_path):
        url = self._get_base_url() + '/units/get_current_schema/' + unit_uuid
        headers = self._get_auth_headers()

        self._download_file(url, headers, file_path)

        read_file = FileManager.read_json(file_path)
        json_load = json.loads(read_file)
        FileManager.write_json(file_path, json_load)

    def set_state_storage(self, unit_uuid, state):
        url = self._get_base_url() + '/unit/' + unit_uuid
        headers = self._get_auth_headers()
        headers['content-type'] = 'application/json'
        try:
            body = json.dumps(state)
        except Exception:
            body = '{}'

        from mrequests import put as m_put
        r = m_put(url, headers=headers, data=body)
        if r.status_code >= 400:
            raise OSError('HTTP error ' + str(r.status_code))
        r.close()

    def get_state_storage(self, unit_uuid):
        url = self._get_base_url() + '/unit/' + unit_uuid
        headers = self._get_auth_headers()

        from mrequests import get as m_get
        r = m_get(url, headers=headers)
        if r.status_code >= 400:
            raise OSError('HTTP error ' + str(r.status_code))
        data = r.json()
        r.close()
        return data

