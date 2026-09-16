"""Run one read-only Devin game-knowledge consultation with durable evidence."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


MODEL = "swe-2-max"


def git(repo: Path, *arguments: str) -> str:
    """Run Git without a shell and return UTF-8 output."""
    return subprocess.check_output(
        ["git", "-C", str(repo), *arguments],
        text=True,
        encoding="utf-8",
        errors="replace",
    ).strip()


def exact_repository(path: str) -> Path:
    """Require the supplied path to be the repository root, not a nested path."""
    repo = Path(path).expanduser().resolve(strict=True)
    top_level = Path(git(repo, "rev-parse", "--show-toplevel")).resolve()
    if top_level != repo:
        raise ValueError(f"--repo must name the exact Git root: {top_level}")
    return repo


def devin_executable() -> str:
    """Resolve Devin from PATH or the documented Windows install location."""
    found = shutil.which("devin")
    if found:
        return found
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidate = Path(local_app_data) / "devin" / "cli" / "bin" / "devin.exe"
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError("Devin CLI not found or not on PATH.")


def question_text(arguments: argparse.Namespace) -> str:
    """Read exactly one non-empty consultation question."""
    supplied = [arguments.question is not None, arguments.question_file is not None]
    if sum(supplied) != 1:
        raise ValueError("Provide exactly one of --question or --question-file.")
    if arguments.question is not None:
        question = arguments.question
    else:
        question = Path(arguments.question_file).read_text(encoding="utf-8")
    question = question.strip()
    if not question:
        raise ValueError("The consultation question is empty.")
    if len(question) > 20_000:
        raise ValueError("The consultation question is limited to 20,000 characters.")
    return question


def slug(value: str) -> str:
    """Create a short filesystem-safe identifier from the question."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (cleaned[:48] or "consultation")


def consultation_prompt(question: str) -> str:
    """Add the non-negotiable read-only consultation contract."""
    return f"""You are consulting on Puzzles & Conquest game knowledge for a Codex lead.

Question:
{question}

Consultation contract:
- Work read-only. Do not edit files, change Git state, commit, push, open a PR, install dependencies, or create project configuration.
- Inspect repository instructions, source, deterministic tests, saved artifacts, screenshots, logs, and fixtures before making claims.
- Do not use credentials, secrets, ignored local configuration, account data, emulator, ADB, or live-game actions unless the question itself explicitly authorizes one exact non-spending observation and target. Never spend resources.
- Distinguish findings as user-confirmed, repository-proven, artifact-observed, live-observed, inferred, or unknown. Cite exact paths, commands, or artifact identifiers.
- If evidence is insufficient or the question crosses an authorization boundary, return NEEDS_LEAD with the smallest missing observation or decision; do not guess.

Return a compact memo with exactly these sections:
Answer
Findings
Automation implications
Next smallest observation (or None)
Handback: READY_FOR_REVIEW, NEEDS_LEAD, BLOCKED, or FAILED
"""


def snapshot(repo: Path) -> dict[str, str]:
    """Capture the Git state needed to detect consultation edits."""
    return {
        "head": git(repo, "rev-parse", "HEAD"),
        "status": git(repo, "status", "--porcelain=v1", "-uall"),
    }


def parse_arguments() -> argparse.Namespace:
    """Parse the narrow consultation interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Exact Git repository root.")
    question = parser.add_mutually_exclusive_group(required=True)
    question.add_argument("--question", help="Focused game-knowledge question.")
    question.add_argument("--question-file", help="UTF-8 file containing the question.")
    parser.add_argument(
        "--run-dir",
        help="Evidence directory; defaults to .local-data/devin-game-knowledge.",
    )
    return parser.parse_args()


def main() -> int:
    """Run Devin and persist bounded transport and worktree evidence."""
    arguments = parse_arguments()
    repo = exact_repository(arguments.repo)
    question = question_text(arguments)
    before = snapshot(repo)
    now = datetime.now(UTC)
    digest = hashlib.sha256(question.encode("utf-8")).hexdigest()[:10]
    default_root = repo / ".local-data" / "devin-game-knowledge"
    run_root = Path(arguments.run_dir).resolve() if arguments.run_dir else default_root
    run_dir = run_root / f"{now:%Y%m%d-%H%M%S}-{slug(question)}-{digest}"
    run_dir.mkdir(parents=True, exist_ok=False)

    prompt_path = run_dir / "prompt.txt"
    response_path = run_dir / "response.txt"
    stderr_path = run_dir / "stderr.log"
    result_path = run_dir / "result.json"
    prompt_path.write_text(consultation_prompt(question), encoding="utf-8")

    command = [
        devin_executable(),
        "--print",
        "--model",
        MODEL,
        "--permission-mode",
        "auto",
        "--respect-workspace-trust",
        "false",
        "--prompt-file",
        str(prompt_path),
    ]
    completed = subprocess.run(
        command,
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    response_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    after = snapshot(repo)
    unchanged = before == after
    status = "completed" if completed.returncode == 0 and unchanged else "failed"
    if completed.returncode == 0 and not unchanged:
        status = "worktree-changed"
    result = {
        "status": status,
        "model": MODEL,
        "returncode": completed.returncode,
        "repo": str(repo),
        "prompt_path": str(prompt_path),
        "response_path": str(response_path),
        "stderr_path": str(stderr_path),
        "worktree_unchanged": unchanged,
        "before": before,
        "after": after,
    }
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "result_path": str(result_path)}))
    if completed.stdout:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print("\n--- Devin consultation ---\n")
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.returncode != 0:
        print(f"Devin exited with code {completed.returncode}; see {stderr_path}.", file=sys.stderr)
    if not unchanged:
        print(
            "The consultation changed the worktree; preserve and review the changes before any other writer starts.",
            file=sys.stderr,
        )
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
