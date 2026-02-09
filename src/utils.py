import gc
import ubinascii as binascii
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
    interval = base_ms << (attempt - 1)
    return min(interval, max_ms)


def extract_uuid_from_topic(topic_url, *, allow_no_slash=False):
    if not topic_url:
        return None
    if allow_no_slash and '/' not in topic_url:
        return topic_url
    first = topic_url.find('/')
    if first < 0:
        return None
    second = topic_url.find('/', first + 1)
    if second < 0:
        uuid = topic_url[first + 1:]
    else:
        uuid = topic_url[first + 1:second]
    return uuid if uuid else None


def dirname(path):
    if not path or '/' not in path:
        return ''
    return path[: path.rfind('/')]


def b64encode(b):
    return binascii.b2a_base64(b).rstrip(b"\n").decode("utf-8")


def b64decode_to_bytes(s):
    if isinstance(s, str):
        bs = s.encode("utf-8")
    elif isinstance(s, (bytes, bytearray, memoryview)):
        bs = bytes(s)
    else:
        bs = str(s).encode("utf-8")
    padding_needed = (-len(bs)) % 4
    if padding_needed:
        bs += b"=" * padding_needed
    return binascii.a2b_base64(bs)


def should_collect_memory(threshold=8000):
    return gc.mem_free() < threshold


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
