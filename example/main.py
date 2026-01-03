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
import machine

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
        client.logger.info("I'll be back", file_only=True)
        machine.reset()
