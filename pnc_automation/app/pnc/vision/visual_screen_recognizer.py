"""Produce screen evidence from reviewed, versioned visual anchor groups."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.domain.observation import VisibleElement
from pnc_automation.app.pnc.vision.screen_classifier import ScreenEvidence
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher


@dataclass(frozen=True, slots=True)
class VisualAnchor:
    """One required appearance patch and its bounded reference-frame search region."""

    path: Path
    search_region: Bounds
    threshold: float


@dataclass(frozen=True, slots=True)
class VisualControl:
    """A control whose clickable bounds must be detected on this frame."""

    selector_id: UiElementId
    anchor: VisualAnchor
    dismisses_surface: bool = False


@dataclass(frozen=True, slots=True)
class VisualScreenProfile:
    """An all-required group of anchors for one reviewed screen variant."""

    id: str
    screen_type: ScreenType
    anchors: tuple[VisualAnchor, ...]
    controls: tuple[VisualControl, ...] = ()
    occludes: frozenset[ScreenType] = frozenset()


@dataclass(frozen=True, slots=True)
class VisualRecognition:
    """Keep competing evidence explicit; similarity is not a probability."""

    evidence: tuple[ScreenEvidence, ...] = ()
    profile_ids: tuple[str, ...] = ()
    controls: tuple[VisibleElement, ...] = ()
    dismiss_controls: tuple[VisibleElement, ...] = ()

    @property
    def ambiguous(self) -> bool:
        """Return whether distinct screen interpretations passed their anchor gates."""
        return len({item.screen_type for item in self.evidence}) > 1


@dataclass(frozen=True, slots=True)
class VisualScreenRecognizer:
    """Match global screen identity independently of requested OCR content families."""

    profiles: tuple[VisualScreenProfile, ...]
    reference_size: tuple[int, int]
    matcher: OpenCvTemplateMatcher

    def recognize(self, image: Image.Image) -> VisualRecognition:
        """Return all matching profiles; the canonical classifier resolves evidence."""
        matching = tuple(
            profile
            for profile in self.profiles
            if all(
                self.matcher.find_best_match(
                    image,
                    anchor.path,
                    threshold=anchor.threshold,
                    search_region=anchor.search_region,
                    reference_size=self.reference_size,
                ) is not None
                for anchor in profile.anchors
            )
        )
        # An observed overlay can cover a still-visible root. Only authored
        # containment relationships resolve overlap; unrelated matches abstain.
        occluded = {screen for profile in matching for screen in profile.occludes}
        matching = tuple(profile for profile in matching if profile.screen_type not in occluded)
        controls: dict[UiElementId, VisibleElement] = {}
        dismiss_ids: set[UiElementId] = set()
        if len({profile.screen_type for profile in matching}) == 1:
            for profile in matching:
                for control in profile.controls:
                    match = self.matcher.find_best_match(
                        image, control.anchor.path, threshold=control.anchor.threshold,
                        search_region=control.anchor.search_region,
                        reference_size=self.reference_size,
                    )
                    if match is not None:
                        controls[control.selector_id] = VisibleElement(
                            control.selector_id, match.bounds, match.confidence,
                        )
                        if control.dismisses_surface:
                            dismiss_ids.add(control.selector_id)
        return VisualRecognition(
            evidence=tuple(
                ScreenEvidence(profile.screen_type, f"visual_anchor:{profile.id}")
                for profile in matching
            ),
            profile_ids=tuple(profile.id for profile in matching),
            controls=tuple(controls.values()),
            dismiss_controls=tuple(controls[selector] for selector in sorted(dismiss_ids, key=lambda value: value.value)),
        )


def load_visual_screen_recognizer(
    catalog_path: Path | None = None,
    *,
    matcher: OpenCvTemplateMatcher | None = None,
) -> VisualScreenRecognizer:
    """Load packaged anchor metadata, rejecting malformed or missing assets eagerly."""
    path = catalog_path or Path(__file__).parent / "data" / "screen_anchors.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or set(document) != {"version", "reference_size", "profiles"}:
        raise ValueError(f"Invalid visual screen catalog fields: {path}")
    if type(document["version"]) is not int or document["version"] != 1:
        raise ValueError("Unsupported visual screen catalog version; expected 1.")
    size = document["reference_size"]
    if not isinstance(size, list) or len(size) != 2 or any(type(v) is not int or v <= 0 for v in size):
        raise ValueError("Visual screen reference_size must contain two positive integers.")
    entries = document["profiles"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("Visual screen profiles must be a non-empty list.")
    profiles: list[VisualScreenProfile] = []
    ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not {"id", "screen", "anchors"} <= set(entry) or set(entry) - {"id", "screen", "anchors", "controls", "occludes"}:
            raise ValueError("Each visual profile requires exactly id, screen, and anchors.")
        identifier = entry["id"]
        if not isinstance(identifier, str) or not identifier or identifier in ids:
            raise ValueError("Visual profile IDs must be non-empty and unique.")
        ids.add(identifier)
        try:
            screen = ScreenType[entry["screen"]]
        except (KeyError, TypeError) as error:
            raise ValueError(f"Invalid screen for visual profile {identifier}.") from error
        if screen == ScreenType.UNKNOWN:
            raise ValueError("UNKNOWN cannot be a positive visual profile.")
        raw_anchors = entry["anchors"]
        if not isinstance(raw_anchors, list) or len(raw_anchors) < 2:
            raise ValueError(f"Visual profile {identifier} requires at least two anchors.")
        anchors = tuple(_load_anchor(item, root=path.parent, reference_size=tuple(size)) for item in raw_anchors)
        if len({anchor.path for anchor in anchors}) != len(anchors):
            raise ValueError(f"Visual profile {identifier} repeats an anchor asset.")
        raw_controls = entry.get("controls", [])
        if not isinstance(raw_controls, list):
            raise ValueError(f"Visual profile {identifier} controls must be a list.")
        controls: list[VisualControl] = []
        for control in raw_controls:
            if not isinstance(control, dict) or not {"selector", "anchor"} <= set(control) or set(control) - {"selector", "anchor", "dismisses_surface"}:
                raise ValueError("Each visual control requires exactly selector and anchor.")
            try:
                selector = UiElementId(control["selector"])
            except (ValueError, TypeError) as error:
                raise ValueError(f"Invalid control selector in {identifier}.") from error
            if any(item.selector_id == selector for item in controls):
                raise ValueError(f"Duplicate control selector in {identifier}.")
            dismisses = control.get("dismisses_surface", False)
            if type(dismisses) is not bool:
                raise ValueError("Control dismisses_surface must be a boolean.")
            controls.append(VisualControl(selector, _load_anchor(control["anchor"], root=path.parent, reference_size=tuple(size)), dismisses))
        raw_occludes = entry.get("occludes", [])
        if not isinstance(raw_occludes, list):
            raise ValueError("Visual profile occludes must be a list of screen names.")
        try:
            occludes = frozenset(ScreenType[name] for name in raw_occludes)
        except (KeyError, TypeError) as error:
            raise ValueError("Invalid occluded screen.") from error
        if screen in occludes or ScreenType.UNKNOWN in occludes:
            raise ValueError("A profile cannot occlude itself or UNKNOWN.")
        profiles.append(VisualScreenProfile(identifier, screen, anchors, tuple(controls), occludes))
    return VisualScreenRecognizer(tuple(profiles), tuple(size), matcher or OpenCvTemplateMatcher())


def _load_anchor(entry: object, *, root: Path, reference_size: tuple[int, int]) -> VisualAnchor:
    """Validate one local asset and its reference-frame region and score gate."""
    if not isinstance(entry, dict) or set(entry) != {"image", "search_region", "threshold"}:
        raise ValueError("Each anchor requires exactly image, search_region, and threshold.")
    image_name = entry["image"]
    if not isinstance(image_name, str) or not image_name:
        raise ValueError("Anchor image must be a local relative path.")
    path = (root / image_name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Missing or out-of-catalog visual anchor: {image_name}")
    region = entry["search_region"]
    if not isinstance(region, list) or len(region) != 4 or any(type(v) is not int for v in region):
        raise ValueError("Anchor search_region must contain four integers.")
    x, y, width, height = region
    if min(x, y) < 0 or min(width, height) <= 0 or x + width > reference_size[0] or y + height > reference_size[1]:
        raise ValueError("Anchor search_region is outside the reference frame.")
    threshold = entry["threshold"]
    if type(threshold) not in (int, float) or not 0 < threshold <= 1:
        raise ValueError("Anchor threshold must be a finite number in (0, 1].")
    with Image.open(path) as image:
        image.verify()
        if image.width > width or image.height > height:
            raise ValueError(f"Anchor {image_name} cannot fit inside its search region.")
    return VisualAnchor(path, Bounds(x, y, width, height), float(threshold))
