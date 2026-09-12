"""Stable repository and fixture roots for nested test packages."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TEST_DATA_ROOT = REPOSITORY_ROOT / "tests" / "data"
