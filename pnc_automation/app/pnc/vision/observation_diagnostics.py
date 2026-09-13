"""Export recognition evidence without requesting additional OCR work."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.core.vision.ocr.ocr_service import (
    ObservationOcrContext,
    OcrLine,
    OcrReadDiagnostic,
    OcrReadStatus,
)


@dataclass(slots=True)
class ObservationDebugArtifactCollector:
    """Persist already acquired OCR and missing-fact evidence beside its capture."""

    def persist_unidentified_ocr_sidecar(
        self,
        *,
        screenshot: CapturedScreenshot,
        observation: Observation,
        ocr_context: ObservationOcrContext,
    ) -> None:
        """Write unmatched recorded lines; never read a new region for debugging."""

        _validate_report_capture(screenshot, observation, ocr_context)
        artifact_path = screenshot.artifact_path
        if artifact_path is None:
            return
        recognized_texts = _recognized_ocr_text_hints(observation)
        recorded_lines = tuple(dict.fromkeys(
            line
            for read in ocr_context.read_diagnostics
            if read.result is not None
            for line in read.result.lines
        ))
        unidentified_lines = _unidentified_ocr_lines(
            lines=recorded_lines, recognized_texts=recognized_texts,
        )
        if not unidentified_lines:
            return
        document = _capture_document(screenshot, observation)
        document.update({
            "recognized_text_hints": sorted(recognized_texts),
            "unidentified_ocr_lines": [_line_document(line) for line in unidentified_lines],
        })
        _write_sidecar(artifact_path, "unidentified_ocr", document)

    def persist_recognition_gap(
        self,
        *,
        screenshot: CapturedScreenshot,
        observation: Observation,
        ocr_context: ObservationOcrContext,
        profile_ids: tuple[str, ...] = (),
    ) -> None:
        """Write unknown decisions and terminal missing reads, including zero-OCR frames."""

        _validate_report_capture(screenshot, observation, ocr_context)
        reads = ocr_context.read_diagnostics
        reasons: list[str] = []
        if observation.screen_type == ScreenType.UNKNOWN:
            reasons.append("unknown_screen")
        if not observation.decision.coordinate_only and observation.decision.guard in {
            GuardVerdict.UNRESOLVED, GuardVerdict.NOT_EVALUATED,
        }:
            reasons.append(f"guard_{observation.decision.guard.value}")
        # A retried read that eventually succeeded is not a remaining OCR gap.
        latest_reads = {(read.purpose, read.region, read.detail): read for read in reads}
        missing_reads = tuple(
            read for read in latest_reads.values()
            if read.status in {OcrReadStatus.MISSING, OcrReadStatus.ERROR}
        )
        if missing_reads:
            reasons.append("missing_ocr_facts")
        if not reasons or screenshot.artifact_path is None:
            return
        document = _capture_document(screenshot, observation)
        document.update({
            "reasons": reasons,
            "matched_profile_ids": list(profile_ids),
            "guard": observation.decision.guard.value,
            "layout_id": observation.decision.layout_id,
            "evidence": [asdict(item) for item in observation.decision.evidence],
            "missing_reads": [_read_document(read) for read in missing_reads],
            "ocr_reads": [_read_document(read) for read in reads],
        })
        _write_sidecar(screenshot.artifact_path, "recognition_gap", document)


def _validate_report_capture(
    screenshot: CapturedScreenshot, observation: Observation, context: ObservationOcrContext,
) -> None:
    """Reject foreign evidence even when no sidecar can be persisted."""

    context.validate_capture(screenshot.image, screenshot.frame_ref)
    if observation.frame_ref != screenshot.frame_ref:
        raise ValueError("Observation diagnostic report used a different capture frame.")


def _capture_document(screenshot: CapturedScreenshot, observation: Observation) -> dict[str, object]:
    """Serialize the source proof shared by both existing artifact exports."""

    frame = None
    if screenshot.frame_ref is not None:
        frame = asdict(screenshot.frame_ref)
        frame["captured_at"] = screenshot.frame_ref.captured_at.isoformat()
    return {
        "artifact_path": str(screenshot.artifact_path),
        "screen_type": observation.screen_type.value,
        "captured_at": observation.captured_at.isoformat(),
        "frame_ref": frame,
    }


def _line_document(line: OcrLine) -> dict[str, object]:
    """Keep the established debug-line schema and native-frame geometry."""

    return {
        "text": line.text,
        "normalized_text": normalize_ocr_text(line.text),
        "bounds": asdict(line.bounds),
        "confidence": line.confidence,
    }


def _read_document(read: OcrReadDiagnostic) -> dict[str, object]:
    """Associate acquired lines with the request that actually produced them."""

    return {
        "purpose": read.purpose.value,
        "status": read.status.value,
        "region": None if read.region is None else asdict(read.region),
        "detail": read.detail,
        "lines": None if read.result is None else [_line_document(line) for line in read.result.lines],
    }


def _write_sidecar(artifact_path: Path, kind: str, document: dict[str, object]) -> None:
    """Use the capture's existing artifact directory and deterministic sidecar name."""

    sidecar_path = artifact_path.with_name(f"{artifact_path.stem}_{kind}.json")
    sidecar_path.write_text(json.dumps(document, indent=2, ensure_ascii=True), encoding="utf-8")


def _recognized_ocr_text_hints(observation: Observation) -> frozenset[str]:
    """Return normalized OCR phrases already explained by the typed observation."""

    recognized_texts: set[str] = set()
    _add_recognized_text(recognized_texts, observation.current_pnc_account_id)
    _add_recognized_text(recognized_texts, observation.verified_pnc_account_id)
    _add_recognized_text(recognized_texts, observation.profile_player_name)
    _add_recognized_text(recognized_texts, observation.chat_draft_text)
    if observation.current_castle is not None:
        _add_recognized_text(recognized_texts, observation.current_castle.castle_name)
        _add_recognized_text(recognized_texts, observation.current_castle.kingdom)
    for element in observation.visible_elements.values():
        _add_recognized_text(recognized_texts, element.extracted_text)
    for entry in observation.list_entries:
        _add_recognized_text(recognized_texts, entry.title_text)
        _add_recognized_text(recognized_texts, entry.subtitle_text)
        for value in entry.metadata.values():
            if isinstance(value, str):
                _add_recognized_text(recognized_texts, value)
    if observation.spatial_surface is not None:
        coordinate_text = observation.spatial_surface.metadata.get("coordinate_text")
        if isinstance(coordinate_text, str):
            _add_recognized_text(recognized_texts, coordinate_text)
        for object_ in observation.spatial_surface.objects:
            _add_recognized_text(recognized_texts, object_.name_text)
            _add_recognized_text(recognized_texts, object_.alliance_tag)
            _add_recognized_text(recognized_texts, object_.kingdom)
            if object_.alliance_tag is not None and object_.name_text is not None:
                _add_recognized_text(recognized_texts, f"{object_.alliance_tag}{object_.name_text}")
    return frozenset(recognized_texts)


def _add_recognized_text(recognized_texts: set[str], text: str | None) -> None:
    """Add one non-blank normalized text hint to the recognized OCR set."""

    if text is not None and (normalized := normalize_ocr_text(text)):
        recognized_texts.add(normalized)


def _unidentified_ocr_lines(
    *, lines: Sequence[OcrLine], recognized_texts: frozenset[str],
) -> tuple[OcrLine, ...]:
    """Return only OCR lines not already represented by the typed observation."""

    return tuple(
        line for line in lines
        if (text := normalize_ocr_text(line.text))
        and not _recognized_text_matches_line(text, recognized_texts)
    )


def _recognized_text_matches_line(normalized_text: str, recognized_texts: frozenset[str]) -> bool:
    """Keep the existing comparison policy for recognized debug phrases."""

    for recognized_text in recognized_texts:
        if normalized_text == recognized_text:
            return True
        if len(normalized_text) >= 4 and len(recognized_text) >= 4:
            if normalized_text in recognized_text or recognized_text in normalized_text:
                return True
    return False
