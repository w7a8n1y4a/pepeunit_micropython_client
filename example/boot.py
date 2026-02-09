import gc

import uasyncio as asyncio

from pepeunit_micropython_client.client import PepeunitClient

print('\nRun init PepeunitClient')

client = PepeunitClient(
    env_file_path='/env.json',
    schema_file_path='/schema.json',
    log_file_path='/log.json',
    ff_version_check_enable=False,
    ff_wifi_manager_enable=True,
)

async def _boot_init():
    if client.wifi_manager:
        await client.wifi_manager.connect_forever()
    await client.time_manager.sync_epoch_ms_from_ntp()

asyncio.run(_boot_init())

gc.collect()

client.logger.warning('Init Success: free_mem {}: alloc_mem {}'.format(gc.mem_free(), gc.mem_alloc()), file_only=True)
