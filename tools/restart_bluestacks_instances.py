"""Compatibility shim for the canonical BlueStacks management module."""

from __future__ import annotations

import sys

from _script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

def main(argv: list[str] | None = None) -> int:
    """Forwards the legacy open-restart command to the canonical package entry point."""

    from pnc_automation.bluestacks_management.__main__ import main

    return main(["restart-open", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    raise SystemExit(main())
