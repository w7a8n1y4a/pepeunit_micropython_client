try:
    import uasyncio as asyncio  # MicroPython
except ImportError:  # CPython
    import asyncio

import socket
import gc

try:
    import ussl as ssl  # MicroPython
except ImportError:
    try:
        import ssl  # type: ignore
    except ImportError:
        ssl = None  # noqa

try:
    from sys import platform
except Exception:
    platform = ""

try:
    from errno import EINPROGRESS, ETIMEDOUT
except Exception:
    EINPROGRESS = 115
    ETIMEDOUT = 110


ESP32 = platform == "esp32"
RP2 = platform == "rp2"
if ESP32:
    BUSY_ERRORS = [EINPROGRESS, ETIMEDOUT, 118, 119]
elif RP2:
    BUSY_ERRORS = [EINPROGRESS, ETIMEDOUT, -110]
else:
    BUSY_ERRORS = [EINPROGRESS, ETIMEDOUT]


def _parse_url(url: str):
    # Minimal URL parser: scheme://host[:port]/path?query
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


async def _as_write(sock, data: bytes):
    mv = memoryview(data)
    off = 0
    t = asyncio.get_event_loop().time() if hasattr(asyncio.get_event_loop(), "time") else 0
    while off < len(mv):
        try:
            n = sock.write(mv[off:])
        except OSError as e:
            if e.args and e.args[0] in BUSY_ERRORS:
                await asyncio.sleep_ms(0)
                continue
            raise
        if n is None or n == 0:
            await asyncio.sleep_ms(0)
            continue
        off += n
        if (off & 0x3FF) == 0:
            await asyncio.sleep_ms(0)


async def _as_read(sock, n: int):
    buf = bytearray(n)
    mv = memoryview(buf)
    got = 0
    while got < n:
        try:
            r = sock.read(n - got)
        except OSError as e:
            if e.args and e.args[0] in BUSY_ERRORS:
                await asyncio.sleep_ms(0)
                continue
            raise
        if r is None:
            await asyncio.sleep_ms(0)
            continue
        if r == b"":
            break
        mv[got : got + len(r)] = r
        got += len(r)
    return bytes(mv[:got])


async def _readline(sock, limit=1024):
    out = bytearray()
    while len(out) < limit:
        ch = await _as_read(sock, 1)
        if not ch:
            break
        out += ch
        if out.endswith(b"\n"):
            break
    return bytes(out)


async def _read_headers(sock):
    headers = {}
    while True:
        line = await _readline(sock, limit=2048)
        if not line or line in (b"\r\n", b"\n"):
            break
        if b":" not in line:
            continue
        k, v = line.split(b":", 1)
        headers[k.strip().lower()] = v.strip()
    return headers


async def request(method, url, headers=None, body=None, *, save_to=None, bufsize=256, max_body=64_000):
    """
    Minimal async HTTP/HTTPS request.
    - If save_to is set, streams body to file and returns (status, headers, None)
    - Else reads body up to max_body and returns (status, headers, bytes_body)
    """
    headers = headers or {}
    scheme, host, port, path = _parse_url(url)
    use_ssl = scheme == "https"

    addr = socket.getaddrinfo(host, port)[0][-1]
    s = socket.socket()
    s.setblocking(False)
    try:
        try:
            s.connect(addr)
        except OSError as e:
            if not (e.args and e.args[0] in BUSY_ERRORS):
                raise
        await asyncio.sleep_ms(0)
        if use_ssl:
            if ssl is None:
                raise OSError("SSL not available")
            s = ssl.wrap_socket(s, server_hostname=host)

        # Build request
        lines = [
            "{} {} HTTP/1.1".format(method, path),
            "Host: {}".format(host),
            "Connection: close",
        ]
        for k, v in headers.items():
            lines.append("{}: {}".format(k, v))
        b = b""
        if body is not None:
            if isinstance(body, bytes):
                b = body
            else:
                b = str(body).encode("utf-8")
            lines.append("Content-Length: {}".format(len(b)))
        lines.append("")  # end headers
        lines.append("")
        req = "\r\n".join(lines).encode("utf-8") + b
        await _as_write(s, req)

        # Status line
        status_line = await _readline(s, limit=2048)
        parts = status_line.split()
        status = int(parts[1]) if len(parts) >= 2 else 0
        resp_headers = await _read_headers(s)

        # Body
        if save_to:
            with open(save_to, "wb") as f:
                while True:
                    try:
                        chunk = s.read(bufsize)
                    except OSError as e:
                        if e.args and e.args[0] in BUSY_ERRORS:
                            await asyncio.sleep_ms(0)
                            continue
                        break
                    if chunk is None:
                        await asyncio.sleep_ms(0)
                        continue
                    if chunk == b"":
                        break
                    f.write(chunk)
                    await asyncio.sleep_ms(0)
            gc.collect()
            return status, resp_headers, None

        out = bytearray()
        while len(out) < max_body:
            try:
                chunk = s.read(min(bufsize, max_body - len(out)))
            except OSError as e:
                if e.args and e.args[0] in BUSY_ERRORS:
                    await asyncio.sleep_ms(0)
                    continue
                break
            if chunk is None:
                await asyncio.sleep_ms(0)
                continue
            if chunk == b"":
                break
            out.extend(chunk)
            if (len(out) & 0x3FF) == 0:
                await asyncio.sleep_ms(0)
        gc.collect()
        return status, resp_headers, bytes(out)
    finally:
        try:
            s.close()
        except Exception:
            pass


