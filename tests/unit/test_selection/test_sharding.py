"""Execution shards preserve the complete canonical selection without overlap."""

import unittest

from tools.test_selection.sharding import shard_modules


class ShardingTests(unittest.TestCase):
    def test_all_shards_partition_selection_in_stable_order(self) -> None:
        modules = [f"tests.unit.sample.test_{i:03}" for i in range(358)]
        shards = [shard_modules(reversed(modules), i, 4) for i in range(4)]
        self.assertEqual(sorted(modules), sorted(m for shard in shards for m in shard))
        self.assertEqual(len(modules), len({m for shard in shards for m in shard}))
        self.assertLessEqual(max(map(len, shards)) - min(map(len, shards)), 1)

    def test_small_selection_has_successful_empty_shards(self) -> None:
        self.assertEqual(["test_a"], shard_modules(["test_a"], 0, 4))
        self.assertEqual([], shard_modules(["test_a"], 3, 4))

    def test_invalid_shard_is_rejected(self) -> None:
        for index, count in ((0, 0), (-1, 4), (4, 4)):
            with self.subTest(index=index, count=count), self.assertRaises(ValueError):
                shard_modules([], index, count)
