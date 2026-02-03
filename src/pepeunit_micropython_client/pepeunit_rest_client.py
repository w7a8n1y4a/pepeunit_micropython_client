import gc
import ujson as json
import uasyncio as asyncio

from .async_http import request


class PepeunitRestClient:
    def __init__(self, settings):
        self.settings = settings

    def _get_auth_headers(self, with_json=False):
        if with_json:
            return {
                'accept': 'application/json',
                'x-auth-token': self.settings.PU_AUTH_TOKEN,
                'content-type': 'application/json',
            }
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

    def _raise_for_status(self, status, body=None):
        if status < 400:
            return
        if body is None:
            raise OSError("HTTP error {}".format(status))
        try:
            body_text = body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else body
        except Exception:
            body_text = body
        raise OSError("HTTP error {}: {}".format(status, body_text))

    async def _download_file(self, url, headers, file_path):
        status, _, _ = await request(
            "GET",
            url,
            headers=headers,
            save_to=file_path,
            bufsize=256,
            collect_headers=False,
        )
        self._raise_for_status(status)


    async def download_update(self, file_path):
        url = self._get_base_url() + '/units/firmware/tgz/' + self.settings.unit_uuid + '?wbits=9&level=9'
        headers = self._get_auth_headers()
        await self._download_file(url, headers, file_path)

    async def download_env(self, file_path):
        url = self._get_base_url() + '/units/env/' + self.settings.unit_uuid
        headers = self._get_auth_headers()
        await self._download_file(url, headers, file_path)

    async def download_schema(self, file_path):
        url = self._get_base_url() + '/units/get_current_schema/' + self.settings.unit_uuid
        headers = self._get_auth_headers()

        await self._download_file(url, headers, file_path)

    async def set_state_storage(self, state):
        url = self._get_base_url() + '/units/set_state_storage/' + self.settings.unit_uuid
        headers = self._get_auth_headers(with_json=True)

        payload = json.dumps({'state': state})
        status, _, _ = await request("POST", url, headers=headers, body=payload, max_body=2048)
        self._raise_for_status(status)
        gc.collect()

    async def get_state_storage(self):
        url = self._get_base_url() + '/units/get_state_storage/' + self.settings.unit_uuid
        headers = self._get_auth_headers()

        status, _, body = await request("GET", url, headers=headers, max_body=4096)
        self._raise_for_status(status, body)

        try:
            return body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else body
        except Exception:
            return body

    async def get_input_by_output(self, topic, limit=10, offset=0):
        first_sep = topic.find('/')
        if first_sep < 0:
            uuid = topic
        else:
            second_sep = topic.find('/', first_sep + 1)
            uuid = topic[first_sep + 1:second_sep] if second_sep > first_sep else topic[first_sep + 1:]

        base_url = self._get_base_url() + '/unit_nodes'
        headers = self._get_auth_headers()

        query_parts = [
            'order_by_create_date=desc',
            'output_uuid={}'.format(uuid),
            'limit={}'.format(limit),
            'offset={}'.format(offset),
        ]
        query = '&'.join(query_parts)
        url = base_url + '?' + query

        gc.collect()
        status, _, body = await request(
            "GET",
            url,
            headers=headers,
            max_body=16_000,
            collect_headers=False,
        )
        self._raise_for_status(status, body)

        gc.collect()
        data = json.loads(body)
        gc.collect()
        return data

    async def get_units_by_nodes(self, unit_node_uuids, limit=10, offset=0):
        if not unit_node_uuids:
            return {'count': 0, 'units': []}

        base_url = self._get_base_url() + '/units'
        headers = self._get_auth_headers()

        query_parts = [
            'is_include_output_unit_nodes=true',
            'order_by_unit_name=asc',
            'order_by_create_date=desc',
            'order_by_last_update=desc',
            'limit={}'.format(limit),
            'offset={}'.format(offset),
        ]
        for uuid in unit_node_uuids:
            query_parts.append('unit_node_uuids={}'.format(uuid))

        query = '&'.join(query_parts)
        url = base_url + '?' + query

        gc.collect()
        status, _, body = await request(
            "GET",
            url,
            headers=headers,
            max_body=32_000,
            collect_headers=False,
        )
        self._raise_for_status(status, body)

        gc.collect()
        data = json.loads(body)
        gc.collect()
        return data

