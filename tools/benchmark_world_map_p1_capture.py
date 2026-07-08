"""Benchmarks live world-map P1 capture/proof and P2 screenshot-analysis costs."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from _script_bootstrap import ensure_repo_root_on_path

root = ensure_repo_root_on_path()

from pnc_automation.app import build_application_runner
from pnc_automation.app.automation.engine.task import TaskPreflight
from pnc_automation.app.pnc.domain.observation import SpatialSurfaceType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.runtime.observation_artifacts import (
    ObservationArtifactRoutine,
    resolve_routine_artifact_selection,
)


@dataclass(slots=True)
class _TimingScreenshotService:
    """Wraps screenshot capture so ObservationService internals can be timed without production edits."""

    inner: Any
    timings_ms: list[float]

    def capture(self, *args: Any, **kwargs: Any) -> Any:
        """Records one delegated screenshot capture duration."""

        value, elapsed_ms = _elapsed_ms(lambda: self.inner.capture(*args, **kwargs))
        self.timings_ms.append(elapsed_ms)
        return value


@dataclass(slots=True)
class _TimingObservationBuilder:
    """Wraps observation building so service residual overhead can be isolated."""

    inner: Any
    timings_ms: list[float]

    def build(self, *args: Any, **kwargs: Any) -> Any:
        """Records one delegated observation-build duration."""

        value, elapsed_ms = _elapsed_ms(lambda: self.inner.build(*args, **kwargs))
        self.timings_ms.append(elapsed_ms)
        return value

    def __getattr__(self, name: str) -> Any:
        """Delegates non-timed attributes used by runtime code to the wrapped builder."""

        return getattr(self.inner, name)


def main() -> None:
    """Runs the granular live benchmark and prints a JSON timing document."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(root / "config" / "accounts.yaml"))
    parser.add_argument("--account", default="testing")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--label", default="world_map_p1_capture_benchmark")
    parser.add_argument("--skip-prepare", action="store_true")
    arguments = parser.parse_args()
    if arguments.iterations <= 0:
        raise ValueError("iterations must be positive.")

    application = build_application_runner(Path(arguments.config))
    if not arguments.skip_prepare:
        prepare_result = application.script_runner.prepare_account_session(account_id=arguments.account)
        if not all(step.status.value == "success" for step in prepare_result.steps):
            raise AssertionError(f"Preparation failed: {prepare_result.steps}")
    account = application.script_runner.config.require_account(arguments.account)
    connected = application.script_runner.build_connected_runtime_bundle(account=account)
    runtime = connected.runtime
    service = runtime.observation_service
    screenshot_service = service.screenshot_service
    builder = service.observation_builder
    session = runtime.session

    start = connected.runner.prove_preflight_state(
        account,
        TaskPreflight.WORLD_MAP,
        label_prefix=f"{arguments.label}_preflight",
        max_steps=20,
    )
    coordinate = start.require_spatial_surface(SpatialSurfaceType.WORLD_MAP).viewport.coordinate
    if coordinate is None:
        raise AssertionError("World-map preflight did not expose a coordinate-addressable viewport.")

    request = ObservationRequest.world_map_movement_proof_follow_up()
    artifact_selection = resolve_routine_artifact_selection(
        mode=service.mode,
        routine=ObservationArtifactRoutine.WORLD_MAP_MOVEMENT_PROOF,
    )
    coordinate_bar_selector = builder.selector_registry.require(UiElementId.PNC_WORLD_COORDINATE_BAR)
    if coordinate_bar_selector.relative_bounds is None:
        raise AssertionError("Coordinate-bar selector must define relative bounds.")

    _warm_live_paths(
        account_artifact_directory=account.artifact_directory_name,
        builder=builder,
        request=request,
        screenshot_service=screenshot_service,
        session=session,
        label=arguments.label,
    )

    payloads, adb_bytes_ms = _benchmark_adb_bytes(session=session, iterations=arguments.iterations)
    png_decode_ms = _benchmark_png_decode(payloads)
    artifact_persist_ms = _benchmark_artifact_persist(
        screenshot_service=screenshot_service,
        account_artifact_directory=account.artifact_directory_name,
        label=arguments.label,
        payloads=payloads,
    )
    ocr_screenshots, screenshot_capture_no_persist_ms = _benchmark_screenshot_capture(
        screenshot_service=screenshot_service,
        session=session,
        account_artifact_directory=account.artifact_directory_name,
        label=arguments.label,
        iterations=arguments.iterations,
        persist=False,
    )
    _persisted_screenshots, screenshot_capture_persist_ms = _benchmark_screenshot_capture(
        screenshot_service=screenshot_service,
        session=session,
        account_artifact_directory=account.artifact_directory_name,
        label=arguments.label,
        iterations=arguments.iterations,
        persist=True,
    )
    coordinate_ocr_ms = _benchmark_coordinate_ocr(
        screenshots=ocr_screenshots,
        coordinate_bar_selector=coordinate_bar_selector,
        ocr_service=builder.enricher.ocr_service,
    )
    builder_screenshots, _builder_input_capture_ms = _benchmark_screenshot_capture(
        screenshot_service=screenshot_service,
        session=session,
        account_artifact_directory=account.artifact_directory_name,
        label=f"{arguments.label}_builder_input",
        iterations=arguments.iterations,
        persist=False,
    )
    coordinate_builder_ms = _benchmark_builder(
        builder=builder,
        screenshots=builder_screenshots,
        request=request,
    )
    p2_builder_ms = _benchmark_builder(
        builder=builder,
        screenshots=builder_screenshots,
        request=ObservationRequest.world_map_checkpoint_analysis(expected_coordinate=coordinate),
    )
    service_timings = _benchmark_observation_service(
        service=service,
        request=request,
        artifact_selection=artifact_selection,
        label=arguments.label,
        iterations=arguments.iterations,
    )
    service_total_mean = statistics.mean(service_timings["total_ms"])

    print(
        json.dumps(
            {
                "account": arguments.account,
                "iterations": arguments.iterations,
                "preflight_coordinate": coordinate,
                "movement_proof_artifact_selection": sorted(kind.value for kind in artifact_selection),
                "adb_capture_screenshot_bytes": _summary(adb_bytes_ms),
                "png_decode_existing_payload": _summary(png_decode_ms),
                "artifact_persist_existing_payload_debug_only": _summary(artifact_persist_ms),
                "screenshot_service_capture_no_persist": _summary(screenshot_capture_no_persist_ms),
                "screenshot_service_capture_with_persist_debug_only": _summary(screenshot_capture_persist_ms),
                "coordinate_bar_ocr_only_existing_screenshot": _summary(coordinate_ocr_ms),
                "observation_builder_coordinate_only_existing_screenshot": _summary(coordinate_builder_ms),
                "p2_checkpoint_builder_existing_screenshot": _summary(p2_builder_ms),
                "observation_service_capture_total": _summary(service_timings["total_ms"]),
                "observation_service_internal_screenshot_capture": _summary(service_timings["screenshot_ms"]),
                "observation_service_internal_builder": _summary(service_timings["builder_ms"]),
                "observation_service_residual_side_effects": _summary(service_timings["residual_ms"]),
                "mean_percent_of_service_total": {
                    "screenshot_capture": round(
                        statistics.mean(service_timings["screenshot_ms"]) / service_total_mean * 100,
                        1,
                    ),
                    "builder": round(
                        statistics.mean(service_timings["builder_ms"]) / service_total_mean * 100,
                        1,
                    ),
                    "residual_side_effects": round(
                        statistics.mean(service_timings["residual_ms"]) / service_total_mean * 100,
                        1,
                    ),
                },
                "service_coordinates": service_timings["coordinates"],
                "service_artifact_paths": service_timings["artifact_paths"],
            },
            indent=2,
            sort_keys=True,
        )
    )


def _warm_live_paths(
    *,
    account_artifact_directory: str,
    builder: Any,
    request: ObservationRequest,
    screenshot_service: Any,
    session: Any,
    label: str,
) -> None:
    """Warms ADB, PNG decode, and OCR initialization before measured iterations."""

    screenshot = screenshot_service.capture(
        session,
        artifact_directory=account_artifact_directory,
        label=f"{label}_warm",
        persist=False,
    )
    builder.build(screenshot, request=request)


def _benchmark_adb_bytes(*, session: Any, iterations: int) -> tuple[list[bytes], list[float]]:
    """Measures raw ADB screenshot transport without PNG decode."""

    payloads: list[bytes] = []
    timings_ms: list[float] = []
    for _ in range(iterations):
        payload, elapsed_ms = _elapsed_ms(session.capture_screenshot_bytes)
        payloads.append(payload)
        timings_ms.append(elapsed_ms)
    return payloads, timings_ms


def _benchmark_png_decode(payloads: list[bytes]) -> list[float]:
    """Measures PIL decode/load cost from already captured PNG bytes."""

    timings_ms: list[float] = []
    for payload in payloads:
        _image, elapsed_ms = _elapsed_ms(lambda payload=payload: _decode_png(payload))
        timings_ms.append(elapsed_ms)
    return timings_ms


def _benchmark_artifact_persist(
    *,
    screenshot_service: Any,
    account_artifact_directory: str,
    label: str,
    payloads: list[bytes],
) -> list[float]:
    """Measures debug-only screenshot artifact persistence from already captured bytes."""

    timings_ms: list[float] = []
    for index, payload in enumerate(payloads):
        _artifact, elapsed_ms = _elapsed_ms(
            lambda index=index, payload=payload: screenshot_service.artifact_store.persist_bytes(
                artifact_directory=account_artifact_directory,
                label=f"{label}_persist_only_{index}",
                extension=screenshot_service.screenshot_format,
                payload=payload,
            )
        )
        timings_ms.append(elapsed_ms)
    return timings_ms


def _benchmark_screenshot_capture(
    *,
    screenshot_service: Any,
    session: Any,
    account_artifact_directory: str,
    label: str,
    iterations: int,
    persist: bool,
) -> tuple[list[Any], list[float]]:
    """Measures canonical ScreenshotService capture with or without persistence."""

    screenshots: list[Any] = []
    timings_ms: list[float] = []
    suffix = "persist" if persist else "no_persist"
    for index in range(iterations):
        screenshot, elapsed_ms = _elapsed_ms(
            lambda index=index: screenshot_service.capture(
                session,
                artifact_directory=account_artifact_directory,
                label=f"{label}_{suffix}_{index}",
                persist=persist,
            )
        )
        screenshots.append(screenshot)
        timings_ms.append(elapsed_ms)
    return screenshots, timings_ms


def _benchmark_coordinate_ocr(
    *,
    screenshots: list[Any],
    coordinate_bar_selector: Any,
    ocr_service: Any,
) -> list[float]:
    """Measures only coordinate-bar OCR on existing screenshots."""

    timings_ms: list[float] = []
    for screenshot in screenshots:
        region = coordinate_bar_selector.relative_bounds.materialize_region(image_size=screenshot.image.size)
        _text, elapsed_ms = _elapsed_ms(lambda screenshot=screenshot, region=region: ocr_service.read_text(screenshot.image, region))
        timings_ms.append(elapsed_ms)
    return timings_ms


def _benchmark_builder(*, builder: Any, screenshots: list[Any], request: ObservationRequest) -> list[float]:
    """Measures one observation-builder request on existing screenshots."""

    timings_ms: list[float] = []
    for screenshot in screenshots:
        _observation, elapsed_ms = _elapsed_ms(lambda screenshot=screenshot: builder.build(screenshot, request=request))
        timings_ms.append(elapsed_ms)
    return timings_ms


def _benchmark_observation_service(
    *,
    service: Any,
    request: ObservationRequest,
    artifact_selection: Any,
    label: str,
    iterations: int,
) -> dict[str, Any]:
    """Measures ObservationService total time and splits screenshot, builder, and residual side effects."""

    screenshot_ms: list[float] = []
    builder_ms: list[float] = []
    total_ms: list[float] = []
    coordinates: list[tuple[int, int] | None] = []
    artifact_paths: list[str | None] = []
    original_screenshot_service = service.screenshot_service
    original_builder = service.observation_builder
    service.screenshot_service = _TimingScreenshotService(original_screenshot_service, screenshot_ms)
    service.observation_builder = _TimingObservationBuilder(original_builder, builder_ms)
    try:
        for index in range(iterations):
            capture, elapsed_ms = _elapsed_ms(
                lambda index=index: service.capture_observation(
                    f"{label}_service_{index}",
                    request=request,
                    artifact_selection=artifact_selection,
                )
            )
            total_ms.append(elapsed_ms)
            coordinates.append(
                capture.observation.require_spatial_surface(SpatialSurfaceType.WORLD_MAP).viewport.coordinate
            )
            artifact_paths.append(None if capture.screenshot.artifact_path is None else str(capture.screenshot.artifact_path))
    finally:
        service.screenshot_service = original_screenshot_service
        service.observation_builder = original_builder
    return {
        "total_ms": total_ms,
        "screenshot_ms": screenshot_ms,
        "builder_ms": builder_ms,
        "residual_ms": [
            total - screenshot - builder
            for total, screenshot, builder in zip(total_ms, screenshot_ms, builder_ms)
        ],
        "coordinates": coordinates,
        "artifact_paths": artifact_paths,
    }


def _elapsed_ms(fn: Any) -> tuple[Any, float]:
    """Returns a function result and elapsed wall-clock milliseconds."""

    started = time.perf_counter()
    value = fn()
    return value, (time.perf_counter() - started) * 1000.0


def _decode_png(payload: bytes) -> Image.Image:
    """Decodes PNG bytes into a fully loaded PIL image."""

    image = Image.open(BytesIO(payload))
    image.load()
    return image


def _summary(values: list[float]) -> dict[str, float]:
    """Returns compact descriptive timing statistics."""

    if not values:
        return {"count": 0, "mean_ms": 0.0, "median_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0}
    return {
        "count": len(values),
        "mean_ms": round(statistics.mean(values), 2),
        "median_ms": round(statistics.median(values), 2),
        "min_ms": round(min(values), 2),
        "max_ms": round(max(values), 2),
    }


if __name__ == "__main__":
    main()
