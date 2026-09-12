"""Validated explicit dependencies for resources and shared contracts."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

import yaml

from tools.test_selection.models import TestModule


@dataclass(frozen=True)
class ResourceRule:
    pattern: str
    groups: tuple[str, ...]


@dataclass(frozen=True)
class OwnershipRules:
    full: tuple[str, ...]
    documentation: tuple[str, ...]
    resources: tuple[ResourceRule, ...]

    def resource_groups(self, path: str) -> tuple[str, ...]:
        # Rules are additive. Multiple matches cannot exclude another owner's tests.
        return tuple(sorted({g for rule in self.resources if fnmatchcase(path, rule.pattern) for g in rule.groups}))


def group_matches(test: TestModule, group: str) -> bool:
    """Match exact package segments; API includes both facade and runner contracts."""
    if not group:
        return False
    if group == "api":
        return (test.tier in {"contract", "integration"} and "entrypoints" in test.component.split(".")) or "public_exports" in test.component.split(".")
    if group == "vision":
        return "vision" in test.component.split(".")
    qualified = f"{test.tier}.{test.component}".rstrip(".")
    return qualified == group or qualified.startswith(group + ".") or test.component == group or test.component.startswith(group + ".")


def _strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise ValueError(f"{name} must be a list of nonempty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"Duplicate values in {name}")
    return tuple(value)


def load_rules(path: Path, tests: tuple[TestModule, ...]) -> OwnershipRules:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or set(document) != {"version", "full", "documentation", "resources"}:
        raise ValueError("Selection rules require exactly version, full, documentation, resources")
    if type(document["version"]) is not int or document["version"] != 1:
        raise ValueError("Unsupported selection rule version")
    full = _strings(document["full"], "full")
    docs = _strings(document["documentation"], "documentation")
    if not isinstance(document["resources"], list):
        raise ValueError("resources must be a list")
    resources = []
    patterns = set()
    for rule in document["resources"]:
        if not isinstance(rule, dict) or set(rule) != {"pattern", "groups"}:
            raise ValueError("Resource rules require exactly pattern and groups")
        pattern = rule["pattern"]
        if not isinstance(pattern, str) or not pattern.strip() or pattern in patterns:
            raise ValueError("Resource patterns must be nonempty and unique")
        groups = _strings(rule["groups"], pattern)
        if not groups:
            raise ValueError(f"Resource rule {pattern} has no owners")
        for group in groups:
            if not any(group_matches(test, group) for test in tests):
                raise ValueError(f"Unknown or empty test group {group}")
        patterns.add(pattern)
        resources.append(ResourceRule(pattern, groups))
    return OwnershipRules(full, docs, tuple(resources))
