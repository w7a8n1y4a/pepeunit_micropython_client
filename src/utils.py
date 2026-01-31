import gc
import time


def _yield(counter, every=32, mem_free_threshold=8000, do_gc=True):
    if counter % every == 0:
        if do_gc and gc.mem_free() < mem_free_threshold:
            gc.collect()
        time.sleep_ms(0)
