from .enums import SearchTopicType, SearchScope, DestinationTopicType

import utils
import ujson as json


_SCOPE_SECTIONS_ALL = (DestinationTopicType.INPUT_TOPIC, DestinationTopicType.OUTPUT_TOPIC)
_SCOPE_SECTIONS_INPUT = (DestinationTopicType.INPUT_TOPIC,)
_SCOPE_SECTIONS_OUTPUT = (DestinationTopicType.OUTPUT_TOPIC,)
_SCOPE_SECTIONS_EMPTY = ()


class SchemaManager:
    def __init__(self, schema_file_path):
        self.schema_file_path = schema_file_path
        self._schema_data = self.update_from_file()

    def update_from_file(self):
        with open(self.schema_file_path, "r") as f:
            self._schema_data = json.load(f)

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
        if search_type == SearchTopicType.UNIT_NODE_UUID:
            search_fn = self._search_uuid_in_topic_section
        elif search_type == SearchTopicType.FULL_NAME:
            search_fn = self._search_topic_name_in_section
        else:
            search_fn = None
        for section in sections:
            if search_fn is None:
                result = None
            else:
                result = await search_fn(section, search_value)
            if result:
                return result
        return None

    def _get_sections_by_scope(self, search_scope):
        if search_scope == SearchScope.ALL:
            return _SCOPE_SECTIONS_ALL
        elif search_scope == SearchScope.INPUT:
            return _SCOPE_SECTIONS_INPUT
        elif search_scope == SearchScope.OUTPUT:
            return _SCOPE_SECTIONS_OUTPUT
        else:
            return _SCOPE_SECTIONS_EMPTY

    async def _search_uuid_in_topic_section(self, section, uuid):
        topic_section = self._schema_data.get(section, {})
        idx = 0
        for topic_name, topic_list in topic_section.items():
            for topic_url in topic_list:
                if self._topic_url_matches_uuid(topic_url, uuid):
                    return topic_name
                idx += 1
                await utils.ayield(idx, every=32)
        return None

    def _topic_url_matches_uuid(self, topic_url, uuid):
        if uuid is None:
            return utils.extract_uuid_from_topic(topic_url) is None

        first = topic_url.find('/')
        if first < 0:
            return False

        start = first + 1
        if not topic_url.startswith(uuid, start):
            return False

        end = start + len(uuid)
        return (end == len(topic_url)) or (topic_url[end] == '/')

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
