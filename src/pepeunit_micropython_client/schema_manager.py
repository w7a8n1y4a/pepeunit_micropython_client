import gc

from .file_manager import FileManager
from .enums import SearchTopicType, SearchScope, DestinationTopicType


class SchemaManager:
    def __init__(self, schema_file_path):
        self.schema_file_path = schema_file_path
        self._schema_data = self.update_from_file()

    def update_from_file(self):
        self._schema_data = FileManager.read_json(self.schema_file_path)
        gc.collect()

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

    def find_topic_by_unit_node(self, search_value, search_type, search_scope=SearchScope.ALL):
        sections = self._get_sections_by_scope(search_scope)
        for section in sections:
            if search_type == SearchTopicType.UNIT_NODE_UUID:
                result = self._search_uuid_in_topic_section(section, search_value)
            elif search_type == SearchTopicType.FULL_NAME:
                result = self._search_topic_name_in_section(section, search_value)
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

    def _search_uuid_in_topic_section(self, section, uuid):
        topic_section = self._schema_data.get(section, {})
        for topic_name, topic_list in topic_section.items():
            for topic_url in topic_list:
                if self._extract_uuid_from_topic(topic_url) == uuid:
                    return topic_name
        return None

    def _extract_uuid_from_topic(self, topic_url):
        parts = topic_url.split('/')
        if len(parts) >= 2:
            return parts[1]
        return None

    def _search_topic_name_in_section(self, section, topic_name):
        topic_section = self._schema_data.get(section, {})
        for topic_key, topic_list in topic_section.items():
            for topic_url in topic_list:
                if topic_url == topic_name:
                    return topic_key
        return None
