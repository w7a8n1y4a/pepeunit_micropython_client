import uasyncio as asyncio
import utils

import socket
import gc
try:
    import ssl
except ImportError:
    import ussl as ssl

import sys

from errno import EINPROGRESS, ETIMEDOUT

if sys.platform == "esp32":
    BUSY_ERRORS = (EINPROGRESS, ETIMEDOUT, 118, 119)
elif sys.platform == "rp2":
    BUSY_ERRORS = (EINPROGRESS, ETIMEDOUT, -110)
else:
    BUSY_ERRORS = (EINPROGRESS, ETIMEDOUT)


def _is_busy_error(e: OSError) -> bool:
    return bool(e.args) and e.args[0] in BUSY_ERRORS


def _parse_url(url: str):
    scheme = "http"
    rest = url
    if "://" in url:
        scheme, rest = url.split("://", 1)
    host_port, path = (rest.split("/", 1) + [""])[:2]
    path = "/" + path
    if ":" in host_port:
        host, port_s = host_port.rsplit(":", 1)
        port = int(port_s)
    else:
        host = host_port
        port = 443 if scheme == "https" else 80
    return scheme, host, port, path


class _BufferedSock:
    def __init__(self, sock, bufsize=512):
        self.sock = sock
        self.buf = bytearray(bufsize)
        self.mv = memoryview(self.buf)
        self.start = 0
        self.end = 0
        self._readinto = sock.readinto

    def _compact(self):
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
                n = self._readinto(self.mv[self.end :])
                if n is None:
                    await utils.ayield(do_gc=False)
                    continue
                if n == 0:
                    return 0
                self.end += n
                return n
            except OSError as e:
                if _is_busy_error(e):
                    await utils.ayield(do_gc=False)
                    continue
                raise

    async def readline(self, limit=2048) -> bytes:
        out = bytearray()
        while len(out) < limit:
            if self.start < self.end:
                i = self.buf.find(b"\n", self.start, self.end)
                if i != -1:
                    i += 1
                    take = min(i - self.start, limit - len(out))
                    out.extend(self.mv[self.start : self.start + take])
                    self.start += take
                    break

                take = min(self.end - self.start, limit - len(out))
                out.extend(self.mv[self.start : self.start + take])
                self.start += take
                if len(out) >= limit:
                    break

            if await self._fill() == 0:
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
            if await self._fill() == 0:
                return b""

    async def skip_headers(self, limit=8192) -> bool:
        pat = b"\r\n\r\n"
        consumed = 0
        while True:
            i = self.buf.find(pat, self.start, self.end)
            if i != -1:
                self.start = i + 4
                return True

            avail = self.end - self.start
            if avail > 3:
                step = avail - 3
                self.start += step
                consumed += step
                if consumed >= limit:
                    return False

            if await self._fill() == 0:
                return False


async def _as_write(sock, data: bytes):
    mv = memoryview(data)
    off = 0
    while off < len(mv):
        try:
            n = sock.write(mv[off:])
        except OSError as e:
            if _is_busy_error(e):
                await utils.ayield(do_gc=False)
                continue
            raise
        if n is None or n == 0:
            await utils.ayield(do_gc=False)
            continue
        off += n
        if (off & 0x3FF) == 0:
            await utils.ayield(off, every=1024, do_gc=False)

def _parse_status(status_line: bytes) -> int:
    sp1 = status_line.find(b" ")
    if sp1 < 0:
        return 0
    sp2 = status_line.find(b" ", sp1 + 1)
    if sp2 < 0:
        sp2 = status_line.find(b"\r", sp1 + 1)
    if sp2 < 0:
        sp2 = len(status_line)
    return int(status_line[sp1 + 1 : sp2])


async def request(
    method,
    url,
    headers=None,
    body=None,
    *,
    save_to=None,
    bufsize=256,
    max_body=64_000,
    collect_headers=True,
    header_limit=2048,
):
    headers = headers or {}
    scheme, host, port, path = _parse_url(url)
    use_ssl = scheme == "https"

    for attempt in range(4):
        try:
            await asyncio.sleep_ms(0)
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
        await utils.ayield(do_gc=False)
        if use_ssl:
            s = ssl.wrap_socket(s, server_hostname=host)
            await utils.ayield(do_gc=False)

        b = utils.to_bytes(body) if body is not None else b""

        await _as_write(s, utils.to_bytes(method))
        await _as_write(s, b" ")
        await _as_write(s, utils.to_bytes(path))
        await _as_write(s, b" HTTP/1.1\r\nHost: ")
        await _as_write(s, utils.to_bytes(host))
        await _as_write(s, b"\r\nConnection: close\r\n")

        for k, v in headers.items():
            await _as_write(s, utils.to_bytes(k))
            await _as_write(s, b": ")
            await _as_write(s, utils.to_bytes(v))
            await _as_write(s, b"\r\n")

        if b:
            await _as_write(s, b"Content-Length: ")
            await _as_write(s, str(len(b)).encode("ascii"))
            await _as_write(s, b"\r\n")

        await _as_write(s, b"\r\n")
        if b:
            await _as_write(s, b)

        reader = _BufferedSock(s, bufsize=bufsize)

        status_line = await reader.readline(limit=256)
        status = _parse_status(status_line)

        content_length = -1

        if collect_headers:
            resp_headers = {}
            while True:
                line = await reader.readline(limit=header_limit)
                if not line or line in (b"\r\n", b"\n"):
                    break
                i = line.find(b":")
                if i < 0:
                    continue
                resp_headers[line[:i].strip().lower()] = line[i + 1 :].strip()
            cl_val = resp_headers.get(b"content-length")
            if cl_val is not None:
                try:
                    content_length = int(cl_val)
                except (ValueError, TypeError):
                    pass
        elif save_to:
            resp_headers = {}
            await reader.skip_headers()
        else:
            resp_headers = {}
            while True:
                line = await reader.readline(limit=header_limit)
                if not line or line in (b"\r\n", b"\n"):
                    break
                if content_length < 0:
                    i = line.find(b":")
                    if i >= 0 and line[:i].strip().lower() == b"content-length":
                        try:
                            content_length = int(line[i + 1 :].strip())
                        except (ValueError, TypeError):
                            pass

        if save_to:
            with open(save_to, "wb") as f:
                while True:
                    chunk = await reader.readchunk(bufsize)
                    if chunk == b"":
                        break
                    f.write(chunk)
                    await utils.ayield(do_gc=False)
            del reader
            gc.collect()
            return status, resp_headers, None

        if 0 < content_length <= max_body:
            out = bytearray(content_length)
            pos = 0
            while pos < content_length:
                chunk = await reader.readchunk(min(bufsize, content_length - pos))
                if chunk == b"":
                    break
                out[pos : pos + len(chunk)] = chunk
                pos += len(chunk)
            if pos < content_length:
                out = out[:pos]
        else:
            out = bytearray()
            while len(out) < max_body:
                chunk = await reader.readchunk(min(bufsize, max_body - len(out)))
                if chunk == b"":
                    break
                out.extend(chunk)
                if (len(out) & 0x3FF) == 0:
                    await utils.ayield(len(out), every=1024, do_gc=False)
        del reader
        gc.collect()
        return status, resp_headers, out
    finally:
        s.close()
