"""Offline Workshop transition engine for solver development and unit tests.

``WorkshopSimulator`` wraps one observed ``WorkshopState`` and applies typed
``WorkshopIntent``s, replicating the client-verified mechanics of the packaged
catalog: merges and activations produce the catalog successor, feeds unlock
feed-locked producers, production draws sample the authored drop groups,
energy spends per production and regenerates on the authored interval, and
producer cooldowns follow ``num`` uses per ``cooldown_ms`` window while
exhaustion applies ``max_num``/``change_item_id``.

The simulator holds the unobservable bookkeeping the observation model omits:
sim time, per-producer cycle and lifetime use counts, cooldown deadlines and
energy-regen progress. ``WorkshopState`` itself stays an observation model —
``apply`` returns the next *observable* state.

Workshop level and EXP are fixed inputs: the replica starts at the authored
level and never advances it — order EXP rewards and item ``exp`` fields are
ignored, so level-gated cells and level rewards are the caller's input
responsibility. Bubble generation is a premium/random mechanic outside the
solver's scope and is never synthesized.

Rules marked ASSUMPTION are not yet verified against captured transitions;
live-captured (state, intent, state') triples are the correction path. The
simulator never touches live state, ADB, or I/O.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from typing import Mapping

from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopActivateIntent,
    WorkshopCell,
    WorkshopCellAccess,
    WorkshopCooldown,
    WorkshopEnergy,
    WorkshopFeedIntent,
    WorkshopInspectIntent,
    WorkshopIntent,
    WorkshopItemStatus,
    WorkshopMergeIntent,
    WorkshopOccupancy,
    WorkshopProduceIntent,
    WorkshopRecycleIntent,
    WorkshopSelectIntent,
    WorkshopSelection,
    WorkshopSelectionKind,
    WorkshopState,
    WorkshopStopIntent,
    WorkshopSubmitOrderIntent,
    WorkshopWaitIntent,
)
from pnc_automation.app.pnc.pet_workshop_catalog import (
    PetWorkshopCatalog,
    load_pet_workshop_catalog,
)


class WorkshopSimulationError(ValueError):
    """Raised when an intent names a transition the game cannot perform."""


@dataclass(frozen=True, slots=True)
class ProduceOutcome:
    """One injected production result for replaying a captured outcome.

    ``item_id`` is the piece the game produced and ``cell_id`` the board
    position it landed on; both are observed facts in a captured next-state,
    so replay asserts the transition logic rather than the draw.
    """

    item_id: int
    cell_id: int
    item_status: WorkshopItemStatus = WorkshopItemStatus.NORMAL

    def __post_init__(self) -> None:
        """Rejects non-positive ids and untyped statuses."""

        if self.item_id <= 0 or self.cell_id <= 0:
            raise WorkshopSimulationError("ProduceOutcome requires positive ids.")
        if not isinstance(self.item_status, WorkshopItemStatus):
            raise TypeError("ProduceOutcome item_status must be a WorkshopItemStatus.")


class WorkshopSimulator:
    """Applies typed Workshop intents to a state replica over sim time.

    Two produce modes: by default a ``PRODUCE`` intent draws from the
    producer's authored drop-group weights (solver development); passing a
    ``ProduceOutcome`` instead replays one determined input (unit tests,
    captured transitions). ``require_produce_outcome=True`` pins the second
    mode so a missing outcome raises instead of silently drawing.

    ``rng`` drives drop-group draws and spawn placement; inject a seeded
    ``random.Random`` for deterministic tests. Sim time advances only through
    ``WAIT`` intents — actions are instantaneous, so cooldowns and energy
    regen progress solely when a wait elapses.
    """

    def __init__(
        self,
        state: WorkshopState,
        *,
        catalog: PetWorkshopCatalog | None = None,
        rng: random.Random | None = None,
        require_produce_outcome: bool = False,
    ) -> None:
        """Starts the replica at sim time zero with no prior producer use."""

        if not isinstance(state, WorkshopState):
            raise TypeError(f"WorkshopSimulator requires a WorkshopState, got {state!r}.")
        self._catalog = catalog if catalog is not None else load_pet_workshop_catalog()
        self._rng = rng if rng is not None else random.Random()
        self._require_produce_outcome = require_produce_outcome
        self._state = state
        self._clock_ms = 0
        self._cycle_uses: dict[int, int] = {}
        self._lifetime_uses: dict[int, int] = {}
        self._cooling_until_ms: dict[int, int] = {}
        self._regen_progress_ms = 0

    @property
    def state(self) -> WorkshopState:
        """Returns the current replicated observable state."""

        return self._state

    @property
    def clock_ms(self) -> int:
        """Returns elapsed sim milliseconds; advances only through WAIT."""

        return self._clock_ms

    def apply(
        self,
        intent: WorkshopIntent,
        *,
        outcome: ProduceOutcome | None = None,
    ) -> WorkshopState:
        """Applies one intent and returns the replicated next state.

        Raises ``WorkshopSimulationError`` on transitions the game cannot
        perform (merging mismatched items, producing from a non-producer,
        feeding the wrong ingredient). ``outcome`` injects a captured
        production result and is meaningful only for ``PRODUCE``.
        """

        if not isinstance(intent, WorkshopIntent):
            raise TypeError(f"WorkshopSimulator requires a WorkshopIntent, got {intent!r}.")
        if outcome is not None and not isinstance(intent, WorkshopProduceIntent):
            raise WorkshopSimulationError("ProduceOutcome applies only to PRODUCE intents.")
        if isinstance(intent, WorkshopSelectIntent):
            self._select(intent)
        elif isinstance(intent, WorkshopProduceIntent):
            self._produce(intent, outcome)
        elif isinstance(intent, WorkshopMergeIntent):
            self._merge(intent)
        elif isinstance(intent, WorkshopActivateIntent):
            self._activate(intent)
        elif isinstance(intent, WorkshopFeedIntent):
            self._feed(intent)
        elif isinstance(intent, WorkshopRecycleIntent):
            self._recycle(intent)
        elif isinstance(intent, WorkshopSubmitOrderIntent):
            self._submit(intent)
        elif isinstance(intent, WorkshopWaitIntent):
            self._wait(intent)
        elif isinstance(intent, (WorkshopInspectIntent, WorkshopStopIntent)):
            pass
        else:
            raise TypeError(f"Unsupported Workshop intent {intent!r}.")
        return self._state

    # --- intents ---------------------------------------------------------

    def _select(self, intent: WorkshopSelectIntent) -> None:
        """Marks the target cell selected; unusable or unobserved cells are ignored."""

        cell = self._observed_cell(intent.cell_id)
        if cell is None or cell.access != WorkshopCellAccess.USABLE:
            return
        self._set_state(
            selection=WorkshopSelection(WorkshopSelectionKind.SELECTED, intent.cell_id)
        )

    def _produce(
        self,
        intent: WorkshopProduceIntent,
        outcome: ProduceOutcome | None,
    ) -> None:
        """Draws one drop-group piece onto a free cell and charges energy.

        Producer ``num`` counts uses per cooldown window; reaching it marks
        the cell's cooldown marker ACTIVE until ``cooldown_ms`` of sim time
        elapses. ``max_num`` counts lifetime uses; reaching it applies the
        authored ``change_item_id`` transform or removes the piece
        ("Disappears after attempts are depleted", per the live tooltip).

        Live evidence (2026-09-18, main): one captured produce spent one
        energy, landed an authored-group piece on a server-chosen cell
        (``targetPos`` in the PRODUCE response), and showed a ``cdTime``
        badge on the producer afterward. A second pass the same day saw
        four consecutive produces succeed — including the same producer
        again ~5 min later and a ~4 s select→produce gap — so rejection is
        producer server state that refreshes, not input timing. Whether
        the badge marks a per-produce window or a ``num``-cycle boundary
        is not separable from these samples — ``num`` is a server-only
        counter the client never displays, and ``num``-cycle keeps
        ``num`` < ``max_num`` producers' transform reachable, so the
        cycle reading is retained.

        ASSUMPTION (unverified): ``num`` uses per ``cooldown_ms`` cycle —
        alternatives (per-produce cooldown, session-scoped budget) are not
        yet ruled out by captures.
        ASSUMPTION (unverified): with ``num=0`` the producer never enters a
        use-count cooldown; exhaustion alone bounds it.
        """

        cell = self._require_usable_cell(intent.cell_id)
        if cell.occupancy != WorkshopOccupancy.OCCUPIED or cell.item_id is None:
            raise WorkshopSimulationError(
                f"Cell {intent.cell_id} holds no piece to produce from."
            )
        if cell.item_id != intent.producer_item_id:
            raise WorkshopSimulationError(
                f"Cell {intent.cell_id} holds {cell.item_id}, "
                f"not expected producer {intent.producer_item_id}."
            )
        if cell.item_status != WorkshopItemStatus.NORMAL:
            raise WorkshopSimulationError(
                f"Cell {intent.cell_id} piece is {cell.item_status}, not producible Normal."
            )
        producer = self._catalog.producer_for(intent.producer_item_id)
        if producer is None:
            raise WorkshopSimulationError(
                f"Item {intent.producer_item_id} is not a catalog producer."
            )
        if self._is_cooling(intent.cell_id) or cell.cooldown == WorkshopCooldown.ACTIVE:
            raise WorkshopSimulationError(f"Producer on cell {intent.cell_id} is cooling down.")
        energy = self._state.energy
        if energy.current is not None and (
            energy.current < self._catalog.activity.production_energy_cost
        ):
            raise WorkshopSimulationError("Not enough energy to produce.")
        if outcome is None and self._require_produce_outcome:
            raise WorkshopSimulationError(
                "Determined-input mode requires a ProduceOutcome for PRODUCE."
            )
        if outcome is not None:
            group = self._catalog.drop_group(producer.group_id)
            if group is not None and not any(
                entry.item_id == outcome.item_id for entry in group.entries
            ):
                raise WorkshopSimulationError(
                    f"Item {outcome.item_id} cannot drop from producer "
                    f"{intent.producer_item_id} (group {producer.group_id})."
                )
            produced_item_id = outcome.item_id
            destination_id = outcome.cell_id
            produced_status = outcome.item_status
        else:
            produced_item_id = self._draw_from_group(producer.group_id)
            destination_id = self._pick_spawn_cell()
            produced_status = WorkshopItemStatus.NORMAL
        destination = self._require_usable_cell(destination_id)
        if destination.occupancy != WorkshopOccupancy.EMPTY:
            raise WorkshopSimulationError(
                f"Spawn cell {destination_id} is not usable and empty."
            )
        if self._catalog.item(produced_item_id) is None:
            raise WorkshopSimulationError(f"Produced item {produced_item_id} is not in the catalog.")

        updates: dict[int, WorkshopCell] = {
            destination_id: replace(
                destination,
                occupancy=WorkshopOccupancy.OCCUPIED,
                item_id=produced_item_id,
                item_status=produced_status,
                cooldown=WorkshopCooldown.CLEAR,
            )
        }
        lifetime = self._lifetime_uses.get(intent.cell_id, 0) + 1
        self._lifetime_uses[intent.cell_id] = lifetime
        if producer.max_num > 0 and lifetime >= producer.max_num:
            self._cycle_uses.pop(intent.cell_id, None)
            self._lifetime_uses.pop(intent.cell_id, None)
            self._cooling_until_ms.pop(intent.cell_id, None)
            if producer.change_item_id is not None:
                updates[intent.cell_id] = replace(
                    cell, item_id=producer.change_item_id, cooldown=WorkshopCooldown.CLEAR
                )
            else:
                updates[intent.cell_id] = replace(
                    cell,
                    occupancy=WorkshopOccupancy.EMPTY,
                    item_id=None,
                    item_status=None,
                    cooldown=WorkshopCooldown.CLEAR,
                )
        else:
            cycle = self._cycle_uses.get(intent.cell_id, 0) + 1
            self._cycle_uses[intent.cell_id] = cycle
            if producer.num > 0 and producer.cooldown_ms > 0 and cycle >= producer.num:
                self._cycle_uses[intent.cell_id] = 0
                self._cooling_until_ms[intent.cell_id] = self._clock_ms + producer.cooldown_ms
                updates[intent.cell_id] = replace(cell, cooldown=WorkshopCooldown.ACTIVE)
            elif cell.cooldown != WorkshopCooldown.CLEAR:
                updates[intent.cell_id] = replace(cell, cooldown=WorkshopCooldown.CLEAR)
        self._set_state(
            cells=self._cells_with(updates),
            energy=self._spend_energy(self._catalog.activity.production_energy_cost),
        )

    def _merge(self, intent: WorkshopMergeIntent) -> None:
        """Merges two matching Normal pieces into the catalog successor."""

        source, target = self._require_pair(
            intent.source_cell_id, intent.target_cell_id, intent.item_id, "merge"
        )
        successor = self._successor(intent.item_id, "merge")
        self._set_state(
            cells=self._cells_with(
                {
                    intent.source_cell_id: self._emptied(source),
                    intent.target_cell_id: replace(
                        target, item_id=successor, cooldown=WorkshopCooldown.CLEAR
                    ),
                }
            )
        )

    def _activate(self, intent: WorkshopActivateIntent) -> None:
        """Merges a Normal fuel piece into a matching Inactive piece."""

        source = self._require_usable_cell(intent.source_cell_id)
        target = self._require_usable_cell(intent.target_cell_id)
        if source.item_id != intent.item_id or target.item_id != intent.item_id:
            raise WorkshopSimulationError(
                f"Activation needs {intent.item_id} on both cells "
                f"{intent.source_cell_id} and {intent.target_cell_id}."
            )
        if source.item_status != WorkshopItemStatus.NORMAL:
            raise WorkshopSimulationError(
                f"Activation fuel on cell {intent.source_cell_id} is not Normal."
            )
        if target.item_status != WorkshopItemStatus.INACTIVE:
            raise WorkshopSimulationError(
                f"Activation target on cell {intent.target_cell_id} is not Inactive."
            )
        successor = self._successor(intent.item_id, "activate")
        self._set_state(
            cells=self._cells_with(
                {
                    intent.source_cell_id: self._emptied(source),
                    intent.target_cell_id: replace(
                        target,
                        item_id=successor,
                        item_status=WorkshopItemStatus.NORMAL,
                        cooldown=WorkshopCooldown.CLEAR,
                    ),
                }
            )
        )

    def _feed(self, intent: WorkshopFeedIntent) -> None:
        """Consumes the food piece and unlocks the feed-locked producer."""

        food = self._require_usable_cell(intent.food_cell_id)
        producer_cell = self._require_usable_cell(intent.producer_cell_id)
        if food.item_id != intent.food_item_id or food.item_status != WorkshopItemStatus.NORMAL:
            raise WorkshopSimulationError(
                f"Cell {intent.food_cell_id} holds no Normal {intent.food_item_id} food piece."
            )
        if producer_cell.item_id is None:
            raise WorkshopSimulationError(
                f"Cell {intent.producer_cell_id} holds no feed-locked producer."
            )
        producer = self._catalog.producer_for(producer_cell.item_id)
        if producer is None or producer.feed_item_id != intent.food_item_id:
            raise WorkshopSimulationError(
                f"Cell {intent.producer_cell_id} piece does not accept food {intent.food_item_id}."
            )
        if producer_cell.item_status != WorkshopItemStatus.FEED_LOCKED:
            raise WorkshopSimulationError(
                f"Cell {intent.producer_cell_id} is not feed-locked."
            )
        self._set_state(
            cells=self._cells_with(
                {
                    intent.food_cell_id: self._emptied(food),
                    intent.producer_cell_id: replace(
                        producer_cell,
                        item_status=WorkshopItemStatus.NORMAL,
                        cooldown=WorkshopCooldown.CLEAR,
                    ),
                }
            )
        )

    def _recycle(self, intent: WorkshopRecycleIntent) -> None:
        """Removes one recoverable piece and grants its authored energy reward."""

        cell = self._require_usable_cell(intent.cell_id)
        if cell.item_id != intent.item_id:
            raise WorkshopSimulationError(
                f"Cell {intent.cell_id} holds {cell.item_id}, not expected {intent.item_id}."
            )
        if cell.item_status != WorkshopItemStatus.NORMAL:
            raise WorkshopSimulationError(
                f"Cell {intent.cell_id} piece is {cell.item_status}, not recyclable Normal."
            )
        item = self._catalog.require_item(intent.item_id)
        if not item.recoverable:
            raise WorkshopSimulationError(f"Item {intent.item_id} is not recoverable.")
        energy = self._state.energy
        reward = item.recycle_reward
        if (
            reward is not None
            and reward.item_id == self._catalog.activity.energy_item_id
            and energy.current is not None
        ):
            energy = replace(energy, current=energy.current + reward.count)
        self._set_state(cells=self._cells_with({intent.cell_id: self._emptied(cell)}), energy=energy)

    def _submit(self, intent: WorkshopSubmitOrderIntent) -> None:
        """Consumes the order's required pieces and removes the surveyed card.

        Required pieces come off the lowest-id Normal cells first — the game
        does not expose which copies a submission consumed. Order rewards are
        not applied: Workshop level/EXP are fixed inputs, and item-family
        rewards land outside the board model.
        """

        order = self._state.order_survey.order(intent.order_ref)
        if order is None:
            raise WorkshopSimulationError(f"Order {intent.order_ref} is not in the survey.")
        updates: dict[int, WorkshopCell] = {}
        for item_id, quantity in order.requirements.items():
            remaining = quantity
            for cell in sorted(self._state.cells, key=lambda cell: cell.cell_id):
                if remaining <= 0:
                    break
                pending = updates.get(cell.cell_id, cell)
                if (
                    pending.access == WorkshopCellAccess.USABLE
                    and pending.occupancy == WorkshopOccupancy.OCCUPIED
                    and pending.item_id == item_id
                    and pending.item_status == WorkshopItemStatus.NORMAL
                ):
                    updates[cell.cell_id] = self._emptied(pending)
                    remaining -= 1
            if remaining > 0:
                raise WorkshopSimulationError(
                    f"Order {intent.order_ref} needs {quantity} of item {item_id}; "
                    f"only {quantity - remaining} usable Normal pieces on board."
                )
        survey = self._state.order_survey
        self._set_state(
            cells=self._cells_with(updates),
            order_survey=replace(
                survey, orders=tuple(o for o in survey.orders if o.order_ref != intent.order_ref)
            ),
        )

    def _wait(self, intent: WorkshopWaitIntent) -> None:
        """Advances sim time, clearing elapsed cooldowns and regenning energy."""

        self._clock_ms += intent.max_wait_ms
        updates: dict[int, WorkshopCell] = {}
        for cell_id, until_ms in list(self._cooling_until_ms.items()):
            if until_ms > self._clock_ms:
                continue
            del self._cooling_until_ms[cell_id]
            self._cycle_uses[cell_id] = 0
            cell = self._observed_cell(cell_id)
            if cell is not None and cell.cooldown == WorkshopCooldown.ACTIVE:
                updates[cell_id] = replace(cell, cooldown=WorkshopCooldown.CLEAR)
        for cell in self._state.cells:
            if cell.cell_id in updates or cell.cooldown != WorkshopCooldown.ACTIVE:
                continue
            producer = (
                self._catalog.producer_for(cell.item_id) if cell.item_id is not None else None
            )
            if producer is not None and intent.max_wait_ms >= producer.cooldown_ms:
                updates[cell.cell_id] = replace(cell, cooldown=WorkshopCooldown.CLEAR)
        energy = self._state.energy
        capacity = energy.capacity or self._catalog.activity.energy_capacity
        if energy.current is not None and energy.current < capacity:
            self._regen_progress_ms += intent.max_wait_ms
            gained = self._regen_progress_ms // self._catalog.activity.energy_regen_ms
            if gained:
                self._regen_progress_ms -= gained * self._catalog.activity.energy_regen_ms
                energy = replace(energy, current=min(energy.current + gained, capacity))
        else:
            self._regen_progress_ms = 0
        self._set_state(cells=self._cells_with(updates), energy=energy)

    # --- internals -------------------------------------------------------

    def _set_state(self, **changes) -> None:
        """Applies field-level changes to the replicated state."""

        self._state = replace(self._state, **changes)

    def _observed_cell(self, cell_id: int) -> WorkshopCell | None:
        """Returns the observed cell with one id, or ``None`` when unobserved."""

        for cell in self._state.cells:
            if cell.cell_id == cell_id:
                return cell
        return None

    def _require_usable_cell(self, cell_id: int) -> WorkshopCell:
        """Returns the observed usable cell or raises on unobserved/locked."""

        cell = self._observed_cell(cell_id)
        if cell is None:
            raise WorkshopSimulationError(f"Cell {cell_id} is not part of the observed state.")
        if cell.access != WorkshopCellAccess.USABLE:
            raise WorkshopSimulationError(f"Cell {cell_id} is not usable.")
        return cell

    def _require_pair(
        self, source_cell_id: int, target_cell_id: int, item_id: int, verb: str
    ) -> tuple[WorkshopCell, WorkshopCell]:
        """Returns two usable cells both holding Normal ``item_id`` pieces."""

        source = self._require_usable_cell(source_cell_id)
        target = self._require_usable_cell(target_cell_id)
        for cell in (source, target):
            if cell.item_id != item_id or cell.item_status != WorkshopItemStatus.NORMAL:
                raise WorkshopSimulationError(
                    f"Cannot {verb}: cell {cell.cell_id} does not hold a Normal {item_id}."
                )
        return source, target

    def _cells_with(self, updates: Mapping[int, WorkshopCell]) -> tuple[WorkshopCell, ...]:
        """Returns the cell tuple with per-id updates applied, id order."""

        cells = {cell.cell_id: cell for cell in self._state.cells}
        cells.update(updates)
        return tuple(cells[cell_id] for cell_id in sorted(cells))

    def _emptied(self, cell: WorkshopCell) -> WorkshopCell:
        """Returns the cell cleared to an empty usable square."""

        return replace(
            cell,
            occupancy=WorkshopOccupancy.EMPTY,
            item_id=None,
            item_status=None,
            cooldown=WorkshopCooldown.CLEAR,
        )

    def _successor(self, item_id: int, verb: str) -> int:
        """Returns the catalog merge successor or raises at max tier."""

        item = self._catalog.require_item(item_id)
        if item.merge_successor_id is None:
            raise WorkshopSimulationError(f"Cannot {verb}: item {item_id} is at max tier.")
        return item.merge_successor_id

    def _is_cooling(self, cell_id: int) -> bool:
        """Returns whether the cell's producer is inside a cooldown window."""

        return self._cooling_until_ms.get(cell_id, 0) > self._clock_ms

    def _spend_energy(self, cost: int) -> WorkshopEnergy:
        """Returns the energy bar after one spend; unknown stays unknown."""

        energy = self._state.energy
        if energy.current is None:
            return energy
        return replace(energy, current=energy.current - cost)

    def _draw_from_group(self, group_id: int) -> int:
        """Samples one item id from the authored drop-group weights."""

        group = self._catalog.drop_group(group_id)
        if group is None:
            raise WorkshopSimulationError(f"Drop group {group_id} is not in the catalog.")
        pick = self._rng.randrange(group.total_weight)
        cumulative = 0
        for entry in group.entries:
            cumulative += entry.weight
            if pick < cumulative:
                return entry.item_id
        raise WorkshopSimulationError(f"Drop group {group_id} has no positive-weight entries.")

    def _pick_spawn_cell(self) -> int:
        """Chooses the spawn cell for a produced piece.

        ASSUMPTION (unverified): the game lands a produced piece on a random
        usable empty cell; no authored placement rule exists in the catalog.
        """

        empty = [
            cell.cell_id
            for cell in sorted(self._state.cells, key=lambda cell: cell.cell_id)
            if cell.access == WorkshopCellAccess.USABLE
            and cell.occupancy == WorkshopOccupancy.EMPTY
        ]
        if not empty:
            raise WorkshopSimulationError("No usable empty cell for the produced piece.")
        return self._rng.choice(empty)
