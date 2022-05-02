import sqlite3
import os


class IndexDatabase:
    db: sqlite3.Connection

    def __init__(self, path: str | os.PathLike | sqlite3.Connection):
        if path is sqlite3.Connection:
            self.db = path
            return
        else:
            if not os.path.exists(path):
                os.makedirs(os.path.dirname(path), exist_ok=True)
            self.db = sqlite3.connect(path)
            self.db.execute("pragma journal_mode=wal")

    def __del__(self):
        self.db.close()

    def create_schema(self):
        with self.db:
            # Path index table
            # stores indexed paths and file hashes
            self.db.execute("""
                create table if not exists
                paths (
                    path text primary key,
                    hash blob,
                    ty int,
                    ix_time real
                )
            """)
            self.db.execute("""
                create index if not exists
                ix_paths_hash
                on paths (
                    hash asc
                )
            """)

            # Category table
            # A category is a collection of groups whose file contents are similar
            # e.g. photos, video projects, etc.
            self.db.execute("""
                create table if not exists
                category (
                    id text primary key,
                    description text
                )
                """)

            # Path grouping table
            #
            # Stores group of paths. Each group is identified by a unique path prefix, and governs
            # all paths starting with this prefix (that is, under the same directory).
            #
            # A path group is ususally a single project file, or a directory containing files from
            # a single project.
            #
            # Path groups can be compressable if they mostly contain plaintext files. This is tested
            # by picking the first few chunks of each file and try to compress them.
            self.db.execute("""
                create table if not exists
                path_groups (
                    prefix text primary key,
                    category text references category (id),
                    compressable bool default 0,
                    // TODO: add more fields
                )
            """)
            self.db.execute("""
                create index if not exists
                ix_path_groups_category
                on path_groups (
                    category asc
                )
            """)

            # Data distribution table
            #
            # This table contains data about how path groups is written into different disk images.
            # In most times this table should be empty. It is used as a result of the packing
            # operation done in later phases.
            self.db.execute("""
                create table if not exists
                data_distribution (
                    path_group text references path_groups (prefix),
                    target_media text
                )
            """)
            self.db.execute("""
                create index if not exists
                ix_data_distribution_path_group
                on data_distribution (
                    path_group asc
                )
            """)
            self.db.execute("""
                create index if not exists
                ix_data_distribution_target_media
                on data_distribution (
                    target_media asc
                )
            """)

        pass
