# Client Framework for Pepeunit

<div align="center">
    <img align="center" src="https://pepeunit.com/pepeunit-og.jpg"  width="640" height="320">
</div>

A cross-platform MicroPython library for integrating with the PepeUnit IoT platform. This library provides MQTT and REST client functionality for managing device communications, configurations, and state management. Built on `uasyncio` and `mqtt_as`.

## Installation
1. Download the latest version for your MicroPython board with the Pepeunit library — [Releases](https://git.pepemoss.com/pepe/pepeunit/libs/pepeunit_micropython_client/-/releases)
2. Flash the MicroPython interpreter to your board: [esp8266](https://micropython.org/download/ESP8266_GENERIC/), [esp32](https://micropython.org/download/ESP32_GENERIC/)
3. Upload your code to the board, for example: `ampy -p /dev/ttyUSB0 -b 115200 put ./example/ .`

## Usage Example

- `boot.py`

```python
import gc

import uasyncio as asyncio

from pepeunit_micropython_client.client import PepeunitClient

print('\nRun init PepeunitClient')

client = PepeunitClient(
    env_file_path='/env.json',
    schema_file_path='/schema.json',
    log_file_path='/log.json',
    ff_wifi_manager_enable=True,
)

async def _boot_init():
    if client.wifi_manager:
        await client.wifi_manager.connect_forever()
    await client.time_manager.sync_epoch_ms_from_ntp()

asyncio.run(_boot_init())

gc.collect()

client.logger.warning('Init Success: free_mem {}: alloc_mem {}'.format(gc.mem_free(), gc.mem_alloc()), file_only=True)
```

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
- Async work
"""

import time
import gc
import uasyncio as asyncio

from pepeunit_micropython_client.client import PepeunitClient
from pepeunit_micropython_client.enums import SearchTopicType, SearchScope
from pepeunit_micropython_client.cipher import AesGcmCipher
    
last_output_send_time = 0

async def output_handler(client: PepeunitClient):
    global last_output_send_time
    current_time = client.time_manager.get_epoch_ms()
    
    if (current_time - last_output_send_time) // 1000 >= client.settings.DELAY_PUB_MSG:
        gc.collect()
        message = str(time.ticks_ms())
        
        client.logger.debug("Send to output/pepeunit: {}".format(message), file_only=True)
        
        await client.publish_to_topics("output/pepeunit", message)
        
        last_output_send_time = current_time


async def input_handler(client: PepeunitClient, msg):
    try:
        topic_parts = msg.topic.split("/")
        if len(topic_parts) == 3:
            gc.collect()
            topic_name = await client.schema.find_topic_by_unit_node(
                msg.topic, SearchTopicType.FULL_NAME, SearchScope.INPUT
            )

            if topic_name == "input/pepeunit":
                value = msg.payload
                try:
                    value = int(value)
                    print('time', time.ticks_ms(), 'free mem:', gc.mem_free())
                    client.logger.debug("Get from input/pepeunit: {}".format(value), file_only=True)

                except ValueError:
                    client.logger.error("Value is not a number: {}".format(value))

    except Exception as e:
        client.logger.error("Input handler error: {}".format(e))


async def test_set_get_storage(client: PepeunitClient):

    try:
        await client.rest_client.set_state_storage('This line is saved in Pepeunit Instance')
        client.logger.info("Success set state")
        
        state = await client.rest_client.get_state_storage()
        client.logger.info("Success get state: {}".format(state))
    except Exception as e:
        client.logger.error("Test set get storage failed: {}".format(e))


async def test_get_units(client: PepeunitClient):
    try:
        gc.collect()
        output_topic_urls = client.schema.output_topic.get('output/pepeunit', [])
        if output_topic_urls:
            unit_nodes_response = await client.rest_client.get_input_by_output(output_topic_urls[0], limit=1, offset=0)
            client.logger.info("Found {} unit nodes".format(unit_nodes_response.get('count', 0)))
            
            unit_node_uuids = []
            for item in unit_nodes_response.get('unit_nodes', []) or ():
                uuid = item.get('uuid')
                if uuid:
                    unit_node_uuids.append(uuid)
                    break
            
            if unit_node_uuids:
                gc.collect()
                units_response = await client.rest_client.get_units_by_nodes(
                    unit_node_uuids,
                    limit=1,
                    offset=0
                )
                client.logger.info("Found {} units".format(units_response.get('count', 0)))
                
                for unit in units_response.get('units', []):
                    name = unit.get('name')
                    uuid = unit.get('uuid')
                    client.logger.info("Unit: {} (UUID: {})".format(name, uuid))
            gc.collect()

    except Exception as e:
        client.logger.error("Test get units failed: {}".format(e))

async def test_cipher(client: PepeunitClient):
    try:
        aes_cipher = AesGcmCipher()
        text = "pepeunit cipher test"
        enc = await aes_cipher.aes_gcm_encode(text, client.settings.PU_ENCRYPT_KEY)
        client.logger.info("Cipher data {}".format(enc))
        dec = await aes_cipher.aes_gcm_decode(enc, client.settings.PU_ENCRYPT_KEY)
        client.logger.info("Decoded data: {}".format(dec))
    except Exception as e:
        client.logger.error("Cipher test error: {}".format(e))


async def main_async(client: PepeunitClient):
    await test_set_get_storage(client)
    await test_get_units(client)
    await test_cipher(client)
    
    client.set_mqtt_input_handler(input_handler)
    client.subscribe_all_schema_topics()
    client.set_output_handler(output_handler)
    await client.run_main_cycle()


if __name__ == '__main__':
    try:
        asyncio.run(main_async(client))
    except KeyboardInterrupt:
        raise
    except Exception as e:
        try:
            client.logger.critical("Error with reset: {}".format(e), file_only=True)
        except Exception:
            print("Error critical log")
        client.restart_device()

```

## API Reference

### PepeunitClient

Method | Description
--- | ---
`get_system_state()` | Returns current device system metrics (time, memory, CPU freq, FS stats, version, network).
`set_mqtt_input_handler(handler)` | Registers an async handler for incoming MQTT messages (after base client commands).
`set_output_handler(output_handler)` | Registers an async handler invoked on each cycle.
`subscribe_all_schema_topics()` | Schedules subscription to all MQTT topics from the current schema (executed in main cycle).
`publish_to_topics(topic_key, message)` | Async. Publishes a message to all topics associated with the schema key (`output_*`).
`run_main_cycle(cycle_ms=20)` | Async. Starts the main loop handling MQTT connection, subscription, and periodic state publishing.
`set_custom_update_handler(custom_update_handler)` | Registers a custom handler for the update command.
`stop_main_cycle()` | Stops the main loop.
`restart_device()` | Reboots the device.
`download_env(file_path)` | Async. Downloads env from Pepeunit and reloads client settings.
`download_schema(file_path)` | Async. Downloads the current schema and updates the schema manager; schedules resubscription.
`set_state_storage(state)` | Async. Stores arbitrary unit state in Pepeunit.
`get_state_storage()` | Async. Returns stored unit state from Pepeunit.
`perform_update()` | Async. Downloads and extracts the firmware update archive.

### PepeunitMqttClient

Method | Description
--- | ---
`connect()` | Async. Establishes a connection to the MQTT broker.
`disconnect()` | Async. Closes the connection to the MQTT broker.
`set_input_handler(handler)` | Sets an async handler for incoming MQTT messages.
`subscribe_all_schema_topics()` | Async. Subscribes to all topics from the schema (input_base_topic, input_topic).
`publish(topic, message, retain=False, qos=0)` | Async. Publishes a message to the specified topic.
`is_connected()` | Returns `True` if connected.
`ensure_connected()` | Async. Ensures MQTT connection; reconnects if needed.
`consume_reconnected()` | Returns `True` if just reconnected (for resubscription logic).
`drop_input()` | Context manager to temporarily drop incoming MQTT messages (e.g. during resubscription).

### PepeunitRestClient

All methods are async.

Method | Description
--- | ---
`download_update(file_path)` | Downloads the unit firmware update archive.
`download_env(file_path)` | Downloads env and saves it to a JSON file.
`download_schema(file_path)` | Downloads the current schema and saves it to a JSON file.
`set_state_storage(state)` | Sets arbitrary unit state.
`get_state_storage()` | Returns the stored unit state (string).
`get_input_by_output(topic, limit=10, offset=0)` | Returns input nodes by a unit's output topic URL.
`get_units_by_nodes(unit_node_uuids, limit=10, offset=0)` | Returns units by a list of node UUIDs.

### Settings

Property/Method | Description
--- | ---
`unit_uuid` | Unit UUID derived from the auth token.
`load_from_file()` | Loads settings from the env JSON file.

### SchemaManager

Property/Method | Description
--- | ---
`update_from_file()` | Loads and caches the schema from file.
`input_base_topic` | Schema section of base input topics.
`output_base_topic` | Schema section of base output topics.
`input_topic` | Schema section of input topics.
`output_topic` | Schema section of output topics.
`find_topic_by_unit_node(search_value, search_type, search_scope)` | Async. Finds the topic key by node UUID or full name; search scope defined by `SearchScope`.

### FileManager (static, async methods)

Method | Description
--- | ---
`read_json(file_path)` | Async. Reads JSON from a file.
`write_json(file_path, data, *, yield_every=32)` | Async. Writes JSON to a file (creates directories if needed).
`file_exists(file_path)` | Async. Checks whether a file exists.
`iter_lines_bytes_cb(file_path, on_line, *, yield_every=32)` | Async. Iterates non-empty lines of a file as bytes; calls `on_line(line)` for each.
`extract_tar_gz(tgz_path, dest_root, *, copy_chunk=256, yield_every=16)` | Async. Extracts a .tgz archive to the destination directory.

### utils (module)

`dirname(path)` | Returns the directory part from a path.

### Logger

Method | Description
--- | ---
`debug(message, file_only=False)` | Debug-level log (to file and/or MQTT).
`info(message, file_only=False)` | Info-level log (to file and/or MQTT).
`warning(message, file_only=False)` | Warning-level log (to file and/or MQTT).
`error(message, file_only=False)` | Error-level log (to file and/or MQTT).
`critical(message, file_only=False)` | Critical-level log (to file and/or MQTT).
`sync_logs_to_mqtt()` | Async. Sends log file contents to MQTT.
`reset_log()` | Async. Clears the log file.

### TimeManager

Method | Description
--- | ---
`sync_epoch_ms_from_ntp()` | Async. Syncs epoch ms from NTP server.
`get_epoch_ms()` | Returns the current time in milliseconds; when base is set, computed via ticks.

### WifiManager

Method | Description
--- | ---
`get_sta()` | Returns (and lazily creates) the `network.WLAN(network.STA_IF)` station interface.
`is_connected()` | Returns `True` if station is connected to target SSID.
`is_wifi_linked()` | Returns `True` if station has any WiFi link.
`scan_has_target_ssid()` | Async. Scans for APs and returns `True` if target SSID `PUC_WIFI_SSID` is present.
`connect_once(timeout_ms=10000)` | Async. Tries to connect to `PUC_WIFI_SSID`/`PUC_WIFI_PASS` once; returns `True` on success.
`connect_forever(connect_timeout_ms=10000)` | Async. Reconnect loop with backoff until connected to target SSID.
`ensure_connected(connect_timeout_ms=10000)` | Async. Ensures WiFi is connected; if not, calls `connect_forever()`.

### AesGcmCipher

The key is a base64-encoded string; after decoding it must be 16, 24, or 32 bytes long.

Method | Description
--- | ---
`aes_gcm_encode(data: str, key: str) -> str` | Async. Encrypts; returns `base64(nonce).base64(cipher+tag)`.
`aes_gcm_decode(data: str, key: str) -> str` | Async. Decrypts encoded string back to plaintext.

### Enums

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
