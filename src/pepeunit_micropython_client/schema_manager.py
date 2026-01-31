from .enums import SearchTopicType, SearchScope, DestinationTopicType

import utils
import ujson as json


class SchemaManager:
    def __init__(self, schema_file_path):
        self.schema_file_path = schema_file_path
        self._schema_data = self.update_from_file()

    def update_from_file(self):
        try:
            with open(self.schema_file_path, "r") as f:
                data = json.load(f)
                if isinstance(data, str):
                    data = json.loads(data)
                self._schema_data = data
        except Exception:
            self._schema_data = {}

        return self._schema_data

    @property
    def input_base_topic(self):
        return self._schema_data.get(DestinationTopicType.INPUT_BASE_TOPIC, {})

    @property
    def output_base_topic(self):
        return self._schema_data.get(DestinationTopicType.OUTPUT_BASE_TOPIC, {})

    @property
    def input_topic(self):
        return self._schema_data.get(DestinationTopicType.INPUT_TOPIC, {})

    @property
    def output_topic(self):
        return self._schema_data.get(DestinationTopicType.OUTPUT_TOPIC, {})

    async def find_topic_by_unit_node(self, search_value, search_type, search_scope=SearchScope.ALL):
        sections = self._get_sections_by_scope(search_scope)
        for section in sections:
            if search_type == SearchTopicType.UNIT_NODE_UUID:
                result = await self._search_uuid_in_topic_section(section, search_value)
            elif search_type == SearchTopicType.FULL_NAME:
                result = await self._search_topic_name_in_section(section, search_value)
            else:
                result = None
            if result:
                return result
        return None

    def _get_sections_by_scope(self, search_scope):
        if search_scope == SearchScope.ALL:
            return [DestinationTopicType.INPUT_TOPIC, DestinationTopicType.OUTPUT_TOPIC]
        elif search_scope == SearchScope.INPUT:
            return [DestinationTopicType.INPUT_TOPIC]
        elif search_scope == SearchScope.OUTPUT:
            return [DestinationTopicType.OUTPUT_TOPIC]
        else:
            return []

    async def _search_uuid_in_topic_section(self, section, uuid):
        topic_section = self._schema_data.get(section, {})
        idx = 0
        for topic_name, topic_list in topic_section.items():
            for topic_url in topic_list:
                if self._extract_uuid_from_topic(topic_url) == uuid:
                    return topic_name
                idx += 1
                await utils.ayield(idx, every=32)
        return None

    def _extract_uuid_from_topic(self, topic_url):
        first = topic_url.find('/')
        if first < 0:
            return None
        second = topic_url.find('/', first + 1)
        if second < 0:
            uuid = topic_url[first + 1:]
        else:
            uuid = topic_url[first + 1:second]
        return uuid if uuid else None

    async def _search_topic_name_in_section(self, section, topic_name):
        topic_section = self._schema_data.get(section, {})
        idx = 0
        for topic_key, topic_list in topic_section.items():
            for topic_url in topic_list:
                if topic_url == topic_name:
                    return topic_key
                idx += 1
                await utils.ayield(idx, every=32)
        return None
