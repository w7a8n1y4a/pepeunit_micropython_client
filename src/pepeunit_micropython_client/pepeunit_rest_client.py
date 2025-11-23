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
            'x-auth-token': self.settings.PU_AUTH_TOKEN,
        }

    def _get_base_url(self):
        gc.collect()
        return (
            self.settings.PU_HTTP_TYPE
            + '://'
            + self.settings.PU_DOMAIN
            + self.settings.PU_APP_PREFIX
            + self.settings.PU_API_ACTUAL_PREFIX
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

    def get_input_by_output(self, topic, limit=10, offset=0):
        uuid = topic.split('/')[1]

        base_url = self._get_base_url() + '/unit_nodes'
        headers = self._get_auth_headers()

        params = [
            ('order_by_create_date', 'desc'),
            ('output_uuid', uuid),
            ('limit', str(limit)),
            ('offset', str(offset)),
        ]
        query = '&'.join(['{}={}'.format(k, v) for (k, v) in params])
        url = base_url + '?' + query

        gc.collect()
        r = mrequests.get(url=url, headers=headers)
        if r.status_code >= 400:
            raise OSError('HTTP error ' + str(r.status_code))
        
        data = json.loads(r.text)
        
        r.close()
        gc.collect()
        return data

    def get_units_by_nodes(self, unit_node_uuids, limit=10, offset=0):
        if not unit_node_uuids:
            return {'count': 0, 'units': []}

        base_url = self._get_base_url() + '/units'
        headers = self._get_auth_headers()

        params = [
            ('is_include_output_unit_nodes', 'true'),
            ('order_by_unit_name', 'asc'),
            ('order_by_create_date', 'desc'),
            ('order_by_last_update', 'desc'),
            ('limit', str(limit)),
            ('offset', str(offset)),
        ]
        for uuid in unit_node_uuids:
            params.append(('unit_node_uuids', uuid))

        query = '&'.join(['{}={}'.format(k, v) for (k, v) in params])
        url = base_url + '?' + query

        gc.collect()
        r = mrequests.get(url=url, headers=headers)
        if r.status_code >= 400:
            raise OSError('HTTP error ' + str(r.status_code))

        data = json.loads(r.text)
        
        r.close()
        gc.collect()
        return data

