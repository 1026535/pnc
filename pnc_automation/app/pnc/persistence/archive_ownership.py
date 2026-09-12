"""Canonical archive stream identities, control paths, and lock scopes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.chat import ChatChannel, chat_channel_archive_directory
from pnc_automation.app.pnc.persistence.artifact_naming import format_castle_artifact_directory
from pnc_automation.core.lifecycle import close_preserving_error
from pnc_automation.core.infra.storage.file_lock import NativePathLock, NativePathLockManager
from pnc_automation.core.infra.storage.path_segments import sanitize_artifact_segment
from pnc_automation.core.infra.storage.artifact_naming import format_account_artifact_directory


class ArchiveOwnershipError(RuntimeError):
    """Raised when an archive scope cannot be mapped to one canonical stream."""


def validate_managed_path(
    root: Path,
    path: Path,
    *,
    allow_missing_leaf: bool = False,
    require_file: bool = False,
    require_directory: bool = False,
) -> Path:
    """Validates an archive path without following aliases or reparse points."""

    root_path = Path(os.path.abspath(os.fspath(root.expanduser())))
    candidate = Path(os.path.abspath(os.fspath(path.expanduser())))
    if not root_path.exists() or not root_path.is_dir() or _is_alias(root_path):
        raise ArchiveOwnershipError("Configured archive root must be an existing regular directory.")
    try:
        relative_parts = candidate.relative_to(root_path).parts
    except ValueError as error:
        raise ArchiveOwnershipError("Managed archive path escapes the configured archive root.") from error
    current = root_path
    for index, part in enumerate(relative_parts):
        current /= part
        if not os.path.lexists(current):
            if not allow_missing_leaf:
                raise ArchiveOwnershipError(f"Managed archive path component is missing: {current.name}")
            break
        if _is_alias(current):
            raise ArchiveOwnershipError(f"Managed archive path cannot use a symlink or reparse point: {current.name}")
        if index != len(relative_parts) - 1 and not current.is_dir():
            raise ArchiveOwnershipError(f"Managed archive path component is not a directory: {current.name}")
    if os.path.lexists(candidate):
        if require_file and not candidate.is_file():
            raise ArchiveOwnershipError(f"Managed archive target is not a regular file: {candidate.name}")
        if require_directory and not candidate.is_dir():
            raise ArchiveOwnershipError(f"Managed archive target is not a directory: {candidate.name}")
    resolved_root = Path(os.path.realpath(root_path))
    resolved_candidate = Path(os.path.realpath(candidate))
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as error:
        raise ArchiveOwnershipError("Managed archive path resolves outside the configured archive root.") from error
    return candidate


def validate_chat_archive_directory(root: Path, directory: Path, *, allow_missing: bool = True) -> Path:
    """Validates the canonical day/account/castle/channel chat directory."""

    root_path = Path(os.path.abspath(os.fspath(root.expanduser())))
    candidate = Path(os.path.abspath(os.fspath(directory.expanduser())))
    try:
        relative = candidate.relative_to(root_path).parts
    except ValueError as error:
        raise ArchiveOwnershipError("Chat archive directory escapes its configured root.") from error
    if len(relative) != 4 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", relative[0]):
        raise ArchiveOwnershipError("Chat archive directory does not match the canonical day/account/castle/channel layout.")
    if relative[3] not in {"kingdom", "alliance"} or any(not item for item in relative[1:]):
        raise ArchiveOwnershipError("Chat archive directory contains an invalid canonical path segment.")
    return validate_managed_path(
        root_path,
        candidate,
        allow_missing_leaf=allow_missing,
        require_directory=not (allow_missing and not os.path.lexists(candidate)),
    )


def validate_chat_archive_file(root: Path, path: Path, *, allowed_names: set[str], allow_missing: bool = False) -> Path:
    """Validates one managed chat file and its canonical parent directory."""

    candidate = Path(os.path.abspath(os.fspath(path.expanduser())))
    if candidate.name not in allowed_names:
        raise ArchiveOwnershipError("Managed chat file has an unexpected name.")
    validate_chat_archive_directory(root, candidate.parent, allow_missing=allow_missing)
    return validate_managed_path(
        root,
        candidate,
        allow_missing_leaf=allow_missing,
        require_file=not (allow_missing and not os.path.lexists(candidate)),
    )


def _is_alias(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = os.lstat(path).st_file_attributes
    except (AttributeError, OSError):
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400))


@dataclass(frozen=True, slots=True)
class ArchiveStreamIdentity:
    """Identifies one day-independent archive stream."""

    kind: str
    components: tuple[str, ...]

    def __post_init__(self) -> None:
        """Normalizes physical path components so Windows case aliases share ownership."""

        object.__setattr__(self, "kind", os.path.normcase(self.kind))
        object.__setattr__(self, "components", tuple(os.path.normcase(component) for component in self.components))

    def encoded(self) -> bytes:
        """Returns an unambiguous canonical identity encoding."""

        return json.dumps(
            {"components": self.components, "kind": self.kind},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")


@dataclass(slots=True)
class ArchiveOwnershipScope:
    """Owns one archive stream's lock and private control directory."""

    root: Path
    identity: ArchiveStreamIdentity
    lock_manager: NativePathLockManager = field(default_factory=NativePathLockManager)
    _active_lock: NativePathLock | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.root = Path(os.path.abspath(os.fspath(self.root.expanduser())))
        validate_managed_path(self.root, self.root, require_directory=True)
        validate_managed_path(self.root, self.control_root, allow_missing_leaf=True)
        self.control_directory.mkdir(parents=True, exist_ok=True)
        validate_managed_path(self.root, self.control_directory, require_directory=True)
        validate_managed_path(
            self.root,
            self.pending_path,
            allow_missing_leaf=True,
            require_file=os.path.lexists(self.pending_path),
        )

    @property
    def key(self) -> str:
        """Returns the full stream hash used for stable control names."""

        return hashlib.sha256(self.identity.encoded()).hexdigest()

    @property
    def control_root(self) -> Path:
        return self.root / ".archive-control"

    @property
    def control_directory(self) -> Path:
        return self.control_root / self.identity.kind / self.key

    @property
    def lock_path(self) -> Path:
        return self.control_root / "locks" / f"{self.key}.lock"

    @property
    def pending_path(self) -> Path:
        return self.control_directory / "pending.json"

    @contextmanager
    def lock(self) -> Iterator[None]:
        """Serializes all operations for this stream until the context exits."""

        if self._active_lock is not None:
            raise ArchiveOwnershipError("Archive stream ownership cannot be re-entered by one store transaction.")
        validate_managed_path(self.root, self.control_root, allow_missing_leaf=True)
        validate_managed_path(self.root, self.control_directory, allow_missing_leaf=True)
        self.control_directory.mkdir(parents=True, exist_ok=True)
        validate_managed_path(self.root, self.control_directory, require_directory=True)
        validate_managed_path(
            self.root,
            self.lock_path,
            allow_missing_leaf=True,
            require_file=os.path.lexists(self.lock_path),
        )
        validate_managed_path(
            self.root,
            self.pending_path,
            allow_missing_leaf=True,
            require_file=os.path.lexists(self.pending_path),
        )
        acquired = self.lock_manager.acquire(self.lock_path)
        self._active_lock = acquired
        try:
            yield
        except BaseException as error:
            self._active_lock = None
            close_preserving_error(
                lambda: self.lock_manager.release(acquired),
                error,
                message="Archive operation and lock cleanup both failed.",
            )
            raise
        else:
            self._active_lock = None
            self.lock_manager.release(acquired)


def chat_archive_scope(
    root: Path,
    *,
    account_id: str,
    castle: CastleIdentity,
    channel: ChatChannel,
    lock_manager: NativePathLockManager | None = None,
) -> ArchiveOwnershipScope:
    """Builds the canonical day-independent scope for one chat stream."""

    components = (
        format_account_artifact_directory(account_id=account_id),
        format_castle_artifact_directory(kingdom=castle.kingdom, castle_name=castle.castle_name),
        chat_channel_archive_directory(channel),
    )
    return ArchiveOwnershipScope(
        root=root,
        identity=ArchiveStreamIdentity(kind="chat", components=components),
        lock_manager=lock_manager or NativePathLockManager(),
    )


def mail_archive_scope(
    root: Path,
    *,
    active_castle: str,
    mailbox_type: str,
    fingerprint: str,
    lock_manager: NativePathLockManager | None = None,
) -> ArchiveOwnershipScope:
    """Builds the canonical cross-day scope for one mail fingerprint."""

    components = (
        sanitize_artifact_segment(active_castle),
        mailbox_type,
        fingerprint,
    )
    return ArchiveOwnershipScope(
        root=root,
        identity=ArchiveStreamIdentity(kind="mail", components=components),
        lock_manager=lock_manager or NativePathLockManager(),
    )


def chat_scope_from_transcript_path(path: Path) -> ArchiveOwnershipScope:
    """Maps the canonical five-level chat layout to its day-independent scope."""

    resolved = Path(os.path.abspath(os.fspath(path.expanduser())))
    if resolved.name != "transcript.log" or len(resolved.parents) < 5:
        raise ArchiveOwnershipError(
            "Managed chat cleanup requires a canonical transcript.log path beneath day/account/castle/channel directories."
        )
    channel, castle_segment, account_segment, day_segment, root = resolved.parents[:5]
    if channel.name not in {"kingdom", "alliance"} or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day_segment.name):
        raise ArchiveOwnershipError("Managed chat cleanup could not determine a canonical archive root from the transcript path.")
    if castle_segment.name == "" or account_segment.name == "":
        raise ArchiveOwnershipError("Managed chat cleanup requires non-empty account and castle path segments.")
    validate_chat_archive_file(root, resolved, allowed_names={"transcript.log"}, allow_missing=False)
    return ArchiveOwnershipScope(
        root=root,
        identity=ArchiveStreamIdentity(
            kind="chat",
            components=(account_segment.name, castle_segment.name, channel.name),
        ),
    )
