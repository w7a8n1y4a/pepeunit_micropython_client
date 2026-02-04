import gc
import uasyncio as asyncio


async def ayield(counter=None, every=32, mem_free_threshold=8000, do_gc=True):
    if counter is not None and counter % every != 0:
        return
    if do_gc and gc.mem_free() < mem_free_threshold:
        gc.collect()
    await asyncio.sleep_ms(0)
