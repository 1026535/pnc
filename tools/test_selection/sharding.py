"""Deterministic module partitioning after canonical test selection."""

from collections.abc import Iterable


def shard_modules(modules: Iterable[str], index: int, count: int) -> list[str]:
    """Partition sorted selected modules exactly once using zero-based indices."""
    if count < 1 or not 0 <= index < count:
        raise ValueError("shard count must be positive and index must be in [0, count)")
    return sorted(modules)[index::count]
