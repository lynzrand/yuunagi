from ast import Tuple
import sqlite3
import os
from sys import prefix
from typing import Iterator
from unicodedata import category

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


class PathData:
    path: str
    hash: bytes | None
    ty: int
    size: int
    index_time: int

    def __init__(self, path: str, hash: bytes | None, ty: int, size: int,
                 index_time: int):
        self.path = path
        self.size = size
        self.hash = hash
        self.ty = ty
        self.index_time = index_time

    def __str__(self):
        return f"{self.path} {self.hash} {self.ty} {self.size} {self.index_time}"


class PathGroup:
    prefix: str
    category: str
    compressable: bool

    def __init__(self, prefix: str, category: str, compressable: bool):
        self.prefix = prefix
        self.category = category
        self.compressable = compressable

    def __str__(self):
        return f"{self.prefix} {self.category} {self.compressable}"


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

            # Save schema version and undo scripts
            self.db.execute("""
            create table if not exists __schema 
            (version integer, undo_script text)
            """)

            # Path index table
            # stores indexed paths and file hashes
            self.db.execute("""
                create table if not exists
                paths (
                    path text primary key,
                    hash blob,
                    ty int,
                    size int,
                    index_time real
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

            # save the current schema and undo script into the database
            self.db.execute(
                """
            insert into __schema
            values (:version, :undo_script)
            """, {
                    "version":
                    1,
                    "undo_script":
                    """
                    delete from __schema;
                    delete from paths;
                    delete from path_groups;
                    delete from data_distribution;
                    delete from category;
                    """
                })

    def add_or_update_path_raw(self, path: str, hash: bytes | None, ty: int,
                               size: int, index_time: float):
        with self.db:
            self.db.execute(
                """
                insert or replace into paths
                values (:path, :hash, :ty, :size, :index_time)
            """, {
                    "path": path,
                    "hash": hash,
                    "ty": ty,
                    "size": size,
                    "index_time": index_time
                })

    def add_or_update_path(self, path_data: PathData):
        self.add_or_update_path_raw(path_data.path, path_data.hash,
                                    path_data.ty, path_data.size,
                                    path_data.index_time)

    def get_path_data(self, path: str) -> PathData | None:
        with self.db:
            cursor = self.db.execute(
                """
            select * from paths
            where path = :path
            """, {"path": path})
            row = cursor.fetchone()
            if row is None:
                return None
            else:
                return PathData(row[0], row[1], row[2], row[3], row[4])

    def create_path_group_raw(self,
                              prefix: str,
                              category: str,
                              compressable: int | None = 0):
        with self.db:
            self.db.execute(
                """
            insert into path_groups
            values (:prefix, :category, :compressable) 
            """, {
                    "prefix": prefix,
                    "category": category,
                    "compressable": compressable
                })

    def create_path_group(self, path_group: PathGroup):
        self.create_path_group_raw(path_group.prefix, path_group.category,
                                   path_group.compressable)

    def set_path_group_category(self, prefix: str, category: str):
        with self.db:
            self.db.execute(
                """
            update path_groups
            set category = :category
            where prefix = :prefix
            """, {
                    "prefix": prefix,
                    "category": category
                })
            self.db.commit()

    def set_path_group_compressable(self, prefix: str, compressable: int):
        with self.db:
            self.db.execute(
                """
            update path_groups
            set compressable = :compressable
            where prefix = :prefix
            """, {
                    "prefix": prefix,
                    "compressable": compressable
                })
            self.db.commit()

    def get_path_group(self, prefix: str) -> PathGroup | None:
        with self.db:
            cursor = self.db.execute(
                """
            select * from path_groups
            where prefix = :prefix
            """, {"prefix": prefix})
            row = cursor.fetchone()
            if row is None:
                return None
            else:
                return PathGroup(row[0], row[1], row[2])

    def iter_path_groups(self, category: str = None) -> Iterator[PathGroup]:

        if category is None:
            cursor = self.db.execute("""
                select * from path_groups
                """)
        else:
            cursor = self.db.execute(
                """
                select * from path_groups
                where category = :category
                """, {"category": category})
        for row in cursor:
            yield PathGroup(row[0], row[1], row[2])

    def iter_path_group_sizes(self,
                              category: str = None
                              ) -> Iterator[Tuple[str, int]]:
        sql = """
            select prefix, sum(size) from 
                path_groups left join paths on like(prefix+"%", paths.path)
        """
        if category is not None:
            sql += " where category = :category"

        sql += " group by prefix"

        cursor = self.db.execute(sql, {"category": category})
        for row in cursor:
            yield row[0], row[1]

    def create_category(self, id: str, description: str):
        with self.db:
            self.db.execute(
                """
            insert into category
            values (:id, :description)
            """, {
                    "id": id,
                    "description": description
                })

    def remove_category(self, id: str):
        with self.db:
            # unset the category of all path groups in this category
            self.db.execute(
                """
            update path_groups
            set category = null
            where category = :id
            """, {"id": id})

            self.db.execute(
                """
            delete from category
            where id = :id
            """, {"id": id})

    def set_group_distribution(self, path_group: str, target_media: str):
        with self.db:
            self.db.execute(
                """
            insert or replace into data_distribution
            values (:path_group, :target_media)
            """, {
                    "path_group": path_group,
                    "target_media": target_media
                })
            self.db.commit()

    def delete_data_distribution(self, media_like: str):
        with self.db:
            self.db.execute(
                """
            delete from data_distribution
            where like(target_media, :media_like)
            """, {"media_like": media_like})
            self.db.commit()
