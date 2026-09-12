"""Evaluate local YOLO shadow inference on reviewed frames or live PNC captures."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
from time import monotonic, sleep
from typing import Callable
from uuid import uuid4

from PIL import Image, ImageDraw, ImageStat

try:
    from _script_bootstrap import ensure_repo_root_on_path
except ModuleNotFoundError:
    from tools._script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from pnc_automation.app.entrypoints.app import build_application_runner, build_observation_builder
from pnc_automation.app.pnc.domain.observation import SpatialObjectKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_builder import CapturedObservation, ObservationService
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.yolo_shadow import (
    YoloShadowObserver,
    YoloShadowReport,
    evaluate_yolo_shadow,
)
from pnc_automation.app.runtime.observation_mode import ObservationMode
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.detection.yolo_onnx import YoloOnnxDetector
from tools.benchmark_screen_recognition import load_manifest


def load_class_map(path: Path | None) -> dict[str, SpatialObjectKind]:
    """Require an explicit model-label to PNC-kind mapping; COCO has none by default."""
    if path is None:
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or any(not isinstance(label, str) or not label for label in value):
        raise ValueError("Class map must be a JSON object of model labels to PNC spatial kinds.")
    return {label: SpatialObjectKind(kind) for label, kind in value.items()}


def save_report(
    directory: Path,
    index: int,
    image: Image.Image,
    report: YoloShadowReport,
    *,
    source: dict[str, object],
) -> dict[str, object]:
    """Write a local overlay and typed JSON; these boxes never authorize clicks."""
    preview = image.convert("RGB")
    draw = ImageDraw.Draw(preview)
    for item in report.detections:
        box = item.bounds
        draw.rectangle((box.x, box.y, box.x + box.width - 1, box.y + box.height - 1), outline="lime", width=3)
        draw.text(
            (box.x, box.y),
            f"{item.label} {item.confidence:.2f}",
            fill="yellow",
            stroke_width=1,
            stroke_fill="black",
        )
    preview_path = directory / f"{index:03d}_yolo.png"
    preview.save(preview_path)
    record = asdict(report)
    record["screen_type"] = report.screen_type.value
    record["preview"] = str(preview_path.resolve())
    record["source"] = source
    (directory / f"{index:03d}_report.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def wait_for_live_visual_state(
    observer: ObservationService,
    *,
    run_id: str,
    timeout_seconds: float,
    clock: Callable[[], float] = monotonic,
    wait: Callable[[float], None] = sleep,
) -> tuple[CapturedObservation, str, int]:
    """Wait boundedly for PNC content after launch, retaining an unknown-screen fallback."""

    started = clock()
    fallback: CapturedObservation | None = None
    attempts = 0
    while True:
        attempts += 1
        capture = observer.capture_observation(f"yolo_shadow_{run_id}_startup_{attempts:03d}")
        if _has_visual_content(capture.screenshot.image):
            fallback = capture
            if capture.observation.screen_type not in {ScreenType.UNKNOWN, ScreenType.PNC_LOADING}:
                return capture, "known_screen", attempts
        remaining = timeout_seconds - (clock() - started)
        if remaining <= 0:
            break
        wait(min(2.0, remaining))
    if fallback is not None:
        return fallback, "visual_content_only", attempts
    raise RuntimeError("PNC remained visually blank through the bounded startup wait.")


def _has_visual_content(image: Image.Image) -> bool:
    """Reject uniform launch-transition frames while ignoring the Android status bar."""

    grayscale = image.convert("L")
    if grayscale.width == 0 or grayscale.height < 2:
        return False
    top = min(grayscale.height - 1, max(1, 36, int(grayscale.height * 0.05)))
    body = grayscale.crop((0, top, grayscale.width, grayscale.height))
    minimum, maximum = body.getextrema()
    return maximum - minimum >= 48 and ImageStat.Stat(body).stddev[0] >= 10


def main() -> int:
    """Load only explicit local weights and keep inference separate from automation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--image", action="append", type=Path)
    sources.add_argument("--manifest", type=Path)
    sources.add_argument("--live", action="store_true")
    parser.add_argument("--account", default="testing")
    parser.add_argument("--config", type=Path, default=Path("config/accounts.yaml"))
    parser.add_argument("--class-map", type=Path)
    parser.add_argument("--confidence", type=float, default=0.35)
    parser.add_argument("--live-samples", type=int, default=1)
    parser.add_argument("--startup-timeout-seconds", type=float, default=90.0)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/yolo_prototype/runs"))
    args = parser.parse_args()
    if not 1 <= args.live_samples <= 20:
        parser.error("--live-samples must be between 1 and 20")
    if not args.live and args.live_samples != 1:
        parser.error("--live-samples is only valid with --live")
    if not 0 < args.startup_timeout_seconds <= 120:
        parser.error("--startup-timeout-seconds must be greater than 0 and at most 120")
    if not args.live and args.startup_timeout_seconds != 90.0:
        parser.error("--startup-timeout-seconds is only valid with --live")
    detector = YoloOnnxDetector(args.model, confidence_threshold=args.confidence)
    shadow = YoloShadowObserver(detector, load_class_map(args.class_map))
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    directory = args.output_dir / run_id
    directory.mkdir(parents=True, exist_ok=False)
    records: list[dict[str, object]] = []
    reports: list[YoloShadowReport] = []
    reports_by_split: defaultdict[str, list[YoloShadowReport]] = defaultdict(list)
    source_summary: dict[str, object]
    if args.live:
        # No navigation, castle switching, roster persistence, or game action.
        # Foregrounding the configured game is necessary for a meaningful capture.
        logging.disable(logging.CRITICAL)
        app = build_application_runner(args.config, observation_mode=ObservationMode.DEBUG)
        account = app.script_runner.config.require_account(args.account)
        instance = app.script_runner.config.require_instance(account.instance_id)
        app_was_foregrounded: bool | None = None
        readiness: str | None = None
        startup_observations = 0
        with app.reserve_accounts((args.account,)):
            with app.script_runner.build_connected_runtime_bundle(account=account) as bundle:
                runtime = bundle.runtime
                observer = runtime.observation_service
                observer.castle_roster_store = None
                app_was_foregrounded = runtime.session.is_app_foregrounded()
                runtime.session.ensure_app_foregrounded()
                ready_capture, readiness, startup_observations = wait_for_live_visual_state(
                    observer,
                    run_id=run_id,
                    timeout_seconds=args.startup_timeout_seconds,
                )
                for index in range(args.live_samples):
                    capture = (
                        ready_capture
                        if index == 0
                        else observer.capture_observation(f"yolo_shadow_{run_id}_{index:03d}")
                    )
                    result = shadow.observe(capture.screenshot, capture.observation)
                    reports.append(result)
                    records.append(
                        save_report(
                            directory,
                            index,
                            capture.screenshot.image,
                            result,
                            source={"kind": "live", "sample_index": index},
                        )
                    )
        source_summary = {
            "kind": "live",
            "account": account.id,
            "instance_display_name": instance.display_name,
            "sample_count": args.live_samples,
            "reservation_scope": "connection_foreground_capture_inference_cleanup",
            "app_was_foregrounded": app_was_foregrounded,
            "startup_readiness": readiness,
            "startup_observation_count": startup_observations,
        }
    else:
        builder = build_observation_builder(build_default_selector_registry())
        if args.manifest is not None:
            samples = load_manifest(args.manifest)
            inputs = tuple(
                (
                    sample.image.copy(),
                    {
                        "kind": "reviewed_manifest",
                        "image": sample.image_name,
                        "expected_screen": sample.expected_screen.value,
                        "split": sample.split,
                        "group": sample.group,
                    },
                )
                for sample in samples
            )
            source_summary = {
                "kind": "reviewed_manifest",
                "manifest": str(args.manifest.resolve()),
                "sample_count": len(samples),
            }
        else:
            inputs_list: list[tuple[Image.Image, dict[str, object]]] = []
            for path in args.image:
                with Image.open(path) as opened:
                    image = opened.convert("RGB")
                inputs_list.append((image, {"kind": "image", "path": str(path.resolve())}))
            inputs = tuple(inputs_list)
            source_summary = {"kind": "images", "sample_count": len(inputs)}
        for index, (image, source) in enumerate(inputs):
            capture = CapturedScreenshot(None, image, "PNG", ephemeral_captured_at=datetime.now(UTC))
            result = shadow.observe(capture, builder.build(capture))
            reports.append(result)
            if "split" in source:
                reports_by_split[str(source["split"])].append(result)
            records.append(save_report(directory, index, image, result, source=source))
    summary = {
        "mode": "shadow_only",
        "live": args.live,
        "source": source_summary,
        "model_sha256": detector.model_sha256,
        "class_names": detector.class_names,
        "confidence_threshold": args.confidence,
        "evaluation": evaluate_yolo_shadow(reports).to_document(),
        "evaluation_by_split": {
            split: evaluate_yolo_shadow(split_reports).to_document()
            for split, split_reports in sorted(reports_by_split.items())
        },
        "frames": records,
        "note": "Detections are diagnostics and never authorize a PNC action.",
    }
    target = directory / "summary.json"
    target.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
