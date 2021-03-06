"""
Proxied IO classes definitions and implementations.

This library contains the implementation of a raw IO class that proxies reads and writes
to another raw IO object.

This library also contains these classes:

- EncryptedWriteIO: an IO instance that encrypts the written bytes using a CipherContext and
    then writes them into the proxy.
- EncryptedReadIO: an IO instance that decrypts the read bytes using a CipherContext and
    then proxies them into the proxy.
- DigestingWriteOnlyBytesIO: an IO instance that digests all bytes written to it and then
    proxies them into the proxy.
"""

import binascii
import hashlib
from io import RawIOBase
from typing import IO, Optional

from cryptography.hazmat.primitives.ciphers.algorithms import AES
from cryptography.hazmat.primitives.ciphers.base import Cipher, CipherContext
from cryptography.hazmat.primitives.ciphers.modes import CBC
from cryptography.hazmat.primitives.hashes import SHA256, Hash, HashContext
from cryptography.hazmat.primitives.padding import PKCS7, PaddingContext


class ProxiedIO(RawIOBase, IO[bytes]):
    """
    A IO instance that proxies the request into another IO instance.
    """

    def __init__(self, proxied: IO[bytes]) -> None:
        super().__init__()
        self.io = proxied

    io: IO[bytes]

    def readable(self) -> bool:
        return self.io.readable()

    def read(self, __size: int = 0) -> bytes | None:
        return self.io.read(__size)

    def write(self, __buffer) -> Optional[int]:
        return self.io.write(__buffer)

    def close(self) -> None:
        if self.io.closed:
            return
        return self.io.close()

    def flush(self) -> None:
        return self.io.flush()

    def tell(self) -> int:
        return self.io.tell()

    def seek(self, __offset: int, __whence: int = ...) -> int:
        return self.io.seek(__offset, __whence)

    def seekable(self) -> bool:
        return self.io.seekable()

    def __exit__(self, *args):
        self.close()


class EncryptedWriteIO(ProxiedIO):
    """
    An IO instance that encrypts the written bytes and then writes them into
    another IO instance.
    """

    def __init__(
        self,
        proxied: IO[bytes],
        enc: CipherContext,
        salt: bytes | None = None,
    ) -> None:
        """
        Initialize the instance.

        If salt is provided, the instance will first write the salt to the proxied IO 
        in OpenSSL's format.
        """

        super().__init__(proxied)
        self.enc = enc
        self.salt = salt
        self.padder = PKCS7(AES.block_size).padder()

    padder: PaddingContext
    enc: CipherContext
    salt: bytes | None
    salt_written: bool = False
    finalized: bool = False

    def write(self, buf) -> int | None:
        if not self.salt_written and self.salt is not None:
            self.salt_written = True
            super().write(b"Salted__")
            super().write(self.salt)
        padded = self.padder.update(buf)
        encrypted = self.enc.update(padded)
        return super().write(encrypted)

    def close(self) -> None:
        if self.finalized:
            return
        self.finalized = True
        remainder = self.padder.finalize()
        remainder = self.enc.update(remainder)
        super().write(remainder)
        remainder = self.enc.finalize()
        super().write(remainder)
        super().flush()
        return super().close()

    def __exit__(self):
        self.close()
        return super().__exit__()


class EncryptedReadIO(ProxiedIO):
    """
    An IO instance that decrypts the read bytes from another IO instance.
    """

    def __init__(
        self,
        proxied: IO[bytes],
        decrypt: CipherContext | None = None,
        key: bytes | None = None,
        salt: bytes | None = None,
        read_salt_from_input: bool = True,
    ) -> None:
        super().__init__(proxied)
        if decrypt is None and key is None:
            raise ValueError("Either decrypt or key must be provided")
        if salt is None and not read_salt_from_input:
            raise ValueError("Salt must be provided in some way")

        self.dec = decrypt
        self.key = key
        self.salt = salt
        self.read_salt_from_input_file = read_salt_from_input
        self.finalized = False

    key: bytes | None = None
    salt: bytes | None = None
    read_salt_from_input_file: bool
    dec: CipherContext | None
    finalized: bool = False

    def read(self, __size: int = 0) -> bytes | None:
        # ensure the decryption context is initialized
        if self.dec is None:
            if self.salt is None:
                if self.read_salt_from_input_file:
                    # ensure header is correct
                    header = super().read(8)
                    if header != b"Salted__":
                        raise ValueError("Invalid header")
                    self.salt = super().read(8)
                    if self.salt is None:
                        raise ValueError("Invalid file format")
                else:
                    raise ValueError("Salt must be provided in some way")
            if len(self.salt) != 8:
                raise ValueError(
                    "Invalid salt length. If it's read from file, the file must be in OpenSSL's format"
                )
            if self.key is None:
                raise ValueError("Key must be provided")

            self.dec = gen_cipher(self.key, self.salt).decryptor()

        encrypted = super().read(__size)
        if encrypted is None or len(encrypted) == 0:
            if not self.finalized:
                self.finalized = True
                return self.dec.finalize()
            else:
                return None
        else:
            return self.dec.update(encrypted)

    def close(self) -> None:
        return super().close()


class DigestingWriteOnlyBytesIO(ProxiedIO):
    """
    An IO instance that digests all bytes written to it and then proxies them 
    into another IO instance.
    """

    def __init__(self, proxied: IO[bytes], digest: HashContext) -> None:
        super().__init__(proxied)
        self.digest = digest

    digest: HashContext

    def write(self, __buffer) -> Optional[int]:
        self.digest.update(__buffer)
        return super().write(__buffer)

    def get_digest(self):
        return self.digest


def with_encryption(target_io: IO[bytes], key: bytes,
                    salt: bytes) -> EncryptedWriteIO:
    """
    Returns an IO instance that encrypts the written bytes and then writes them into
    another IO instance.
    """
    cipher = gen_cipher(key, salt)
    return EncryptedWriteIO(target_io, cipher.encryptor(), salt=salt)


def with_decryption(target_io: IO[bytes], key: bytes,
                    salt: bytes) -> EncryptedReadIO:
    """
    Returns an IO instance that decrypts the read bytes from another IO instance.
    """
    cipher = gen_cipher(key, salt)
    return EncryptedReadIO(target_io, cipher.decryptor())


def gen_cipher(key: bytes, salt: bytes) -> Cipher:
    """
    Generates a Cipher instance using AES-256-CBC and PBKDF2 with the given key and salt.
    """

    # follows the format of the openssl command line tool
    enc_key_and_iv = hashlib.pbkdf2_hmac("sha256", key, salt, 10000, dklen=48)
    enc_key = enc_key_and_iv[:32]
    iv = enc_key_and_iv[32:]

    # debug print hex of enc_key and iv
    print("enc_key:", binascii.hexlify(enc_key).decode())
    print("iv:", binascii.hexlify(iv).decode())

    cipher = Cipher(AES(enc_key), CBC(iv))
    return cipher


def with_digest(target_io: IO[bytes]) -> DigestingWriteOnlyBytesIO:
    """
    Returns an IO instance that digests all bytes written to it and then proxies them 
    into another IO instance.
    """
    return DigestingWriteOnlyBytesIO(target_io, Hash(SHA256()))
