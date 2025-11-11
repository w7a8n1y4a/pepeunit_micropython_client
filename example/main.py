import time
import gc
from pepeunit_micropython_client.client import PepeunitClient
from pepeunit_micropython_client.enums import SearchTopicType, SearchScope
    
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

                    if value < 10000:
                        client.rest_client.set_state_storage('This line is saved in Pepeunit Instance')
                        client.logger.info(f"Success set state")
                    
                    if value > 10000 and value < 20000:
                        state = client.rest_client.get_state_storage()
                        client.logger.info(f"Success get state: {state}")

                    client.logger.debug(f"Get from input/pepeunit: {value}", file_only=True)

                except ValueError:
                    client.logger.error(f"Value is not a number: {value}")

    except Exception as e:
        client.logger.error(f"Input handler error: {e}")


def main():
    client = PepeunitClient(
        env_file_path='/env.json',
        schema_file_path='/schema.json',
        log_file_path='/log.json',
        sta=sta
    )
    client.set_mqtt_input_handler(input_handler)
    client.mqtt_client.connect()
    client.subscribe_all_schema_topics()
    client.set_output_handler(output_handler)
    client.run_main_cycle()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('Error:', str(e))
