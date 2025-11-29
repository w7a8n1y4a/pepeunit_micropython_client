import os
import gc
import ubinascii as binascii

import ucryptolib as _cryptolib


class AesGcmCipher:
    def _get_key(self, key_b64: str) -> bytes:
        key = self._b64decode_to_bytes(key_b64)
        if len(key) not in (16, 24, 32):
            raise ValueError("AES key must be 16, 24, or 32 bytes after base64 decoding")
        return key
    
    def aes_gcm_encode(self, data: str, key: str) -> str:
        plaintext = data.encode("utf-8")
        nonce = os.urandom(12)

        key = self._get_key(key)
        ciphertext, tag = self._aes_gcm_encrypt(plaintext, nonce, key)
        gc.collect()
        out = self._b64encode(nonce) + "." + self._b64encode(ciphertext + tag)
        gc.collect()
        return out

    def aes_gcm_decode(self, data: str, key: str) -> str:
        parts = data.split(".")
        if len(parts) != 2:
            raise ValueError("Invalid ciphertext format")
        nonce = self._b64decode_to_bytes(parts[0])
        ct_and_tag = self._b64decode_to_bytes(parts[1])
        if len(nonce) != 12:
            raise ValueError("Nonce must be 12 bytes")
        if len(ct_and_tag) < 16:
            raise ValueError("Ciphertext too short")

        ciphertext = ct_and_tag[:-16]
        tag = ct_and_tag[-16:]
        key = self._get_key(key)
        plaintext = self._aes_gcm_decrypt(ciphertext, tag, nonce, key)
        return plaintext.decode("utf-8")

    @staticmethod
    def _to_bytes(value: int, length: int) -> bytes:
        return value.to_bytes(length, "big")

    @staticmethod
    def _from_bytes(b: bytes) -> int:
        return int.from_bytes(b, "big")

    @staticmethod
    def _b64encode(b: bytes) -> str:
        return binascii.b2a_base64(b).rstrip(b"\n").decode("utf-8")

    @staticmethod
    def _b64decode_to_bytes(s: str) -> bytes:
        bs = s.encode("utf-8")
        padding_needed = (-len(bs)) % 4
        if padding_needed:
            bs += b"=" * padding_needed
        return binascii.a2b_base64(bs)

    def _aes_ecb_encrypt_block(self, block16: bytes, cipher) -> bytes:
        if len(block16) != 16:
            raise ValueError("ECB block must be 16 bytes")
        return cipher.encrypt(block16)

    @staticmethod
    def _xor_bytes(a: bytes, b: bytes) -> bytes:
        n = len(a)
        return bytes(a[i] ^ b[i] for i in range(n))

    @staticmethod
    def _pad16(b: bytes) -> bytes:
        if not b:
            return b""
        rem = len(b) % 16
        if rem == 0:
            return b
        return b + b"\x00" * (16 - rem)

    @staticmethod
    def _inc32(counter_block: bytes) -> bytes:
        y = bytearray(counter_block)
        c = (y[12] << 24) | (y[13] << 16) | (y[14] << 8) | y[15]
        c = (c + 1) & 0xFFFFFFFF
        y[12] = (c >> 24) & 0xFF
        y[13] = (c >> 16) & 0xFF
        y[14] = (c >> 8) & 0xFF
        y[15] = c & 0xFF
        return bytes(y)

    @staticmethod
    def _gf_mul(x: int, y: int) -> int:
        R = 0xE1000000000000000000000000000000
        z = 0
        v = x
        for i in range(128):
            if (y >> (127 - i)) & 1:
                z ^= v
            if v & 1:
                v = (v >> 1) ^ R
            else:
                v >>= 1
        return z

    def _ghash(self, H: bytes, associated_data: bytes, ciphertext: bytes) -> bytes:
        h = self._from_bytes(H)
        y = 0

        if associated_data:
            aad_padded = self._pad16(associated_data)
            for i in range(0, len(aad_padded), 16):
                y ^= self._from_bytes(aad_padded[i : i + 16])
                y = self._gf_mul(y, h)

        if ciphertext:
            c_padded = self._pad16(ciphertext)
            for i in range(0, len(c_padded), 16):
                y ^= self._from_bytes(c_padded[i : i + 16])
                y = self._gf_mul(y, h)

        aad_bits = (len(associated_data) if associated_data else 0) * 8
        c_bits = len(ciphertext) * 8
        len_block = self._to_bytes(aad_bits, 8) + self._to_bytes(c_bits, 8)
        y ^= self._from_bytes(len_block)
        y = self._gf_mul(y, h)
        return self._to_bytes(y, 16)

    def _aes_gcm_encrypt(self, plaintext: bytes, nonce: bytes, key: bytes) -> tuple:
        ecb = _cryptolib.aes(key, 1)
        H = self._aes_ecb_encrypt_block(b"\x00" * 16, ecb)

        if len(nonce) != 12:
            raise ValueError("Nonce must be 12 bytes")
        J0 = nonce + b"\x00\x00\x00\x01"

        counter = self._inc32(J0)
        ciphertext = bytearray(len(plaintext))
        i = 0
        while i < len(plaintext):
            s_i = self._aes_ecb_encrypt_block(counter, ecb)
            block = plaintext[i : i + 16]
            keystream = s_i[: len(block)]
            ct_block = self._xor_bytes(block, keystream)
            ciphertext[i : i + len(block)] = ct_block
            i += len(block)
            counter = self._inc32(counter)

        S = self._ghash(H, b"", bytes(ciphertext))
        tag = self._xor_bytes(self._aes_ecb_encrypt_block(J0, ecb), S)
        gc.collect()
        return bytes(ciphertext), tag

    def _aes_gcm_decrypt(self, ciphertext: bytes, tag: bytes, nonce: bytes, key: bytes) -> bytes:
        if len(tag) != 16:
            raise ValueError("Invalid tag size")
        if len(nonce) != 12:
            raise ValueError("Nonce must be 12 bytes")

        ecb = _cryptolib.aes(key, 1)
        H = self._aes_ecb_encrypt_block(b"\x00" * 16, ecb)
        J0 = nonce + b"\x00\x00\x00\x01"

        S = self._ghash(H, b"", ciphertext)
        expected_tag = self._xor_bytes(self._aes_ecb_encrypt_block(J0, ecb), S)

        mismatch = 0
        for a, b in zip(tag, expected_tag):
            mismatch |= a ^ b
        if mismatch != 0:
            raise ValueError("Authentication failed")

        counter = self._inc32(J0)
        plaintext = bytearray(len(ciphertext))
        i = 0
        while i < len(ciphertext):
            s_i = self._aes_ecb_encrypt_block(counter, ecb)
            block = ciphertext[i : i + 16]
            keystream = s_i[: len(block)]
            pt_block = self._xor_bytes(block, keystream)
            plaintext[i : i + len(block)] = pt_block
            i += len(block)
            counter = self._inc32(counter)

        return bytes(plaintext)


