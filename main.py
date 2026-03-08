"""Thin entry point that delegates to the packaged CLI."""

from pnc_automation.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
