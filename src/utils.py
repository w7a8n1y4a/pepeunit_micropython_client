import gc
import uasyncio as asyncio


def to_bytes(value):
    if value is None:
        return b""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return str(value).encode("utf-8")


def to_str(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("utf-8")
    return str(value)


def backoff_interval_ms(attempt, base_ms, max_ms):
    if attempt <= 0:
        return 0
    interval = base_ms * (2 ** (attempt - 1))
    if interval > max_ms:
        return max_ms
    return int(interval)


def spawn(coro):
    if coro is None:
        return
    asyncio.create_task(coro)


async def maybe_await(coro):
    if coro is None:
        return
    await coro


async def ayield(counter=None, every=32, mem_free_threshold=8000, do_gc=True):
    if counter is not None and counter % every != 0:
        return
    if do_gc and gc.mem_free() < mem_free_threshold:
        gc.collect()
    await asyncio.sleep_ms(0)
