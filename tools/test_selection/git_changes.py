"""Read Git snapshots including local edits without changing repository state."""

from __future__ import annotations

import subprocess
from pathlib import Path


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
    if result.returncode:
        raise ValueError(f"Git command failed ({args[0]}): {result.stderr.decode('utf-8', errors='replace').strip()}")
    return result.stdout


def resolve(root: Path, ref: str) -> str:
    return git(root, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode().strip()


def base_revision(root: Path, ref: str | None) -> str:
    if ref is not None:
        return resolve(root, ref)
    upstream = git(root, "rev-parse", "--abbrev-ref", "@{upstream}").decode().strip()
    return resolve(root, git(root, "merge-base", "HEAD", upstream).decode().strip())


def changed_paths(root: Path, base: str) -> list[str]:
    """Include both sides of renames/deletions and staged/unstaged/untracked files."""
    raw = git(root, "diff", "--name-status", "-z", "--find-renames", base, "--").decode("utf-8")
    tokens = iter(raw.rstrip("\0").split("\0") if raw else [])
    paths: set[str] = set()
    for status in tokens:
        paths.add(next(tokens))
        if status[0] in "RC":
            paths.add(next(tokens))
    paths.update(p for p in git(root, "ls-files", "--others", "--exclude-standard", "-z").decode().split("\0") if p)
    return sorted(paths)


def working_paths(root: Path) -> list[str]:
    output = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    return sorted({p for p in output.decode().split("\0") if p and (root / p).is_file()})


def _python_blobs(root: Path, revision: str) -> dict[str, bytes]:
    """Keep NUL-framed paths separate from validated, filename-free batch OIDs."""
    tree = git(root, "ls-tree", "-r", "--full-tree", "-z", revision, "--")
    if tree and not tree.endswith(b"\0"):
        raise ValueError("Truncated Git tree response")
    blobs: dict[str, bytes] = {}
    for entry in tree.split(b"\0")[:-1]:
        metadata, separator, raw_path = entry.partition(b"\t")
        fields = metadata.split(b" ")
        if not separator or not raw_path or len(fields) != 3:
            raise ValueError("Malformed Git tree entry")
        mode, kind, oid = fields
        if (len(mode) != 6 or any(c not in b"01234567" for c in mode)
                or len(oid) not in {40, 64}
                or any(c not in b"0123456789abcdef" for c in oid)):
            raise ValueError("Malformed Git tree mode or object ID")
        path = raw_path.decode("utf-8")
        if not path.endswith(".py"):
            continue
        if kind != b"blob":
            raise ValueError(f"Expected source blob for {path}")
        if path in blobs:
            raise ValueError(f"Duplicate Git source path: {path}")
        blobs[path] = oid
    return blobs


def python_snapshot(root: Path, revision: str | None) -> dict[str, str]:
    """Read source blobs by OID, validating every response and its exact framing."""
    if revision is None:
        return {p: (root / p).read_text(encoding="utf-8-sig") for p in working_paths(root) if p.endswith(".py")}
    blobs = _python_blobs(root, revision)
    if not blobs:
        return {}
    query = b"".join(oid + b"\n" for oid in blobs.values())
    batch = subprocess.run(
        ["git", "-C", str(root), "cat-file", "--batch"],
        input=query, capture_output=True, check=False,
    )
    if batch.returncode:
        raise ValueError("Git source blob batch failed")
    response = batch.stdout
    result: dict[str, str] = {}
    offset = 0
    for path, expected_oid in blobs.items():
        end = response.find(b"\n", offset)
        if end == -1:
            raise ValueError(f"Missing Git blob header for {path}")
        fields = response[offset:end].split(b" ")
        if (len(fields) != 3 or fields[0] != expected_oid
                or fields[1] != b"blob" or not fields[2].isdigit()):
            raise ValueError(f"Invalid Git blob header for {path}")
        offset = end + 1
        content_end = offset + int(fields[2])
        if content_end >= len(response) or response[content_end:content_end + 1] != b"\n":
            raise ValueError(f"Truncated or incorrectly framed Git blob for {path}")
        result[path] = response[offset:content_end].decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        offset = content_end + 1
    if offset != len(response):
        raise ValueError("Unexpected trailing Git blob response")
    return result
