import gc
import socket
import struct
import time

gc.collect()
import uasyncio as asyncio
import utils

gc.collect()
from errno import EINPROGRESS, ETIMEDOUT

gc.collect()
from sys import platform

IBUFSIZE = 50
MSG_BYTES = True
ESP8266 = platform == "esp8266"
ESP32 = platform == "esp32"
BUSY_ERRORS = [EINPROGRESS, ETIMEDOUT, 118, 119] if platform == "esp32" else [EINPROGRESS, ETIMEDOUT]


async def eliza(*_):
    await utils.ayield()


def _noop(*_):
    return None


def pid_gen():
    pid = 0
    while True:
        pid = pid + 1 if pid < 65535 else 1
        yield pid


def qos_check(qos):
    if not (qos == 0 or qos == 1):
        raise ValueError("Only qos 0 and 1 are supported.")


def vbi(buf: bytearray, offs: int, x: int):
    while True:
        buf[offs] = x & 0x7F
        x >>= 7
        if x:
            buf[offs] |= 0x80
            offs += 1
            continue
        return offs + 1


class MQTTClient:
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2

    REPUB_COUNT = 0
    __slots__ = (
        "_addr",
        "_cb",
        "_clean",
        "_clean_init",
        "_client_id",
        "_connect_handler",
        "_has_connected",
        "_ibuf",
        "_keepalive",
        "_max_repubs",
        "_mvbuf",
        "_ping_interval",
        "_pswd",
        "_response_time",
        "_state",
        "_sock",
        "_ssl",
        "_ssl_params",
        "_tasks",
        "_user",
        "last_rx",
        "lock",
        "newpid",
        "port",
        "rcv_pids",
        "server",
        "topic_alias_maximum",
    )

    def __init__(
        self,
        *,
        client_id=None,
        server=None,
        port=0,
        user="",
        password="",
        keepalive=60,
        ping_interval=20,
        ssl=False,
        ssl_params=None,
        response_time=5,
        clean_init=True,
        clean=True,
        max_repubs=4,
        subs_cb=None,
        connect_coro=eliza,
    ):
        if ssl_params is None:
            ssl_params = {}
        if subs_cb is None:
            subs_cb = _noop

        self._client_id = client_id
        self._user = user
        self._pswd = password
        self._keepalive = keepalive
        self._response_time = response_time * 1000
        self._max_repubs = max_repubs
        self._clean_init = clean_init
        self._clean = clean
        self._ping_interval = ping_interval * 1000

        self._state = self.DISCONNECTED
        self._has_connected = False
        self._tasks = []

        if ESP8266:
            import esp
            esp.sleep_type(0)
        
        self._ssl = ssl
        self._ssl_params = ssl_params

        self._cb = subs_cb
        self._connect_handler = connect_coro

        self.port = port
        if self.port == 0:
            self.port = 8883 if self._ssl else 1883
        self.server = server
        self._sock = None

        self.newpid = pid_gen()
        self.rcv_pids = set()
        self.last_rx = time.ticks_ms()
        self.lock = asyncio.Lock()
        self._ibuf = bytearray(IBUFSIZE)
        self._mvbuf = memoryview(self._ibuf)

        self.topic_alias_maximum = 0

    def _timeout(self, t):
        return time.ticks_diff(time.ticks_ms(), t) > self._response_time

    async def _as_read(self, n, sock=None, use_ibuf=True):
        if sock is None:
            sock = self._sock

        if use_ibuf:
            oflow = n - len(self._ibuf)
            if oflow > 0:
                self._ibuf.extend(bytearray(oflow))
                self._mvbuf = memoryview(self._ibuf)
            buffer = self._mvbuf
        else:
            buffer = memoryview(bytearray(n))
        size = 0
        t = time.ticks_ms()
        while size < n:
            if self._timeout(t) or not self.is_connected():
                raise OSError(-1, "Timeout on socket read")
            try:
                msg_size = sock.readinto(buffer[size:], n - size)
            except OSError as e:
                msg_size = None
                if e.args[0] not in BUSY_ERRORS:
                    raise
            if msg_size == 0:
                raise OSError(-1, "Connection closed by host")
            if msg_size is not None:
                size += msg_size
                t = time.ticks_ms()
                self.last_rx = time.ticks_ms()
            await utils.ayield(do_gc=False)
        return buffer[:n]

    async def _as_write(self, bytes_wr, length=0, sock=None):
        if sock is None:
            sock = self._sock

        bytes_wr = memoryview(bytes_wr)
        if length:
            bytes_wr = bytes_wr[:length]
        t = time.ticks_ms()
        while bytes_wr:
            if self._timeout(t) or not self.is_connected():
                raise OSError(-1, "Timeout on socket write")
            try:
                n = sock.write(bytes_wr)
            except OSError as e:
                n = 0
                if e.args[0] not in BUSY_ERRORS:
                    raise
            if n:
                t = time.ticks_ms()
                bytes_wr = bytes_wr[n:]
            await utils.ayield(do_gc=False)

    async def _send_str(self, s):
        await self._as_write(struct.pack("!H", len(s)))
        await self._as_write(s)


    async def _recv_len(self):
        d = 0
        i = 0
        while True:
            s = (await self._as_read(1))[0]
            d |= (s & 0x7F) << (i * 7)
            i += 1
            if not (s & 0x80):
                return d, i

    async def _connect(self, clean):
        self._sock = socket.socket()
        self._sock.setblocking(False)
        try:
            self._sock.connect(self._addr)
        except OSError as e:
            if e.args[0] not in BUSY_ERRORS:
                raise
        await utils.ayield(do_gc=False)
        if self._ssl:
            try:
                import ssl
            except ImportError:
                import ussl as ssl

            self._sock = ssl.wrap_socket(self._sock, **self._ssl_params)
        premsg = bytearray(b"\x10\0\0\0\0\0")
        msg = bytearray(b"\x04MQTT\x00\0\0\0")
        msg[5] = 0x04

        sz = 10 + 2 + len(self._client_id)
        msg[6] = clean << 1
        if self._user:
            sz += 2 + len(self._user) + 2 + len(self._pswd)
            msg[6] |= 0xC0
        if self._keepalive:
            msg[7] |= self._keepalive >> 8
            msg[8] |= self._keepalive & 0x00FF

        i = vbi(premsg, 1, sz)
        await self._as_write(premsg, i + 1)
        await self._as_write(msg)

        await self._send_str(self._client_id)
        if self._user:
            await self._send_str(self._user)
            await self._send_str(self._pswd)

        del premsg, msg
        packet_type = await self._as_read(1)
        if packet_type[0] != 0x20:
            raise OSError(-1, "CONNACK not received")

        sz, _ = await self._recv_len()
        if sz != 2:
            raise OSError(-1, "Invalid CONNACK packet")

        connack_resp = await self._as_read(2)

        if connack_resp[0] != 0:
            raise OSError(-1, "CONNACK flags not 0")

        if connack_resp[1] != 0:
            raise OSError(-1, "CONNACK reason code 0x%x" % connack_resp[1])

        del connack_resp

    async def _ping(self):
        async with self.lock:
            await self._as_write(b"\xc0\0")

    async def disconnect(self):
        if self._sock is not None:
            await self._kill_tasks(False)
            try:
                async with self.lock:
                    self._sock.write(b"\xe0\0")
                    await asyncio.sleep_ms(100)
            except OSError:
                pass
            self._close()
        self._state = self.DISCONNECTED
        self._has_connected = False

    def _close(self):
        if self._sock is not None:
            self._sock.close()

    async def _await_pid(self, pid):
        t = time.ticks_ms()
        while pid in self.rcv_pids:
            if self._timeout(t) or not self.is_connected():
                break
            await asyncio.sleep_ms(100)
        else:
            return True
        return False

    async def _publish_core(self, topic, msg, retain, qos, properties=None):
        pid = next(self.newpid)
        if qos:
            self.rcv_pids.add(pid)
        async with self.lock:
            await self._publish(topic, msg, retain, qos, 0, pid, properties)
        if qos == 0:
            return

        count = 0
        while 1:
            if await self._await_pid(pid):
                return

            if count >= self._max_repubs or not self.is_connected():
                raise OSError(-1)
            async with self.lock:

                await self._publish(topic, msg, retain, qos, dup=1, pid=pid, properties=properties)
            count += 1
            self.REPUB_COUNT += 1

    async def _publish(self, topic, msg, retain, qos, dup, pid, properties=None):
        pkt = bytearray(b"\x30\0\0\0")
        pkt[0] |= qos << 1 | retain | dup << 3
        sz = 2 + len(topic) + len(msg)
        if qos > 0:
            sz += 2

        await self._as_write(pkt, vbi(pkt, 1, sz))
        await self._send_str(topic)

        if qos > 0:
            struct.pack_into("!H", pkt, 0, pid)
            await self._as_write(pkt, 2)

        await self._as_write(msg)

    async def _subscribe_core(self, topic, qos, properties=None):
        await self._usub(topic, qos, properties)

    async def _unsubscribe_core(self, topic, properties=None):
        await self._usub(topic, None, properties)

    async def _usub(self, topic, qos, _properties):
        sub = qos is not None
        pkt = bytearray(7)
        pkt[0] = 0x82 if sub else 0xA2
        pid = next(self.newpid)
        self.rcv_pids.add(pid)

        sz = 2 + 2 + len(topic) + (1 if sub else 0)
        offs = vbi(pkt, 1, sz)
        struct.pack_into("!H", pkt, offs, pid)

        async with self.lock:
            await self._as_write(pkt, offs + 2)
            await self._send_str(topic)
            if sub:
                await self._as_write(qos.to_bytes(1, "little"))

        if not await self._await_pid(pid):
            raise OSError(-1)

    def kill_pid(self, pid, msg):
        if pid in self.rcv_pids:
            self.rcv_pids.discard(pid)
        else:
            raise OSError(-1, f"Invalid pid in {msg} packet")

    async def wait_msg(self):
        try:
            res = self._sock.read(1)
        except OSError as e:
            if e.args[0] in BUSY_ERRORS:
                await utils.ayield(do_gc=False)
                return
            raise

        if res is None:
            return
        if res == b"":
            raise OSError(-1, "Empty response")

        if res == b"\xd0":
            await self._as_read(1)
            return
        op = res[0]

        if op == 0x40:
            sz, _ = await self._recv_len()
            if sz != 2:
                raise OSError(-1, "Invalid PUBACK packet")
            rcv_pid = await self._as_read(2)
            pid = rcv_pid[0] << 8 | rcv_pid[1]

            if sz != 2:
                reason_code = await self._as_read(1)
                reason_code = reason_code[0]
                if reason_code >= 0x80:
                    raise OSError(-1, "PUBACK reason code 0x%x" % reason_code)
            if sz > 3:
                puback_props_sz, _ = await self._recv_len()
                if puback_props_sz > 0:
                    puback_props = await self._as_read(puback_props_sz)

            self.kill_pid(pid, "PUBACK")

        if op == 0x90 or op == 0xB0:
            un = "UN" if op == 0xB0 else ""
            suback = op == 0x90
            sz, _ = await self._recv_len()
            rcv_pid = await self._as_read(2)
            pid = rcv_pid[0] << 8 | rcv_pid[1]
            sz -= 2

            if sz > 1:
                raise OSError(-1, "Got too many bytes")
            if suback:
                reason_code = await self._as_read(sz)
                reason_code = reason_code[0]
                
                if reason_code >= 0x80:
                    raise OSError(-1, f"{un}SUBACK reason code 0x{reason_code:x}")
            
            self.kill_pid(pid, f"{un}SUBACK")

        if op & 0xF0 != 0x30:
            return

        sz, _ = await self._recv_len()
        topic_len = await self._as_read(2)
        topic_len = (topic_len[0] << 8) | topic_len[1]
        topic = await self._as_read(topic_len, use_ibuf=topic_len <= len(self._ibuf))
        topic = bytes(topic)
        sz -= topic_len + 2

        if op & 6:
            pid = await self._as_read(2)
            pid = pid[0] << 8 | pid[1]
            sz -= 2

        msg = await self._as_read(sz, use_ibuf=sz <= len(self._ibuf))

        if MSG_BYTES:
            msg = bytes(msg)
        retained = op & 0x01
        self._cb(topic, msg, bool(retained))

        if op & 6 == 2:
            pkt = bytearray(b"\x40\x02\0\0")
            struct.pack_into("!H", pkt, 2, pid)
            await self._as_write(pkt)
        elif op & 6 == 4:
            raise OSError(-1, "QoS 2 not supported")

    async def connect(self, *, quick=False):
        if not self._has_connected:
            self._addr = socket.getaddrinfo(self.server, self.port)[0][-1]

        self._state = self.CONNECTING
        try:
            is_clean = self._clean
            if not self._has_connected and self._clean_init and not self._clean:
                await self._connect(True)

                try:
                    async with self.lock:
                        self._sock.write(b"\xe0\0")
                except OSError:
                    pass

                await asyncio.sleep(2)

            await self._connect(is_clean)
        except Exception:
            self._close()
            self._state = self.DISCONNECTED
            raise
        self.rcv_pids.clear()

        self._state = self.CONNECTED
        if not self._has_connected:
            self._has_connected = True

        asyncio.create_task(self._handle_msg())

        self._tasks.append(asyncio.create_task(self._keep_alive()))
        asyncio.create_task(self._connect_handler(self))

    async def _handle_msg(self):
        try:
            while self.is_connected():
                async with self.lock:
                    await self.wait_msg()
                await asyncio.sleep_ms(5)

        except OSError:
            pass
        self._reconnect()

    async def _keep_alive(self):
        while self.is_connected():
            pings_due = time.ticks_diff(time.ticks_ms(), self.last_rx) // self._ping_interval
            if pings_due >= 4:
                break
            await asyncio.sleep_ms(self._ping_interval)
            try:
                await self._ping()
            except OSError:
                break
        self._reconnect()

    async def _kill_tasks(self, kill_skt):
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        await utils.ayield(do_gc=False)
        if kill_skt:
            self._close()

    def get_state(self):
        return self._state

    def is_connected(self):
        return self._state > self.DISCONNECTED

    def _reconnect(self):
        if self._state != self.DISCONNECTED:
            self._state = self.DISCONNECTED
            asyncio.create_task(self._kill_tasks(True))

    async def _connection(self):
        if self._state != self.CONNECTED:
            raise OSError(-1, "Not connected")

    async def subscribe(self, topic, qos=0, properties=None):
        qos_check(qos)
        await self._connection()
        return await self._subscribe_core(topic, qos, properties)

    async def unsubscribe(self, topic, properties=None):
        await self._connection()
        return await self._unsubscribe_core(topic, properties)

    async def publish(self, topic, msg, retain=False, qos=0, properties=None):
        qos_check(qos)
        await self._connection()
        return await self._publish_core(topic, msg, retain, qos, properties)
