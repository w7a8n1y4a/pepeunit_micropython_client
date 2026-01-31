import gc
import ujson as json
try:
    import uasyncio as asyncio  # MicroPython
except ImportError:  # CPython
    import asyncio

from .async_http import request


class PepeunitRestClient:
    def __init__(self, settings):
        self.settings = settings

    def _get_auth_headers(self):
        return {
            'accept': 'application/json',
            'x-auth-token': self.settings.PU_AUTH_TOKEN,
        }

    def _get_base_url(self):
        return (
            self.settings.PU_HTTP_TYPE
            + '://'
            + self.settings.PU_DOMAIN
            + self.settings.PU_APP_PREFIX
            + self.settings.PU_API_ACTUAL_PREFIX
        )

    async def _download_file(self, url, headers, file_path):
        status, _, _ = await request("GET", url, headers=headers, save_to=file_path, bufsize=256)
        if status >= 400:
            raise OSError("HTTP error {}".format(status))
        gc.collect()


    async def download_update(self, file_path):
        url = self._get_base_url() + '/units/firmware/tgz/' + self.settings.unit_uuid + '?wbits=9&level=9'
        headers = self._get_auth_headers()
        
        await self._download_file(url, headers, file_path)

    async def download_env(self, file_path):
        url = self._get_base_url() + '/units/env/' + self.settings.unit_uuid
        headers = self._get_auth_headers()
        await self._download_file(url, headers, file_path)
        # Avoid JSON load/dump pass: it can spike RAM on low-memory boards.
        gc.collect()

    async def download_schema(self, file_path):
        url = self._get_base_url() + '/units/get_current_schema/' + self.settings.unit_uuid
        headers = self._get_auth_headers()

        await self._download_file(url, headers, file_path)
        # Avoid JSON load/dump pass: it can spike RAM on low-memory boards.
        gc.collect()

    async def set_state_storage(self, state):
        url = self._get_base_url() + '/units/set_state_storage/' + self.settings.unit_uuid
        headers = self._get_auth_headers()
        headers['content-type'] = 'application/json'

        payload = json.dumps({'state': state})
        status, _, _ = await request("POST", url, headers=headers, body=payload, max_body=2048)
        if status >= 400:
            raise OSError("HTTP error {}".format(status))
        gc.collect()
        

    async def get_state_storage(self):
        url = self._get_base_url() + '/units/get_state_storage/' + self.settings.unit_uuid
        headers = self._get_auth_headers()

        status, _, body = await request("GET", url, headers=headers, max_body=4096)
        if status >= 400:
            raise OSError("HTTP error {}".format(status))
        gc.collect()

        try:
            return body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else body
        except Exception:
            return body

    async def get_input_by_output(self, topic, limit=10, offset=0):
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

        status, _, body = await request("GET", url, headers=headers, max_body=16_000)
        if status >= 400:
            raise OSError("HTTP error {}".format(status))

        data = json.loads(body)
        gc.collect()
        return data

    async def get_units_by_nodes(self, unit_node_uuids, limit=10, offset=0):
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

        status, _, body = await request("GET", url, headers=headers, max_body=32_000)
        if status >= 400:
            raise OSError("HTTP error {}".format(status))

        data = json.loads(body)
        gc.collect()
        return data

