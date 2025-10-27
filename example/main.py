import time
import gc
from pepeunit_micropython_client.client import PepeunitClient


def output_handler(client: PepeunitClient):
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

