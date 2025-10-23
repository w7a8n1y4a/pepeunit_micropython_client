import time
from pepeunit_micropython_client.client import PepeunitClient


def output_handler(client: PepeunitClient):
    # Put your periodic publishing logic here if needed
    # Example: publish to a custom topic key if present in schema
    # client.publish_to_topics('your_output_topic_key', 'your_message')
    pass


def mqtt_input_handler(client: PepeunitClient, msg):
    print(msg)


def main():
    client = PepeunitClient(
        env_file_path='/env.json',
        schema_file_path='/schema.json',
        log_file_path='/log.json',
        enable_mqtt=True,
        enable_rest=True,
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
        # On MicroPython, keep errors short to save RAM
        print('Error:', str(e))
        time.sleep(3)

