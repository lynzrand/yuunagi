"""
Create encrypted, compressed archives with error check support
"""

import hashlib
from io import BytesIO
import os
import pathlib
import tarfile
import argparse
from typing import Callable, Iterable
from lib.IOProxy import *


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
    ap.add_argument("--encrypt",
                    action="store_true",
                    help="Encrypt the archive with AES-256-CBC.")
    ap.add_argument("--decrypt",
                    action="store_true",
                    help="Decrypt the archive with AES-256-CBC.")
    ap.add_argument(
        "--key",
        help=
        "The key to use for encryption or decryption. If not specified, the key is read from stdin.",
    )
    ap.add_argument(
        "--salt",
        help="""
        The salt to use for encryption or decryption. 

        If we are encrypting, the salt is generated randomly. If we are decrypting,
        the salt should either be provided or read from the archive.
        """,
    )
    args = ap.parse_args()

    archive = pathlib.Path(args.archive_file)
    digest_name = archive.with_name(archive.name + ".sha256")
    file_io = open(archive, "wb")
    target_io = file_io
    if args.encrypt:
        key = args.key
        if key is None:
            key = input("Enter encryption key: ").encode("utf-8")
        else:
            key = key.encode("utf-8")
        # generate random salt
        salt = args.salt
        if salt is None:
            salt = os.urandom(AES.block_size // 8 - len("Salted__"))

        target_io = with_encryption(target_io, key, salt)
    target_io = with_digest(target_io)
    digest = open(digest_name, "w")

    with digest, target_io:
        create_archive(map(pathlib.Path, args.source), target_io,
                       lambda f, d: digest.write(f + " " + d + "\n"))


def create_archive(
    source: Iterable[pathlib.Path],
    target_io: BytesIO,
    add_digest: Callable[[str, str], None],
):
    """
    Creates an archive of the following source, and write the digest into the given path.
    """
    with tarfile.TarFile.gzopen(None, 'w', fileobj=target_io) as rf:
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
                            if buf is None or len(buf) == 0: break
                            dd.update(buf)
                        add_digest(f_path, dd.hexdigest())
                        print(f"{dd.hexdigest()} {f_path}")


if __name__ == "__main__": main()
