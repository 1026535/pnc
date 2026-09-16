"""Canonical typed research node, detail, and queue facts.

The node catalog is the single identity owner for supported institute research
nodes. Vision producers resolve observed labels through
:func:`research_node_for_label`; automation consumers read the typed facts
without re-deriving category, level, or lock state from OCR text.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pnc_automation.app.pnc.domain.policy_models import ResearchCategory
from pnc_automation.app.pnc.domain.resource_cost import ResourceCost
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.core.vision.image.models import Bounds


class ResearchNodeId(StrEnum):
    """Canonical identities of the captured, supported Institute research nodes."""

    CONSTRUCTION_I = "construction_i"
    RESEARCH_SPEED_I = "research_speed_i"
    TROOP_LOAD_I = "troop_load_i"
    STORAGE_I = "storage_i"
    INFIRMARY_CAP_I = "infirmary_cap_i"
    MIRACULOUS_SURVIVAL_I = "miraculous_survival_i"
    TRAINING_SPEED_I = "training_speed_i"
    FAST_HEAL_I = "fast_heal_i"
    FOOD_OUTPUT_I = "food_output_i"
    WOOD_OUTPUT_I = "wood_output_i"
    FOOD_HARVEST_I = "food_harvest_i"
    WOOD_HARVEST_I = "wood_harvest_i"
    IRON_OUTPUT_I = "iron_output_i"
    IRON_HARVEST_I = "iron_harvest_i"
    MARCH_SPEED_I = "march_speed_i"
    INFANTRY_HP_I = "infantry_hp_i"
    INFANTRY_ATK_I = "infantry_atk_i"
    INFANTRY_DEF_I = "infantry_def_i"
    HUNT_MARCH_I = "hunt_march_i"
    SIEGE_ATK_I = "siege_atk_i"
    CAVALRY_ATK_I = "cavalry_atk_i"
    RANGED_ATK_I = "ranged_atk_i"
    MARCH_QUEUE_I = "march_queue_i"
    WALL_DEF_I = "wall_def_i"
    TRAP_ATK_I = "trap_atk_i"
    TRAP_DEF_I = "trap_def_i"
    TRAP_HP_I = "trap_hp_i"
    DEFENDER_ATK_I = "defender_atk_i"
    DEFENDER_DEF_I = "defender_def_i"
    DEFENDER_HP_I = "defender_hp_i"


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
    ResearchNodeId.WOOD_OUTPUT_I: "Wood Output I",
    ResearchNodeId.FOOD_HARVEST_I: "Food Harvest I",
    ResearchNodeId.WOOD_HARVEST_I: "Wood Harvest I",
    ResearchNodeId.IRON_OUTPUT_I: "Iron Output I",
    ResearchNodeId.IRON_HARVEST_I: "Iron Harvest I",
    ResearchNodeId.MARCH_SPEED_I: "March Speed I",
    ResearchNodeId.INFANTRY_HP_I: "Infantry HP I",
    ResearchNodeId.INFANTRY_ATK_I: "Infantry ATK I",
    ResearchNodeId.INFANTRY_DEF_I: "Infantry DEF I",
    ResearchNodeId.HUNT_MARCH_I: "Hunt March I",
    ResearchNodeId.SIEGE_ATK_I: "Siege ATK I",
    ResearchNodeId.CAVALRY_ATK_I: "Cavalry ATK I",
    ResearchNodeId.RANGED_ATK_I: "Ranged ATK I",
    ResearchNodeId.MARCH_QUEUE_I: "March Queue I",
    ResearchNodeId.WALL_DEF_I: "Wall DEF I",
    ResearchNodeId.TRAP_ATK_I: "Trap ATK I",
    ResearchNodeId.TRAP_DEF_I: "Trap DEF I",
    ResearchNodeId.TRAP_HP_I: "Trap HP I",
    ResearchNodeId.DEFENDER_ATK_I: "Defender ATK I",
    ResearchNodeId.DEFENDER_DEF_I: "Defender DEF I",
    ResearchNodeId.DEFENDER_HP_I: "Defender HP I",
}


@dataclass(frozen=True, slots=True)
class ResearchCategoryDefinition:
    """One qualified Institute category, its entry, layout and supported nodes."""

    category: ResearchCategory
    title: str
    layout_id: str
    entry_selector: UiElementId
    node_ids: frozenset[ResearchNodeId]


RESEARCH_CATEGORY_DEFINITIONS = (
    ResearchCategoryDefinition(
        ResearchCategory.DEVELOPMENT, "Development", "research_tree_development",
        UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON,
        frozenset({ResearchNodeId.CONSTRUCTION_I, ResearchNodeId.RESEARCH_SPEED_I,
                   ResearchNodeId.TROOP_LOAD_I, ResearchNodeId.STORAGE_I,
                   ResearchNodeId.INFIRMARY_CAP_I, ResearchNodeId.MIRACULOUS_SURVIVAL_I,
                   ResearchNodeId.TRAINING_SPEED_I, ResearchNodeId.FAST_HEAL_I,
                   ResearchNodeId.FOOD_OUTPUT_I}),
    ),
    ResearchCategoryDefinition(
        ResearchCategory.ECONOMY, "Economy", "research_tree_economy",
        UiElementId.PNC_INSTITUTE_ECONOMY_BUTTON,
        frozenset({ResearchNodeId.FOOD_OUTPUT_I, ResearchNodeId.WOOD_OUTPUT_I,
                   ResearchNodeId.FOOD_HARVEST_I, ResearchNodeId.WOOD_HARVEST_I,
                   ResearchNodeId.IRON_OUTPUT_I, ResearchNodeId.IRON_HARVEST_I}),
    ),
    ResearchCategoryDefinition(
        ResearchCategory.MILITARY, "Military", "research_tree_military",
        UiElementId.PNC_INSTITUTE_MILITARY_BUTTON,
        frozenset({ResearchNodeId.MARCH_SPEED_I, ResearchNodeId.INFANTRY_HP_I,
                   ResearchNodeId.INFANTRY_ATK_I, ResearchNodeId.INFANTRY_DEF_I,
                   ResearchNodeId.HUNT_MARCH_I, ResearchNodeId.SIEGE_ATK_I,
                   ResearchNodeId.CAVALRY_ATK_I, ResearchNodeId.RANGED_ATK_I,
                   ResearchNodeId.MARCH_QUEUE_I}),
    ),
    ResearchCategoryDefinition(
        ResearchCategory.FORTIFICATION, "Fortification", "research_tree_fortification",
        UiElementId.PNC_INSTITUTE_FORTIFICATION_BUTTON,
        frozenset({ResearchNodeId.WALL_DEF_I, ResearchNodeId.TRAP_ATK_I,
                   ResearchNodeId.TRAP_DEF_I, ResearchNodeId.TRAP_HP_I,
                   ResearchNodeId.DEFENDER_ATK_I, ResearchNodeId.DEFENDER_DEF_I,
                   ResearchNodeId.DEFENDER_HP_I}),
    ),
)


def research_category_definition(category: ResearchCategory) -> ResearchCategoryDefinition:
    """Resolve one typed category to its canonical qualified definition."""
    if not isinstance(category, ResearchCategory):
        raise TypeError("research_category_definition requires a ResearchCategory.")
    return next(item for item in RESEARCH_CATEGORY_DEFINITIONS if item.category is category)


def research_category_for_layout(layout_id: str | None) -> ResearchCategory | None:
    """Return the category proved by a qualified tree layout, or None."""
    return next((item.category for item in RESEARCH_CATEGORY_DEFINITIONS
                 if item.layout_id == layout_id), None)


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


def research_node_for_label(
    text: str, *, category: ResearchCategory | None = None,
) -> ResearchNodeId | None:
    """Resolve one normalized OCR node label to its canonical node identity."""

    node_id = _RESEARCH_NODE_BY_LABEL.get(normalize_ocr_text(text))
    if category is not None and node_id not in research_category_definition(category).node_ids:
        return None
    return node_id


def research_node_for_title(
    title_text: str, *, category: ResearchCategory | None = None,
) -> ResearchNodeId | None:
    """Resolve an exact canonical node title, tolerating bounded OCR variants."""

    return research_node_for_label(title_text, category=category)


class ResearchQueueState(StrEnum):
    """Explicit queue state observed on a detail panel or queue row."""

    IDLE = "idle"
    ACTIVE = "active"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ResearchNodeFacts:
    """Typed facts measured for one research-tree row.

    ``category`` comes only from the proved category layout; ``node_id`` only from
    the measured label tile; level and lock only from that node's own icon
    region. Every field stays ``None`` when its evidence is absent. A literal
    MAX badge sets ``maximum_reached`` without inventing numeric levels.
    """

    category: ResearchCategory | None = None
    node_id: ResearchNodeId | None = None
    current_level: int | None = None
    max_level: int | None = None
    locked: bool | None = None
    selected: bool | None = None
    maximum_reached: bool | None = None

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
        if self.maximum_reached is not None and not isinstance(self.maximum_reached, bool):
            raise TypeError("ResearchNodeFacts.maximum_reached must be bool or None.")
        if (
            self.maximum_reached is not None and self.current_level is not None
            and self.maximum_reached != (self.current_level == self.max_level)
        ):
            raise ValueError("ResearchNodeFacts.maximum_reached contradicts its observed levels.")


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
    costs: tuple[ResourceCost, ...] = ()
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
