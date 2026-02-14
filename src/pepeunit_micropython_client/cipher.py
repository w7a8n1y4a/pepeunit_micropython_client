import os
import gc
import micropython

import utils

import ucryptolib as _cryptolib


@micropython.viper
def _gf_mul_core(z, v, x, y):
    pz = ptr8(z)
    pv = ptr8(v)
    px = ptr8(x)
    py = ptr8(y)
    j: int = 0
    while j < 16:
        pz[j] = 0
        pv[j] = px[j]
        j += 1
    i: int = 0
    while i < 128:
        if (py[i >> 3] >> (7 - (i & 7))) & 1:
            j = 0
            while j < 16:
                pz[j] = pz[j] ^ pv[j]
                j += 1
        lsb: int = pv[15] & 1
        j = 15
        while j > 0:
            pv[j] = (pv[j] >> 1) | ((pv[j - 1] & 1) << 7)
            j -= 1
        pv[0] = pv[0] >> 1
        if lsb:
            pv[0] = pv[0] ^ 0xE1
        i += 1


class AesGcmCipher:
    __slots__ = ("_gf_v", "_gf_z", "_y")

    def __init__(self):
        self._gf_v = bytearray(16)
        self._gf_z = bytearray(16)
        self._y = bytearray(16)

    def _get_key(self, key_b64: str) -> bytes:
        key = utils.b64decode_to_bytes(key_b64)
        if len(key) not in (16, 24, 32):
            raise ValueError("AES key must be 16, 24, or 32 bytes after base64 decoding")
        return key

    async def aes_gcm_encode(self, data: str, key: str) -> str:
        plaintext = data.encode("utf-8")
        nonce = os.urandom(12)
        key = self._get_key(key)
        ciphertext, tag = await self._aes_gcm_encrypt(plaintext, nonce, key)
        del plaintext
        ct_tag = bytearray(len(ciphertext) + 16)
        ct_tag[:len(ciphertext)] = ciphertext
        ct_tag[len(ciphertext):] = tag
        del ciphertext, tag
        out = utils.b64encode(nonce) + "." + utils.b64encode(ct_tag)
        del ct_tag
        gc.collect()
        return out

    async def aes_gcm_decode(self, data: str, key: str) -> str:
        parts = data.split(".")
        if len(parts) != 2:
            raise ValueError("Invalid ciphertext format")
        nonce = utils.b64decode_to_bytes(parts[0])
        ct_and_tag = utils.b64decode_to_bytes(parts[1])
        del parts
        if len(nonce) != 12:
            raise ValueError("Nonce must be 12 bytes")
        if len(ct_and_tag) < 16:
            raise ValueError("Ciphertext too short")

        ciphertext = ct_and_tag[:-16]
        tag = ct_and_tag[-16:]
        key = self._get_key(key)
        plaintext = await self._aes_gcm_decrypt(ciphertext, tag, nonce, key)
        del nonce, ct_and_tag, ciphertext, tag
        gc.collect()
        return plaintext.decode("utf-8")

    @staticmethod
    @micropython.viper
    def _xor_bytes(a, b) -> object:
        n: int = int(len(a))
        out = bytearray(n)
        pa = ptr8(a)
        pb = ptr8(b)
        po = ptr8(out)
        i: int = 0
        while i < n:
            po[i] = pa[i] ^ pb[i]
            i += 1
        return bytes(out)

    @staticmethod
    @micropython.viper
    def _xor_into(out, out_offset: int, a, b, n: int):
        po = ptr8(out)
        pa = ptr8(a)
        pb = ptr8(b)
        i: int = 0
        while i < n:
            po[out_offset + i] = pa[i] ^ pb[i]
            i += 1

    @staticmethod
    @micropython.viper
    def _inc32(counter_block):
        y = ptr8(counter_block)
        c: int = (y[12] << 24) | (y[13] << 16) | (y[14] << 8) | y[15]
        c = (c + 1) & 0xFFFFFFFF
        y[12] = (c >> 24) & 0xFF
        y[13] = (c >> 16) & 0xFF
        y[14] = (c >> 8) & 0xFF
        y[15] = c & 0xFF

    def _gf_mul(self, x, y):
        """GF(2^128) multiply using pre-allocated byte arrays.
        Result in self._gf_z; caller must use/copy before next call.
        """
        _gf_mul_core(self._gf_z, self._gf_v, x, y)
        return self._gf_z

    async def _ghash_update(self, y, h, data):
        """XOR and GF-multiply data blocks into y (bytearray 16) in place."""
        mv = memoryview(data)
        n = len(mv)
        full = n & ~0xF

        if full:
            for i in range(0, full, 16):
                for j in range(16):
                    y[j] ^= mv[i + j]
                y[:] = self._gf_mul(y, h)
                await utils.ayield((i >> 4) + 1, every=32, do_gc=False)

        if n != full:
            for j in range(n - full):
                y[j] ^= mv[full + j]
            y[:] = self._gf_mul(y, h)

    async def _ghash(self, H, aad, ciphertext):
        """GHASH; result in self._gf_z (valid until next _gf_mul)."""
        y = self._y
        for j in range(16):
            y[j] = 0

        if aad:
            await self._ghash_update(y, H, aad)

        if ciphertext:
            await self._ghash_update(y, H, ciphertext)

        bits = (len(aad) if aad else 0) << 3
        for j in range(7, -1, -1):
            y[j] ^= bits & 0xFF
            bits >>= 8

        bits = len(ciphertext) << 3
        for j in range(15, 7, -1):
            y[j] ^= bits & 0xFF
            bits >>= 8

        return self._gf_mul(y, H)

    async def _aes_gcm_encrypt(self, plaintext: bytes, nonce: bytes, key: bytes) -> tuple:
        ecb = _cryptolib.aes(key, 1)
        H = ecb.encrypt(b"\x00" * 16)

        if len(nonce) != 12:
            raise ValueError("Nonce must be 12 bytes")
        J0 = nonce + b"\x00\x00\x00\x01"

        counter = bytearray(J0)
        self._inc32(counter)
        ciphertext = bytearray(len(plaintext))
        plaintext_mv = memoryview(plaintext)
        i = 0
        while i < len(plaintext):
            s_i = ecb.encrypt(counter)
            block_len = min(16, len(plaintext) - i)
            self._xor_into(ciphertext, i, plaintext_mv[i : i + block_len], s_i, block_len)
            i += block_len
            self._inc32(counter)
            await utils.ayield(i >> 4, every=32, do_gc=False)

        S = await self._ghash(H, b"", ciphertext)
        tag = self._xor_bytes(ecb.encrypt(J0), S)
        return bytes(ciphertext), tag

    async def _aes_gcm_decrypt(self, ciphertext: bytes, tag: bytes, nonce: bytes, key: bytes) -> bytes:
        if len(tag) != 16:
            raise ValueError("Invalid tag size")
        if len(nonce) != 12:
            raise ValueError("Nonce must be 12 bytes")

        ecb = _cryptolib.aes(key, 1)
        H = ecb.encrypt(b"\x00" * 16)
        J0 = nonce + b"\x00\x00\x00\x01"

        S = await self._ghash(H, b"", ciphertext)
        expected_tag = self._xor_bytes(ecb.encrypt(J0), S)

        mismatch = 0
        for a, b in zip(tag, expected_tag):
            mismatch |= a ^ b
        if mismatch != 0:
            raise ValueError("Authentication failed")

        counter = bytearray(J0)
        self._inc32(counter)
        plaintext = bytearray(len(ciphertext))
        ciphertext_mv = memoryview(ciphertext)
        i = 0
        while i < len(ciphertext):
            s_i = ecb.encrypt(counter)
            block_len = min(16, len(ciphertext) - i)
            self._xor_into(plaintext, i, ciphertext_mv[i : i + block_len], s_i, block_len)
            i += block_len
            self._inc32(counter)
            await utils.ayield(i >> 4, every=32, do_gc=False)

        return bytes(plaintext)
