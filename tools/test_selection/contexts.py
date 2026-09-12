"""Optional additive execution dependencies; invalid evidence always fails closed."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.test_selection.models import POLICY_VERSION, SelectionPlan, TestModule
from tools.test_selection.reporting import environment, write_json


def fingerprint(sources: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()


def seed_contexts(path: Path, coverage, root: Path, sources: dict[str, str], tests: tuple[TestModule, ...], head: str) -> None:
    """Unattributed imports/shared fixtures conservatively belong to every module."""
    known = {t.module for t in tests}
    data = coverage.get_data()
    owners = {}
    for filename in data.measured_files():
        try:
            relative = Path(filename).resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
        contexts = {context for values in data.contexts_by_lineno(filename).values() for context in values}
        modules = {context.rsplit(".", 2)[0] for context in contexts if context}
        owners[relative] = sorted(known if "" in contexts else modules & known)
    write_json(path, {"version": POLICY_VERSION, "head": head, "fingerprint": fingerprint(sources),
                      "environment": environment(), "inventory": sorted(known), "owners": owners})


def add_contexts(plan: SelectionPlan, path: Path, old: dict[str, str], tests: tuple[TestModule, ...]) -> None:
    """Only a complete seed matching the requested base can augment a plan."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        known = {t.module for t in tests}
        if (set(document) != {"version", "head", "fingerprint", "environment", "inventory", "owners"}
                or document["version"] != POLICY_VERSION or document["head"] != plan.base
                or document["fingerprint"] != fingerprint(old)
                or document["environment"] != environment()
                or document["inventory"] != sorted(known)
                or not isinstance(document["owners"], dict)):
            raise ValueError("incompatible context seed")
        for source, modules in document["owners"].items():
            if not isinstance(source, str) or not isinstance(modules, list) or any(m not in known for m in modules):
                raise ValueError("malformed context ownership")
        for source in plan.changed_paths:
            for module in document["owners"].get(source, []):
                plan.add(module, f"observed execution dependency: {source}")
    except (OSError, ValueError, TypeError, KeyError):
        plan.full(tests, "missing, corrupt, or incompatible coverage context seed")
