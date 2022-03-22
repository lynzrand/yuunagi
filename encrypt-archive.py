"""
Create encrypted, compressed archives with error check support
"""

import hashlib
import pathlib
import tarfile
import argparse
from typing import Iterable


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
    create_archive(map(pathlib.Path, args.source),
                   pathlib.Path(args.archive_file))


def create_archive(source: Iterable[pathlib.Path], res_archive: pathlib.Path):
    with open(res_archive.with_name(res_archive.name + ".sha256"),
              "w") as digest:
        with tarfile.TarFile.xzopen(res_archive, 'w') as rf:
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
                            digest.write(f"{dd.hexdigest()} {f_path}\r\n")
                            print(f"{dd.hexdigest()} {f_path}")
        with open(res_archive, "rb") as rf:
            digest.write("\r\n\r\n====\r\n")
            print("\r\n\r\n====")
            d = hashlib.sha256()
            while True:
                buf = rf.read(1024 * 1024)
                if len(buf) == 0: break
                d.update(buf)
            digest.write(f"{d.hexdigest()} {res_archive.name}\r\n")
            print(f"{d.hexdigest()} {res_archive.name}\r\n")


if __name__ == "__main__": main()
