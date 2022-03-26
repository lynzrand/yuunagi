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
        with self.db:
            self.db.execute("pragma journal_mode = WAL")
            self.db.execute("""
                create table if not exists
                pkg (
                    path text,
                    hash blob,
                    ty int,
                    ix_time real
                )
            """)
            self.db.execute("""
                create index if not exists
                ix_pkg_hash
                on pkg (
                    hash asc
                )
            """)

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
                rel_path = p.relative_to(rel).as_posix()

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
                table_column=table.Column(ratio=2),
            ),
            progress.BarColumn(None, table_column=table.Column(ratio=5)),
            progress.MofNCompleteColumn(table_column=table.Column(ratio=4)),
            expand=True,
        )

        self._file_size_prog = progress.Progress(
            progress.TextColumn(
                "{task.description}",
                markup=False,
                justify="right",
                table_column=table.Column(ratio=2, no_wrap=True),
            ),
            progress.BarColumn(None, table_column=table.Column(ratio=5)),
            progress.FileSizeColumn(table_column=table.Column(ratio=1)),
            progress.TotalFileSizeColumn(table_column=table.Column(ratio=1)),
            progress.TimeElapsedColumn(table_column=table.Column(ratio=1)),
            progress.TimeRemainingColumn(table_column=table.Column(ratio=1)),
            expand=True,
        )

        tbl.add_row(self._node_scan_prog)
        tbl.add_row(self._file_size_prog)
        self._disp = live.Live(
            tbl,
            transient=True,
            console=console,
            refresh_per_second=5,
        )

        self._tid_node_scan = self._node_scan_prog.add_task(
            "Files scanned",
            start=False,
            total=0,
        )
        self._tid_whole_scan = self._file_size_prog.add_task(
            "Data scanned",
            start=False,
            total=0,
        )
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
            db_data = next(
                self.db.execute(
                    "select * from pkg where path = ?",
                    (rel_path, ),
                ),
                None,
            )

            stat = path.stat()

            rescan = True
            if db_data is not None:
                last_index_time = db_data[3]
                if db_data[1] is not None and stat.st_mtime <= last_index_time:
                    rescan = False
                    console.log(f"Skipping already scanned file {path}")

            if not rescan:
                # Skip the file and mark it as scanned
                self._file_size_prog.advance(self._tid_whole_scan,
                                             stat.st_size)
                self._node_scan_prog.advance(self._tid_node_scan)
                return

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
                if db_data:
                    self.db.execute(
                        """
                        update pkg set hash = :hash, ty = :ty, ix_time = :ix_time
                        where path = :path
                        """, {
                            "hash": hasher.digest(),
                            "path": rel_path,
                            "ty": TY_FILE,
                            "ix_time": time()
                        })
                else:
                    self.db.execute(
                        """
                        insert into pkg values(:path, :hash, :ty, :ix_time)
                        """, {
                            "path": rel_path,
                            "hash": hasher.digest(),
                            "ty": TY_FILE,
                            "ix_time": time()
                        })
            self._node_scan_prog.advance(self._tid_node_scan)
        finally:
            if curr_file is not None:
                self._file_size_prog.remove_task(curr_file)

    def _add_dir(self, rel: Path, path: Path):
        rel_path = path.relative_to(rel).as_posix()
        db_data = next(
            self.db.execute(
                "select * from pkg where path = ?",
                (rel_path, ),
            ),
            None,
        )
        stat = path.stat()
        full_rescan = True
        if db_data is not None:
            last_index_time = db_data[3]
            if stat.st_mtime < last_index_time:
                full_rescan = False
                console.log(f"Skipping already scanned folder {path}")

        for v in path.iterdir():
            if v.is_dir() or full_rescan:
                self._add_path(rel, v)
            else:
                self._file_size_prog.advance(self._tid_whole_scan,
                                             v.stat().st_size)
                self._node_scan_prog.advance(self._tid_node_scan)

        # insert after all contents are indexed
        with self.db:
            if db_data:
                self.db.execute(
                    """
                        update pkg set hash = :hash, ty = :ty, ix_time = :ix_time
                        where path = :path
                        """, {
                        "hash": None,
                        "path": rel_path,
                        "ty": TY_DIR,
                        "ix_time": time()
                    })
            else:
                self.db.execute(
                    """
                    insert into pkg values(:path, :hash, :ty, :ix_time)
                    """, {
                        "hash": None,
                        "path": rel_path,
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
    ap = argparse.ArgumentParser("yuunagi-index")
    makeParser(ap)
    ns = ap.parse_args()
    try:
        ps = PackState(ns.database)
        for d in ns.source:
            ps.add_path(Path(ns.relative_to).resolve(), Path(d).resolve())

        result_by_type = {
            x[1]: x[0]
            for x in ps.db.execute(
                "select count(*), ty from pkg group by ty order by ty asc")
        }
        console.log("Scan completed.")
        file_cnt = result_by_type[TY_FILE] if TY_FILE in result_by_type else 0
        dir_cnt = result_by_type[TY_DIR] if TY_DIR in result_by_type else 0
        console.log(
            f"Total: [bold]{file_cnt}[/bold] files and [bold]{dir_cnt}[/bold] directories."
        )
    except KeyboardInterrupt:
        console.log(
            "Progress interrupted. Restart with the same arguments to resume.")
        pass
    finally:
        ps.close()


if __name__ == "__main__": main()
