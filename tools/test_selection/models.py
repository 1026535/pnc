"""Typed selection contracts shared by the runner and analysis tools."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath

POLICY_VERSION = 1
TIERS = ("unit", "contract", "integration", "architecture")


@dataclass(frozen=True)
class TestModule:
    path: str
    module: str
    tier: str
    component: str


def module_name(path: str) -> str:
    parts = list(PurePosixPath(path).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def inventory(paths: list[str]) -> tuple[TestModule, ...]:
    """Enumerate eligible modules without importing tests or running setup."""
    result = []
    for path in sorted(paths):
        parts = PurePosixPath(path).parts
        if (len(parts) >= 3 and parts[0] == "tests" and parts[1] in TIERS
                and parts[-1].startswith("test_") and path.endswith(".py")):
            result.append(TestModule(path, module_name(path), parts[1], ".".join(parts[2:-1])))
    return tuple(result)


@dataclass
class SelectionPlan:
    mode: str
    base: str
    head: str
    changed_paths: list[str] = field(default_factory=list)
    reasons: dict[str, list[str]] = field(default_factory=dict)
    fallbacks: list[str] = field(default_factory=list)
    policy_version: int = POLICY_VERSION
    source_fingerprint: str = ""
    inventory_modules: list[str] = field(default_factory=list)

    def add(self, module: str, reason: str) -> None:
        reasons = self.reasons.setdefault(module, [])
        if reason not in reasons:
            reasons.append(reason)

    def full(self, tests: tuple[TestModule, ...], reason: str) -> None:
        self.fallbacks.append(reason)
        for test in tests:
            self.add(test.module, reason)

    def document(self) -> dict:
        value = asdict(self)
        value["reasons"] = {key: sorted(val) for key, val in sorted(self.reasons.items())}
        if not self.reasons and not self.fallbacks:
            value["no_test_reason"] = "unchanged or explicitly documentation-only changes"
        return value
