"""Builds the client window/scene navigation graph from recovered PNC gameplay Lua.

The recovered Lua tree is ignored local evidence. See ``docs/game-reference/PROVENANCE.md``
for how to reproduce it and ``docs/game-reference/navigation-graph.md`` for how to read the
output. This tool is a pure text analysis: it never touches ADB, the emulator, or config.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_SOURCE = Path(".local-data/apk-exploration/gameplay-lua")
DEFAULT_OUTPUT = Path(".local-data/apk-exploration/navigation-graph.json")
_REGISTRY_MODULE = "uis/winsprefabtype.lua"

_PREFAB_PATTERN = re.compile(r"^\s*WinsPreFabType\.(\w+)\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
_SCENE_PATTERN = re.compile(r"^\s*SceneName\.(\w+)\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
_FUNCTION_PATTERN = re.compile(r"^\s*(?:local\s+)?function\s+([\w.:]+)")
_WINDOW_CALL_PATTERN = re.compile(
    r"\b(OpenWin|RealyOpenWin|ShowWin|CloseWin|RealyCloseWin|HideWin)"
    r"\s*\(\s*WinsPreFabType\.(\w+)"
)
_LAYER_PATTERN = re.compile(r"LayerManager\.instance\.([A-Z_]+)")
_SCENE_CALL_PATTERN = re.compile(r"\bLoadLevel\s*\(\s*SceneName\.(\w+)")
_UNTYPED_OPEN_PATTERN = re.compile(r"\bOpenWin\s*\(\s*(?!WinsPreFabType\.)")

_TRAVERSAL_KINDS = frozenset({"OpenWin", "RealyOpenWin", "ShowWin"})
_DISMISSAL_KINDS = frozenset({"CloseWin", "RealyCloseWin", "HideWin"})


@dataclass(frozen=True, slots=True)
class Window:
    """One registered client window and the Lua module that implements it, when known."""

    name: str
    prefab: str
    module: str | None
    group: str | None
    declared_in: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WindowEdge:
    """One statically resolved window transition expressed by a single call site."""

    source_module: str
    source_group: str
    source_windows: tuple[str, ...]
    function: str | None
    line: int
    kind: str
    target: str
    layer: str | None


@dataclass(frozen=True, slots=True)
class SceneEdge:
    """One statically resolved scene load expressed by a single call site."""

    source_module: str
    source_group: str
    function: str | None
    line: int
    target: str


@dataclass(frozen=True, slots=True)
class Coverage:
    """Counts that bound how much of the client graph this extraction actually resolved."""

    lua_files: int
    registered_windows: int
    windows_with_module: int
    window_edges: int
    scene_edges: int
    unregistered_targets: int
    untyped_open_calls: int
    modules_emitting_edges: int


def main() -> int:
    """Parses arguments, extracts the graph, and writes one JSON document."""

    parser = argparse.ArgumentParser(description="Build the PNC client navigation graph from recovered Lua.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Recovered gameplay Lua root.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="JSON graph destination.")
    arguments = parser.parse_args()

    source = arguments.source.resolve()
    if not (source / _REGISTRY_MODULE).is_file():
        parser.error(f"{source} does not look like a recovered gameplay Lua root.")

    document = build_graph_document(source)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(document, indent=2, sort_keys=False), encoding="utf-8")

    coverage = document["coverage"]
    print(f"windows={coverage['registered_windows']} (module-backed {coverage['windows_with_module']})")
    print(f"window_edges={coverage['window_edges']} scene_edges={coverage['scene_edges']}")
    print(f"targets referenced but never registered={coverage['unregistered_targets']}")
    print(f"unresolvable OpenWin call sites={coverage['untyped_open_calls']}")
    print(f"wrote {arguments.output}")
    return 0


def build_graph_document(source: Path) -> dict[str, object]:
    """Returns the serializable navigation graph extracted from the recovered Lua root."""

    modules = sorted(path.relative_to(source).as_posix() for path in source.rglob("*.lua"))
    windows = _resolve_windows(source, modules)
    scenes = dict(_SCENE_PATTERN.findall(_read(source / "scenename.lua")))
    module_windows = _index_modules_to_windows(windows)

    window_edges: list[WindowEdge] = []
    scene_edges: list[SceneEdge] = []
    untyped = 0
    for module in modules:
        text = _read(source / module)
        untyped += len(_UNTYPED_OPEN_PATTERN.findall(text))
        group = _group_of(module)
        owners = tuple(module_windows.get(module, ()))
        for function, line_number, line in _annotated_lines(text):
            for kind, target in _WINDOW_CALL_PATTERN.findall(line):
                layer_match = _LAYER_PATTERN.search(line)
                window_edges.append(
                    WindowEdge(
                        source_module=module,
                        source_group=group,
                        source_windows=owners,
                        function=function,
                        line=line_number,
                        kind=kind,
                        target=target,
                        layer=layer_match.group(1) if layer_match else None,
                    )
                )
            for target in _SCENE_CALL_PATTERN.findall(line):
                scene_edges.append(
                    SceneEdge(
                        source_module=module,
                        source_group=group,
                        function=function,
                        line=line_number,
                        target=target,
                    )
                )

    coverage = Coverage(
        lua_files=len(modules),
        registered_windows=len(windows),
        windows_with_module=sum(1 for window in windows.values() if window.module is not None),
        window_edges=len(window_edges),
        scene_edges=len(scene_edges),
        untyped_open_calls=untyped,
        modules_emitting_edges=len({edge.source_module for edge in window_edges}),
        unregistered_targets=len({edge.target for edge in window_edges} - set(windows)),
    )
    return {
        "source_root": source.as_posix(),
        "coverage": asdict(coverage),
        "scenes": scenes,
        "windows": [asdict(window) for window in windows.values()],
        "window_edges": [asdict(edge) for edge in window_edges],
        "scene_edges": [asdict(edge) for edge in scene_edges],
        "group_graph": _build_group_graph(window_edges, windows),
    }


def _resolve_windows(source: Path, modules: Iterable[str]) -> dict[str, Window]:
    """Maps each registered window to the Lua module named after its prefab, when one exists.

    A handful of names are rebound outside the registry file, so every module is scanned and
    each declaring module is recorded rather than assuming a single binding.
    """

    by_stem: dict[str, list[str]] = defaultdict(list)
    for module in modules:
        by_stem[module.rsplit("/", 1)[-1].removesuffix(".lua").lower()].append(module)

    # The registry file is scanned first so a conditional rebinding elsewhere never displaces
    # the canonical prefab, only appends to ``declared_in``.
    ordered = sorted(modules, key=lambda module: module != _REGISTRY_MODULE)
    declarations: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for module in ordered:
        for name, prefab in _PREFAB_PATTERN.findall(_read(source / module)):
            declarations[name].append((prefab, module))

    windows: dict[str, Window] = {}
    for name, bindings in declarations.items():
        prefab, _ = bindings[0]
        stem = prefab.rsplit("/", 1)[-1].removesuffix(".prefab").lower()
        candidates = by_stem.get(stem, [])
        module = candidates[0] if len(candidates) == 1 else None
        windows[name] = Window(
            name=name,
            prefab=prefab,
            module=module,
            group=_group_of(module) if module else None,
            declared_in=tuple(dict.fromkeys(declaring for _, declaring in bindings)),
        )
    return windows


def _index_modules_to_windows(windows: dict[str, Window]) -> dict[str, list[str]]:
    """Returns the reverse index from Lua module to every window it backs."""

    index: dict[str, list[str]] = defaultdict(list)
    for window in windows.values():
        if window.module is not None:
            index[window.module].append(window.name)
    return index


def _build_group_graph(edges: Iterable[WindowEdge], windows: dict[str, Window]) -> dict[str, dict[str, list[str]]]:
    """Aggregates call sites into a module-group graph with opened and closed targets."""

    opened: dict[str, Counter[str]] = defaultdict(Counter)
    closed: dict[str, Counter[str]] = defaultdict(Counter)
    for edge in edges:
        target_group = windows[edge.target].group if edge.target in windows else None
        if target_group is None or target_group == edge.source_group:
            continue
        if edge.kind in _TRAVERSAL_KINDS:
            opened[edge.source_group][target_group] += 1
        elif edge.kind in _DISMISSAL_KINDS:
            closed[edge.source_group][target_group] += 1

    groups = sorted(set(opened) | set(closed))
    return {
        group: {
            "opens": sorted(opened[group], key=lambda name: (-opened[group][name], name)),
            "closes": sorted(closed[group], key=lambda name: (-closed[group][name], name)),
        }
        for group in groups
    }


def _annotated_lines(text: str) -> Iterator[tuple[str | None, int, str]]:
    """Yields each line with the enclosing Lua function name and one-based line number."""

    current: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        match = _FUNCTION_PATTERN.match(line)
        if match:
            current = match.group(1)
        yield current, number, line


def _group_of(module: str) -> str:
    """Returns the coarse navigation group for a module path, such as ``uis/mail``."""

    parts = module.split("/")
    return "/".join(parts[:2]) if len(parts) > 1 else parts[0]


def _read(path: Path) -> str:
    """Reads recovered Lua, tolerating the encoding noise present in extracted assets."""

    return path.read_text(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
