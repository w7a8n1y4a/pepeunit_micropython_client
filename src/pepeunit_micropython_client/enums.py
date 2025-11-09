class LogLevel:
    DEBUG = 'Debug'
    INFO = 'Info'
    WARNING = 'Warning'
    ERROR = 'Error'
    CRITICAL = 'Critical'

    @staticmethod
    def get_int_level(level_str):
        mapping = {
            LogLevel.DEBUG: 0,
            LogLevel.INFO: 1,
            LogLevel.WARNING: 2,
            LogLevel.ERROR: 3,
            LogLevel.CRITICAL: 4,
        }
        return mapping.get(level_str, 0)


class SearchTopicType:
    UNIT_NODE_UUID = 'unit_node_uuid'
    FULL_NAME = 'full_name'


class SearchScope:
    ALL = 'all'
    INPUT = 'input'
    OUTPUT = 'output'


class DestinationTopicType:
    INPUT_BASE_TOPIC = 'input_base_topic'
    OUTPUT_BASE_TOPIC = 'output_base_topic'
    INPUT_TOPIC = 'input_topic'
    OUTPUT_TOPIC = 'output_topic'


class BaseInputTopicType:
    UPDATE_PEPEUNIT = 'update/pepeunit'
    ENV_UPDATE_PEPEUNIT = 'env_update/pepeunit'
    SCHEMA_UPDATE_PEPEUNIT = 'schema_update/pepeunit'
    LOG_SYNC_PEPEUNIT = 'log_sync/pepeunit'


class BaseOutputTopicType:
    LOG_PEPEUNIT = 'log/pepeunit'
    STATE_PEPEUNIT = 'state/pepeunit'


class RestartMode:
    RESTART_EXEC = 'restart_exec'
    NO_RESTART = 'no_restart'
