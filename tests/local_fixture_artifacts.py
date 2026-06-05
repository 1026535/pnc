"""Helpers for optional local screenshot-backed test fixtures."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


_FIXTURE_DATA_PATH = Path(__file__).resolve().parent / "data" / "local_fixture_artifacts.json"


def require_local_fixture_artifact(name: str, *, default_repo_relative_path: str | None = None) -> Path:
    """Returns the configured local screenshot fixture path or skips the test with a clear setup message."""

    default_path = None if default_repo_relative_path is None else Path(__file__).resolve().parents[1] / default_repo_relative_path
    if default_path is not None and default_path.is_file():
        return default_path
    document = _load_fixture_document()
    configured_path = document.get(name)
    if not configured_path:
        raise unittest.SkipTest(
            "Local screenshot fixture is not configured. "
            f"Add a path for '{name}' in '{_FIXTURE_DATA_PATH.relative_to(Path(__file__).resolve().parents[1])}'."
        )
    artifact_path = Path(configured_path).expanduser()
    if not artifact_path.is_absolute():
        artifact_path = (Path(__file__).resolve().parents[1] / artifact_path).resolve()
    if not artifact_path.is_file():
        raise unittest.SkipTest(
            f"Configured local screenshot fixture '{name}' does not exist: '{artifact_path}'."
        )
    return artifact_path


def _load_fixture_document() -> dict[str, str]:
    """Loads the local fixture-path document, defaulting to an empty mapping when it is absent."""

    if not _FIXTURE_DATA_PATH.is_file():
        return {}
    document = json.loads(_FIXTURE_DATA_PATH.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in document.items()
    ):
        raise AssertionError(
            f"Local fixture artifact file '{_FIXTURE_DATA_PATH}' must be a JSON object mapping fixture names to paths."
        )
    return document
