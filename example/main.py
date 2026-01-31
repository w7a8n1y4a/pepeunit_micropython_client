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
import uasyncio as asyncio

from pepeunit_micropython_client.client import PepeunitClient
from pepeunit_micropython_client.enums import SearchTopicType, SearchScope
from pepeunit_micropython_client.cipher import AesGcmCipher
    
last_output_send_time = 0

async def output_handler(client: PepeunitClient):
    global last_output_send_time
    current_time = client.time_manager.get_epoch_ms()
    
    if (current_time - last_output_send_time) / 1000 >= client.settings.DELAY_PUB_MSG:
        gc.collect()
        message = str(time.ticks_ms())
        
        client.logger.debug(f"Send to output/pepeunit: {message}", file_only=True)
        
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
                    client.logger.debug(f"Get from input/pepeunit: {value}", file_only=True)

                except ValueError:
                    client.logger.error(f"Value is not a number: {value}")

    except Exception as e:
        client.logger.error(f"Input handler error: {e}")


async def test_set_get_storage(client: PepeunitClient):

    try:
        await client.rest_client.set_state_storage('This line is saved in Pepeunit Instance')
        client.logger.info(f"Success set state")
        
        state = await client.rest_client.get_state_storage()
        client.logger.info(f"Success get state: {state}")
    except Exception as e:
        client.logger.error(f"Test set get storage failed: {e}")


async def test_get_units(client: PepeunitClient):
    try:
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
                units_response = await client.rest_client.get_units_by_nodes(unit_node_uuids, limit=1, offset=0)
                client.logger.info("Found {} units".format(units_response.get('count', 0)))
                
                for unit in units_response.get('units', []):
                    name = unit.get('name')
                    uuid = unit.get('uuid')
                    client.logger.info("Unit: {} (UUID: {})".format(name, uuid))
    except Exception as e:
        client.logger.error("Test get units failed: {}".format(e))

async def test_cipher(client: PepeunitClient):
    try:
        aes_cipher = AesGcmCipher()
        text = "pepeunit cipher test"
        enc = await aes_cipher.aes_gcm_encode(text, client.settings.PU_ENCRYPT_KEY)
        client.logger.info(f"Cipher data {enc}")
        dec = await aes_cipher.aes_gcm_decode(enc, client.settings.PU_ENCRYPT_KEY)
        client.logger.info(f"Decoded data: {dec}")
    except Exception as e:
        client.logger.error("Cipher test error: {}".format(e))


async def main_async(client: PepeunitClient):
    await client.wifi_manager.ensure_connected()
    await client.time_manager.sync_epoch_ms_from_ntp()

    await test_set_get_storage(client)
    await test_get_units(client)
    await test_cipher(client)
    
    client.set_mqtt_input_handler(input_handler)
    await client.mqtt_client.connect()
    await client.mqtt_client.subscribe_all_schema_topics()
    client.set_output_handler(output_handler)
    await client.run_main_cycle()


if __name__ == '__main__':
    try:
        asyncio.run(main_async(client))
    except KeyboardInterrupt:
        raise
    except Exception as e:
        client.logger.critical(f"Error with reset: {str(e)}", file_only=True)
        client.restart_device()
