"""Produce screen evidence from reviewed, versioned visual anchor groups."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cache
import json
from pathlib import Path
import string

from PIL import Image

from pnc_automation.app.pnc.domain.screen_decision import ScreenDecision, ScreenEvidence
from pnc_automation.app.pnc.domain.observation import VisibleElement, VisibleElementSourceKind
from pnc_automation.app.pnc.domain.popup import (
    PopupControlKind,
    PopupDismissCandidate,
    PopupEvidenceKind,
    PopupOverlayObservation,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher


_BLOCKING_VISUAL_SCREENS = frozenset({
    ScreenType.PNC_POPUP,
    ScreenType.PNC_VIP_DAILY_RESET,
})
# These screens can be observed before the city session has completed login.
# They must not disarm startup/login popup families merely because their base
# anchors matched successfully.
_PRE_LOGIN_SCREEN_TYPES = frozenset({
    ScreenType.ANDROID_HOME,
    ScreenType.PNC_LOADING,
    ScreenType.PNC_LOGIN,
    ScreenType.PNC_ACCOUNT_SWITCH,
    ScreenType.PNC_CASTLE_SELECTION,
})
_VISUAL_DISMISS_KINDS = frozenset({
    PopupControlKind.CANCEL,
    PopupControlKind.CLOSE_TEXT,
    PopupControlKind.CLOSE_X,
    PopupControlKind.POPUP_BACK,
})
_VISUAL_DISMISS_SELECTOR_KINDS = {
    UiElementId.PNC_POPUP_CLOSE_BUTTON: _VISUAL_DISMISS_KINDS,
    UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON: frozenset({PopupControlKind.CLOSE_TEXT}),
    UiElementId.PNC_KING_RETURN_GET_STARTED_BUTTON: frozenset({PopupControlKind.KING_RETURN_GET_STARTED}),
}


@dataclass(frozen=True, slots=True)
class VisualAnchor:
    """One required appearance patch and its bounded reference-frame search region."""

    path: Path
    search_region: Bounds
    threshold: float


@dataclass(frozen=True, slots=True)
class VisualScreenProfile:
    """An anchor variant whose reviewed layout may be shared by other appearances."""

    id: str
    layout_id: str
    screen_type: ScreenType
    revision: int
    source: "VisualProfileSource"
    review: "VisualProfileReview"
    anchors: tuple[VisualAnchor, ...]
    controls: tuple["VisualControl", ...] = ()
    occludes: tuple[ScreenType, ...] = ()
    modal_bounds: Bounds | None = None


@dataclass(frozen=True, slots=True)
class VisualControl:
    """One measured control owned by a recognized visual profile."""

    selector_id: UiElementId
    anchor: VisualAnchor
    dismisses_surface: bool = False
    popup_control_kind: PopupControlKind | None = None


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


@dataclass(slots=True)
class PopupRecognitionSessionState:
    """Conservative popup-family eligibility owned by one observation session."""

    session_key: tuple[str, int] | None = None
    post_login_proven: bool = False
    vip_consumed: bool = False
    valiant_consumed: bool = False
    matched_families: set[str] = field(default_factory=set)

    def reset_for_session(self, session_key: tuple[str, int] | None) -> None:
        """Reset one state owner when the emulator observation session changes."""

        if session_key is None or self.session_key == session_key:
            return
        self.session_key = session_key
        self.post_login_proven = False
        self.vip_consumed = False
        self.valiant_consumed = False
        self.matched_families.clear()

    def observe_base_identity(
        self,
        profiles: tuple["VisualScreenProfile", ...],
        *,
        session_key: tuple[str, int] | None,
    ) -> None:
        """Treat a stable in-game base profile as proof startup/login passed."""

        self.reset_for_session(session_key)
        if session_key is None or not profiles:
            return
        matched_screens = {profile.screen_type for profile in profiles}
        if len(matched_screens) != 1:
            return
        matched_screen = next(iter(matched_screens))
        if matched_screen in _PRE_LOGIN_SCREEN_TYPES:
            return
        self.post_login_proven = True
        if "vip" in self.matched_families:
            self.vip_consumed = True
        if "valiant" in self.matched_families:
            self.valiant_consumed = True

    def allow(self, profile: "VisualScreenProfile") -> bool:
        """Return whether this session may spend matcher work on one popup family."""

        if self.post_login_proven and profile.screen_type in _BLOCKING_VISUAL_SCREENS:
            # Only these delayed families have captured post-Home evidence
            # (Lucifer after startup Home; Growth Boost Weekly Pass after a
            # castle switch surfaced brief Home on 2026-09-22). Keep the
            # established expiry of every other blocking family intact.
            return profile.id in {"lucifer_special_offer", "growth_boost_weekly_pass"}
        if profile.id == "vip_daily_reset":
            return not self.vip_consumed and not self.post_login_proven
        if profile.id == "valiant_conquest":
            return not self.valiant_consumed
        if profile.id.startswith("savannah_hero_offer"):
            return not self.post_login_proven
        if profile.id.startswith("alliance_invitation"):
            return not self.post_login_proven
        return True

    def note_matches(
        self,
        profiles: tuple["VisualScreenProfile", ...],
        *,
        session_key: tuple[str, int] | None,
    ) -> None:
        """Remember active popup families until a later base frame proves transition."""

        self.reset_for_session(session_key)
        if session_key is None:
            return
        for profile in profiles:
            if profile.id == "valiant_conquest":
                self.matched_families.add("valiant")
            elif profile.id == "vip_daily_reset":
                self.matched_families.add("vip")
            elif profile.id.startswith("savannah_hero_offer"):
                self.matched_families.add("savannah")
            elif profile.id.startswith("alliance_invitation"):
                self.matched_families.add("alliance")


@dataclass(frozen=True, slots=True)
class VisualRecognition:
    """Keep competing evidence explicit; similarity is not a probability."""

    evidence: tuple[ScreenEvidence, ...] = ()
    profile_ids: tuple[str, ...] = ()
    controls: tuple[VisibleElement, ...] = ()
    dismiss_controls: tuple[VisibleElement, ...] = ()
    control_selector_ids: frozenset[UiElementId] = frozenset()
    popup_overlay: PopupOverlayObservation | None = None
    declared_popup_control_kinds: frozenset[PopupControlKind] = frozenset()

    @property
    def ambiguous(self) -> bool:
        """Return whether distinct screen interpretations passed their anchor gates."""
        return len({item.screen_type for item in self.evidence}) > 1

    @property
    def needs_generic_popup_close(self) -> bool:
        """Probe modal-owned X geometry only for unknown or unactionable popups.

        Named profiles have already passed session eligibility. A missing
        expected X must not disable independent measurement of the same modal.
        Recognized base screens and already measured dismissals stay zero-work.
        """

        if not self.evidence:
            return True
        return bool(
            all(item.screen_type == ScreenType.PNC_POPUP for item in self.evidence)
            and PopupControlKind.CLOSE_X in self.declared_popup_control_kinds
            and self.popup_overlay is not None
            and self.popup_overlay.evidence_kind == PopupEvidenceKind.KNOWN_LAYOUT
            and self.popup_overlay.modal_bounds is not None
            and not self.popup_overlay.candidates
        )


def visual_controls_for_decision(
    recognition: VisualRecognition,
    decision: ScreenDecision,
    *,
    candidates: Mapping[UiElementId, VisibleElement] | None = None,
) -> dict[UiElementId, VisibleElement]:
    """Publish controls measured on the accepted profile, withholding other variants.

    Legacy candidates may supply other screen-owned facts, but cannot replace a
    measured control or recover its missing template from text or default geometry.
    A screen's alternate profiles also reserve their controls: a tree's Back
    button must not appear behind a detail panel that shares the screen type.
    """

    published = dict(candidates or {})
    if decision.effective_screen in {
        ScreenType.UNKNOWN,
        ScreenType.PNC_LOADING,
    }:
        return published
    if not recognition.evidence or any(
        evidence.screen_type != decision.effective_screen
        or evidence.layout_id != decision.layout_id
        for evidence in recognition.evidence
    ):
        return published
    published = {
        selector_id: element for selector_id, element in published.items()
        if selector_id not in recognition.control_selector_ids
    }
    published.update({control.selector_id: control for control in recognition.controls})
    return published


@dataclass(frozen=True, slots=True)
class VisualScreenRecognizer:
    """Match global screen identity independently of requested OCR content families."""

    profiles: tuple[VisualScreenProfile, ...]
    reference_size: tuple[int, int]
    matcher: OpenCvTemplateMatcher
    popup_state: PopupRecognitionSessionState = field(default_factory=PopupRecognitionSessionState)

    def recognize(
        self,
        image: Image.Image,
        *,
        include_blocking_profiles: bool = True,
        blocking_profiles_only: bool = False,
        session_key: tuple[str, int] | None = None,
    ) -> VisualRecognition:
        """Return matching profiles, optionally excluding popup families for base identity."""
        self.popup_state.reset_for_session(session_key)
        if blocking_profiles_only:
            candidate_profiles = tuple(
                profile for profile in self.profiles
                if profile.screen_type in _BLOCKING_VISUAL_SCREENS
            )
        else:
            candidate_profiles = tuple(
                profile
                for profile in self.profiles
                if include_blocking_profiles or profile.screen_type not in _BLOCKING_VISUAL_SCREENS
            )
        if (blocking_profiles_only or include_blocking_profiles) and session_key is not None:
            candidate_profiles = tuple(
                profile for profile in candidate_profiles if self.popup_state.allow(profile)
            )
        # Eligibility is resolved before any image preparation.  An expired
        # popup phase must be genuinely zero-work, including no full-frame
        # preprocessing, after the base pass proves the session progressed.
        if not candidate_profiles:
            return VisualRecognition()
        prepared_frame = self.matcher.prepare_frame(image, reference_size=self.reference_size)
        if prepared_frame is None:
            return VisualRecognition()
        matching = tuple(
            profile
            for profile in candidate_profiles
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
        if not include_blocking_profiles and not blocking_profiles_only:
            self.popup_state.observe_base_identity(matching, session_key=session_key)
        if blocking_profiles_only or include_blocking_profiles:
            self.popup_state.note_matches(matching, session_key=session_key)
        controls: dict[UiElementId, VisibleElement] = {}
        dismiss_ids: set[UiElementId] = set()
        matched_screens = {profile.screen_type for profile in matching}
        if len(matched_screens) == 1:
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
                        # The profile anchors own identity. Its controls must
                        # not independently reclassify the accepted surface.
                        identity_evidence=False,
                    )
                    controls[control.selector_id] = element
                    if control.dismisses_surface:
                        dismiss_ids.add(control.selector_id)
        popup_overlay: PopupOverlayObservation | None = None
        blocking_profiles = tuple(
            profile for profile in matching if profile.screen_type in {
                ScreenType.PNC_POPUP,
                ScreenType.PNC_VIP_DAILY_RESET,
            }
        )
        blocking_layouts = {profile.layout_id for profile in blocking_profiles}
        if blocking_profiles and len(blocking_layouts) == 1 and len(matched_screens) == 1:
            profile = blocking_profiles[0]
            matched_profile_ids = ",".join(item.id for item in blocking_profiles)
            candidates = tuple(
                PopupDismissCandidate(
                    control_kind=control.popup_control_kind,
                    bounds=controls[control.selector_id].bounds,
                    action_point=controls[control.selector_id].action_point or controls[control.selector_id].bounds.center(),
                    confidence=controls[control.selector_id].confidence,
                    evidence_kind=PopupEvidenceKind.TEMPLATE,
                    reason=f"visual_anchor:{matched_profile_ids}",
                )
                for control in profile.controls
                if (
                    control.dismisses_surface
                    and control.popup_control_kind is not None
                    and control.selector_id in controls
                )
            )
            popup_overlay = PopupOverlayObservation(
                image_size=image.size,
                modal_bounds=(
                    None if profile.modal_bounds is None else _project_bounds(
                        profile.modal_bounds,
                        original_size=image.size,
                        reference_size=self.reference_size,
                    )
                ),
                layout_id=profile.layout_id,
                candidates=candidates,
                confidence=min(
                    (candidate.confidence for candidate in candidates),
                    default=1.0,
                ),
                evidence_kind=PopupEvidenceKind.KNOWN_LAYOUT,
                reason=f"visual_anchor:{matched_profile_ids}",
            )
        return VisualRecognition(
            evidence=tuple(
                ScreenEvidence(
                    profile.screen_type,
                    f"visual_anchor:{profile.id}",
                    layout_id=profile.layout_id,
                    layout_revision=profile.revision,
                )
                for profile in matching
            ),
            profile_ids=tuple(profile.id for profile in matching),
            controls=tuple(controls.values()),
            dismiss_controls=tuple(controls[selector] for selector in sorted(dismiss_ids, key=lambda value: value.value)),
            control_selector_ids=frozenset(
                control.selector_id
                for profile in candidate_profiles if profile.screen_type in matched_screens
                for control in profile.controls
            ),
            popup_overlay=popup_overlay,
            declared_popup_control_kinds=frozenset(
                control.popup_control_kind
                for profile in blocking_profiles
                for control in profile.controls
                if control.dismisses_surface and control.popup_control_kind is not None
            ),
        )


def load_visual_screen_recognizer(
    catalog_path: Path | None = None,
    *,
    matcher: OpenCvTemplateMatcher | None = None,
) -> VisualScreenRecognizer:
    """Load anchor metadata, caching the immutable packaged default recognizer."""

    if catalog_path is None and matcher is None:
        return _load_default_visual_screen_recognizer()
    path = catalog_path or Path(__file__).parent / "data" / "screen_anchors.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or set(document) != {"version", "reference_size", "profiles"}:
        raise ValueError(f"Invalid visual screen catalog fields: {path}")
    if type(document["version"]) is not int or document["version"] != 4:
        raise ValueError("Unsupported visual screen catalog version; expected 4.")
    size = document["reference_size"]
    if not isinstance(size, list) or len(size) != 2 or any(type(v) is not int or v <= 0 for v in size):
        raise ValueError("Visual screen reference_size must contain two positive integers.")
    entries = document["profiles"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("Visual screen profiles must be a non-empty list.")
    profiles: list[VisualScreenProfile] = []
    ids: set[str] = set()
    layout_screens: dict[str, ScreenType] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not {"id", "layout_id", "screen", "revision", "source", "review", "anchors"} <= set(entry):
            raise ValueError("Each visual profile requires id, layout_id, screen, revision, source, review, and anchors.")
        unknown = set(entry) - {"id", "layout_id", "screen", "revision", "source", "review", "anchors", "controls", "occludes", "modal_bounds"}
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
        layout_id = entry["layout_id"]
        if not isinstance(layout_id, str) or not layout_id.strip():
            raise ValueError(f"Visual profile {identifier} requires a non-empty layout_id.")
        if layout_id in layout_screens and layout_screens[layout_id] != screen:
            raise ValueError(f"Visual layout {layout_id} cannot identify different screens.")
        layout_screens[layout_id] = screen
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
            if not isinstance(raw_control, dict) or set(raw_control) - {"selector", "anchor", "dismisses_surface", "popup_control_kind"} or "selector" not in raw_control or "anchor" not in raw_control:
                raise ValueError(f"Visual profile {identifier} has malformed controls.")
            try:
                selector = UiElementId(raw_control["selector"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"Visual profile {identifier} has an invalid control selector.") from error
            dismisses = raw_control.get("dismisses_surface", False)
            if type(dismisses) is not bool:
                raise ValueError(f"Visual profile {identifier} control dismisses_surface must be boolean.")
            popup_control_kind = raw_control.get("popup_control_kind")
            if popup_control_kind is not None:
                try:
                    popup_control_kind = PopupControlKind(popup_control_kind)
                except (TypeError, ValueError) as error:
                    raise ValueError(f"Visual profile {identifier} has an invalid popup control kind.") from error
                if not dismisses:
                    raise ValueError(
                        f"Visual profile {identifier} typed popup control {selector.value} "
                        "must dismiss its surface."
                    )
            if screen in _BLOCKING_VISUAL_SCREENS and dismisses:
                allowed_kinds = _VISUAL_DISMISS_SELECTOR_KINDS.get(selector, frozenset())
                if popup_control_kind is None:
                    raise ValueError(
                        f"Visual profile {identifier} dismiss control {selector.value} "
                        "requires popup_control_kind."
                    )
                if popup_control_kind not in allowed_kinds:
                    raise ValueError(
                        f"Visual profile {identifier} has incompatible popup control kind "
                        f"{popup_control_kind.value} for {selector.value}."
                    )
            controls.append(
                VisualControl(
                    selector_id=selector,
                    anchor=_load_anchor(raw_control["anchor"], root=path.parent, reference_size=tuple(size)),
                    dismisses_surface=dismisses,
                    popup_control_kind=popup_control_kind,
                )
            )
        raw_occludes = entry.get("occludes", [])
        if not isinstance(raw_occludes, list):
            raise ValueError(f"Visual profile {identifier} occludes must be a list.")
        try:
            occludes = tuple(ScreenType[value] for value in raw_occludes)
        except (KeyError, TypeError) as error:
            raise ValueError(f"Visual profile {identifier} has invalid occluded screen types.") from error
        raw_modal_bounds = entry.get("modal_bounds")
        modal_bounds = None
        if raw_modal_bounds is not None:
            if (
                not isinstance(raw_modal_bounds, list)
                or len(raw_modal_bounds) != 4
                or any(type(value) is not int for value in raw_modal_bounds)
            ):
                raise ValueError(f"Visual profile {identifier} modal_bounds must contain four integers.")
            modal_bounds = Bounds(*raw_modal_bounds)
            if (
                modal_bounds.x < 0 or modal_bounds.y < 0
                or modal_bounds.width <= 0 or modal_bounds.height <= 0
                or modal_bounds.x + modal_bounds.width > size[0]
                or modal_bounds.y + modal_bounds.height > size[1]
            ):
                raise ValueError(f"Visual profile {identifier} modal_bounds must fit inside reference_size.")
        profiles.append(VisualScreenProfile(identifier, layout_id, screen, revision, source, review, anchors, tuple(controls), occludes, modal_bounds))
    return VisualScreenRecognizer(tuple(profiles), tuple(size), matcher or OpenCvTemplateMatcher())


@cache
def _load_default_visual_screen_recognizer() -> VisualScreenRecognizer:
    """Validate and construct the packaged recognizer once per process."""

    return load_visual_screen_recognizer(matcher=OpenCvTemplateMatcher())


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


def _project_bounds(
    bounds: Bounds,
    *,
    original_size: tuple[int, int],
    reference_size: tuple[int, int],
) -> Bounds:
    """Project profile geometry from the catalog reference viewport."""

    reference_width, reference_height = reference_size
    original_width, original_height = original_size
    return Bounds(
        x=round(bounds.x * original_width / reference_width),
        y=round(bounds.y * original_height / reference_height),
        width=max(1, round(bounds.width * original_width / reference_width)),
        height=max(1, round(bounds.height * original_height / reference_height)),
    )


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
