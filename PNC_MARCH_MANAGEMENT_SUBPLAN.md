# Puzzles & Conquest March Management Sub-Plan

## 1. Purpose

This document owns the shared march-management shell that is beginning to emerge from Alliance Hall reinforce and Market transport follow-up screens.

It is intentionally separate from:

- [PNC_BUILDING_ACTIONS_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_BUILDING_ACTIONS_SUBPLAN.md), which owns buildings such as `alliance_hall`, `market`, `hall_of_war`, and `pit`, plus the existence of their building-owned entry screens,
- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md), which owns reusable navigation patterns,
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md), which owns broader feature-task planning,
- [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md), which owns the primary platform architecture.

This file should answer one class of questions only:

- how march-slot capacity and unlock state are modeled,
- which action families consume a march,
- which troop-selection or dispatch surfaces are shared across features,
- what post-dispatch verification proves that a march is active, unavailable, or locked.

## 2. Current confirmed context

From the current user guidance and screenshots already referenced by [PNC_BUILDING_ACTIONS_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_BUILDING_ACTIONS_SUBPLAN.md):

- total march capacity ranges from one to five marches,
- additional march slots unlock through VIP level 8 and Institute technology upgrades,
- each march can build an alliance building, occupy an empty map spot, gather a node, attack, rally, reinforce, or transport,
- Alliance Hall reinforce currently shows a result popup/modal such as `Send reinforcements to defend an ally's territory` with a bottom `Dispatch` button,
- a follow-up `Reinforce` troop-selection screen exists for reinforcement,
- the user clarified that the Market transport flow also reaches the reinforce-style troop-selection screen after the transport setup surface.

## 3. Scope

This sub-plan should own:

- canonical march-slot modeling, including total capacity, locked slots, free slots, and occupied slots,
- the shared troop-selection or dispatch surfaces reused by reinforce, transport, attack, rally, gather, alliance-building, and empty-spot occupation flows,
- post-dispatch verification requirements for active marches,
- fail-fast behavior when a requested action has no available march slot,
- screenshot and selector follow-up specific to march-management surfaces once the entry paths are confirmed.

This sub-plan should not own:

- building-specific entry buttons such as Alliance Hall `Reinforce` or Market `Resource Transport`,
- generic home-city or world-map navigation,
- feature policy about when automation should choose one march-consuming action over another.

## 4. Core modeling direction

March management should be treated as one shared action layer reused by multiple feature entry points rather than re-described independently by each building or task.

Recommended ownership boundary:

1. [PNC_BUILDING_ACTIONS_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_BUILDING_ACTIONS_SUBPLAN.md) keeps the high-level facts that building-owned entry flows such as `alliance_hall -> alliance_member_reinforce` and `market -> alliance_member_transport` exist.
2. This sub-plan owns what happens once those entry flows hand off into shared march-slot, troop-selection, dispatch, and post-dispatch verification surfaces.
3. Later feature plans for gathering, rally, attack, alliance building, or map occupation should consume the canonical shared march model defined here instead of restating slot semantics.

## 5. Seed open questions

- Do the Alliance Hall `Reinforce` result flow and the Market `Transport` result flow converge on one canonical troop-selection surface, or do they only partially overlap after distinct intermediate screens?
- Is `Transport Resources` always a transport-specific setup screen that then hands off into the same reinforce-style march screen, or can transport complete without that shared troop-selection surface in some states?
- Where is the current free-versus-occupied march count exposed during reinforce, transport, rally, attack, gather, alliance-building, and empty-map occupation flows?
- How are additional march slots and their unlock state shown once VIP level 8 and Institute march-tech upgrades raise total march capacity from one slot toward the five-march cap?
- What does the no-free-march failure state look like, and does it vary by action family?
- What stable post-dispatch proof exists for an active march across the currently known action families?

## 6. Immediate next additions when more screenshots arrive

The next screenshots should be added to this plan in the following order:

- Alliance Hall reinforce-result follow-up screens, starting with the row-result popup/modal such as `Send reinforcements to defend an ally's territory` with bottom `Dispatch`, then the subsequent `Reinforce` troop-selection screen.
- Market transport-result follow-up screens, starting with the `Transport Resources` screen and then any confirmation or dispatch popup that leads into the reinforce-style troop-selection screen the user described.
- March-management verification screenshots after the reinforcement and transport follow-up screens are resolved, especially screenshots that expose free marches, occupied marches, locked march slots, and action-specific outbound march states.

Additional screenshot examples that will be especially useful once the first queue items land:

- one free march versus multiple unlocked march slots,
- at least one occupied march after reinforce or transport dispatch,
- any UI that exposes march-slot unlock progression beyond the first slot,
- future march-entry screenshots for alliance building, empty-map occupation, gathering, attack, and rally.
