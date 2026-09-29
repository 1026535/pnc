"""Compare warm canonical Home surface costs for endpoint-first V44 captures.

Run only after native matching CPU is released. This measures the camera/surface
producer; full runtime recognition, guarding, capture and input remain separate.
"""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

from PIL import Image

from pnc_automation.app.pnc.domain.home_city_camera import HomeCityCameraScanMode
from pnc_automation.app.pnc.vision.home_city_camera import HomeCityCameraLocalizer
from pnc_automation.app.pnc.vision.spatial_surfaces import build_home_city_spatial_surface
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher


FIXTURES = Path(__file__).resolve().parents[1] / "tests/data/home_city_camera"
CASES = (
    ("endpoint_probe", "home_city_zoom_endpoint_20260925.png", HomeCityCameraScanMode.ENDPOINT_PROBE),
    ("endpoint_certify", "home_city_zoom_endpoint_20260925.png", HomeCityCameraScanMode.UNRESTRICTED),
    ("endpoint_reacquire", "home_city_zoom_endpoint_20260925.png", HomeCityCameraScanMode.NORMALIZED_ENDPOINT),
    ("nearest_rung_probe", "home_city_zoom_rung_20260925.png", HomeCityCameraScanMode.ENDPOINT_PROBE),
    ("default_start_probe", "home_city_default_start_20260927.png", HomeCityCameraScanMode.ENDPOINT_PROBE),
)


def main() -> None:
    """Print warm elapsed values and semantic output for the smallest saved cases."""

    camera = HomeCityCameraLocalizer(matcher=OpenCvTemplateMatcher())
    images = {}
    for _, name, _ in CASES:
        if name not in images:
            with Image.open(FIXTURES / name) as source:
                images[name] = source.copy()

    def build(name: str, mode: HomeCityCameraScanMode):
        return build_home_city_spatial_surface(
            image=images[name], lines=(), selector_registry=None,
            camera=camera, camera_mode=mode,
        )

    for _, name, mode in CASES:
        build(name, mode)
    rows = []
    for label, name, mode in CASES:
        start = perf_counter()
        surface = build(name, mode)
        elapsed_ms = (perf_counter() - start) * 1000
        proof = surface.camera_proof
        view = surface.home_city_view
        rows.append({
            "case": label,
            "wall_ms": round(elapsed_ms, 2),
            "camera_status": None if proof is None else proof.status.value,
            "translation": None if proof is None else proof.translation,
            "zoom_status": None if view is None else view.zoom_status.value,
            "targets": [item.metadata.get("home_city_object_id") for item in surface.objects],
        })
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
