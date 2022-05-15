from pathlib import Path
from random import random
import pycdlib

from lib.Database import IndexDatabase


def to_base36_4_digit(n: int, n_digits: int = 4) -> str:
    res = ""
    for i in range(n_digits):
        res += "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"[n % 36]
        n //= 36
    return res


# Well, ISO demands 8.3 file naming in the base case, so here we are
class EightDotThreeNameProvider:
    """
    A class to provide 8.3 names for files inside a single directory
    """

    def __init__(self) -> None:
        self.taken_names = set()
        self.taken_name_prefixes = dict()

    taken_names: set[str]
    " A set of names that have been taken"

    taken_name_prefixes: dict[str, int]
    " A dictionary of already taken name prefixes (and suffixes) and their count "

    def get_name(self, name: str, is_dir: bool = False) -> str:
        """
        Get a name for a file
        """
        # assert it's a relative path with no parent
        assert name.find("/") == -1 and name.find("\\") == -1, \
            "The name must be a pure filename"

        # replace any invalid char in the name with underscore
        name = name.strip(".")
        invalid_chars = " :*?<>|+='\"[]"
        for c in invalid_chars:
            name = name.replace(c, "_")
        if is_dir:
            name = name.replace(".", "_")  # directories can't have extensions

        name_parts = Path(name)
        # check if the name is already 8.3 and not taken
        if ((len(name_parts.stem) <= 8) and (len(name_parts.suffix) <= 3)
                and (name_parts.name.upper() not in self.taken_names)):
            self.taken_names.add(name_parts.name.upper())
            return name_parts.name.upper()

        eight_dot_three_ext = name_parts.suffix.upper(
        )[:4]  # include the period
        eight_dot_three_name = name_parts.stem.upper()[:8]

        # first we test if the name can be stored as `XXXXX~X.EXT`
        name_prefix_5 = eight_dot_three_name[:5]
        if name_prefix_5 not in self.taken_name_prefixes:
            self.taken_name_prefixes[name_prefix_5] = 0
            return name_prefix_5 + "~0" + eight_dot_three_ext

        if self.taken_name_prefixes[name_prefix_5] < 4:
            self.taken_name_prefixes[name_prefix_5] += 1
            return name_prefix_5 + "~" + str(
                self.taken_name_prefixes[name_prefix_5]) + eight_dot_three_ext

        # This is unlikely, but if there's already 4 names sharing the same
        # starting letters, we need to use the hash of the name.

        # We now take the first 2 letters and use a hash as the rest of the name
        name_prefix_2 = eight_dot_three_name[:2]
        # The hash string is the last 4 digits of the name's hash in base 36
        name_hash = to_base36_4_digit(hash(name))
        name_prefix_2_hash = name_prefix_2 + name_hash

        if name_prefix_2_hash not in self.taken_name_prefixes:
            self.taken_name_prefixes[name_prefix_2_hash] = 0
            return name_prefix_2_hash + "~0" + eight_dot_three_ext

        if self.taken_name_prefixes[name_prefix_2_hash] < 10:
            self.taken_name_prefixes[name_prefix_2_hash] += 1
            return name_prefix_2_hash + "~" + str(
                self.taken_name_prefixes[name_prefix_2_hash]
            ) + eight_dot_three_ext

        # in an VERY UNLIKELY cast we reached here.
        # We have no choice left, so just generate a random 8-letter upper case
        # name and hope for the best
        while True:
            s = to_base36_4_digit(int(random() * 2**32), 8)
            if s + eight_dot_three_ext not in self.taken_names:
                self.taken_names.add(s)
                return s + eight_dot_three_ext


def create_iso(media_name: str, db: IndexDatabase):
    path_groups = db.get_media_paths(media_name)
    iso = pycdlib.PyCdlib()
    iso.new(udf=True)
    udf = iso.get_udf_facade()
    for path_group_name in path_groups:
        path_group = db.get_path_group(path_group_name)
        iso.add_directory()
    pass


def main():
    pass


if __name__ == "__main__":
    main()
