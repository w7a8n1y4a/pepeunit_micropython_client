from .file_manager import FileManager
from .enums import DestinationTopicType


class SchemaManager:
    def __init__(self, schema_file_path):
        self.schema_file_path = schema_file_path
        self._schema_data = self.update_from_file()

    def update_from_file(self):
        return FileManager.read_json(self.schema_file_path)

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
