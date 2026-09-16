"""Canonical typed research node, detail, and queue facts.

The node catalog is the single identity owner for supported institute research
nodes. Vision producers resolve observed labels through
:func:`research_node_for_label`; automation consumers read the typed facts
without re-deriving category, level, or lock state from OCR text.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pnc_automation.app.pnc.domain.policy_models import ResearchCategory, ResourceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.core.vision.image.models import Bounds


class ResearchNodeId(StrEnum):
    """Canonical identities of the supported Development research-tree nodes."""

    CONSTRUCTION_I = "construction_i"
    RESEARCH_SPEED_I = "research_speed_i"
    TROOP_LOAD_I = "troop_load_i"
    STORAGE_I = "storage_i"
    INFIRMARY_CAP_I = "infirmary_cap_i"
    MIRACULOUS_SURVIVAL_I = "miraculous_survival_i"
    TRAINING_SPEED_I = "training_speed_i"
    FAST_HEAL_I = "fast_heal_i"
    FOOD_OUTPUT_I = "food_output_i"


_RESEARCH_NODE_TITLES: dict[ResearchNodeId, str] = {
    ResearchNodeId.CONSTRUCTION_I: "Construction I",
    ResearchNodeId.RESEARCH_SPEED_I: "Research Speed I",
    ResearchNodeId.TROOP_LOAD_I: "Troop Load I",
    ResearchNodeId.STORAGE_I: "Storage I",
    ResearchNodeId.INFIRMARY_CAP_I: "Infirmary Cap I",
    ResearchNodeId.MIRACULOUS_SURVIVAL_I: "Miraculous Survival I",
    ResearchNodeId.TRAINING_SPEED_I: "Training Speed I",
    ResearchNodeId.FAST_HEAL_I: "Fast Heal I",
    ResearchNodeId.FOOD_OUTPUT_I: "Food Output I",
}


def _normalized_node_variants(title: str) -> tuple[str, ...]:
    """Return the bounded OCR variants observed for one tier-I node label.

    Live reads drop or reshape the terminal numeral: ``Construction``,
    ``Storagel``, ``Troop LoadI``, and ``Speed!`` (whose ``!`` normalizes
    away) were all captured on the same node tiles. Variants stay bounded to
    the tier-I family; other tiers or arbitrary suffixes never map.
    """

    base = normalize_ocr_text(title)[: -len("I")]
    return (f"{base}I", f"{base}L", f"{base}1", base)


_RESEARCH_NODE_BY_LABEL: dict[str, ResearchNodeId] = {
    variant: node_id
    for node_id, title in _RESEARCH_NODE_TITLES.items()
    for variant in _normalized_node_variants(title)
}


def research_node_title(node_id: ResearchNodeId) -> str:
    """Return the canonical display title for one supported research node."""

    if not isinstance(node_id, ResearchNodeId):
        raise TypeError("research_node_title requires a ResearchNodeId.")
    return _RESEARCH_NODE_TITLES[node_id]


def research_node_for_label(text: str) -> ResearchNodeId | None:
    """Resolve one normalized OCR node label to its canonical node identity."""

    return _RESEARCH_NODE_BY_LABEL.get(normalize_ocr_text(text))


def research_node_for_title(title_text: str) -> ResearchNodeId | None:
    """Resolve an exact canonical node title, tolerating bounded OCR variants."""

    return research_node_for_label(title_text)


class ResearchQueueState(StrEnum):
    """Explicit queue state observed on a detail panel or queue row."""

    IDLE = "idle"
    ACTIVE = "active"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ResearchNodeFacts:
    """Typed facts measured for one research-tree row.

    ``category`` comes only from the proved tree header; ``node_id`` only from
    the measured label tile; level and lock only from that node's own icon
    region. Every field stays ``None`` when its evidence is absent.
    """

    category: ResearchCategory | None = None
    node_id: ResearchNodeId | None = None
    current_level: int | None = None
    max_level: int | None = None
    locked: bool | None = None
    selected: bool | None = None

    def __post_init__(self) -> None:
        """Reject malformed typed facts instead of publishing partial guesses."""

        if self.category is not None and not isinstance(self.category, ResearchCategory):
            raise TypeError("ResearchNodeFacts.category must be a ResearchCategory or None.")
        if self.node_id is not None and not isinstance(self.node_id, ResearchNodeId):
            raise TypeError("ResearchNodeFacts.node_id must be a ResearchNodeId or None.")
        for field_name in ("current_level", "max_level"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise SelectorResolutionError(
                    f"ResearchNodeFacts.{field_name} must be a non-negative integer or None.",
                    value=value,
                )
        if (self.current_level is None) != (self.max_level is None):
            raise SelectorResolutionError(
                "ResearchNodeFacts levels must be observed together or stay unknown."
            )


@dataclass(frozen=True, slots=True)
class ResearchTextRecord:
    """One bounded text fact measured inside the research detail panel."""

    text: str
    bounds: Bounds

    def __post_init__(self) -> None:
        """Require non-empty text inside measured bounds."""

        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("ResearchTextRecord.text must be non-empty.")
        if not isinstance(self.bounds, Bounds):
            raise TypeError("ResearchTextRecord.bounds must be Bounds.")


@dataclass(frozen=True, slots=True)
class ResearchResourceCost:
    """One resource requirement row measured inside the research detail panel."""

    resource_type: ResourceType | None
    available: int | None
    required: int | None
    text_bounds: Bounds

    def __post_init__(self) -> None:
        """Keep cost rows numeric and bounded; resource type stays optional."""

        if self.resource_type is not None and not isinstance(self.resource_type, ResourceType):
            raise TypeError("ResearchResourceCost.resource_type must be a ResourceType or None.")
        for field_name in ("available", "required"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise SelectorResolutionError(
                    f"ResearchResourceCost.{field_name} must be a non-negative integer or None.",
                    value=value,
                )
        if not isinstance(self.text_bounds, Bounds):
            raise TypeError("ResearchResourceCost.text_bounds must be Bounds.")


@dataclass(frozen=True, slots=True)
class ResearchDetail:
    """Typed facts measured on the research node-detail panel.

    Identity stays owned by the visual detail profile; these facts describe
    the selected node and its costs without authorizing any action.
    ``category`` remains ``None`` unless the panel itself displays it; a
    blurred background header or node title never invents one.
    """

    title_text: str | None = None
    node_id: ResearchNodeId | None = None
    category: ResearchCategory | None = None
    current_level: int | None = None
    max_level: int | None = None
    effect_records: tuple[ResearchTextRecord, ...] = ()
    prerequisite_record: ResearchTextRecord | None = None
    costs: tuple[ResearchResourceCost, ...] = ()
    original_time_text: str | None = None
    actual_time_text: str | None = None
    premium_gem_cost: int | None = None
    premium_button_bounds: Bounds | None = None
    queue_state: ResearchQueueState | None = None
    queue_timer_text: str | None = None
    frame_ref: FrameRef | None = None
    source_screen: ScreenType | None = None
    source_layout_id: str | None = None

    def __post_init__(self) -> None:
        """Keep detail facts typed, paired, and inside the measured panel."""

        if self.node_id is not None and not isinstance(self.node_id, ResearchNodeId):
            raise TypeError("ResearchDetail.node_id must be a ResearchNodeId or None.")
        if self.category is not None and not isinstance(self.category, ResearchCategory):
            raise TypeError("ResearchDetail.category must be a ResearchCategory or None.")
        for field_name in ("current_level", "max_level", "premium_gem_cost"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise SelectorResolutionError(
                    f"ResearchDetail.{field_name} must be a non-negative integer or None.",
                    value=value,
                )
        if (self.current_level is None) != (self.max_level is None):
            raise SelectorResolutionError(
                "ResearchDetail levels must be observed together or stay unknown."
            )
        if self.queue_state is not None and not isinstance(self.queue_state, ResearchQueueState):
            raise TypeError("ResearchDetail.queue_state must be a ResearchQueueState or None.")
        if self.queue_state != ResearchQueueState.ACTIVE and self.queue_timer_text is not None:
            raise SelectorResolutionError(
                "ResearchDetail.queue_timer_text requires an observed active queue."
            )
        if self.premium_button_bounds is not None and not isinstance(self.premium_button_bounds, Bounds):
            raise TypeError("ResearchDetail.premium_button_bounds must be Bounds.")


@dataclass(frozen=True, slots=True)
class ResearchQueueRow:
    """One measured research-queue row with explicit idle/active evidence."""

    bounds: Bounds
    title_text: str | None = None
    state: ResearchQueueState = ResearchQueueState.UNKNOWN
    timer_text: str | None = None
    frame_ref: FrameRef | None = None
    source_screen: ScreenType | None = None
    source_layout_id: str | None = None

    def __post_init__(self) -> None:
        """Require measured row bounds and a typed state."""

        if not isinstance(self.bounds, Bounds):
            raise TypeError("ResearchQueueRow.bounds must be Bounds.")
        if not isinstance(self.state, ResearchQueueState):
            raise TypeError("ResearchQueueRow.state must be a ResearchQueueState.")
        if self.state != ResearchQueueState.ACTIVE and self.timer_text is not None:
            raise SelectorResolutionError(
                "ResearchQueueRow.timer_text requires an observed active row."
            )


def research_entry_category_metadata(
    facts: ResearchNodeFacts | None,
) -> dict[str, str]:
    """Project typed category facts once for generic list-entry consumers.

    ``TapListEntryAction`` resolves rows through ``metadata``; the canonical
    semantic owner is :class:`ResearchNodeFacts`, so this is the only place a
    category value is copied into metadata. No level, cost, or identity data
    is duplicated.
    """

    if facts is None or facts.category is None:
        return {}
    return {"category": facts.category.value}
