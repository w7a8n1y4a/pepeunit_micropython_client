import gc

from pepeunit_micropython_client.client import PepeunitClient

print('\nRun init PepeunitClient')

client = PepeunitClient(
    env_file_path='/env.json',
    schema_file_path='/schema.json',
    log_file_path='/log.json',
    ff_version_check_enable=True,
    ff_wifi_manager_enable=True,
)

client.wifi_manager.connect_forever()

client.time_manager.sync_epoch_ms_from_ntp()

gc.collect()

client.logger.warning(f'Init Success: free_mem {gc.mem_free()}: alloc_mem {gc.mem_alloc()}', file_only=True)
