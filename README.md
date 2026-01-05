# Client Framework for Pepeunit

<div align="center">
    <img align="center" src="https://pepeunit.com/pepeunit-og.jpg"  width="640" height="320">
</div>

A cross-platform Python library for integrating with the PepeUnit IoT platform. This library provides MQTT and REST client functionality for managing device communications, configurations, and state management.

## Installation
1. Download the latest version for your Micropython board with the Pepeunit library - [Releases](https://git.pepemoss.com/pepe/pepeunit/libs/pepeunit_micropython_client/-/releases)
1. Write the interpreter to your board: [esp8266 example](https://micropython.org/download/ESP8266_GENERIC/), [esp32 example](https://micropython.org/download/ESP32_GENERIC/)
1. Write your code to the board, for example using the command: `ampy -p /dev/ttyUSB0 -b 115200 put ./example/ .`


## Usage Example

- `main.py`
```python
"""
Basic PepeUnit Client Example

To use this example, simply create a Pepeunit Unit based on the repository https://git.pepemoss.com/pepe/pepeunit/units/universal_test_unit on any instance.

The resulting schema.json and env.json files should be added to the example directory.

This example demonstrates basic usage of the PepeUnit client with both MQTT and REST functionality.
It shows how to:
- Initialize the client with configuration files
- Set up message handlers
- Subscribe to topics
- Run the main application cycle
- Storage api
- Units Nodes api
- Cipher api
"""

import time
import gc

from pepeunit_micropython_client.client import PepeunitClient
from pepeunit_micropython_client.enums import SearchTopicType, SearchScope
from pepeunit_micropython_client.cipher import AesGcmCipher
    
last_output_send_time = 0

def output_handler(client: PepeunitClient):
    global last_output_send_time
    current_time = client.time_manager.get_epoch_ms()
    
    if (current_time - last_output_send_time) / 1000 >= client.settings.DELAY_PUB_MSG:
        message = str(time.ticks_ms())
        print('free mem:', gc.mem_free())
        
        client.logger.debug(f"Send to output/pepeunit: {message}", file_only=True)
        
        client.publish_to_topics("output/pepeunit", message)
        
        last_output_send_time = current_time


def input_handler(client: PepeunitClient, msg):
    try:
        topic_parts = msg.topic.split("/")
        if len(topic_parts) == 3:
            topic_name = client.schema.find_topic_by_unit_node(
                msg.topic, SearchTopicType.FULL_NAME, SearchScope.INPUT
            )

            if topic_name == "input/pepeunit":
                value = msg.payload
                try:
                    value = int(value)
                    client.logger.debug(f"Get from input/pepeunit: {value}", file_only=True)

                except ValueError:
                    client.logger.error(f"Value is not a number: {value}")

    except Exception as e:
        client.logger.error(f"Input handler error: {e}")


def test_set_get_storage(client: PepeunitClient):

    try:
        client.rest_client.set_state_storage('This line is saved in Pepeunit Instance')
        client.logger.info(f"Success set state")
        
        state = client.rest_client.get_state_storage()
        client.logger.info(f"Success get state: {state}")
    except Exception as e:
        client.logger.error(f"Test set get storage failed: {e}")


def test_get_units(client: PepeunitClient):
    try:
        output_topic_urls = client.schema.output_topic.get('output/pepeunit', [])
        if output_topic_urls:
            unit_nodes_response = client.rest_client.get_input_by_output(output_topic_urls[0])
            client.logger.info("Found {} unit nodes".format(unit_nodes_response.get('count', 0)))
            
            unit_node_uuids = [item.get('uuid')for item in unit_nodes_response.get('unit_nodes', [])]
            
            if unit_node_uuids:
                units_response = client.rest_client.get_units_by_nodes(unit_node_uuids)
                client.logger.info("Found {} units".format(units_response.get('count', 0)))
                
                for unit in units_response.get('units', []):
                    name = unit.get('name')
                    uuid = unit.get('uuid')
                    client.logger.info("Unit: {} (UUID: {})".format(name, uuid))
    except Exception as e:
        client.logger.error("Test get units failed: {}".format(e))

def test_cipher(client: PepeunitClient):
    try:
        aes_cipher = AesGcmCipher()
        text = "pepeunit cipher test"
        enc = aes_cipher.aes_gcm_encode(text, client.settings.PU_ENCRYPT_KEY)
        client.logger.info(f"Cipher data {enc}")
        dec = aes_cipher.aes_gcm_decode(enc, client.settings.PU_ENCRYPT_KEY)
        client.logger.info(f"Decoded data: {dec}")
    except Exception as e:
        client.logger.error("Cipher test error: {}".format(e))


def main(client: PepeunitClient):
    test_set_get_storage(client)
    test_get_units(client)
    test_cipher(client)
    
    client.set_mqtt_input_handler(input_handler)
    client.mqtt_client.connect()
    client.subscribe_all_schema_topics()
    client.set_output_handler(output_handler)
    client.run_main_cycle()


if __name__ == '__main__':
    try:
        main(client)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        client.logger.critical(f"Error with reset: {str(e)}", file_only=True)
        client.restart_device()

```

- `boot.py`

```python
import gc

from pepeunit_micropython_client.client import PepeunitClient

print('\nRun init PepeunitClient')

client = PepeunitClient(
    env_file_path='/env.json',
    schema_file_path='/schema.json',
    log_file_path='/log.json',
    cycle_speed=0.001,
    ff_wifi_manager_enable=True,
)

client.wifi_manager.connect_forever()

client.time_manager.sync_epoch_ms_from_ntp()

gc.collect()

client.logger.warning(f'Init Success: free_mem {gc.mem_free()}: alloc_mem {gc.mem_alloc()}', file_only=True)

```

## API Reference
### PepeunitClient

Method | Description
--- | ---
`get_system_state()` | Returns current device system metrics (time, memory, CPU freq, FS stats, version, network).
`set_mqtt_input_handler(handler)` | Registers a handler for incoming MQTT messages (after base client commands).
`download_env(file_path)` | Downloads env from Pepeunit and reloads client settings.
`download_schema(file_path)` | Downloads the current schema and updates the schema manager; schedules resubscription.
`set_state_storage(state)` | Stores arbitrary unit state in Pepeunit.
`get_state_storage()` | Returns stored unit state from Pepeunit.
`perform_update()` | Downloads and extracts the firmware update archive.
`subscribe_all_schema_topics()` | Subscribes to all MQTT topics from the current schema.
`publish_to_topics(topic_key, message)` | Publishes a message to all topics associated with the schema key (`output_*`).
`run_main_cycle()` | Starts the main loop handling MQTT and periodic state publishing.
`set_output_handler(output_handler)` | Registers a handler invoked on each cycle.
`set_custom_update_handler(custom_update_handler)` | Registers a custom handler for the update command.
`stop_main_cycle()` | Stops the main loop.
`restart_device()` | Reboots the device.

### PepeunitMqttClient

Method | Description
--- | ---
`connect()` | Establishes a connection to the MQTT broker.
`disconnect()` | Closes the connection to the MQTT broker.
`set_input_handler(handler)` | Sets a handler for incoming MQTT messages.
`subscribe_topics(topics)` | Subscribes to the provided list of topics.
`publish(topic, message)` | Publishes a message to the specified topic.
`check_msg()` | Polls and processes incoming messages.

### PepeunitRestClient

Method | Description
--- | ---
`download_update(file_path)` | Downloads the unit firmware update archive.
`download_env(file_path)` | Downloads env and saves it to a JSON file.
`download_schema(file_path)` | Downloads the current schema and saves it to a JSON file.
`set_state_storage(state)` | Sets arbitrary unit state.
`get_state_storage()` | Returns the stored unit state (string).
`get_input_by_output(topic, limit=10, offset=0)` | Returns input nodes by a unit's output topic.
`get_units_by_nodes(unit_node_uuids, limit=10, offset=0)` | Returns units by a list of node UUIDs.

### Settings

Method | Description
--- | ---
`unit_uuid` | Unit UUID derived from the auth token.
`load_from_file()` | Loads settings from the env JSON file.

### SchemaManager

Method | Description
--- | ---
`update_from_file()` | Loads and caches the schema from file.
`input_base_topic` | Schema section of base input topics.
`output_base_topic` | Schema section of base output topics.
`input_topic` | Schema section of input topics.
`output_topic` | Schema section of output topics.
`find_topic_by_unit_node(search_value, search_type, search_scope)` | Finds the topic key by node UUID or full name; search scope defined by `SearchScope`.

### FileManager

Method | Description
--- | ---
`dirname(path)` | Returns the directory part from a path.
`read_json(file_path)` | Reads JSON from a file.
`write_json(file_path, data)` | Writes JSON to a file (creates directories if needed).
`file_exists(file_path)` | Checks whether a file exists.
`append_ndjson_with_limit(file_path, item, max_lines)` | Appends an entry to an NDJSON file, limiting the number of lines.
`iter_ndjson(file_path)` | Iterates items of an NDJSON file.
`iter_lines_bytes(file_path)` | Iterates non-empty lines of a file as bytes.
`trim_ndjson(file_path, max_lines)` | Trims an NDJSON file to the last N lines.
`extract_tar_gz(tgz_path, dest_root)` | Extracts a .tgz archive to the destination directory.

### Logger

Method | Description
--- | ---
`debug(message, file_only=False)` | Debug-level log (to file and/or MQTT).
`info(message, file_only=False)` | Info-level log (to file and/or MQTT).
`warning(message, file_only=False)` | Warning-level log (to file and/or MQTT).
`error(message, file_only=False)` | Error-level log (to file and/or MQTT).
`critical(message, file_only=False)` | Critical-level log (to file and/or MQTT).
`reset_log()` | Clears the log file.
`iter_log()` | Iterates log entries from the file.

### TimeManager

Method | Description
--- | ---
`sync_epoch_ms_from_ntp()` | Sync epoch ms from ntp server
`set_epoch_base_ms(epoch_ms)` | Sets the base epoch time in milliseconds.
`get_epoch_ms()` | Returns the current time in milliseconds; when base is set, computed via ticks.

### WifiManager
Method | Description
--- | ---
`get_sta()` | Returns (and lazily creates) the `network.WLAN(network.STA_IF)` station interface.
`is_connected()` | Returns `True` if station is connected.
`get_connected_ssid()` | Returns SSID of the current connection (or empty string if unknown).
`scan_has_target_ssid()` | Scans for APs and returns `True` if target SSID `PUC_WIFI_SSID` is present.
`connect_once(timeout_ms=10000)` | Tries to connect to `PUC_WIFI_SSID`/`PUC_WIFI_PASS` once; returns `True` on success, `False` on timeout.
`connect_forever(connect_timeout_ms=10000)` | Reconnect loop with backoff (capped by `PUC_MAX_RECONNECTION_INTERVAL`) until connected to target SSID.
`ensure_connected()` | Ensures WiFi is connected; if not, calls `connect_forever()`.


### AesGcmCipher

The key can be 16, 24, or 32 bits long.

Method | Description
--- | ---
`aes_gcm_encode(data: str, key: str) -> str` | Encrypts text and returns `base64(nonce).base64(cipher)`.
`aes_gcm_decode(data: str, key: str) -> str` | Decrypts encoded string back to plaintext.

### Enum

Entity | Key | Description
--- | --- | ---
`LogLevel` | `DEBUG` | Debug log level.
`LogLevel` | `INFO` | Info log level.
`LogLevel` | `WARNING` | Warning log level.
`LogLevel` | `ERROR` | Error log level.
`LogLevel` | `CRITICAL` | Critical log level.
`SearchTopicType` | `UNIT_NODE_UUID` | Search by unit node UUID.
`SearchTopicType` | `FULL_NAME` | Search by full topic name.
`SearchScope` | `ALL` | Search sections: input and output.
`SearchScope` | `INPUT` | Search sections: input only.
`SearchScope` | `OUTPUT` | Search sections: output only.
`DestinationTopicType` | `INPUT_BASE_TOPIC` | Schema section: base input topics.
`DestinationTopicType` | `OUTPUT_BASE_TOPIC` | Schema section: base output topics.
`DestinationTopicType` | `INPUT_TOPIC` | Schema section: input topics.
`DestinationTopicType` | `OUTPUT_TOPIC` | Schema section: output topics.
`BaseInputTopicType` | `UPDATE_PEPEUNIT` | Base command to update the client.
`BaseInputTopicType` | `ENV_UPDATE_PEPEUNIT` | Base command to update env.
`BaseInputTopicType` | `SCHEMA_UPDATE_PEPEUNIT` | Base command to update schema.
`BaseInputTopicType` | `LOG_SYNC_PEPEUNIT` | Base command to synchronize logs.
`BaseOutputTopicType` | `LOG_PEPEUNIT` | Base output topic for logs.
`BaseOutputTopicType` | `STATE_PEPEUNIT` | Base output topic for state.
`RestartMode` | `RESTART_EXEC` | After update, execute update and restart.
`RestartMode` | `NO_RESTART` | Do not restart the device after update.
