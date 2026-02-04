import time
import ntptime
import utils


EPOCH_UNIX_DELTA_MS = 946684800000


class TimeManager:
    def __init__(self, ntp_host='pool.ntp.org'):
        self.ntp_host = ntp_host
        self._epoch_base_ms = None
        self._ticks_base_ms = None

        self.sync_epoch_ms_from_ntp()

    def set_epoch_base_ms(self, epoch_ms):
        try:
            self._epoch_base_ms = int(epoch_ms)
            self._ticks_base_ms = time.ticks_ms()
        except Exception:
            self._epoch_base_ms = None
            self._ticks_base_ms = None

    async def sync_epoch_ms_from_ntp(self):
        try:
            try:
                ntptime.host = self.ntp_host
            except Exception:
                pass
            ntptime.settime()
            await utils.ayield()
            self.set_epoch_base_ms(int(time.time()) * 1000 + EPOCH_UNIX_DELTA_MS)
        except Exception:
            pass

    def get_epoch_ms(self):
        if self._epoch_base_ms is not None and self._ticks_base_ms is not None:
            try:
                elapsed = time.ticks_diff(time.ticks_ms(), self._ticks_base_ms)
                return int(self._epoch_base_ms + elapsed)
            except Exception:
                pass

        return time.ticks_ms()
