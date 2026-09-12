"""Shared helpers for preserving operation failures during resource cleanup."""

from __future__ import annotations

from collections.abc import Callable


def close_preserving_error(
    close: Callable[[], None],
    active_error: BaseException | None,
    *,
    message: str,
) -> None:
    """Runs cleanup without replacing an already-active operation failure."""

    try:
        close()
    except BaseException as cleanup_error:
        if active_error is None:
            raise
        raise BaseExceptionGroup(message, [active_error, cleanup_error]) from None
