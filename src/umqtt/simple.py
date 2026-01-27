import socket
import struct
import gc
import select


class MQTTException(Exception):
    def __init__(self, msg=None, cause=None, errno=None, transport=False):
        super().__init__(msg if msg is not None else "")
        self.cause = cause
        self.errno = errno
        self.transport = transport


class MQTTClient:
    def __init__(
        self,
        client_id,
        server,
        port=0,
        user=None,
        password=None,
        keepalive=0,
        ssl=None,
        socket_timeout=5,
    ):
        if port == 0:
            port = 8883 if ssl else 1883
        self.client_id = client_id
        self.sock = None
        self.server = server
        self.port = port
        self.ssl = ssl
        self.pid = 0
        self.cb = None
        self.user = user
        self.pswd = password
        self.keepalive = keepalive
        self.lw_topic = None
        self.lw_msg = None
        self.lw_qos = 0
        self.lw_retain = False
        self.socket_timeout = socket_timeout
        self._poller = None
        self._rx_buf = bytearray()
        self._rx_off = 0
        self._addr = None

    def _set_sock_timeout(self):
        if self.socket_timeout is None:
            return
        try:
            self.sock.settimeout(self.socket_timeout)
        except Exception:
            pass

    def _setup_poller(self):
        self._poller = select.poll()
        self._poller.register(
            self.sock,
            select.POLLIN | select.POLLOUT | select.POLLERR | select.POLLHUP,
        )

    def _poll(self, mask, timeout_ms):
        if self._poller is None:
            return True
        try:
            events = self._poller.poll(timeout_ms)
        except Exception:
            return True
        for _, event in events:
            if event & (select.POLLERR | select.POLLHUP):
                raise MQTTException("poll", transport=True)
            if event & mask:
                return True
        return False

    def _raise_transport(self, e, where="socket"):
        errno = None
        try:
            errno = e.args[0]
        except Exception:
            pass
        raise MQTTException(where, cause=e, errno=errno, transport=True)

    def _sock_write(self, buf, length=None):
        try:
            if length is None:
                return self.sock.write(buf)
            return self.sock.write(buf, length)
        except OSError as e:
            self._raise_transport(e, where="write")

    def _sock_read(self, n):
        try:
            return self.sock.read(n)
        except OSError as e:
            self._raise_transport(e, where="read")

    def _sock_read_some(self, n):
        try:
            if self._poller and self.socket_timeout is not None:
                timeout_ms = int(self.socket_timeout * 1000)
                if not self._poll(select.POLLIN, timeout_ms):
                    return None
            recv = getattr(self.sock, "recv", None)
            if recv:
                return recv(n)
            return self.sock.read(n)
        except OSError as e:
            self._raise_transport(e, where="read")

    def _send_str(self, s):
        self._sock_write(struct.pack("!H", len(s)))
        self._sock_write(s)

    def _recv_len(self):
        n = 0
        sh = 0
        while 1:
            b = self._sock_read(1)[0]
            n |= (b & 0x7F) << sh
            if not b & 0x80:
                return n
            sh += 7

    def _rx_available(self):
        return len(self._rx_buf) - self._rx_off

    def _rx_compact(self):
        if self._rx_off > 0 and self._rx_off >= len(self._rx_buf) // 2:
            self._rx_buf = self._rx_buf[self._rx_off:]
            self._rx_off = 0

    def _rx_wait(self, need, blocking):
        while self._rx_available() < need:
            if not blocking and self._poller and not self._poll(select.POLLIN, 0):
                return False
            data = self._sock_read_some(1024)
            if data is None:
                return False
            if data == b"":
                raise MQTTException("eof", errno=-1, transport=True)
            self._rx_buf.extend(data)
        return True

    def _rx_wait_from_idx(self, idx, need, blocking):
        required = idx + need - self._rx_off
        if required <= 0:
            return True
        return self._rx_wait(required, blocking)

    def _rx_read(self, n, blocking=True):
        if not self._rx_wait(n, blocking):
            return None
        start = self._rx_off
        end = start + n
        out = bytes(self._rx_buf[start:end])
        self._rx_off = end
        self._rx_compact()
        return out

    def set_callback(self, f):
        self.cb = f

    def set_last_will(self, topic, msg, retain=False, qos=0):
        assert 0 <= qos <= 2
        assert topic
        self.lw_topic = topic
        self.lw_msg = msg
        self.lw_qos = qos
        self.lw_retain = retain

    def connect(self, clean_session=True):
        self.sock = socket.socket()
        self._set_sock_timeout()
        try:
            self._addr = socket.getaddrinfo(self.server, self.port)[0][-1]
        except Exception:
            if self._addr is None:
                raise
        addr = self._addr
        try:
            self.sock.connect(addr)
        except OSError as e:
            self._raise_transport(e, where="connect")
        if self.ssl:
            self.sock = self.ssl.wrap_socket(self.sock, server_hostname=self.server)
            self._set_sock_timeout()
        self._setup_poller()
        
        premsg = bytearray(b"\x10\0\0\0\0\0")
        msg = bytearray(b"\x04MQTT\x04\x02\0\0")

        sz = 10 + 2 + len(self.client_id)
        msg[6] = clean_session << 1
        if self.user:
            sz += 2 + len(self.user) + 2 + len(self.pswd)
            msg[6] |= 0xC0
        if self.keepalive:
            assert self.keepalive < 65536
            msg[7] |= self.keepalive >> 8
            msg[8] |= self.keepalive & 0x00FF
        if self.lw_topic:
            sz += 2 + len(self.lw_topic) + 2 + len(self.lw_msg)
            msg[6] |= 0x4 | (self.lw_qos & 0x1) << 3 | (self.lw_qos & 0x2) << 3
            msg[6] |= self.lw_retain << 5

        i = 1
        while sz > 0x7F:
            premsg[i] = (sz & 0x7F) | 0x80
            sz >>= 7
            i += 1
        premsg[i] = sz

        self._sock_write(premsg, i + 2)
        self._sock_write(msg)
        self._send_str(self.client_id)
        if self.lw_topic:
            self._send_str(self.lw_topic)
            self._send_str(self.lw_msg)
        if self.user:
            self._send_str(self.user)
            self._send_str(self.pswd)
        resp = self._sock_read(4)
        assert resp[0] == 0x20 and resp[1] == 0x02
        if resp[3] != 0:
            raise MQTTException(resp[3])
        gc.collect()
        
        return resp[2] & 1

    def disconnect(self):
        try:
            self._sock_write(b"\xe0\0")
        except Exception:
            pass

        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None
        self._poller = None
        gc.collect()
        

    def ping(self):
        self._sock_write(b"\xc0\0")

    def publish(self, topic, msg, retain=False, qos=0):
        pkt = bytearray(b"\x30\0\0\0")
        pkt[0] |= qos << 1 | retain
        sz = 2 + len(topic) + len(msg)
        if qos > 0:
            sz += 2
        assert sz < 2097152
        i = 1
        while sz > 0x7F:
            pkt[i] = (sz & 0x7F) | 0x80
            sz >>= 7
            i += 1
        pkt[i] = sz
        self._sock_write(pkt, i + 1)
        self._send_str(topic)
        if qos > 0:
            self.pid += 1
            pid = self.pid
            struct.pack_into("!H", pkt, 0, pid)
            self._sock_write(pkt, 2)
        self._sock_write(msg)
        if qos == 1:
            while 1:
                op = self.wait_msg()
                if op == 0x40:
                    sz = self._rx_read(1)
                    assert sz == b"\x02"
                    rcv_pid = self._rx_read(2)
                    rcv_pid = rcv_pid[0] << 8 | rcv_pid[1]
                    if pid == rcv_pid:
                        gc.collect()
                        return
        elif qos == 2:
            assert 0
        gc.collect()

    def subscribe(self, topic, qos=0):
        assert self.cb is not None, "Subscribe callback is not set"
        pkt = bytearray(b"\x82\0\0\0")
        self.pid += 1
        struct.pack_into("!BH", pkt, 1, 2 + 2 + len(topic) + 1, self.pid)
        self._sock_write(pkt)
        self._send_str(topic)
        self._sock_write(qos.to_bytes(1, "little"))
        while 1:
            op = self.wait_msg()
            if op == 0x90:
                resp = self._rx_read(4)
                assert resp[1] == pkt[2] and resp[2] == pkt[3]
                if resp[3] == 0x80:
                    raise MQTTException(resp[3])
                gc.collect()
                return

    def wait_msg(self, blocking=True):
        if not blocking and self._poller and not self._poll(select.POLLIN, 0):
            return None
        if self.socket_timeout is None:
            self.sock.setblocking(True)
        else:
            self._set_sock_timeout()
        if not self._rx_wait(1, blocking):
            return None

        idx = self._rx_off

        if not self._rx_wait_from_idx(idx, 1, blocking):
            return None
        op = self._rx_buf[idx]
        idx += 1

        if op == 0xD0:  # PINGRESP
            if not self._rx_wait_from_idx(idx, 1, blocking):
                return None
            sz = self._rx_buf[idx]
            idx += 1
            assert sz == 0
            self._rx_off = idx
            self._rx_compact()
            return None

        if op & 0xF0 != 0x30:
            # Ensure whole control packet is buffered before returning op.
            idx2 = idx
            rem = 0
            sh = 0
            while True:
                if not self._rx_wait_from_idx(idx2, 1, blocking):
                    return None
                b = self._rx_buf[idx2]
                idx2 += 1
                rem |= (b & 0x7F) << sh
                if not b & 0x80:
                    break
                sh += 7
            if not self._rx_wait_from_idx(idx2, rem, blocking):
                return None
            self._rx_off = idx
            self._rx_compact()
            return op

        # Remaining length (MQTT varint)
        sz = 0
        sh = 0
        while True:
            if not self._rx_wait_from_idx(idx, 1, blocking):
                return None
            b = self._rx_buf[idx]
            idx += 1
            sz |= (b & 0x7F) << sh
            if not b & 0x80:
                break
            sh += 7

        if not self._rx_wait_from_idx(idx, sz, blocking):
            return None

        topic_len = (self._rx_buf[idx] << 8) | self._rx_buf[idx + 1]
        idx += 2
        topic = bytes(self._rx_buf[idx:idx + topic_len])
        idx += topic_len
        sz -= topic_len + 2
        pid = None
        if op & 6:
            pid = (self._rx_buf[idx] << 8) | self._rx_buf[idx + 1]
            idx += 2
            sz -= 2
        msg = bytes(self._rx_buf[idx:idx + sz])
        idx += sz

        self._rx_off = idx
        self._rx_compact()

        self.cb(topic, msg)
        if op & 6 == 2:
            pkt = bytearray(b"\x40\x02\0\0")
            struct.pack_into("!H", pkt, 2, pid)
            self._sock_write(pkt)
        elif op & 6 == 4:
            assert 0
        if gc.mem_free() < 8000:
            gc.collect()
        return op

    def check_msg(self):
        return self.wait_msg(blocking=False)
