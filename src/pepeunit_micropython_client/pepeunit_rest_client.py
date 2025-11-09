import gc
import ujson as json
import mrequests

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
        gc.collect()

        r = mrequests.get(url=url, headers=headers)

        if r.status_code == 200:
            r.save(file_path, buf=bytearray(256))
        elif  r.status_code >= 400:
            raise OSError('HTTP error ' + str(r.status_code))
        r.close()
        gc.collect()


    def download_update(self, file_path):
        url = self._get_base_url() + '/units/firmware/tgz/' + self.settings.unit_uuid + '?wbits=9&level=9'
        headers = self._get_auth_headers()
        
        self._download_file(url, headers, file_path)

    def download_env(self, file_path):
        url = self._get_base_url() + '/units/env/' + self.settings.unit_uuid
        headers = self._get_auth_headers()
        self._download_file(url, headers, file_path)
        
        read_file = FileManager.read_json(file_path)
        json_load = json.loads(read_file)
        FileManager.write_json(file_path, json_load)

    def download_schema(self, file_path):
        url = self._get_base_url() + '/units/get_current_schema/' + self.settings.unit_uuid
        headers = self._get_auth_headers()

        self._download_file(url, headers, file_path)

        read_file = FileManager.read_json(file_path)
        json_load = json.loads(read_file)
        FileManager.write_json(file_path, json_load)

    def set_state_storage(self, state):
        url = self._get_base_url() + '/units/set_state_storage/' + self.settings.unit_uuid
        headers = self._get_auth_headers()
        headers['content-type'] = 'application/json'

        r = mrequests.post(url, headers=headers, data=json.dumps({'state': state}))
        if r.status_code >= 400:
            raise OSError('HTTP error ' + str(r.status_code))
        r.close()

    def get_state_storage(self):
        url = self._get_base_url() + '/units/get_state_storage/' + self.settings.unit_uuid
        headers = self._get_auth_headers()

        r = mrequests.get(url, headers=headers)
        if r.status_code >= 400:
            raise OSError('HTTP error ' + str(r.status_code))
        data = r.text
        r.close()
        return data

