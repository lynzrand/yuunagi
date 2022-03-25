import argparse
from hashlib import sha256
from pathlib import Path
from posixpath import relpath
from turtle import width
import rich.progress as progress
import rich.live as live
import rich.table as table
import rich.style as style
import rich
from sqlite3 import Connection as Db, connect
import sqlite3
from time import time

TY_FILE = 0
"Stored type value for files"

TY_DIR = 1
"Stored type value for files"

TY_SOFT_LINK = 2
"Stored type value for soft links"

TY_HARD_LINK = 3
"Stored type value for hard links"

TY_MAP = {
    0: "file",
    1: "dir",
    2: "soft_link",
    3: "hard_link",
}

console = rich.console.Console()


class PackState():
    db: Db

    def __init__(self, path: str) -> None:
        self._inode_cnt = 0
        self._file_size_cnt = 0

        console.log("Loading database")
        self.db = sqlite3.connect(path)
        self.db.execute("pragma journal_mode = WAL")
        self.db.execute("""
            create table if not exists
            pkg (
                hash blob,
                path text,
                ty int,
                ix_time real
            )
        """)
        self.db.execute("""
            create index if not exists
            ix_pkg_path
            on pkg (
                path asc
            )
        """)
        self.db.commit()

    _disp: live.Live
    _node_scan_prog: progress.Progress
    _file_size_prog: progress.Progress

    _tid_node_scan: progress.TaskID
    _tid_whole_scan: progress.TaskID

    _inode_cnt: int
    _file_size_cnt: int

    def add_path(self, rel: Path, path: Path):
        console.log(
            "Scanning folders to get a rough estimate on work amount...")
        try:
            self._build_display()
            self._disp.start()
            for p in path.rglob("*"):
                self._inode_cnt += 1
                self._node_scan_prog.update(self._tid_node_scan,
                                            total=self._inode_cnt)
                if p.is_file():
                    self._file_size_cnt += p.stat().st_size
                    self._file_size_prog.update(self._tid_whole_scan,
                                                total=self._file_size_cnt)

            # do real scan
            console.log("Indexing all files...")
            self._file_size_prog.start_task(self._tid_whole_scan)
            self._node_scan_prog.start_task(self._tid_node_scan)
            self._add_path(rel, path)
        finally:
            self._disp.stop()

    def _build_display(self):
        tbl = table.Table.grid()

        self._node_scan_prog = progress.Progress(
            progress.TextColumn(
                "{task.description}",
                justify="right",
                table_column=table.Column(width=30),
            ),
            progress.BarColumn(None),
            progress.MofNCompleteColumn(),
        )

        self._file_size_prog = progress.Progress(
            progress.TextColumn(
                "{task.description}",
                markup=False,
                justify="right",
                table_column=table.Column(width=30),
            ),
            progress.BarColumn(None),
            progress.DownloadColumn(True),
            progress.TimeElapsedColumn(),
            progress.TimeRemainingColumn(),
        )

        tbl.add_row(self._node_scan_prog)
        tbl.add_row(self._file_size_prog)
        self._disp = live.Live(tbl,
                               transient=True,
                               console=console,
                               refresh_per_second=10)

        self._tid_node_scan = self._node_scan_prog.add_task("Files scanned",
                                                            start=False,
                                                            total=0)
        self._tid_whole_scan = self._file_size_prog.add_task("Data scanned",
                                                             start=False,
                                                             total=0)
        return self._disp

    def _add_path(self, rel: Path, path: Path):
        if path.is_dir():
            self._add_dir(rel, path)
        elif path.is_file():
            self._add_file(rel, path)

    _shared_buf = memoryview(bytearray(1024**2 * 8))

    def _add_file(self, rel: Path, path: Path):
        curr_file = None
        try:
            rel_path = path.relative_to(rel).as_posix()
            stat = path.stat()
            curr_file = self._file_size_prog.add_task(
                rel_path,
                total=stat.st_size,
            )
            hasher = sha256()
            with open(path, "rb") as f:
                while True:
                    rd = f.readinto1(self._shared_buf)
                    if rd == 0: break
                    hasher.update(self._shared_buf[0:rd])
                    self._file_size_prog.advance(curr_file, rd)
                    self._file_size_prog.advance(self._tid_whole_scan, rd)
            with self.db:
                self.db.execute(
                    "insert into pkg values(:hash, :path, :ty, :ix_time)", {
                        "hash": hasher.digest(),
                        "path": rel_path,
                        "ty": TY_FILE,
                        "ix_time": time()
                    })
            self._node_scan_prog.advance(self._tid_node_scan)
        finally:
            if curr_file is not None:
                self._file_size_prog.remove_task(curr_file)

    def _add_dir(self, rel: Path, path: Path):
        for v in path.iterdir():
            self._add_path(rel, v)
        # insert after all contents are indexed
        with self.db:
            self.db.execute(
                "insert into pkg values(:hash, :path, :ty, :ix_time)", {
                    "hash": None,
                    "path": path.relative_to(rel).as_posix(),
                    "ty": TY_DIR,
                    "ix_time": time()
                })
        self._node_scan_prog.advance(self._tid_node_scan)

    def flush(self):
        # self.db.execute("pragma wal_checkpoint(FULL)")
        pass

    def close(self):
        self.flush()
        self.db.commit()
        self.db.close()

    pass


def makeParser(a: argparse.ArgumentParser):
    a.add_argument("database",
                   help="The database file to store packing information to")
    a.add_argument("source", nargs="+", help="The folder and file(s) to index")
    a.add_argument("--relative-to",
                   help="Stored directory relative to current",
                   default=Path.cwd())
    pass


def main():
    ap = argparse.ArgumentParser("yuunagi-pack")
    makeParser(ap)
    ns = ap.parse_args()
    ps = PackState(ns.database)
    for d in ns.source:
        ps.add_path(Path(ns.relative_to).absolute(), Path(d).absolute())
    ps.close()


if __name__ == "__main__": main()
