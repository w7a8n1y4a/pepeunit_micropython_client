import time
import uasyncio as asyncio

try:
    import ntptime
except Exception:
    ntptime = None

EPOCH_UNIX_DELTA_MS = 946684800000

class TimeManager:
    def __init__(self, ntp_host='pool.ntp.org'):
        self.ntp_host = ntp_host
        self._epoch_base_ms = None
        self._ticks_base_ms = None



    def set_epoch_base_ms(self, epoch_ms):
        try:
            self._epoch_base_ms = int(epoch_ms)
            self._ticks_base_ms = time.ticks_ms()
        except Exception:
            self._epoch_base_ms = None
            self._ticks_base_ms = None

    async def sync_epoch_ms_from_ntp(self, timeout_ms=3000):

        try:
            import socket
            import struct
        except Exception:
            return


        msg = bytearray(48)
        msg[0] = 0x1B

        addr = None
        for attempt in range(4):
            try:
                addr = socket.getaddrinfo(self.ntp_host, 123)[0][-1]
                break
            except OSError as e:
                # OSError(-2) == DNS not ready (EAI_NONAME) on first boot.
                if e.args and e.args[0] == -2 and attempt < 3:
                    await asyncio.sleep_ms(200 * (attempt + 1))
                    continue
                return
            except Exception:
                return
        if addr is None:
            return

        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.setblocking(False)
            except Exception:
                pass
            try:
                s.sendto(msg, addr)
            except Exception:

                try:
                    s.connect(addr)
                    s.send(msg)
                except Exception:
                    return

            start = time.ticks_ms()
            while True:
                try:
                    data = s.recv(48)
                    if data and len(data) >= 48:
                        break
                except OSError:
                    data = None
                if time.ticks_diff(time.ticks_ms(), start) >= int(timeout_ms):
                    return
                await asyncio.sleep_ms(50)


            t = struct.unpack("!12I", data)[10]

            unix_s = int(t - 2208988800)
            unix_ms = unix_s * 1000
            self.set_epoch_base_ms(unix_ms)
        except Exception:
            return
        finally:
            try:
                if s:
                    s.close()
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

