"""Canonical immutable Pet Workshop logical models and action contracts.

This module owns the shared types exchanged between the Workshop recognizer
(PW02), the pure solver (Plan 02, packages PW03/PW04) and the execution
boundary (Plan 03). ``WorkshopState`` is the coordinate-free logical reading
of one frame; ``WorkshopView`` holds the measured geometry and capture
provenance for the same frame; the published ``WorkshopObservation``
composes both so a solver never sees pixels and an executor never re-reads
state.

Every reading is explicit about knowledge: ``None`` marks an unread numeric
fact, dedicated enum members mark unknown item/selection/survey states, and
excluded surfaces or rewards stay representable instead of being rejected.
The models never invent server order ids, predicted spawn positions, exact
cooldown deadlines, remaining finite-producer uses, or inferred prerequisite
completion. Logical construction performs no runtime I/O.

The pure interface contract agreed with downstream packets is fixed here as
typed callables without implementations:

- ``plan_next(state, catalog, policy) -> WorkshopDecision`` (PW04) selects
  one logical action for the current state.
- ``validate_intent(state, intent, catalog, policy) ->
  WorkshopIntentValidation`` (PW03) is the single legal-action check reused
  by the planner and by fresh-state revalidation before execution.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import ClassVar, Protocol

from pnc_automation.app.pnc.domain.observation import RowRecognitionStatus
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.pet_workshop_catalog import (
    PetWorkshopCatalog,
    WorkshopBoardLayout,
)
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.vision.image.models import Bounds


class WorkshopSurfaceKind(StrEnum):
    """Identifies which Pet Workshop surface the observed frame shows."""

    BOARD = "board"
    ITEM_DETAIL = "item_detail"
    ORDER_DETAIL = "order_detail"
    HELP = "help"
    EXCLUDED_MODAL = "excluded_modal"
    UNKNOWN = "unknown"


class WorkshopProductionMode(StrEnum):
    """The production mode the observed Workshop surface supports.

    ``ORDINARY`` is per-produce manual production spending the shared energy
    currency. ``AUTO_FUSION`` is a premium surface that the agreed mechanics
    exclude; it stays representable so the planner can stop on it explicitly.
    """

    ORDINARY = "ordinary"
    AUTO_FUSION = "auto_fusion"
    UNKNOWN = "unknown"


class WorkshopCellAccess(StrEnum):
    """Whether a board cell can hold usable pieces, apart from occupancy."""

    USABLE = "usable"
    LOCKED = "locked"
    UNKNOWN = "unknown"


class WorkshopOccupancy(StrEnum):
    """Whether a measured cell holds a piece, apart from its access state."""

    EMPTY = "empty"
    OCCUPIED = "occupied"
    UNKNOWN = "unknown"


class WorkshopItemStatus(StrEnum):
    """The observed interaction state of a piece occupying a cell.

    ``INACTIVE`` is a grey piece activated only by a matching merge;
    ``BUBBLE`` is an encased piece outside ordinary activation; ``FEED_LOCKED``
    is a producer visibly awaiting its catalog feed ingredient. ``UNKNOWN``
    means a piece is present but its overlay/state was not read.
    """

    NORMAL = "normal"
    INACTIVE = "inactive"
    BUBBLE = "bubble"
    FEED_LOCKED = "feed_locked"
    UNKNOWN = "unknown"


class WorkshopCooldown(StrEnum):
    """The visible cooldown marker on one cell; no deadline is measured."""

    CLEAR = "clear"
    ACTIVE = "active"
    UNKNOWN = "unknown"


class WorkshopSelectionKind(StrEnum):
    """Whether the board selection is a known cell, known absent, or unread."""

    SELECTED = "selected"
    NONE = "none"
    UNKNOWN = "unknown"


class WorkshopInspectKind(StrEnum):
    """Logical information needs an Inspect intent can name."""

    ORDER_CONTENTS = "order_contents"
    CELL_STATE = "cell_state"
    ORDER_SURVEY = "order_survey"
    BOARD = "board"


class WorkshopStopReason(StrEnum):
    """The typed reason a planner or executor ends the current Workshop work."""

    ZERO_ENERGY = "zero_energy"
    BOARD_BLOCKED = "board_blocked"
    NO_ELIGIBLE_GOAL = "no_eligible_goal"
    COOLDOWN_TIMEOUT = "cooldown_timeout"
    EXCLUDED_SURFACE = "excluded_surface"
    UNRESOLVED_STATE = "unresolved_state"


class WorkshopIntentKind(StrEnum):
    """The logical action families shared by the planner and the executor."""

    SELECT = "select"
    PRODUCE = "produce"
    MERGE = "merge"
    ACTIVATE = "activate"
    FEED = "feed"
    RECYCLE = "recycle"
    SUBMIT_ORDER = "submit_order"
    INSPECT = "inspect"
    WAIT = "wait"
    STOP = "stop"


class WorkshopOrderRewardCategory(StrEnum):
    """Reward families the recognizer can name; unknown/other stay representable."""

    BEAST_LASSO = "beast_lasso"
    FEED = "feed"
    WORKSHOP_EXP = "workshop_exp"
    BOTTLE = "bottle"
    CHEST = "chest"
    OTHER = "other"
    UNKNOWN = "unknown"


class WorkshopSurveyCoverage(StrEnum):
    """How much of the reachable order strip the survey measured."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class WorkshopSurveyFreshness(StrEnum):
    """Whether the order survey reflects the current frame or stale state."""

    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"


class WorkshopValidationVerdict(StrEnum):
    """The outcome of validating one intent against a fresh state.

    ``UNCERTAIN`` means facts the intent depends on were never observed; the
    caller must inspect and revalidate rather than treating unknown as legal.
    """

    LEGAL = "legal"
    ILLEGAL = "illegal"
    UNCERTAIN = "uncertain"


def _require_positive_int(value: int | None, what: str) -> int:
    """Returns a strict positive int, rejecting bools, ``None`` and zero."""

    if type(value) is not int or value <= 0:
        raise ValueError(f"{what} must be a positive integer, got {value!r}.")
    return value


def _optional_positive_int(value: int | None, what: str) -> int | None:
    """Returns ``None`` or a strict positive int for optional id/count fields."""

    if value is None:
        return None
    return _require_positive_int(value, what)


def _quantity_map(raw: Mapping[int, int], owner: str) -> Mapping[int, int]:
    """Validates an item-id -> quantity map and returns an immutable copy."""

    if not isinstance(raw, Mapping):
        raise TypeError(f"{owner} must be a mapping of item id to quantity.")
    checked: dict[int, int] = {}
    for item_id, quantity in raw.items():
        _require_positive_int(item_id, f"{owner} item id")
        _require_positive_int(quantity, f"{owner} quantity for item {item_id}")
        checked[item_id] = quantity
    return MappingProxyType(checked)


@dataclass(frozen=True, slots=True)
class WorkshopCell:
    """Logical state of one observed board cell; carries no screen geometry.

    ``cell_id``, ``row`` and ``column`` are 1-based logical addresses matching
    ``cell_id = (row - 1) * columns + column``. ``access`` is the cell's
    usability (for example a level-locked square) and is independent of
    ``occupancy``. ``item_id`` and ``item_status`` describe the occupying
    piece; an ``OCCUPIED`` cell may still carry ``item_id=None`` when a piece
    is visible but its identity was not read. An unread square defaults to
    unknown access/occupancy and carries no item facts. ``cooldown`` is the visible
    cooldown marker only — an absent icon is ``CLEAR``, an unread one is
    ``UNKNOWN``, and no deadline is inferred.
    """

    cell_id: int
    row: int
    column: int
    access: WorkshopCellAccess = WorkshopCellAccess.UNKNOWN
    occupancy: WorkshopOccupancy = WorkshopOccupancy.UNKNOWN
    item_id: int | None = None
    item_status: WorkshopItemStatus | None = None
    cooldown: WorkshopCooldown = WorkshopCooldown.UNKNOWN

    def __post_init__(self) -> None:
        """Rejects malformed addresses and inconsistent occupancy/item pairs."""

        _require_positive_int(self.cell_id, "WorkshopCell cell_id")
        _require_positive_int(self.row, "WorkshopCell row")
        _require_positive_int(self.column, "WorkshopCell column")
        if not isinstance(self.access, WorkshopCellAccess):
            raise TypeError(f"WorkshopCell access must be a WorkshopCellAccess, got {self.access!r}.")
        if not isinstance(self.occupancy, WorkshopOccupancy):
            raise TypeError(f"WorkshopCell occupancy must be a WorkshopOccupancy, got {self.occupancy!r}.")
        if not isinstance(self.cooldown, WorkshopCooldown):
            raise TypeError(f"WorkshopCell cooldown must be a WorkshopCooldown, got {self.cooldown!r}.")
        _optional_positive_int(self.item_id, f"WorkshopCell {self.cell_id} item_id")
        if self.item_status is not None and not isinstance(self.item_status, WorkshopItemStatus):
            raise TypeError(
                f"WorkshopCell item_status must be a WorkshopItemStatus, got {self.item_status!r}."
            )
        if self.occupancy == WorkshopOccupancy.EMPTY:
            if self.item_id is not None or self.item_status is not None:
                raise ValueError("An empty WorkshopCell cannot carry item facts.")
        elif self.occupancy == WorkshopOccupancy.OCCUPIED and self.item_status is None:
            raise ValueError(
                "An occupied WorkshopCell requires an item_status "
                "(WorkshopItemStatus.UNKNOWN when the state was not read)."
            )


@dataclass(frozen=True, slots=True)
class WorkshopSelection:
    """The observed board selection, keeping known-none distinct from unknown.

    ``kind=SELECTED`` requires the selected ``cell_id``; ``NONE`` and
    ``UNKNOWN`` carry no cell. The distinction matters because a repeated tap
    on a selected producer consumes energy and produces a piece.
    """

    kind: WorkshopSelectionKind
    cell_id: int | None = None

    def __post_init__(self) -> None:
        """Rejects a selected selection without a cell or a cell without selection."""

        if not isinstance(self.kind, WorkshopSelectionKind):
            raise TypeError(f"WorkshopSelection kind must be a WorkshopSelectionKind, got {self.kind!r}.")
        if self.kind == WorkshopSelectionKind.SELECTED:
            _require_positive_int(self.cell_id, "WorkshopSelection cell_id")
        elif self.cell_id is not None:
            raise ValueError("A non-selected WorkshopSelection cannot carry a cell_id.")


@dataclass(frozen=True, slots=True)
class WorkshopEnergy:
    """The observed energy bar; ``None`` fields are explicitly unknown.

    ``current`` counts energy units on the bar (0 is a reliable stop signal,
    distinct from an unread ``None``) and may exceed the authored capacity
    when level-up or refund gains push the bar over the regeneration cap.
    ``capacity`` is the observed capacity label when read.
    """

    current: int | None = None
    capacity: int | None = None

    def __post_init__(self) -> None:
        """Rejects negative readings while keeping over-cap values representable."""

        if self.current is not None and (type(self.current) is not int or self.current < 0):
            raise ValueError(f"WorkshopEnergy current must be a non-negative integer, got {self.current!r}.")
        _optional_positive_int(self.capacity, "WorkshopEnergy capacity")

    @property
    def known(self) -> bool:
        """Returns whether the current energy reading was observed."""

        return self.current is not None

    @property
    def is_zero(self) -> bool:
        """Returns whether zero energy was reliably observed (never for unknown)."""

        return self.current == 0


@dataclass(frozen=True, slots=True)
class WorkshopOrderReward:
    """One reward line on an observed order card.

    ``quantity`` is the observed count, or ``None`` when the category is
    recognized but its count was not read. ``label`` preserves the raw
    observed reward text, primarily for ``OTHER``/``UNKNOWN`` categories.
    """

    category: WorkshopOrderRewardCategory
    quantity: int | None = None
    label: str | None = None

    def __post_init__(self) -> None:
        """Rejects malformed categories, non-positive counts, and blank labels."""

        if not isinstance(self.category, WorkshopOrderRewardCategory):
            raise TypeError(
                f"WorkshopOrderReward category must be a WorkshopOrderRewardCategory, got {self.category!r}."
            )
        _optional_positive_int(self.quantity, "WorkshopOrderReward quantity")
        if self.label is not None and (not isinstance(self.label, str) or not self.label.strip()):
            raise ValueError("WorkshopOrderReward label must be a non-empty string or None.")


@dataclass(frozen=True, slots=True)
class WorkshopOrder:
    """One surveyed order card; an observation-local object, never a server id.

    ``order_ref`` identifies the card within this observation's survey only.
    ``requirements`` maps item id to required piece count and preserves
    duplicate quantities exactly as shown (``{item: 2}`` is meaningful);
    orders of any size remain representable because eligibility is policy,
    not a model invariant. ``completeness`` records how much of the card was
    read (clipped cards keep their partial data). ``ready`` reports the
    observed submit/ready control: ``True`` observed, ``False`` observed
    absent, ``None`` not evaluated. ``source`` names the measured surface the
    read came from (for example the order strip or the detail panel).
    """

    order_ref: int
    requirements: Mapping[int, int]
    rewards: tuple[WorkshopOrderReward, ...] = ()
    completeness: RowRecognitionStatus = RowRecognitionStatus.COMPLETE
    ready: bool | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        """Rejects malformed refs, quantities, and statuses; freezes the requirement map."""

        _require_positive_int(self.order_ref, "WorkshopOrder order_ref")
        object.__setattr__(self, "requirements", _quantity_map(self.requirements, "WorkshopOrder requirements"))
        for reward in self.rewards:
            if not isinstance(reward, WorkshopOrderReward):
                raise TypeError(f"WorkshopOrder rewards must be WorkshopOrderReward, got {reward!r}.")
        if not isinstance(self.completeness, RowRecognitionStatus):
            raise TypeError(
                f"WorkshopOrder completeness must be a RowRecognitionStatus, got {self.completeness!r}."
            )
        if self.ready is not None and not isinstance(self.ready, bool):
            raise TypeError(f"WorkshopOrder ready must be a bool or None, got {self.ready!r}.")
        if self.source is not None and (not isinstance(self.source, str) or not self.source.strip()):
            raise ValueError("WorkshopOrder source must be a non-empty string or None.")

    @property
    def total_pieces(self) -> int:
        """Returns the summed required piece count across all requirements."""

        return sum(self.requirements.values())


@dataclass(frozen=True, slots=True)
class WorkshopOrderSurvey:
    """The order cards reachable in this observation plus coverage/freshness.

    ``orders`` lists surveyed cards in strip order. ``coverage`` records how
    much of the reachable strip was measured (a clipped strip is ``PARTIAL``);
    ``freshness`` records whether the survey comes from this frame
    (``CURRENT``) or was carried across a possibly order-changing mutation
    (``STALE``), so a planner never treats stale cards as confirmed.
    """

    orders: tuple[WorkshopOrder, ...] = ()
    coverage: WorkshopSurveyCoverage = WorkshopSurveyCoverage.UNKNOWN
    freshness: WorkshopSurveyFreshness = WorkshopSurveyFreshness.UNKNOWN

    def __post_init__(self) -> None:
        """Rejects duplicate order refs and untyped coverage/freshness values."""

        if not isinstance(self.coverage, WorkshopSurveyCoverage):
            raise TypeError(
                f"WorkshopOrderSurvey coverage must be a WorkshopSurveyCoverage, got {self.coverage!r}."
            )
        if not isinstance(self.freshness, WorkshopSurveyFreshness):
            raise TypeError(
                f"WorkshopOrderSurvey freshness must be a WorkshopSurveyFreshness, got {self.freshness!r}."
            )
        refs = [order.order_ref for order in self.orders]
        if len(set(refs)) != len(refs):
            raise ValueError("WorkshopOrderSurvey order refs must be unique within one observation.")

    def order(self, order_ref: int) -> WorkshopOrder | None:
        """Returns the surveyed order with one local ref, or ``None``."""

        for order in self.orders:
            if order.order_ref == order_ref:
                return order
        return None


@dataclass(frozen=True, slots=True)
class WorkshopState:
    """Canonical logical state of one Workshop frame; consumed by the solver.

    Every field is a measured or explicitly unknown reading with no screen
    coordinates and no I/O. ``board`` reuses the catalog's
    ``WorkshopBoardLayout`` owner for dimensions and the cell-id formula.
    ``cells`` holds one entry per observed cell; board positions without an
    entry were not observed this frame (partial recognition stays
    representable). ``selection`` distinguishes a known selected cell from a
    known empty selection and an unread one.
    """

    board: WorkshopBoardLayout
    surface: WorkshopSurfaceKind = WorkshopSurfaceKind.BOARD
    cells: tuple[WorkshopCell, ...] = ()
    energy: WorkshopEnergy = field(default_factory=WorkshopEnergy)
    production_mode: WorkshopProductionMode = WorkshopProductionMode.UNKNOWN
    workshop_level: int | None = None
    workshop_exp: int | None = None
    selection: WorkshopSelection = field(
        default_factory=lambda: WorkshopSelection(WorkshopSelectionKind.UNKNOWN)
    )
    order_survey: WorkshopOrderSurvey = field(default_factory=WorkshopOrderSurvey)

    def __post_init__(self) -> None:
        """Rejects out-of-board cells, duplicate ids, and inconsistent addresses."""

        if not isinstance(self.board, WorkshopBoardLayout):
            raise TypeError(f"WorkshopState board must be a WorkshopBoardLayout, got {self.board!r}.")
        if not isinstance(self.surface, WorkshopSurfaceKind):
            raise TypeError(f"WorkshopState surface must be a WorkshopSurfaceKind, got {self.surface!r}.")
        if not isinstance(self.energy, WorkshopEnergy):
            raise TypeError(f"WorkshopState energy must be a WorkshopEnergy, got {self.energy!r}.")
        if not isinstance(self.production_mode, WorkshopProductionMode):
            raise TypeError(
                f"WorkshopState production_mode must be a WorkshopProductionMode, got {self.production_mode!r}."
            )
        _optional_positive_int(self.workshop_level, "WorkshopState workshop_level")
        if self.workshop_exp is not None and (type(self.workshop_exp) is not int or self.workshop_exp < 0):
            raise ValueError(
                f"WorkshopState workshop_exp must be a non-negative integer, got {self.workshop_exp!r}."
            )
        if not isinstance(self.selection, WorkshopSelection):
            raise TypeError(f"WorkshopState selection must be a WorkshopSelection, got {self.selection!r}.")
        if not isinstance(self.order_survey, WorkshopOrderSurvey):
            raise TypeError(
                f"WorkshopState order_survey must be a WorkshopOrderSurvey, got {self.order_survey!r}."
            )
        seen: set[int] = set()
        for cell in self.cells:
            if not isinstance(cell, WorkshopCell):
                raise TypeError(f"WorkshopState cells must be WorkshopCell, got {cell!r}.")
            if cell.cell_id in seen:
                raise ValueError(f"Duplicate observed cell id {cell.cell_id} in WorkshopState.")
            seen.add(cell.cell_id)
            if self.board.cell_id(cell.row, cell.column) != cell.cell_id:
                raise ValueError(
                    f"Observed cell {cell.cell_id} does not match board coordinate "
                    f"({cell.row}, {cell.column})."
                )
        if self.selection.cell_id is not None and not self.board.contains_cell_id(self.selection.cell_id):
            raise ValueError(
                f"Selected cell {self.selection.cell_id} is outside the {self.board.rows} x {self.board.columns} board."
            )

    def cell(self, cell_id: int) -> WorkshopCell | None:
        """Returns the observed cell with one id, or ``None`` when unobserved."""

        for cell in self.cells:
            if cell.cell_id == cell_id:
                return cell
        return None

    def cell_at(self, row: int, column: int) -> WorkshopCell | None:
        """Returns the observed cell at a 1-based board coordinate, or ``None``."""

        for cell in self.cells:
            if cell.row == row and cell.column == column:
                return cell
        return None

    @property
    def observed_cell_ids(self) -> frozenset[int]:
        """Returns the board cell ids that carried an observation this frame."""

        return frozenset(cell.cell_id for cell in self.cells)

    @property
    def unobserved_cell_ids(self) -> frozenset[int]:
        """Returns board positions with no observation; never resized into a fake board."""

        return frozenset(range(1, self.board.cell_count + 1)) - self.observed_cell_ids


@dataclass(frozen=True, slots=True)
class WorkshopOrderView:
    """Measured geometry for one surveyed order card.

    ``portrait_bounds`` is the card region that opens the order detail;
    ``submit_bounds`` is the observed ready control. Both stay ``None`` when
    not measured — no offscreen click point is inferred.
    """

    order_ref: int
    portrait_bounds: Bounds | None = None
    submit_bounds: Bounds | None = None

    def __post_init__(self) -> None:
        """Rejects malformed refs and non-Bounds geometry."""

        _require_positive_int(self.order_ref, "WorkshopOrderView order_ref")
        for name in ("portrait_bounds", "submit_bounds"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Bounds):
                raise TypeError(f"WorkshopOrderView {name} must be Bounds or None, got {value!r}.")


@dataclass(frozen=True, slots=True)
class WorkshopView:
    """Measured geometry and capture provenance paired with one WorkshopState.

    ``cell_bounds`` maps observed board cell ids to their measured bounds;
    ``order_views`` carries per-card portrait/submit geometry. The named
    control bounds are the safe detail/close/recycle/confirmation controls
    measured on this frame. The recognizer supplies ``image_size`` from the
    capture. ``frame_ref``, ``source_screen`` and ``source_layout_id`` are
    stamped by the observation-provenance owner at publication; nothing here
    is inferred offscreen.
    """

    cell_bounds: Mapping[int, Bounds] = field(default_factory=dict)
    order_views: tuple[WorkshopOrderView, ...] = ()
    detail_control_bounds: Bounds | None = None
    close_control_bounds: Bounds | None = None
    recycle_control_bounds: Bounds | None = None
    confirm_control_bounds: Bounds | None = None
    image_size: tuple[int, int] | None = None
    frame_ref: FrameRef | None = None
    source_screen: ScreenType | None = None
    source_layout_id: str | None = None

    def __post_init__(self) -> None:
        """Rejects non-Bounds geometry, malformed ids, and duplicate order views."""

        if not isinstance(self.cell_bounds, Mapping):
            raise TypeError("WorkshopView cell_bounds must map cell id to Bounds.")
        checked: dict[int, Bounds] = {}
        for cell_id, bounds in self.cell_bounds.items():
            _require_positive_int(cell_id, "WorkshopView cell_bounds key")
            if not isinstance(bounds, Bounds):
                raise TypeError(f"WorkshopView cell_bounds value must be Bounds, got {bounds!r}.")
            checked[cell_id] = bounds
        object.__setattr__(self, "cell_bounds", MappingProxyType(checked))
        refs = [view.order_ref for view in self.order_views]
        if len(set(refs)) != len(refs):
            raise ValueError("WorkshopView order_views must have unique order refs.")
        for name in (
            "detail_control_bounds",
            "close_control_bounds",
            "recycle_control_bounds",
            "confirm_control_bounds",
        ):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Bounds):
                raise TypeError(f"WorkshopView {name} must be Bounds or None, got {value!r}.")
        if self.image_size is not None and (
            not isinstance(self.image_size, tuple)
            or len(self.image_size) != 2
            or type(self.image_size[0]) is not int
            or type(self.image_size[1]) is not int
            or self.image_size[0] <= 0
            or self.image_size[1] <= 0
        ):
            raise ValueError(f"WorkshopView image_size must be a positive (width, height) pair.")
        if self.frame_ref is not None and not isinstance(self.frame_ref, FrameRef):
            raise TypeError(f"WorkshopView frame_ref must be a FrameRef or None, got {self.frame_ref!r}.")
        if self.source_screen is not None and not isinstance(self.source_screen, ScreenType):
            raise TypeError(
                f"WorkshopView source_screen must be a ScreenType or None, got {self.source_screen!r}."
            )
        if self.source_layout_id is not None and (
            not isinstance(self.source_layout_id, str) or not self.source_layout_id.strip()
        ):
            raise ValueError("WorkshopView source_layout_id must be a non-empty string or None.")

    def cell_bounds_for(self, cell_id: int) -> Bounds | None:
        """Returns the measured bounds for one cell id, or ``None`` when unmeasured."""

        return self.cell_bounds.get(cell_id)

    def order_view(self, order_ref: int) -> WorkshopOrderView | None:
        """Returns the measured view for one surveyed order ref, or ``None``."""

        for view in self.order_views:
            if view.order_ref == order_ref:
                return view
        return None


@dataclass(frozen=True, slots=True)
class WorkshopObservation:
    """The published Workshop fact: one logical state plus its measured view.

    The executor resolves logical intent targets against ``view`` on the
    matching frame; the solver consumes only ``state``. Publication stamps
    the view's provenance fields through the existing observation-provenance
    owner.
    """

    state: WorkshopState
    view: WorkshopView = field(default_factory=WorkshopView)

    def __post_init__(self) -> None:
        """Rejects view geometry that names cells or orders the state never surveyed."""

        if not isinstance(self.state, WorkshopState):
            raise TypeError(f"WorkshopObservation state must be a WorkshopState, got {self.state!r}.")
        if not isinstance(self.view, WorkshopView):
            raise TypeError(f"WorkshopObservation view must be a WorkshopView, got {self.view!r}.")
        for cell_id in self.view.cell_bounds:
            if not self.state.board.contains_cell_id(cell_id):
                raise ValueError(
                    f"WorkshopView cell_bounds key {cell_id} is outside the "
                    f"{self.state.board.rows} x {self.state.board.columns} board."
                )
        surveyed_refs = {order.order_ref for order in self.state.order_survey.orders}
        for order_view in self.view.order_views:
            if order_view.order_ref not in surveyed_refs:
                raise ValueError(
                    f"WorkshopView order ref {order_view.order_ref} has no surveyed order."
                )


class WorkshopIntent:
    """Base for typed logical Workshop intents.

    Each variant is a frozen dataclass carrying a ``kind`` class tag and the
    logical targets the executor needs for fresh-state revalidation — cell
    ids, order refs and expected item ids — never screen coordinates or raw
    gestures. Ordinary producer upgrades are ``MERGE`` intents on matching
    producer pieces; no separate upgrade variant exists.
    """

    kind: ClassVar[WorkshopIntentKind]


@dataclass(frozen=True, slots=True)
class WorkshopSelectIntent(WorkshopIntent):
    """Selects one board cell, typically a producer before ``PRODUCE``."""

    kind: ClassVar[WorkshopIntentKind] = WorkshopIntentKind.SELECT
    cell_id: int

    def __post_init__(self) -> None:
        """Requires the target cell id."""

        _require_positive_int(self.cell_id, "WorkshopSelectIntent cell_id")


@dataclass(frozen=True, slots=True)
class WorkshopProduceIntent(WorkshopIntent):
    """Produces once from the generator on ``cell_id``.

    ``producer_item_id`` is the catalog item the planner expects on that cell,
    so fresh-state revalidation can reject a board that no longer shows it.
    """

    kind: ClassVar[WorkshopIntentKind] = WorkshopIntentKind.PRODUCE
    cell_id: int
    producer_item_id: int

    def __post_init__(self) -> None:
        """Requires the producer cell and its expected catalog item."""

        _require_positive_int(self.cell_id, "WorkshopProduceIntent cell_id")
        _require_positive_int(self.producer_item_id, "WorkshopProduceIntent producer_item_id")


@dataclass(frozen=True, slots=True)
class WorkshopMergeIntent(WorkshopIntent):
    """Merges the piece on ``source_cell_id`` onto the matching piece on ``target_cell_id``.

    ``item_id`` is the catalog item the planner expects on both cells; the
    merge successor (including ordinary producer upgrades) comes from the
    catalog, not from this intent.
    """

    kind: ClassVar[WorkshopIntentKind] = WorkshopIntentKind.MERGE
    source_cell_id: int
    target_cell_id: int
    item_id: int

    def __post_init__(self) -> None:
        """Requires two distinct cells and their expected shared item."""

        _require_positive_int(self.source_cell_id, "WorkshopMergeIntent source_cell_id")
        _require_positive_int(self.target_cell_id, "WorkshopMergeIntent target_cell_id")
        _require_positive_int(self.item_id, "WorkshopMergeIntent item_id")
        if self.source_cell_id == self.target_cell_id:
            raise ValueError("WorkshopMergeIntent requires two distinct cells.")


@dataclass(frozen=True, slots=True)
class WorkshopActivateIntent(WorkshopIntent):
    """Activates a grey/inactive piece with a matching normal piece.

    ``source_cell_id`` holds the normal ``item_id`` piece and
    ``target_cell_id`` the inactive one; kept distinct from ``MERGE`` because
    its consumption and preconditions differ.
    """

    kind: ClassVar[WorkshopIntentKind] = WorkshopIntentKind.ACTIVATE
    source_cell_id: int
    target_cell_id: int
    item_id: int

    def __post_init__(self) -> None:
        """Requires two distinct cells and their expected matching item."""

        _require_positive_int(self.source_cell_id, "WorkshopActivateIntent source_cell_id")
        _require_positive_int(self.target_cell_id, "WorkshopActivateIntent target_cell_id")
        _require_positive_int(self.item_id, "WorkshopActivateIntent item_id")
        if self.source_cell_id == self.target_cell_id:
            raise ValueError("WorkshopActivateIntent requires two distinct cells.")


@dataclass(frozen=True, slots=True)
class WorkshopFeedIntent(WorkshopIntent):
    """Feeds the exact catalog ingredient to a feed-locked producer.

    ``food_cell_id`` holds the ``food_item_id`` piece and
    ``producer_cell_id`` the feed-locked producer; the ingredient identity is
    revalidated against the catalog's ``feed_item_id``, never by icon shape.
    """

    kind: ClassVar[WorkshopIntentKind] = WorkshopIntentKind.FEED
    food_cell_id: int
    producer_cell_id: int
    food_item_id: int

    def __post_init__(self) -> None:
        """Requires two distinct cells and the exact food item id."""

        _require_positive_int(self.food_cell_id, "WorkshopFeedIntent food_cell_id")
        _require_positive_int(self.producer_cell_id, "WorkshopFeedIntent producer_cell_id")
        _require_positive_int(self.food_item_id, "WorkshopFeedIntent food_item_id")
        if self.food_cell_id == self.producer_cell_id:
            raise ValueError("WorkshopFeedIntent requires two distinct cells.")


@dataclass(frozen=True, slots=True)
class WorkshopRecycleIntent(WorkshopIntent):
    """Recycles the single piece on ``cell_id`` through the garbage-bin control.

    ``item_id`` is the catalog item the planner expects there, so revalidation
    can enforce the restricted recycling allowlist on a fresh state.
    """

    kind: ClassVar[WorkshopIntentKind] = WorkshopIntentKind.RECYCLE
    cell_id: int
    item_id: int

    def __post_init__(self) -> None:
        """Requires the target cell and its expected item."""

        _require_positive_int(self.cell_id, "WorkshopRecycleIntent cell_id")
        _require_positive_int(self.item_id, "WorkshopRecycleIntent item_id")


@dataclass(frozen=True, slots=True)
class WorkshopSubmitOrderIntent(WorkshopIntent):
    """Submits the surveyed order card identified by ``order_ref``.

    The ref is observation-local; readiness and reservation checks are
    revalidated against the fresh state's survey, never a server identity.
    """

    kind: ClassVar[WorkshopIntentKind] = WorkshopIntentKind.SUBMIT_ORDER
    order_ref: int

    def __post_init__(self) -> None:
        """Requires the survey-local order ref."""

        _require_positive_int(self.order_ref, "WorkshopSubmitOrderIntent order_ref")


@dataclass(frozen=True, slots=True)
class WorkshopInspectIntent(WorkshopIntent):
    """Requests bounded inspection of a logical information need.

    ``ORDER_CONTENTS`` needs ``order_ref``; ``CELL_STATE`` needs ``cell_id``;
    ``ORDER_SURVEY`` and ``BOARD`` take no subject. Plan 03 owns the reviewed
    navigation that satisfies the need; the planner never schedules retries.
    """

    kind: ClassVar[WorkshopIntentKind] = WorkshopIntentKind.INSPECT
    need: WorkshopInspectKind
    cell_id: int | None = None
    order_ref: int | None = None

    def __post_init__(self) -> None:
        """Requires the subject matching the declared need, and no other."""

        if not isinstance(self.need, WorkshopInspectKind):
            raise TypeError(f"WorkshopInspectIntent need must be a WorkshopInspectKind, got {self.need!r}.")
        _optional_positive_int(self.cell_id, "WorkshopInspectIntent cell_id")
        _optional_positive_int(self.order_ref, "WorkshopInspectIntent order_ref")
        if self.need == WorkshopInspectKind.ORDER_CONTENTS and (
            self.order_ref is None or self.cell_id is not None
        ):
            raise ValueError("ORDER_CONTENTS inspection requires exactly an order_ref.")
        if self.need == WorkshopInspectKind.CELL_STATE and (
            self.cell_id is None or self.order_ref is not None
        ):
            raise ValueError("CELL_STATE inspection requires exactly a cell_id.")
        if self.need in (WorkshopInspectKind.ORDER_SURVEY, WorkshopInspectKind.BOARD) and (
            self.cell_id is not None or self.order_ref is not None
        ):
            raise ValueError(f"{self.need} inspection takes no cell or order subject.")


@dataclass(frozen=True, slots=True)
class WorkshopWaitIntent(WorkshopIntent):
    """Requests a bounded wait for a blocking condition such as cooldown.

    ``max_wait_ms`` is the ceiling for one continuously blocked episode in
    milliseconds; the executor owns elapsed monotonic time and returns
    ``STOP(cooldown_timeout)`` when it is exhausted.
    """

    kind: ClassVar[WorkshopIntentKind] = WorkshopIntentKind.WAIT
    max_wait_ms: int

    def __post_init__(self) -> None:
        """Requires a positive bound; waits are never open-ended."""

        _require_positive_int(self.max_wait_ms, "WorkshopWaitIntent max_wait_ms")


@dataclass(frozen=True, slots=True)
class WorkshopStopIntent(WorkshopIntent):
    """Ends the current Workshop attempt with a typed reason."""

    kind: ClassVar[WorkshopIntentKind] = WorkshopIntentKind.STOP
    reason: WorkshopStopReason

    def __post_init__(self) -> None:
        """Requires a typed stop reason."""

        if not isinstance(self.reason, WorkshopStopReason):
            raise TypeError(f"WorkshopStopIntent reason must be a WorkshopStopReason, got {self.reason!r}.")


@dataclass(frozen=True, slots=True)
class WorkshopDecision:
    """One proposed logical intent plus the facts needed for revalidation.

    ``intent`` is the typed action; ``reason`` is a human-readable
    explanation. ``goal_order_ref`` names the primary order goal the intent
    serves when one exists, and ``missing_quantities``/``protected_quantities``
    carry the reservation diagnostics (item id -> piece count) the planner
    reports for the current goal. Together with the intent's typed targets
    these are the state facts a fresh-state ``validate_intent`` re-checks —
    no generic read-set framework is added.
    """

    intent: WorkshopIntent
    reason: str = ""
    goal_order_ref: int | None = None
    missing_quantities: Mapping[int, int] = field(default_factory=dict)
    protected_quantities: Mapping[int, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Rejects untyped intents and freezes the diagnostic quantity maps."""

        if not isinstance(self.intent, WorkshopIntent):
            raise TypeError(f"WorkshopDecision intent must be a WorkshopIntent, got {self.intent!r}.")
        if not isinstance(self.reason, str):
            raise TypeError("WorkshopDecision reason must be a string.")
        _optional_positive_int(self.goal_order_ref, "WorkshopDecision goal_order_ref")
        object.__setattr__(
            self, "missing_quantities", _quantity_map(self.missing_quantities, "WorkshopDecision missing_quantities")
        )
        object.__setattr__(
            self, "protected_quantities",
            _quantity_map(self.protected_quantities, "WorkshopDecision protected_quantities"),
        )


@dataclass(frozen=True, slots=True)
class WorkshopPolicy:
    """The typed policy contract shared by ``plan_next`` and ``validate_intent``.

    PW01 fixes the knobs only: admitted orders require exactly
    ``order_piece_total`` pieces; ``reward_priority`` ranks reward categories
    best-first; ``recyclable_item_ids`` is the restricted recycling allowlist;
    ``max_cooldown_wait_ms`` bounds one continuously blocked episode. Default
    values and the evaluation logic belong to the Plan 02 owner;
    account/castle scope stays with the existing application owners.
    """

    order_piece_total: int
    reward_priority: tuple[WorkshopOrderRewardCategory, ...]
    recyclable_item_ids: frozenset[int]
    max_cooldown_wait_ms: int

    def __post_init__(self) -> None:
        """Rejects empty or malformed policy knobs."""

        _require_positive_int(self.order_piece_total, "WorkshopPolicy order_piece_total")
        if not self.reward_priority:
            raise ValueError("WorkshopPolicy reward_priority must name at least one category.")
        for category in self.reward_priority:
            if not isinstance(category, WorkshopOrderRewardCategory):
                raise TypeError(
                    f"WorkshopPolicy reward_priority must hold WorkshopOrderRewardCategory, got {category!r}."
                )
        if len(set(self.reward_priority)) != len(self.reward_priority):
            raise ValueError("WorkshopPolicy reward_priority must not repeat a category.")
        if not isinstance(self.recyclable_item_ids, frozenset):
            raise TypeError("WorkshopPolicy recyclable_item_ids must be a frozenset of item ids.")
        for item_id in self.recyclable_item_ids:
            _require_positive_int(item_id, "WorkshopPolicy recyclable item id")
        _require_positive_int(self.max_cooldown_wait_ms, "WorkshopPolicy max_cooldown_wait_ms")


@dataclass(frozen=True, slots=True)
class WorkshopIntentValidation:
    """The result contract returned by ``validate_intent``.

    ``verdict`` is ``LEGAL`` only when every fact the intent depends on was
    observed and permits it; ``ILLEGAL`` when a known fact forbids it;
    ``UNCERTAIN`` when a required fact was never observed. ``reason`` explains
    the verdict for diagnostics.
    """

    verdict: WorkshopValidationVerdict
    reason: str = ""

    def __post_init__(self) -> None:
        """Requires a typed verdict and a string reason."""

        if not isinstance(self.verdict, WorkshopValidationVerdict):
            raise TypeError(
                f"WorkshopIntentValidation verdict must be a WorkshopValidationVerdict, got {self.verdict!r}."
            )
        if not isinstance(self.reason, str):
            raise TypeError("WorkshopIntentValidation reason must be a string.")


class WorkshopPlanNext(Protocol):
    """Signature of the pure one-step planner implemented by the Plan 02 owner.

    ``plan_next(state, catalog, policy)`` reads only the logical state, the
    packaged catalog and the policy; it performs no I/O and returns one
    ``WorkshopDecision``. PW01 fixes this contract without shipping an
    implementation.
    """

    def __call__(
        self,
        state: WorkshopState,
        catalog: PetWorkshopCatalog,
        policy: WorkshopPolicy,
    ) -> WorkshopDecision:
        """Proposes one logical action without performing I/O or mutating state."""
        ...


class WorkshopValidateIntent(Protocol):
    """Signature of the shared legal-action check implemented by the Plan 02 owner.

    ``validate_intent(state, intent, catalog, policy)`` applies the same
    canonical predicates the planner uses — relevant known item/status/
    selection, recipe/feed identity, quantity reservations, order
    eligibility/readiness, energy, space, restricted recycling and surface —
    and is reused verbatim for fresh-state revalidation before execution.
    PW01 fixes this contract without shipping an implementation.
    """

    def __call__(
        self,
        state: WorkshopState,
        intent: WorkshopIntent,
        catalog: PetWorkshopCatalog,
        policy: WorkshopPolicy,
    ) -> WorkshopIntentValidation:
        """Checks an action against current facts and the canonical policy predicates."""
        ...


__all__ = [
    "WorkshopActivateIntent",
    "WorkshopCell",
    "WorkshopCellAccess",
    "WorkshopCooldown",
    "WorkshopDecision",
    "WorkshopEnergy",
    "WorkshopFeedIntent",
    "WorkshopInspectIntent",
    "WorkshopInspectKind",
    "WorkshopIntent",
    "WorkshopIntentKind",
    "WorkshopIntentValidation",
    "WorkshopItemStatus",
    "WorkshopMergeIntent",
    "WorkshopObservation",
    "WorkshopOccupancy",
    "WorkshopOrder",
    "WorkshopOrderReward",
    "WorkshopOrderRewardCategory",
    "WorkshopOrderSurvey",
    "WorkshopOrderView",
    "WorkshopPlanNext",
    "WorkshopPolicy",
    "WorkshopProduceIntent",
    "WorkshopProductionMode",
    "WorkshopRecycleIntent",
    "WorkshopSelectIntent",
    "WorkshopSelection",
    "WorkshopSelectionKind",
    "WorkshopState",
    "WorkshopStopIntent",
    "WorkshopStopReason",
    "WorkshopSubmitOrderIntent",
    "WorkshopSurfaceKind",
    "WorkshopSurveyCoverage",
    "WorkshopSurveyFreshness",
    "WorkshopValidateIntent",
    "WorkshopValidationVerdict",
    "WorkshopView",
    "WorkshopWaitIntent",
]
