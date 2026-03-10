"""Ensures standalone tool scripts can import the repository packages."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_repo_root_on_path() -> Path:
    """Prepends the repository root to ``sys.path`` when a tool runs as a script."""

    root = Path(__file__).resolve().parents[1]
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    return root
