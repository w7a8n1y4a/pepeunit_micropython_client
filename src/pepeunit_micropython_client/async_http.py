import uasyncio as asyncio

import socket
import gc

try:
    import ussl as ssl
except ImportError:
    try:
        import ssl
    except ImportError:
        ssl = None

try:
    import sys

    platform = getattr(sys, "platform", "")
except Exception:
    platform = ""

EINPROGRESS = 115
ETIMEDOUT = 110
try:
    from errno import EINPROGRESS as _EINPROGRESS, ETIMEDOUT as _ETIMEDOUT

    EINPROGRESS = _EINPROGRESS
    ETIMEDOUT = _ETIMEDOUT
except ImportError:
    pass


ESP32 = platform == "esp32"
RP2 = platform == "rp2"
if ESP32:
    BUSY_ERRORS = (EINPROGRESS, ETIMEDOUT, 118, 119)
elif RP2:
    BUSY_ERRORS = (EINPROGRESS, ETIMEDOUT, -110)
else:
    BUSY_ERRORS = (EINPROGRESS, ETIMEDOUT)


def _is_busy_error(e: OSError) -> bool:
    # MicroPython uses numeric errno in e.args[0].
    return bool(getattr(e, "args", None)) and e.args[0] in BUSY_ERRORS


def _parse_url(url: str):
    scheme = "http"
    rest = url
    if "://" in url:
        scheme, rest = url.split("://", 1)
    host_port, path = (rest.split("/", 1) + [""])[:2]
    path = "/" + path
    if ":" in host_port:
        host, port_s = host_port.rsplit(":", 1)
        try:
            port = int(port_s)
        except Exception:
            port = 443 if scheme == "https" else 80
    else:
        host = host_port
        port = 443 if scheme == "https" else 80
    return scheme, host, port, path


def _to_bytes(v) -> bytes:
    if v is None:
        return b""
    if isinstance(v, bytes):
        return v
    if isinstance(v, str):
        return v.encode("utf-8")
    return str(v).encode("utf-8")


class _BufferedSock:
    def __init__(self, sock, bufsize=512):
        self.sock = sock
        self.buf = bytearray(bufsize)
        self.mv = memoryview(self.buf)
        self.start = 0
        self.end = 0
        self._readinto = getattr(sock, "readinto", None)

    def _compact(self):
        if self.start == 0:
            return
        if self.start >= self.end:
            self.start = 0
            self.end = 0
            return
        n = self.end - self.start
        self.buf[:n] = self.buf[self.start : self.end]
        self.start = 0
        self.end = n

    async def _fill(self):
        if self.end >= len(self.buf):
            self._compact()
        if self.end >= len(self.buf):
            return 0

        while True:
            try:
                if self._readinto is not None:
                    n = self._readinto(self.mv[self.end :])
                    if n is None:
                        await asyncio.sleep_ms(0)
                        continue
                    if n == 0:
                        return 0
                    self.end += n
                    return n
                data = self.sock.read(len(self.buf) - self.end)
            except OSError as e:
                if _is_busy_error(e):
                    await asyncio.sleep_ms(0)
                    continue
                raise
            if data is None:
                await asyncio.sleep_ms(0)
                continue
            if data == b"":
                return 0
            n = len(data)
            self.buf[self.end : self.end + n] = data
            self.end += n
            return n

    async def readline(self, limit=2048) -> bytes:
        out = bytearray()
        while len(out) < limit:
            if self.start < self.end:
                i = self.buf.find(b"\n", self.start, self.end)
                if i != -1:
                    i += 1
                    take = i - self.start
                    if len(out) + take > limit:
                        take = limit - len(out)
                    out.extend(self.mv[self.start : self.start + take])
                    self.start += take
                    break

                # No newline in current buffer: consume what we can.
                take = self.end - self.start
                if len(out) + take > limit:
                    take = limit - len(out)
                out.extend(self.mv[self.start : self.start + take])
                self.start += take
                if len(out) >= limit:
                    break

            n = await self._fill()
            if n == 0:
                break

        return bytes(out)

    async def readchunk(self, max_n: int):
        while True:
            avail = self.end - self.start
            if avail:
                if avail > max_n:
                    avail = max_n
                mv = self.mv[self.start : self.start + avail]
                self.start += avail
                return mv
            n = await self._fill()
            if n == 0:
                return b""


async def _as_write(sock, data: bytes):
    mv = memoryview(data)
    off = 0
    while off < len(mv):
        try:
            n = sock.write(mv[off:])
        except OSError as e:
            if _is_busy_error(e):
                await asyncio.sleep_ms(0)
                continue
            raise
        if n is None or n == 0:
            await asyncio.sleep_ms(0)
            continue
        off += n
        if (off & 0x3FF) == 0:
            await asyncio.sleep_ms(0)

async def request(method, url, headers=None, body=None, *, save_to=None, bufsize=256, max_body=64_000):

    headers = headers or {}
    scheme, host, port, path = _parse_url(url)
    use_ssl = scheme == "https"

    for attempt in range(4):
        try:
            addr = socket.getaddrinfo(host, port)[0][-1]
            break
        except OSError as e:
            if e.args and e.args[0] == -2 and attempt < 3:
                gc.collect()
                await asyncio.sleep_ms(200 * (attempt + 1))
                continue
            raise

    s = socket.socket()
    s.setblocking(False)
    try:
        try:
            s.connect(addr)
        except OSError as e:
            if not _is_busy_error(e):
                raise
        await asyncio.sleep_ms(0)
        if use_ssl:
            if ssl is None:
                raise OSError("SSL not available")
            s = ssl.wrap_socket(s, server_hostname=host)

        b = b""
        if body is not None:
            b = body if isinstance(body, bytes) else _to_bytes(body)

        req = bytearray()
        req.extend(_to_bytes(method))
        req.extend(b" ")
        req.extend(_to_bytes(path))
        req.extend(b" HTTP/1.1\r\n")
        req.extend(b"Host: ")
        req.extend(_to_bytes(host))
        req.extend(b"\r\n")
        req.extend(b"Connection: close\r\n")
        for k, v in headers.items():
            req.extend(_to_bytes(k))
            req.extend(b": ")
            req.extend(_to_bytes(v))
            req.extend(b"\r\n")
        if b:
            req.extend(b"Content-Length: ")
            req.extend(str(len(b)).encode("ascii"))
            req.extend(b"\r\n")
        req.extend(b"\r\n")
        if b:
            req.extend(b)

        await _as_write(s, req)

        reader = _BufferedSock(s, bufsize=512 if bufsize < 512 else bufsize)

        status_line = await reader.readline(limit=2048)
        parts = status_line.split()
        status = int(parts[1]) if len(parts) >= 2 else 0

        resp_headers = {}
        while True:
            line = await reader.readline(limit=2048)
            if not line or line in (b"\r\n", b"\n"):
                break
            i = line.find(b":")
            if i < 0:
                continue
            k = line[:i].strip().lower()
            v = line[i + 1 :].strip()
            resp_headers[k] = v


        if save_to:
            with open(save_to, "wb") as f:
                while True:
                    chunk = await reader.readchunk(bufsize)
                    if chunk == b"":
                        break
                    f.write(chunk)
                    await asyncio.sleep_ms(0)
            gc.collect()
            return status, resp_headers, None

        out = bytearray()
        while len(out) < max_body:
            chunk = await reader.readchunk(min(bufsize, max_body - len(out)))
            if chunk == b"":
                break
            out.extend(chunk)
            if (len(out) & 0x3FF) == 0:
                await asyncio.sleep_ms(0)
        gc.collect()
        return status, resp_headers, out
    finally:
        try:
            s.close()
        except Exception:
            pass

