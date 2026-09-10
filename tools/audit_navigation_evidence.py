"""Index navigation contracts and saved evidence without treating OCR labels as truth."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path

import yaml

try:
    from _script_bootstrap import ensure_repo_root_on_path
except ModuleNotFoundError:
    from tools._script_bootstrap import ensure_repo_root_on_path

ROOT = ensure_repo_root_on_path()

from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    home_city_map_atlas,
    home_city_object_definition,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.selector_catalog import (
    default_selector_catalog_path,
    load_selector_catalog_document,
)
from pnc_automation.app.pnc.vision.pnc_ocr_capabilities import runtime_screen_family_ocr_types
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry


def canonical_screen(value: str) -> str:
    """Resolve the enum's documented name/value representations, including aliases."""
    if value in ScreenType.__members__:
        return ScreenType[value].name
    return ScreenType(value).name


def build_audit(root: Path, output: Path) -> dict[str, object]:
    """Inventory every evidence file and retain provenance for each modeled screen."""
    catalog = load_selector_catalog_document(default_selector_catalog_path())
    screens = {
        screen.name: {
            "selectors": [], "recorded_frames": [], "discovery_frames": [],
            "visual_profiles": [], "incoming_contracts": [], "outgoing_contracts": [],
            "has_ocr_family": screen in runtime_screen_family_ocr_types(),
        }
        for screen in ScreenType
    }
    edges = []
    for selector in catalog.selectors:
        for source in selector.screens:
            source = canonical_screen(source)
            screens[source]["selectors"].append({
                "id": selector.id, "detection": selector.detection_kind,
                "interaction": selector.interaction_kind, "status": selector.status,
                "has_geometry": selector.relative_bounds is not None,
                "materializes_geometry": selector.materialize_relative_bounds,
            })
            if selector.click is None:
                continue
            for outcome in selector.click.outcomes:
                if outcome.target_screen is None:
                    continue
                target = canonical_screen(outcome.target_screen)
                edge = {
                    "source": source, "selector": selector.id, "target": target,
                    "safe_to_click": outcome.safe_to_click, "monetized": outcome.monetized,
                    "verification_selectors": outcome.verification_selectors,
                }
                edges.append(edge)
                screens[source]["outgoing_contracts"].append(len(edges) - 1)
                screens[target]["incoming_contracts"].append(len(edges) - 1)

    profiles = json.loads((root / "pnc_automation/app/pnc/vision/data/screen_anchors.json").read_text())
    for profile in profiles["profiles"]:
        screens[canonical_screen(profile["screen"])]["visual_profiles"].append(profile["id"])

    inventory = []
    validations = []
    transitions = []
    errors = []
    extensions = Counter()
    roots = ("artifacts", "archives", "selector_discovery_output", "navigation_selector_validation_output", "reviewed_plans", "tests/data")
    for directory in roots:
        for path in sorted((root / directory).rglob("*")):
            if not path.is_file() or path.resolve().is_relative_to(output.resolve()):
                continue
            relative = path.relative_to(root).as_posix()
            inventory.append({"path": relative, "bytes": path.stat().st_size})
            extensions[path.suffix] += 1
            try:
                if path.name.endswith("_ocr.json"):
                    document = json.loads(path.read_text(encoding="utf-8"))
                    screen = canonical_screen(document["screen_type"])
                    # Persist paths and labels only, never captured player/account text.
                    screens[screen]["recorded_frames"].append(relative)
                elif path.name == "trace.jsonl":
                    pending = None
                    for line in path.read_text(encoding="utf-8").splitlines():
                        entry = json.loads(line)
                        if entry.get("event") in {"pending_action", "pending_actions"}:
                            pending = entry
                        elif entry.get("event") in {"completed_action", "completed_actions"} and pending is not None:
                            transitions.append({
                                "trace": relative,
                                "source": canonical_screen(pending["before"]["screen"]),
                                "destination": canonical_screen(entry["after"]["screen"]),
                                "before_artifact": pending["before"]["artifact"],
                                "after_artifact": entry["after"]["artifact"],
                            })
                            pending = None
                        elif entry.get("event") == "failure":
                            pending = None
                elif path.name.endswith("_report.yaml") or path.name.endswith("_validation.yaml") or path.parent.name == "navigation":
                    if path.suffix != ".yaml":
                        continue
                    document = yaml.safe_load(path.read_text(encoding="utf-8"))
                    if not isinstance(document, dict):
                        raise ValueError("Evidence report must be a mapping")
                    if "snapshots" in document:
                        for snapshot in document["snapshots"]:
                            screen = canonical_screen(snapshot["screen_type"])
                            screens[screen]["discovery_frames"].append({
                                "report": relative, "artifact": snapshot["artifact_path"],
                                "artifact_exists": Path(snapshot["artifact_path"]).is_file(),
                                "visible_selectors": snapshot["visible_selector_ids"],
                            })
                    if "results" in document:
                        for result in document["results"]:
                            validations.append({
                                "report": relative,
                                "selector": result["selector_id"],
                                "source": canonical_screen(result["source_screen"]),
                                "status": result["status"],
                                "destination": result.get("destination_screen"),
                                "source_artifact": result.get("source_artifact_path"),
                                "destination_artifact": result.get("destination_artifact_path"),
                                "destination_artifact_exists": (
                                    result.get("destination_artifact_path") is not None
                                    and Path(result["destination_artifact_path"]).is_file()
                                ),
                            })
            except (ValueError, KeyError, TypeError, yaml.YAMLError) as error:
                errors.append({"path": relative, "error_type": type(error).__name__})

    city = [asdict(home_city_object_definition(item)) for item in HomeCityObjectId]
    missing_templates = [
        {"selector": selector.id.value, "path": str(selector.template_path)}
        for selector in build_default_selector_registry().all()
        if selector.template_path is not None and not selector.template_path.is_file()
    ]
    result = {
        "schema_version": 1,
        "interpretation": "Recorded classifications are historical predictions, not reviewed truth. Contracts are authored expectations, not observed transitions. File inventory is not visual review. No adjacency is inferred from neighboring filenames.",
        "file_count": len(inventory), "extensions": dict(extensions),
        "screens": screens, "contracts": edges, "validation_results": validations,
        "observed_transitions": transitions,
        "city_atlas": asdict(home_city_map_atlas()), "city_objects": city,
        "surfaces": [surface.to_document() for surface in catalog.surfaces],
        "missing_selector_templates": missing_templates,
        "parse_errors": errors,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    (output / "coverage.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = ["# Navigation evidence coverage", "", result["interpretation"], "",
             "| Screen | Selectors | Recorded OCR frames | Discovery frames | Visual profiles | Outgoing contracts |",
             "|---|---:|---:|---:|---:|---:|"]
    for screen, evidence in screens.items():
        values = [len(evidence[key]) for key in ("selectors", "recorded_frames", "discovery_frames", "visual_profiles", "outgoing_contracts")]
        lines.append(f"| {screen} | " + " | ".join(map(str, values)) + " |")
    lines.extend(["", "## Authored transitions", "", "```mermaid", "flowchart LR"])
    for edge in edges:
        lines.append(f'  {edge["source"]} -->|{edge["selector"]}| {edge["target"]}')
    lines.append("```")
    (output / "coverage.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def main() -> int:
    """Write a reproducible coverage index; malformed evidence yields a failing exit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/navigation_audit/index")
    arguments = parser.parse_args()
    result = build_audit(ROOT, arguments.output_dir)
    print(json.dumps({key: result[key] for key in ("file_count", "extensions", "parse_errors")}, indent=2))
    return int(bool(result["parse_errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
