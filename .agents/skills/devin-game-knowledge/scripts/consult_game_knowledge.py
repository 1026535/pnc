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

# A completed consultation must end with the memo's Handback line; a clean
# exit code alone cannot prove Devin returned it (a headless tool rejection
# exits 0 with a truncated response).
# The memo may style the label (`**Handback**`) and put the token on the next
# line, so match the label then the nearest token rather than one strict line.
HANDBACK_RE = re.compile(
    r"(?is)handback\b[\s*:`#-]*\*{0,2}\s*(READY_FOR_REVIEW|NEEDS_LEAD|BLOCKED|FAILED)\b"
)
TOOL_REJECTION_MARKER = "rejected a tool call that requires confirmation"

# Permission rules for the run-scoped --config file. The launcher keeps
# --permission-mode auto (read-only tools auto-approve); these rules widen
# only the read/inspection surface a consultant legitimately needs so a
# headless run never stalls on a confirmation prompt. Deny rules always win
# over allows, keeping the obvious mutation paths closed.
CONSULTANT_ALLOW_RULES = (
    "Read(**)",
    # Read-only Git plumbing only; every mutating subcommand is denied below.
    "Exec(git status)",
    "Exec(git log)",
    "Exec(git show)",
    "Exec(git diff)",
    "Exec(git grep)",
    "Exec(git blame)",
    "Exec(git ls-files)",
    "Exec(git ls-tree)",
    "Exec(git cat-file)",
    "Exec(git rev-parse)",
    "Exec(git shortlog)",
    "Exec(git describe)",
    "Exec(git count-objects)",
    # Read-only shell inspection and evidence analysis.
    "Exec(rg)",
    "Exec(grep)",
    "Exec(find)",
    "Exec(ls)",
    "Exec(cat)",
    "Exec(head)",
    "Exec(tail)",
    "Exec(wc)",
    "Exec(sort)",
    "Exec(uniq)",
    "Exec(file)",
    "Exec(stat)",
    "Exec(dir)",
    "Exec(type)",
    "Exec(where)",
    "Exec(echo)",
    "Exec(python)",
    "Exec(py)",
)

CONSULTANT_DENY_RULES = (
    # Mutating Git state must stay unreachable for a read-only consultation.
    "Exec(git add)",
    "Exec(git am)",
    "Exec(git apply)",
    "Exec(git bisect)",
    "Exec(git branch)",
    "Exec(git checkout)",
    "Exec(git cherry-pick)",
    "Exec(git clean)",
    "Exec(git clone)",
    "Exec(git commit)",
    "Exec(git config)",
    "Exec(git fetch)",
    "Exec(git init)",
    "Exec(git merge)",
    "Exec(git mv)",
    "Exec(git pull)",
    "Exec(git push)",
    "Exec(git rebase)",
    "Exec(git remote)",
    "Exec(git reset)",
    "Exec(git restore)",
    "Exec(git revert)",
    "Exec(git rm)",
    "Exec(git stash)",
    "Exec(git submodule)",
    "Exec(git switch)",
    "Exec(git tag)",
    "Exec(git update-ref)",
    "Exec(git worktree)",
    # Destructive/writing shell verbs and live/install paths the contract bans.
    "Exec(rm)",
    "Exec(del)",
    "Exec(rmdir)",
    "Exec(rd)",
    "Exec(move)",
    "Exec(ren)",
    "Exec(copy)",
    "Exec(xcopy)",
    "Exec(mkdir)",
    "Exec(md)",
    "Exec(touch)",
    "Exec(tee)",
    "Exec(sed)",
    "Exec(pip)",
    "Exec(npm)",
    "Exec(adb)",
)


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
- Distinguish findings as user-confirmed, repository-proven, artifact-observed, live-observed, inferred, or unknown, each with high, medium, or low confidence.
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


def consultant_config() -> dict:
    """Build the run-scoped Devin config holding the read-only allow rules.

    The consultation stays in ``auto`` permission mode; the allow list only
    widens read/inspection commands so headless execution never waits on a
    confirmation prompt, and the deny list keeps mutation verbs closed.
    """
    return {
        "auto_update": False,
        "notify": "never",
        "theme_mode": "nocolor",
        "subagents_enabled": False,
        "read_config_from": {"claude": False, "cursor": False, "windsurf": False},
        "permissions": {
            "allow": list(CONSULTANT_ALLOW_RULES),
            "deny": list(CONSULTANT_DENY_RULES),
        },
    }


def consultation_status(
    returncode: int,
    unchanged: bool,
    response_text: str,
    stderr_text: str,
) -> tuple[str, str | None, bool]:
    """Classify the run as (status, handback, tool_rejection_seen).

    ``completed`` requires a clean exit, an unchanged worktree, and the memo's
    ``Handback:`` line — a zero exit without a returned memo, including an
    observed headless tool rejection, is ``incomplete``, not a consultation.
    """

    handback_match = HANDBACK_RE.search(response_text)
    handback = handback_match.group(1).upper() if handback_match else None
    rejected = TOOL_REJECTION_MARKER in stderr_text
    if returncode != 0:
        return "failed", handback, rejected
    if not unchanged:
        return "worktree-changed", handback, rejected
    if handback is None:
        return "incomplete", handback, rejected
    return "completed", handback, rejected


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
    config_path = run_dir / "devin-config.json"
    export_path = run_dir / "export.json"
    result_path = run_dir / "result.json"
    prompt_path.write_text(consultation_prompt(question), encoding="utf-8")
    config_path.write_text(json.dumps(consultant_config(), indent=2) + "\n", encoding="utf-8")

    command = [
        devin_executable(),
        "--config",
        str(config_path),
        "--print",
        "--model",
        MODEL,
        "--permission-mode",
        "auto",
        "--respect-workspace-trust",
        "false",
        "--prompt-file",
        str(prompt_path),
        "--export",
        str(export_path),
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
    status, handback, tool_rejection = consultation_status(
        completed.returncode, unchanged, completed.stdout, completed.stderr
    )
    result = {
        "status": status,
        "model": MODEL,
        "returncode": completed.returncode,
        "handback": handback,
        "tool_rejection": tool_rejection,
        "repo": str(repo),
        "prompt_path": str(prompt_path),
        "response_path": str(response_path),
        "stderr_path": str(stderr_path),
        "config_path": str(config_path),
        "export_path": str(export_path),
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
    if status == "incomplete":
        reason = "a headless tool rejection" if tool_rejection else "no Handback memo line"
        print(
            f"The consultation ended without a final memo ({reason}); "
            f"see {response_path} and {export_path}.",
            file=sys.stderr,
        )
    elif tool_rejection:
        print(
            f"Devin returned a memo but a tool call was rejected mid-run; "
            f"review {stderr_path} for what evidence may be missing.",
            file=sys.stderr,
        )
    if not unchanged:
        print(
            "The consultation changed the worktree; preserve and review the changes before any other writer starts.",
            file=sys.stderr,
        )
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
