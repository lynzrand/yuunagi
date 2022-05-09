"""
Pack the indexed data in an efficient manner.
"""

import argparse
from turtle import delay
from typing import Callable, Iterator, List, Tuple
from lib.Database import IndexDatabase


def binpack(it: Iterator[Tuple[str, int]], block_size: int,
            save_data: Callable[[Tuple[str, int]], None]):
    """
    Pack the indexed data in an efficient manner.
    """

    # The maximum number of items to put back so that smaller items could fit in the current block.
    MAX_DELAY_CNT = 5

    cur_block_id = 0
    cur_block_len = 0
    cur_block_size = 0

    # blocks delayed for more optimal packing
    delayed = []

    # We try to fit the items into blocks at `block_size` size in the order they are
    # emitted from `it`. If the current item does not fit inside the current block, we
    # put it into the `delayed` list and try to fit it in the next block. If the current
    # item size is larger than the block size, we put it into the `delayed` list and
    # try to put it into an exclusive block.

    # This loop is called every block
    while True:
        # We first try to fit any delayed item into the current block
        while len(delayed) > 0:
            item = delayed[0]
            item_size = item[1]
            if item_size + cur_block_size <= block_size or cur_block_size == 0:
                cur_block_len += 1
                save_data((item[0], cur_block_id))
                cur_block_size += item_size
                delayed.pop(0)
            else:
                break

        # Then we try to fit items from the iterator into the current block
        while cur_block_size < block_size:
            try:
                item = next(it)
            except StopIteration:
                break
            item_size = item[1]
            if item_size + cur_block_size <= block_size or cur_block_len == 0:
                cur_block_len += 1
                save_data((item[0], cur_block_id))
                cur_block_size += item_size
            else:
                if len(delayed) < MAX_DELAY_CNT:
                    delayed.append(item)
                else:
                    break

        # If the current block is empty, we are done
        if cur_block_len == 0:
            break

        assert (cur_block_size <= block_size or cur_block_len
                == 1), "We've fit too many items into the block!"

        # Otherwise, we add the current block to the result and start a new block
        cur_block_size = 0
        cur_block_len = 0


def binpack_data(db: IndexDatabase, category: str, block_size: int):

    def save_data(item: Tuple[str, int]):
        db.set_group_distribution(item[0], f"{category}_vol{item[1]}")

    binpack(db.iter_path_group_sizes(category), block_size, save_data)
