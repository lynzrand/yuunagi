"""
Create encrypted, compressed archives with error check support
"""

import hashlib
from io import BytesIO, RawIOBase
from optparse import Option
import pathlib
import tarfile
import argparse
from types import FunctionType, NoneType
from typing import Callable, Iterable, Optional
from cryptography.hazmat.primitives.ciphers.modes import CBC
from cryptography.hazmat.primitives.ciphers.algorithms import AES
from cryptography.hazmat.primitives.ciphers.base import CipherContext
from cryptography.hazmat.primitives.hashes import HashContext


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("archive_file",
                    help="The resulting archive file to create")
    ap.add_argument(
        "source",
        nargs="+",
        help=
        """Source directories or files to add. All items are placed in the top 
        level of the created archive.""")
    ap.add_argument(
        "-e, --encrypt",
        action="store_true",
        help="Encrypt the archive with AES-256-CBC. [UNIMPLEMENTED]")
    args = ap.parse_args()

    archive = pathlib.Path(args.archive_file)
    digest_name = archive.with_name(archive.name + ".sha256")
    create_archive(map(pathlib.Path, args.source), archive)


class ProxiedIO(RawIOBase):
    """
    A IO instance that proxies the request into another IO instance.
    """

    def __init__(self, proxied: RawIOBase) -> None:
        super().__init__()
        self.io = proxied

    io: RawIOBase

    def readable(self) -> bool:
        return self.io.readable()

    def read(self, __size: int = 0) -> bytes | None:
        return self.io.read(__size)

    def write(self, __buffer) -> Optional[int]:
        return self.io.write(__buffer)

    def get_digest(self):
        return self.digest


class EncryptedWriteIO(ProxiedIO):
    """
    An IO instance that encrypts the written bytes and then writes them into
    another IO instance.
    """

    def __init__(self, proxied: RawIOBase, enc: CipherContext) -> None:
        super().__init__(proxied)
        self.enc = enc

    enc: CipherContext

    def write(self, buf) -> int | None:
        return super().write(buf)

    def close(self) -> None:
        remainder = self.enc.finalize()
        self.write(remainder)
        return super().close()


class EncryptedReadIO(ProxiedIO):
    """
    An IO instance that decrypts the read bytes from another IO instance.
    """

    def __init__(self, proxied: RawIOBase, dec: CipherContext) -> None:
        super().__init__(proxied)
        self.dec = dec

    dec: CipherContext
    finalized: bool = False

    def read(self, __size: int = 0) -> bytes | None:
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

    def __init__(self, proxied: RawIOBase, digest: HashContext) -> None:
        super().__init__(proxied)
        self.digest = digest

    digest: HashContext

    def write(self, __buffer) -> Optional[int]:
        self.digest.update(__buffer)
        return super().write(__buffer)

    def get_digest(self):
        return self.digest


def create_archive(
    source: Iterable[pathlib.Path],
    target_io: BytesIO,
    add_digest: Callable[[str, str], None],
):
    """
    Creates an archive of the following source, and write the digest into the given path.
    """
    with tarfile.TarFile.xzopen(None, 'w', fileobj=target_io) as rf:
        for s in source:
            source_name = pathlib.Path(s.name)
            for f in s.rglob("*"):
                f_path = (source_name / f.relative_to(s)).as_posix()
                if f.is_file():
                    rf.add(f, f_path)
                    with open(f, "rb") as ff:
                        dd = hashlib.sha256()
                        while True:
                            buf = ff.read(1024 * 1024)
                            if len(buf) == 0: break
                            dd.update(buf)
                        add_digest(f_path, dd.hexdigest())
                        print(f"{dd.hexdigest()} {f_path}")


if __name__ == "__main__": main()
