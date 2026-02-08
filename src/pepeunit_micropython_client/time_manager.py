import time
import ntptime
import utils


EPOCH_UNIX_DELTA_MS = 946684800000


class TimeManager:
    def __init__(self, ntp_host='pool.ntp.org'):
        self.ntp_host = ntp_host
        self._epoch_base_ms = None
        self._ticks_base_ms = None

    async def sync_epoch_ms_from_ntp(self):
        try:
            ntptime.host = self.ntp_host
            ntptime.settime()
            await utils.ayield()
            self._epoch_base_ms = int(time.time()) * 1000 + EPOCH_UNIX_DELTA_MS
            self._ticks_base_ms = time.ticks_ms()
        except Exception:
            pass

    def get_epoch_ms(self):
        if self._epoch_base_ms is not None:
            return int(self._epoch_base_ms + time.ticks_diff(time.ticks_ms(), self._ticks_base_ms))
        return time.ticks_ms()
