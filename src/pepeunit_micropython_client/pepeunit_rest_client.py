import gc
import ujson as json
import utils

from .async_http import request


class PepeunitRestClient:
    def __init__(self, settings):
        self.settings = settings

    def _get_auth_headers(self, with_json=False):
        h = {'accept': 'application/json', 'x-auth-token': self.settings.PU_AUTH_TOKEN}
        if with_json:
            h['content-type'] = 'application/json'
        return h

    def _build_url(self, path):
        return (
            self.settings.PU_HTTP_TYPE
            + '://'
            + self.settings.PU_DOMAIN
            + self.settings.PU_APP_PREFIX
            + self.settings.PU_API_ACTUAL_PREFIX
            + path
        )

    @staticmethod
    def _raise_for_status(status, body=None):
        if status < 400:
            return
        msg = "HTTP error {}".format(status)
        if body is not None:
            msg += ": " + utils.to_str(body)
        raise OSError(msg)

    async def _download_file(self, url, headers, file_path):
        status, _, _ = await request(
            "GET", url, headers=headers, save_to=file_path, bufsize=256, collect_headers=False,
        )
        self._raise_for_status(status)

    async def download_update(self, file_path):
        url = self._build_url('/units/firmware/tgz/' + self.settings.unit_uuid + '?wbits=9&level=9')
        await self._download_file(url, self._get_auth_headers(), file_path)

    async def download_env(self, file_path):
        url = self._build_url('/units/env/' + self.settings.unit_uuid)
        await self._download_file(url, self._get_auth_headers(), file_path)

    async def download_schema(self, file_path):
        url = self._build_url('/units/get_current_schema/' + self.settings.unit_uuid)
        await self._download_file(url, self._get_auth_headers(), file_path)

    async def set_state_storage(self, state):
        url = self._build_url('/units/set_state_storage/' + self.settings.unit_uuid)
        payload = json.dumps({'state': state})
        status, _, _ = await request(
            "POST", url, headers=self._get_auth_headers(with_json=True), body=payload, collect_headers=False,
        )
        self._raise_for_status(status)
        gc.collect()

    async def get_state_storage(self):
        url = self._build_url('/units/get_state_storage/' + self.settings.unit_uuid)
        status, _, body = await request("GET", url, headers=self._get_auth_headers(), collect_headers=False)
        self._raise_for_status(status, body)
        result = utils.to_str(body)
        del body
        gc.collect()
        return result

    async def get_input_by_output(self, topic, limit=10, offset=0):
        uuid = utils.extract_uuid_from_topic(topic, allow_no_slash=True)
        query = 'order_by_create_date=desc&output_uuid={}&limit={}&offset={}'.format(uuid, limit, offset)
        url = self._build_url('/unit_nodes?' + query)

        gc.collect()
        status, _, body = await request("GET", url, headers=self._get_auth_headers(), collect_headers=False)
        self._raise_for_status(status, body)

        data = json.loads(body)
        del body
        gc.collect()
        return data

    async def get_units_by_nodes(self, unit_node_uuids, limit=10, offset=0):
        if not unit_node_uuids:
            return {'count': 0, 'units': []}

        parts = [
            'is_include_output_unit_nodes=true',
            'order_by_unit_name=asc',
            'order_by_create_date=desc',
            'order_by_last_update=desc',
            'limit={}'.format(limit),
            'offset={}'.format(offset),
        ]
        for uuid in unit_node_uuids:
            parts.append('unit_node_uuids={}'.format(uuid))
        url = self._build_url('/units?' + '&'.join(parts))
        del parts

        gc.collect()
        status, _, body = await request("GET", url, headers=self._get_auth_headers(), collect_headers=False)
        self._raise_for_status(status, body)

        data = json.loads(body)
        del body
        gc.collect()
        return data
