"""Test package initialization that keeps temporary files inside the writable workspace."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4


_WORKSPACE_TEMPDIR = Path(__file__).resolve().parent.parent / ".tmp_test_workspace"


class _WorkspaceTemporaryDirectory:
    """Minimal workspace-backed replacement for tempfile.TemporaryDirectory used by tests."""

    def __init__(
        self,
        suffix: str | None = None,
        prefix: str | None = None,
        dir: str | os.PathLike[str] | None = None,
        ignore_cleanup_errors: bool = False,
    ) -> None:
        """Creates one writable temporary directory inside the repository workspace."""

        self._ignore_cleanup_errors = ignore_cleanup_errors
        root = _WORKSPACE_TEMPDIR if dir is None else Path(dir)
        root.mkdir(parents=True, exist_ok=True)
        safe_prefix = "tmp" if prefix is None else prefix
        safe_suffix = "" if suffix is None else suffix
        self.name = str(root / f"{safe_prefix}{uuid4().hex}{safe_suffix}")
        Path(self.name).mkdir(parents=True, exist_ok=False)

    def __enter__(self) -> str:
        """Returns the created directory path for context-manager callers."""

        return self.name

    def __exit__(self, exc_type: object, exc: object, exc_tb: object) -> None:
        """Cleans up the created workspace directory after the context exits."""

        del exc_type, exc, exc_tb
        self.cleanup()

    def cleanup(self) -> None:
        """Removes the created directory tree unless cleanup errors are explicitly ignored."""

        try:
            shutil.rmtree(self.name)
        except FileNotFoundError:
            return
        except PermissionError:
            if not self._ignore_cleanup_errors:
                raise

    def __del__(self) -> None:
        """Best-effort cleanup for callers that do not use the context-manager form."""

        self.cleanup()


def _configure_workspace_tempdir() -> None:
    """Redirects Python temp files into the repository workspace for deterministic test writes."""

    _WORKSPACE_TEMPDIR.mkdir(parents=True, exist_ok=True)
    workspace_tempdir_path = str(_WORKSPACE_TEMPDIR)
    os.environ["TMP"] = workspace_tempdir_path
    os.environ["TEMP"] = workspace_tempdir_path
    tempfile.tempdir = workspace_tempdir_path
    tempfile.TemporaryDirectory = _WorkspaceTemporaryDirectory


_configure_workspace_tempdir()
