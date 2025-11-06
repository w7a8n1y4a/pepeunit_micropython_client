import time
from pepeunit_micropython_client.client import PepeunitClient

    
last_output_send_time = 0

def output_handler(client: PepeunitClient):
    global last_output_send_time
    current_time = time.time()
    
    if current_time - last_output_send_time >= client.settings.DELAY_PUB_MSG:
        message = str(time.ticks_ms())
        
        client.publish_to_topics("output/pepeunit", message)
        
        last_output_send_time = current_time


def mqtt_input_handler(client: PepeunitClient, msg):
    print(msg)


def main():
    client = PepeunitClient(
        env_file_path='/env.json',
        schema_file_path='/schema.json',
        log_file_path='/log.json',
        sta=sta
    )
    client.set_mqtt_input_handler(mqtt_input_handler)
    client.mqtt_client.connect()
    client.subscribe_all_schema_topics()
    client.set_output_handler(output_handler)
    client.run_main_cycle()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('Error:', str(e))
