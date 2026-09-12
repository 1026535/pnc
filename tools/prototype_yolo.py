"""Run local YOLO shadow inference on saved frames or one live PNC capture."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw

try:
    from _script_bootstrap import ensure_repo_root_on_path
except ModuleNotFoundError:
    from tools._script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from pnc_automation.app.entrypoints.app import build_application_runner, build_observation_builder
from pnc_automation.app.pnc.domain.observation import SpatialObjectKind
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.yolo_shadow import YoloShadowObserver, YoloShadowReport
from pnc_automation.core.vision.observation_policy import ObservationMode
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.detection.yolo_onnx import YoloOnnxDetector


def load_class_map(path: Path | None) -> dict[str, SpatialObjectKind]:
    """Require an explicit model-label to PNC-kind mapping; COCO has none by default."""
    if path is None:
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or any(not isinstance(label, str) or not label for label in value):
        raise ValueError("Class map must be a JSON object of model labels to PNC spatial kinds.")
    return {label: SpatialObjectKind(kind) for label, kind in value.items()}


def save_report(directory: Path, index: int, image: Image.Image, report: YoloShadowReport) -> dict[str, object]:
    """Write a local overlay and typed JSON; these boxes never authorize clicks."""
    preview = image.convert("RGB")
    draw = ImageDraw.Draw(preview)
    for item in report.detections:
        box = item.bounds
        draw.rectangle((box.x, box.y, box.x + box.width - 1, box.y + box.height - 1), outline="lime", width=3)
        draw.text((box.x, box.y), f"{item.label} {item.confidence:.2f}", fill="yellow", stroke_width=1, stroke_fill="black")
    preview_path = directory / f"{index:03d}_yolo.png"
    preview.save(preview_path)
    record = asdict(report)
    record["screen_type"] = report.screen_type.value
    record["preview"] = str(preview_path.resolve())
    (directory / f"{index:03d}_report.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def main() -> int:
    """Load only explicit local weights and keep inference separate from automation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--image", action="append", type=Path)
    sources.add_argument("--live", action="store_true")
    parser.add_argument("--account", default="testing")
    parser.add_argument("--config", type=Path, default=Path("config/accounts.yaml"))
    parser.add_argument("--class-map", type=Path)
    parser.add_argument("--confidence", type=float, default=0.35)
    parser.add_argument("--output-dir", type=Path, default=Path(".local-data/artifacts/yolo_prototype/runs"))
    args = parser.parse_args()
    detector = YoloOnnxDetector(args.model, confidence_threshold=args.confidence)
    shadow = YoloShadowObserver(detector, load_class_map(args.class_map))
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    directory = args.output_dir / run_id
    directory.mkdir(parents=True, exist_ok=False)
    records = []
    if args.live:
        # No navigation, castle switching, roster persistence, or game action.
        # Foregrounding the configured game is necessary for a meaningful capture.
        logging.disable(logging.CRITICAL)
        app = build_application_runner(args.config, observation_mode=ObservationMode.DEBUG)
        account = app.script_runner.config.require_account(args.account)
        bundle = app.script_runner.build_connected_runtime_bundle(account=account)
        runtime = bundle.runtime
        observer = runtime.observation_service
        observer.castle_roster_store = None
        runtime.session.ensure_app_foregrounded()
        capture = observer.capture_observation(f"yolo_shadow_{run_id}")
        result = shadow.observe(capture.screenshot, capture.observation)
        records.append(save_report(directory, 0, capture.screenshot.image, result))
    else:
        builder = build_observation_builder(build_default_selector_registry())
        for index, path in enumerate(args.image):
            with Image.open(path) as source:
                image = source.convert("RGB")
            capture = CapturedScreenshot(None, image, "PNG", ephemeral_captured_at=datetime.now(UTC))
            result = shadow.observe(capture, builder.build(capture))
            records.append(save_report(directory, index, image, result))
    summary = {"mode": "shadow_only", "live": args.live, "model_sha256": detector.model_sha256,
               "class_names": detector.class_names, "frames": records,
               "note": "Detections are diagnostics; no PNC accuracy claim or action authorization."}
    target = directory / "summary.json"
    target.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
