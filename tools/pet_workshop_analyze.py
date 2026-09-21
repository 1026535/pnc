"""Saved-screenshot Pet Workshop analysis (PW05).

Replays saved captures through the canonical production observation
pipeline — the same selector registry, visual recognizer, OCR context and
Workshop content producer the live observer uses — then runs the accepted
``plan_next`` planner over the published Workshop state. For every input it
writes one machine-readable JSON report and one annotated review image
under the ignored output directory.

The tool performs no I/O beyond reading the named images and writing its
own reports: no emulator, ADB, lease or live game state is touched. Native
RGBA captures stay native; labels record whether an input is a real
screenshot or a synthesized frame, and black, unknown or unreadable frames
never produce a gameplay proposal.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from PIL import Image, ImageDraw, UnidentifiedImageError

try:
    from _script_bootstrap import ensure_repo_root_on_path
except ModuleNotFoundError:
    from tools._script_bootstrap import ensure_repo_root_on_path

ROOT = ensure_repo_root_on_path()

from pnc_automation.app.automation.pet_workshop.planner import plan_next
from pnc_automation.app.automation.pet_workshop.policy import assess_order, default_policy
from pnc_automation.app.pnc.domain.observation import Bounds, Observation
from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopDecision,
    WorkshopIntent,
    WorkshopIntentKind,
    WorkshopOrder,
    WorkshopState,
    WorkshopView,
)
from pnc_automation.app.pnc.pet_workshop_catalog import PetWorkshopCatalog, load_pet_workshop_catalog
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import (
    ImageSelectorEngine,
    ObservationBuilder,
)
from pnc_automation.app.pnc.vision.pet_workshop import WorkshopContentProducer
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot, FrameRef
from pnc_automation.core.vision.ocr.ocr_service import OcrService, RapidOcrService
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

FIXTURES_DIR = ROOT / "tests" / "data" / "screen_recognition"
DEFAULT_LABELS = ROOT / "tests" / "data" / "pet_workshop" / "analysis_labels.json"
DEFAULT_OUT_DIR = ROOT / ".local-data" / "pet-workshop-analysis"
REPORT_SCHEMA = "pet_workshop_analysis/v1"
LABELS_SCHEMA = "pet_workshop_analysis_labels/v1"

#: Intent kinds that would mutate board or order state if executed.
_GAMEPLAY_INTENTS = frozenset(
    {
        WorkshopIntentKind.SELECT,
        WorkshopIntentKind.PRODUCE,
        WorkshopIntentKind.MERGE,
        WorkshopIntentKind.ACTIVATE,
        WorkshopIntentKind.FEED,
        WorkshopIntentKind.RECYCLE,
        WorkshopIntentKind.SUBMIT_ORDER,
    }
)

#: List element fields the label comparator may use as an index key.
_INDEX_KEYS = ("order_ref", "cell_id")


class AnalysisError(ValueError):
    """Raised for inputs that cannot be analyzed, with an actionable message."""


@dataclass(frozen=True, slots=True)
class AnalysisInput:
    """One named input image plus its authored provenance kind."""

    path: Path
    source_kind: str = "unknown"


@dataclass(frozen=True, slots=True)
class Perception:
    """The production observation pipeline used for saved-frame analysis."""

    perception: NavigationPerception
    builder: ObservationBuilder


def build_perception(ocr_service: OcrService | None = None) -> Perception:
    """Wires the canonical production publishers exactly as the live observer does."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    enricher = PncObservationEnricher(
        selector_registry=registry,
        workshop_producer=WorkshopContentProducer(matcher=matcher),
    )
    builder = ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=enricher,
        ocr_service=ocr_service if ocr_service is not None else RapidOcrService(),
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
    )
    perception = NavigationPerception(
        builder.visual_recognizer,
        enricher,
        ScreenClassifier(),
        builder.create_ocr_context,
    )
    return Perception(perception=perception, builder=builder)


def _load_image(path: Path) -> Image.Image:
    """Decodes one input, preserving its native pixel layout (RGBA stays RGBA)."""

    if not path.is_file():
        raise AnalysisError(f"input image not found: {path}")
    try:
        with Image.open(path) as source:
            return source.copy()
    except (UnidentifiedImageError, OSError) as error:
        raise AnalysisError(f"input is not a readable image file: {path} ({error})") from error


def _capture(image: Image.Image) -> CapturedScreenshot:
    """Builds one offline capture with explicit frame provenance."""

    captured_at = datetime.now(UTC)
    return CapturedScreenshot(
        None,
        image,
        "PNG",
        frame_ref=FrameRef(
            session_id="pw05-analysis",
            session_epoch=1,
            capture_sequence=1,
            input_sequence=0,
            captured_at=captured_at,
        ),
        ephemeral_captured_at=captured_at,
    )


def _decoded_image_sha256(image: Image.Image) -> str:
    """Manifest-compatible content hash: ``width‖height‖RGB`` (see benchmark tool)."""

    digest = hashlib.sha256()
    digest.update(image.width.to_bytes(8, "big"))
    digest.update(image.height.to_bytes(8, "big"))
    digest.update(image.convert("RGB").tobytes())
    return digest.hexdigest()


def _bounds_json(bounds: Bounds | None) -> list[int] | None:
    return (
        None
        if bounds is None
        else [bounds.x, bounds.y, bounds.width, bounds.height]
    )


def _order_json(order: WorkshopOrder, catalog: PetWorkshopCatalog, policy) -> dict[str, Any]:
    assessment = assess_order(order, order.order_ref, catalog, policy)
    return {
        "order_ref": order.order_ref,
        "requirements": {str(k): v for k, v in order.requirements.items()},
        "rewards": [
            {
                "category": reward.category.value,
                "quantity": reward.quantity,
                "label": reward.label,
            }
            for reward in order.rewards
        ],
        "completeness": order.completeness.value,
        "ready": order.ready,
        "source": order.source,
        "assessment": {
            "eligible": assessment.eligible,
            "ineligible_reason": assessment.ineligible_reason,
            "category": None if assessment.category is None else assessment.category.value,
            "category_rank": assessment.category_rank,
            "primary_quantity": assessment.primary_quantity,
            "secondary_quantities": list(assessment.secondary_quantities),
            "unresolved": assessment.unresolved,
            "unknown_reward": assessment.unknown_reward,
            "ranking_blocked": assessment.ranking_blocked,
        },
    }


def _state_json(state: WorkshopState) -> dict[str, Any]:
    return {
        "surface": state.surface.value,
        "board": {"rows": state.board.rows, "columns": state.board.columns},
        "workshop_level": state.workshop_level,
        "workshop_exp": state.workshop_exp,
        "energy": {"current": state.energy.current, "capacity": state.energy.capacity},
        "production_mode": state.production_mode.value,
        "selection": {"kind": state.selection.kind.value, "cell_id": state.selection.cell_id},
        "cells": [
            {
                "cell_id": cell.cell_id,
                "row": cell.row,
                "column": cell.column,
                "access": cell.access.value,
                "occupancy": cell.occupancy.value,
                "item_id": cell.item_id,
                "item_status": None if cell.item_status is None else cell.item_status.value,
                "cooldown": cell.cooldown.value,
            }
            for cell in state.cells
        ],
        "order_survey": {
            "coverage": state.order_survey.coverage.value,
            "freshness": state.order_survey.freshness.value,
        },
    }


def _view_json(view: WorkshopView) -> dict[str, Any]:
    controls = {
        "order_strip_bounds": _bounds_json(view.order_strip_bounds),
        "detail_control_bounds": _bounds_json(view.detail_control_bounds),
        "close_control_bounds": _bounds_json(view.close_control_bounds),
        "recycle_control_bounds": _bounds_json(view.recycle_control_bounds),
        "confirm_control_bounds": _bounds_json(view.confirm_control_bounds),
    }
    return {
        "image_size": list(view.image_size),
        "source_screen": view.source_screen.value,
        "source_layout_id": view.source_layout_id,
        "cell_bounds": {str(k): _bounds_json(v) for k, v in view.cell_bounds.items()},
        "order_views": [
            {
                "order_ref": order_view.order_ref,
                "portrait_bounds": _bounds_json(order_view.portrait_bounds),
                "submit_bounds": _bounds_json(order_view.submit_bounds),
            }
            for order_view in view.order_views
        ],
        **controls,
    }


def _intent_json(intent: WorkshopIntent) -> dict[str, Any]:
    data: dict[str, Any] = {"kind": intent.kind.value, "gameplay": intent.kind in _GAMEPLAY_INTENTS}
    for field_name in (
        "cell_id",
        "source_cell_id",
        "target_cell_id",
        "producer_cell_id",
        "food_cell_id",
        "order_ref",
        "item_id",
        "producer_item_id",
        "food_item_id",
        "max_wait_ms",
    ):
        if hasattr(intent, field_name):
            value = getattr(intent, field_name)
            if value is not None:
                data[field_name] = value
    need = getattr(intent, "need", None)
    if need is not None:
        data["inspect_kind"] = need.value
    reason = getattr(intent, "reason", None)
    if reason is not None and hasattr(reason, "value"):
        data["stop_reason"] = reason.value
    return data


def _decision_json(decision: WorkshopDecision | None) -> dict[str, Any] | None:
    if decision is None:
        return None
    return {
        "intent": _intent_json(decision.intent),
        "reason": decision.reason,
        "goal_order_ref": decision.goal_order_ref,
        "missing_quantities": {str(k): v for k, v in decision.missing_quantities.items()},
        "protected_quantities": {str(k): v for k, v in decision.protected_quantities.items()},
    }


def _git_revision() -> dict[str, Any]:
    """Binds the report to the checked-out candidate; ``unknown`` outside a checkout."""

    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
        dirty = (
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=no"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            ).stdout.strip()
            != ""
        )
        return {"commit": head, "tracked_tree_dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"commit": "unknown", "tracked_tree_dirty": None}


def analyze(
    observation: Observation,
    *,
    image: Image.Image,
    input_path: str,
    source_kind: str,
    catalog: PetWorkshopCatalog,
    policy=None,
    include_git: bool = True,
) -> dict[str, Any]:
    """Builds the machine-readable report from one published observation."""

    policy = default_policy() if policy is None else policy
    workshop = observation.workshop
    state = workshop.state if workshop is not None else None
    view = workshop.view if workshop is not None else None
    decision = (
        plan_next(state, catalog, policy)
        if state is not None
        else None
    )
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "input": {
            "path": input_path,
            "source_kind": source_kind,
            "size": list(image.size),
            "mode": image.mode,
            "decoded_sha256": _decoded_image_sha256(image),
        },
        "screen": {
            "screen_type": observation.decision.effective_screen.value,
            "base_screen": observation.decision.base_screen.value,
            "layout_id": observation.decision.layout_id,
            "guard": observation.decision.guard.value,
            "blocking_popup": observation.popup_overlay is not None,
        },
        "workshop": None if state is None else _state_json(state),
        "orders": (
            []
            if state is None
            else [
                _order_json(order, catalog, policy)
                for order in state.order_survey.orders
            ]
        ),
        "view": None if view is None else _view_json(view),
        "decision": _decision_json(decision),
    }
    if include_git:
        report["candidate"] = _git_revision()
    return report


def analyze_image(
    perception: NavigationPerception,
    image: Image.Image,
    *,
    input_path: str,
    source_kind: str,
    catalog: PetWorkshopCatalog,
    policy=None,
) -> dict[str, Any]:
    """Publishes one decoded image through production perception, then reports it."""

    observation = perception.build(_capture(image), include_content=True)
    return analyze(
        observation,
        image=image,
        input_path=input_path,
        source_kind=source_kind,
        catalog=catalog,
        policy=policy,
    )


def _index_list(actual: Sequence[Any]) -> dict[str, Any] | None:
    """Indexes a report list by its identity field for label comparison."""

    for key in _INDEX_KEYS:
        if actual and all(isinstance(item, Mapping) and key in item for item in actual):
            return {str(item[key]): item for item in actual}
    return None


def _compare(expected: Any, actual: Any, path: str, mismatches: list[dict[str, Any]]) -> None:
    if isinstance(expected, Mapping) and isinstance(actual, Mapping):
        for key, sub in expected.items():
            if key not in actual:
                mismatches.append(
                    {"path": f"{path}.{key}", "expected": sub, "actual": "<missing>"}
                )
            else:
                _compare(sub, actual[key], f"{path}.{key}", mismatches)
        return
    if isinstance(expected, Mapping) and isinstance(actual, Sequence) and not isinstance(actual, (str, bytes)):
        indexed = _index_list(actual)
        if indexed is not None:
            for key, sub in expected.items():
                if key not in indexed:
                    mismatches.append(
                        {"path": f"{path}.{key}", "expected": sub, "actual": "<missing>"}
                    )
                else:
                    _compare(sub, indexed[key], f"{path}.{key}", mismatches)
            return
    if isinstance(expected, Sequence) and not isinstance(expected, (str, bytes)) and isinstance(actual, Sequence) and not isinstance(actual, (str, bytes)):
        if len(expected) != len(actual):
            mismatches.append(
                {"path": path, "expected": f"length {len(expected)}", "actual": f"length {len(actual)}"}
            )
            return
        for index, (sub_expected, sub_actual) in enumerate(zip(expected, actual)):
            _compare(sub_expected, sub_actual, f"{path}[{index}]", mismatches)
        return
    if actual != expected:
        mismatches.append({"path": path, "expected": expected, "actual": actual})


def compare_labels(report: Mapping[str, Any], expected: Mapping[str, Any] | None) -> dict[str, Any]:
    """Compares recognized facts and the decision against one authored label."""

    if expected is None:
        return {"status": "unlabeled", "mismatches": []}
    mismatches: list[dict[str, Any]] = []
    _compare(expected, report, "report", mismatches)
    return {"status": "match" if not mismatches else "mismatch", "mismatches": mismatches}


def load_labels(path: Path) -> dict[str, dict[str, Any]]:
    """Loads the authored label manifest keyed by fixture image name."""

    if not path.is_file():
        raise AnalysisError(f"labels manifest not found: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise AnalysisError(f"labels manifest is not valid JSON: {path} ({error})") from error
    if document.get("schema") != LABELS_SCHEMA:
        raise AnalysisError(
            f"labels manifest schema must be {LABELS_SCHEMA!r}: {path}"
        )
    labels: dict[str, dict[str, Any]] = {}
    for entry in document.get("samples", ()):
        image = entry.get("image")
        if not isinstance(image, str) or not image:
            raise AnalysisError(f"labels manifest sample is missing its image name: {entry}")
        labels[image] = entry
    return labels


# ---------------------------------------------------------------------------
# Annotated review image
# ---------------------------------------------------------------------------

_CELL_COLORS = {
    "locked": (120, 120, 120, 255),
    "unknown": (230, 60, 60, 255),
}
_ORDER_COLORS = {
    "eligible": (60, 200, 60, 255),
    "ineligible": (230, 60, 60, 255),
    "unresolved": (240, 190, 40, 255),
}


def _order_color(order: Mapping[str, Any]) -> tuple[int, int, int, int]:
    assessment = order["assessment"]
    if assessment["eligible"]:
        return _ORDER_COLORS["eligible"]
    if assessment["unresolved"] or order["completeness"] != "complete":
        return _ORDER_COLORS["unresolved"]
    return _ORDER_COLORS["ineligible"]


def annotate(
    image: Image.Image,
    report: Mapping[str, Any],
    *,
    catalog: PetWorkshopCatalog,
) -> Image.Image:
    """Draws measured controls, read facts and the proposal on the source frame."""

    annotated = image.convert("RGBA")
    draw = ImageDraw.Draw(annotated)
    view = report.get("view") or {}
    workshop = report.get("workshop") or {}
    orders = {str(order["order_ref"]): order for order in report.get("orders", ())}
    cells = {cell["cell_id"]: cell for cell in workshop.get("cells", ())}

    strip = view.get("order_strip_bounds")
    if strip is not None:
        draw.rectangle(strip[:2] + [strip[0] + strip[2], strip[1] + strip[3]], outline=(240, 190, 40, 255), width=3)
    for order_view in view.get("order_views", ()):
        order = orders.get(str(order_view["order_ref"]))
        color = _order_color(order) if order is not None else (240, 190, 40, 255)
        for key in ("portrait_bounds", "submit_bounds"):
            rect = order_view.get(key)
            if rect is not None:
                draw.rectangle(rect[:2] + [rect[0] + rect[2], rect[1] + rect[3]], outline=color, width=3)
        if order is not None and order.get("ready") is True:
            rect = order_view.get("submit_bounds") or order_view.get("portrait_bounds")
            if rect is not None:
                draw.text((rect[0], rect[1] - 16), "READY", fill=(60, 200, 60, 255))

    selection = workshop.get("selection") or {}
    for cell_id, rect in (view.get("cell_bounds") or {}).items():
        cell = cells.get(int(cell_id))
        if cell is None:
            continue
        box = rect[:2] + [rect[0] + rect[2], rect[1] + rect[3]]
        if cell["occupancy"] == "occupied":
            item = catalog.item(cell["item_id"]) if cell["item_id"] is not None else None
            label = item.name if item is not None else (
                f"#{cell['item_id']}" if cell["item_id"] is not None else "?"
            )
            color = (90, 160, 250, 255) if cell["item_status"] == "normal" else (240, 190, 40, 255)
            draw.rectangle(box, outline=color, width=2)
            draw.text((box[0] + 4, box[1] + 4), label, fill=color)
        elif cell["access"] == "locked":
            draw.rectangle(box, outline=_CELL_COLORS["locked"], width=1)
        elif cell["occupancy"] == "unknown" or cell["access"] == "unknown":
            draw.rectangle(box, outline=_CELL_COLORS["unknown"], width=2)
    if selection.get("kind") == "selected" and selection.get("cell_id") is not None:
        rect = (view.get("cell_bounds") or {}).get(str(selection["cell_id"]))
        if rect is not None:
            box = rect[:2] + [rect[0] + rect[2], rect[1] + rect[3]]
            draw.rectangle([box[0] - 3, box[1] - 3, box[2] + 3, box[3] + 3], outline=(60, 220, 220, 255), width=4)

    lines = [
        f"input: {Path(report['input']['path']).name} ({report['input']['source_kind']})",
        f"screen: {report['screen']['screen_type']} layout={report['screen']['layout_id']} guard={report['screen']['guard']}",
        (
            f"workshop: surface={workshop.get('surface')} level={workshop.get('workshop_level')} "
            f"exp={workshop.get('workshop_exp')} energy={workshop.get('energy')} "
            f"mode={workshop.get('production_mode')}"
        ),
        f"selection: {selection.get('kind')} cell={selection.get('cell_id')}",
    ]
    decision = report.get("decision")
    if decision is None:
        lines.append("decision: none (no workshop state published)")
    else:
        lines.append(f"decision: {decision['intent']} gameplay={decision['intent']['gameplay']}")
        lines.append(f"reason: {decision['reason'][:110]}")
    check = report.get("label_check") or {}
    if check.get("status"):
        lines.append(f"label_check: {check['status']}")
    width = max(draw.textlength(line) for line in lines) + 16
    draw.rectangle([8, 8, 8 + width, 8 + 18 * len(lines) + 10], fill=(0, 0, 0, 190))
    for index, line in enumerate(lines):
        draw.text((14, 12 + 18 * index), line, fill=(240, 240, 240, 255))
    return annotated


def _resolve_inputs(images: Iterable[str], fixture_names: Iterable[str]) -> list[AnalysisInput]:
    """Resolves positional paths and fixture names against the fixture directory."""

    resolved: list[AnalysisInput] = []
    for name in fixture_names:
        resolved.append(AnalysisInput(path=FIXTURES_DIR / name, source_kind="real_screenshot"))
    for raw in images:
        path = Path(raw)
        if not path.is_file() and not path.is_absolute():
            candidate = FIXTURES_DIR / raw
            if candidate.is_file():
                path = candidate
        resolved.append(AnalysisInput(path=path))
    return resolved


def _reject_stem_collisions(inputs: Sequence[AnalysisInput]) -> None:
    """Fails fast when distinct inputs would write the same output names."""

    stems: dict[str, list[Path]] = {}
    for analysis_input in inputs:
        # Reports must remain distinct on the supported Windows filesystem.
        stems.setdefault(analysis_input.path.stem.casefold(), []).append(analysis_input.path)
    duplicates = {stem: paths for stem, paths in stems.items() if len(paths) > 1}
    if duplicates:
        details = "; ".join(
            f"{stem}: {', '.join(str(path) for path in paths)}"
            for stem, paths in sorted(duplicates.items())
        )
        raise AnalysisError(
            f"output name collision: {details}. "
            "Rename the inputs or analyze them in separate --out-dir runs."
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Replay saved Pet Workshop screenshots through the production recognizer "
            "and planner; writes JSON reports and annotated review images under "
            "the ignored output directory."
        )
    )
    parser.add_argument("images", nargs="*", help="image paths or fixture names")
    parser.add_argument(
        "--fixtures",
        action="store_true",
        help="analyze every image named by the labels manifest",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        default=DEFAULT_LABELS if DEFAULT_LABELS.is_file() else None,
        help="authored label manifest for report comparison",
    )
    parser.add_argument(
        "--source-kind",
        choices=("real_screenshot", "synthesized", "unknown"),
        default=None,
        help="provenance kind for inputs not covered by the labels manifest",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="ignored output directory")
    parser.add_argument("--no-annotate", action="store_true", help="skip annotated review images")
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="exit nonzero when a labeled report does not match",
    )
    args = parser.parse_args(argv)

    labels: dict[str, dict[str, Any]] = {}
    if args.labels is not None:
        labels = load_labels(args.labels)
    fixture_names: list[str] = []
    if args.fixtures:
        if not labels:
            raise AnalysisError("--fixtures requires a labels manifest naming fixture images")
        fixture_names = [entry["image"] for entry in labels.values()]
    inputs = _resolve_inputs(args.images, fixture_names)
    if not inputs:
        parser.error("no inputs: pass image paths or --fixtures")
    _reject_stem_collisions(inputs)

    perception = build_perception().perception
    catalog = load_pet_workshop_catalog()
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    index: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "labels": None if args.labels is None else str(args.labels),
        "reports": [],
    }
    failures = 0
    mismatches = 0
    for analysis_input in inputs:
        label = labels.get(analysis_input.path.name)
        source_kind = (
            label.get("source_kind")
            if label is not None and label.get("source_kind") is not None
            else (args.source_kind or "unknown")
        )
        try:
            image = _load_image(analysis_input.path)
            report = analyze_image(
                perception,
                image,
                input_path=str(analysis_input.path),
                source_kind=source_kind,
                catalog=catalog,
            )
        except AnalysisError as error:
            failures += 1
            index["reports"].append(
                {"input": str(analysis_input.path), "status": "error", "error": str(error)}
            )
            print(f"error: {error}", file=sys.stderr)
            continue
        report["label_check"] = compare_labels(report, (label or {}).get("expected"))
        if report["label_check"]["status"] == "mismatch":
            mismatches += 1
        stem = analysis_input.path.stem
        report_path = out_dir / f"{stem}.report.json"
        annotated_name = f"{stem}.annotated.png"
        if not args.no_annotate:
            annotate(image, report, catalog=catalog).save(out_dir / annotated_name)
            report["annotated_image"] = annotated_name
        report_path.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        index["reports"].append(
            {
                "input": str(analysis_input.path),
                "report": report_path.name,
                "annotated_image": None if args.no_annotate else annotated_name,
                "status": "ok",
                "label_check": report["label_check"]["status"],
            }
        )
        print(f"{analysis_input.path.name}: label_check={report['label_check']['status']}")
    (out_dir / "index.json").write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    if failures:
        return 1
    if mismatches and args.fail_on_mismatch:
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AnalysisError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
