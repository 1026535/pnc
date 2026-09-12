"""Produce screen evidence from reviewed, versioned visual anchor groups."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import string

from PIL import Image

from pnc_automation.app.pnc.domain.screen_decision import ScreenEvidence
from pnc_automation.app.pnc.domain.observation import VisibleElement, VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher


@dataclass(frozen=True, slots=True)
class VisualAnchor:
    """One required appearance patch and its bounded reference-frame search region."""

    path: Path
    search_region: Bounds
    threshold: float


@dataclass(frozen=True, slots=True)
class VisualScreenProfile:
    """An all-required group of anchors for one reviewed screen variant."""

    id: str
    screen_type: ScreenType
    revision: int
    source: "VisualProfileSource"
    review: "VisualProfileReview"
    anchors: tuple[VisualAnchor, ...]
    controls: tuple["VisualControl", ...] = ()
    occludes: tuple[ScreenType, ...] = ()


@dataclass(frozen=True, slots=True)
class VisualControl:
    """One measured control owned by a recognized visual profile."""

    selector_id: UiElementId
    anchor: VisualAnchor
    dismisses_surface: bool = False


@dataclass(frozen=True, slots=True)
class VisualProfileSource:
    """Immutable provenance for the reviewed source frame behind one profile."""

    fixture: str
    decoded_sha256: str
    capture_group: str


@dataclass(frozen=True, slots=True)
class VisualProfileReview:
    """Immutable review metadata that does not affect runtime matching."""

    reference_manifest: str
    description: str
    build: str | None
    locale: str | None
    qualification: str


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
        prepared_frame = self.matcher.prepare_frame(image, reference_size=self.reference_size)
        if prepared_frame is None:
            return VisualRecognition()
        matching = tuple(
            profile
            for profile in self.profiles
            if all(
                self.matcher.find_best_match(
                    prepared_frame,
                    anchor.path,
                    threshold=anchor.threshold,
                    search_region=anchor.search_region,
                ) is not None
                for anchor in profile.anchors
            )
        )
        occluded_screens = {
            screen
            for profile in matching
            for screen in profile.occludes
        }
        if occluded_screens:
            matching = tuple(
                profile
                for profile in matching
                if profile.screen_type not in occluded_screens
            )
        controls: dict[UiElementId, VisibleElement] = {}
        dismiss_ids: set[UiElementId] = set()
        if len({profile.screen_type for profile in matching}) == 1:
            for profile in matching:
                for control in profile.controls:
                    match = self.matcher.find_best_match(
                        prepared_frame,
                        control.anchor.path,
                        threshold=control.anchor.threshold,
                        search_region=control.anchor.search_region,
                    )
                    if match is None:
                        continue
                    element = VisibleElement(
                        selector_id=control.selector_id,
                        bounds=match.bounds,
                        confidence=match.confidence,
                        source_kind=VisibleElementSourceKind.TEMPLATE,
                        action_point=match.bounds.center(),
                    )
                    controls[control.selector_id] = element
                    if control.dismisses_surface:
                        dismiss_ids.add(control.selector_id)
        return VisualRecognition(
            evidence=tuple(
                ScreenEvidence(
                    profile.screen_type,
                    f"visual_anchor:{profile.id}",
                    layout_id=profile.id,
                    layout_revision=profile.revision,
                )
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
    if type(document["version"]) is not int or document["version"] != 2:
        raise ValueError("Unsupported visual screen catalog version; expected 2.")
    size = document["reference_size"]
    if not isinstance(size, list) or len(size) != 2 or any(type(v) is not int or v <= 0 for v in size):
        raise ValueError("Visual screen reference_size must contain two positive integers.")
    entries = document["profiles"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("Visual screen profiles must be a non-empty list.")
    profiles: list[VisualScreenProfile] = []
    ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not {"id", "screen", "revision", "source", "review", "anchors"} <= set(entry):
            raise ValueError("Each visual profile requires id, screen, revision, source, review, and anchors.")
        unknown = set(entry) - {"id", "screen", "revision", "source", "review", "anchors", "controls", "occludes"}
        if unknown:
            raise ValueError(f"Visual profile has unknown fields: {sorted(unknown)}")
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
        revision = entry["revision"]
        if type(revision) is not int or revision <= 0:
            raise ValueError(f"Visual profile {identifier} revision must be a positive integer.")
        source = _load_profile_source(entry["source"], identifier=identifier)
        review = _load_profile_review(entry["review"], identifier=identifier)
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
        for raw_control in raw_controls:
            if not isinstance(raw_control, dict) or set(raw_control) - {"selector", "anchor", "dismisses_surface"} or "selector" not in raw_control or "anchor" not in raw_control:
                raise ValueError(f"Visual profile {identifier} has malformed controls.")
            try:
                selector = UiElementId(raw_control["selector"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"Visual profile {identifier} has an invalid control selector.") from error
            dismisses = raw_control.get("dismisses_surface", False)
            if type(dismisses) is not bool:
                raise ValueError(f"Visual profile {identifier} control dismisses_surface must be boolean.")
            controls.append(
                VisualControl(
                    selector_id=selector,
                    anchor=_load_anchor(raw_control["anchor"], root=path.parent, reference_size=tuple(size)),
                    dismisses_surface=dismisses,
                )
            )
        raw_occludes = entry.get("occludes", [])
        if not isinstance(raw_occludes, list):
            raise ValueError(f"Visual profile {identifier} occludes must be a list.")
        try:
            occludes = tuple(ScreenType[value] for value in raw_occludes)
        except (KeyError, TypeError) as error:
            raise ValueError(f"Visual profile {identifier} has invalid occluded screen types.") from error
        profiles.append(VisualScreenProfile(identifier, screen, revision, source, review, anchors, tuple(controls), occludes))
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


def _load_profile_source(entry: object, *, identifier: str) -> VisualProfileSource:
    """Validate source provenance without resolving artifact paths at runtime."""
    if not isinstance(entry, dict) or set(entry) != {"fixture", "decoded_sha256", "capture_group"}:
        raise ValueError(f"Visual profile {identifier} source requires fixture, decoded_sha256, and capture_group.")
    fixture = entry["fixture"]
    if not isinstance(fixture, str) or not fixture or Path(fixture).is_absolute() or ".." in Path(fixture).parts:
        raise ValueError(f"Visual profile {identifier} source fixture must be a relative path without traversal.")
    digest = entry["decoded_sha256"]
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in string.hexdigits for character in digest)
    ):
        raise ValueError(f"Visual profile {identifier} source decoded_sha256 must be a 64-character hex digest.")
    capture_group = entry["capture_group"]
    if not isinstance(capture_group, str) or not capture_group.strip():
        raise ValueError(f"Visual profile {identifier} source capture_group must be a non-empty string.")
    return VisualProfileSource(fixture=fixture, decoded_sha256=digest.lower(), capture_group=capture_group)


def _load_profile_review(entry: object, *, identifier: str) -> VisualProfileReview:
    """Validate review metadata while keeping build and locale explicitly nullable."""
    required = {"reference_manifest", "description", "build", "locale", "qualification"}
    if not isinstance(entry, dict) or set(entry) != required:
        raise ValueError(f"Visual profile {identifier} review metadata is incomplete or has unknown fields.")
    reference_manifest = entry["reference_manifest"]
    description = entry["description"]
    if (
        not isinstance(reference_manifest, str)
        or not reference_manifest
        or Path(reference_manifest).is_absolute()
        or ".." in Path(reference_manifest).parts
    ):
        raise ValueError(f"Visual profile {identifier} reference_manifest must be a relative path without traversal.")
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"Visual profile {identifier} review description must be a non-empty string.")
    build = entry["build"]
    locale = entry["locale"]
    for field_name, value in (("build", build), ("locale", locale)):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"Visual profile {identifier} review {field_name} must be a string or null.")
    if entry["qualification"] != "guarded_reference_only":
        raise ValueError(f"Visual profile {identifier} has an unsupported review qualification.")
    return VisualProfileReview(
        reference_manifest=reference_manifest,
        description=description,
        build=build,
        locale=locale,
        qualification="guarded_reference_only",
    )
