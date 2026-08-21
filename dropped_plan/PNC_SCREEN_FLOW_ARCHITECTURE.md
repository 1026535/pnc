# Puzzles & Conquest Screen Flow Architecture

## 1. Purpose

This document is the durable ownership contract for reusable Puzzles & Conquest screen navigation.

The implementation already has one canonical reusable flow surface:

- [`ScreenFlowPlanner`](/c:/Users/lebel/pnc/pnc_automation/app/pnc/navigation/screen_flows.py)

Use this document as architecture guidance, not as an implementation backlog. New concrete feature work belongs in feature plans or tests; this document only defines where reusable navigation responsibilities live.

## 2. Current Boundary

Screen flow owns reusable navigation increments that move between proven app states or guarantee a reusable screen-readiness condition.

Screen flow does not own:

- the runner's `observe -> popup recovery -> navigate -> prove preflight` loop,
- world-map viewport traversal, search patterns, matching, survey indexing, or stop policy,
- spatial-object parsing or coordinate OCR,
- selector discovery or selector-registry refinement,
- task-specific business policy or success verification,
- feature-local flows until reuse is proven.

The current code returns declarative `ActionRequest` increments. It does not execute actions, capture screenshots, or run retry loops by itself.

## 3. Canonical Implementation

The canonical implementation is `ScreenFlowPlanner`.

No second planner, task-local navigation helper, or legacy compatibility API should be added for the same concept. When a new reusable path is needed, add it to `ScreenFlowPlanner` or to the more specific canonical owner if it is not truly screen flow.

Current lower-level collaborators:

- `Observation` owns interpreted screen state, visible selectors, list entries, and spatial surfaces.
- `ObservationRequest` owns action-scoped follow-up proof requests.
- `HomeCityNavigator` owns camera-relative home-city spatial movement and target taps.
- `WorldMapNavigator` owns one world-map movement/tap primitive, while world-map search orchestration lives below the search subsystem rather than on the screen-flow surface.

## 4. Implemented Flow Groups

### 4.1 Bootstrap and Recovery

- `recover_unknown_game_screen(...)`
- `ensure_android_home(...)`
- `ensure_pnc_foreground(...)`
- `close_blocking_popup(...)`
- `return_to_safe_root_screen(...)`
- `ensure_home_city(...)`

These provide conservative recovery and root-return increments shared by account navigation, task preflight, popup recovery, and feature tasks.

### 4.2 Account and Castle Navigation

- `open_more_menu(...)`
- `open_lord_info(...)`
- `open_castle_selection(...)`
- `ensure_correct_castle_selected(...)`

These remain screen-flow responsibilities because account bootstrap, castle targeting, and later profile-aware work all need the same paths.

### 4.3 Shared App Screens

- `open_world_map(...)`
- `ensure_world_map_ready(...)`
- `return_home_city_from_world_map(...)`
- `open_chat(...)`
- `ensure_chat_channel(...)`
- `open_alliance_home(...)`
- `open_mail_hub(...)`
- `open_mailbox(...)`
- `open_alliance_member_list(...)`
- `open_might_rank(...)`
- `open_player_profile(...)`
- `open_mail_compose(...)`
- `send_mail(...)`
- `send_chat_message(...)`

These are canonical because multiple tasks and workflows consume the same chat, mail, alliance, profile, and root-screen routes.

`ensure_world_map_ready(...)` belongs here only as a root entry/readiness guarantee. It must not be called as routine per-checkpoint movement inside world-map search.

### 4.4 Home-City Spatial Entry

- `open_institute(...)`
- `open_campaign_map(...)`
- `open_visible_home_city_object(...)`
- `focus_home_city_object(...)`
- `focus_home_city_coordinate(...)`
- `open_home_city_object(...)`
- `open_home_city_empty_slot(...)`

These are exposed through `ScreenFlowPlanner` because tasks need one canonical way to enter home-city objects from a home-city observation. The spatial movement and tap details remain delegated to `HomeCityNavigator`.

Do not duplicate home-city camera search logic inside individual building, research, campaign, or construction tasks.

## 5. Deliberately Outside Screen Flow

World-map-local search remains outside screen-flow ownership.

Screen flow may own:

- entering world map,
- proving world-map readiness,
- returning to home city.

World-map search and spatial ownership own:

- repeated world-map swipes,
- checkpoint route generation,
- search radius or sweep pattern,
- visible object matching,
- castle-profile enrichment,
- survey/index persistence,
- stop-policy evaluation.

This follows the boundary in [PNC_WORLD_MAP_SEARCH_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_WORLD_MAP_SEARCH_SUBPLAN.md) and [PNC_SPATIAL_SURFACE_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_SPATIAL_SURFACE_SUBPLAN.md).

## 6. Runner Preflight Relationship

The runner owns reusable task-entry loops through `TaskPreflight`.

Current runner-owned preflight states:

- `TaskPreflight.HOME_CITY`
- `TaskPreflight.WORLD_MAP`

The runner consumes `ScreenFlowPlanner.ensure_home_city(...)` and `ScreenFlowPlanner.ensure_world_map_ready(...)` to prove those states before task bodies execute. Tasks whose bodies truly start from a root screen should declare preflight instead of reimplementing root-entry logic.

Tasks with resumable in-progress screens may keep local subflow ownership, but they should still call canonical screen flows when they need a shared transition.

## 7. Promotion Gate

A navigation path belongs in `ScreenFlowPlanner` only when at least one condition is true:

- it is required by account navigation and later feature work,
- it is reused by two or more post-navigation features,
- it represents core safety, recovery, or root-readiness behavior,
- it centralizes a route that would otherwise be duplicated across tasks.

Before promotion, the path must have:

- one owning canonical name,
- explicit source and destination guarantees,
- exact allowed `ScreenType` entry assumptions,
- canonical selectors, list entries, or spatial queries,
- action-scoped follow-up proof where destination classification is narrow or ambiguous,
- fail-fast behavior for unsupported states,
- focused offline tests,
- no duplicated task-local version left behind.

If a path is still feature-local, provisional, or poorly understood, keep it in that feature plan until reuse is proven.

## 8. Flow Contract Template

Each new reusable flow should be specified with the same compact contract.

### Purpose

- the navigation state it guarantees,
- the states it intentionally does not guarantee.

### Entry Assumptions

- allowed starting `ScreenType` values,
- required selectors, list entries, or spatial-surface facts,
- known blocking conditions.

### Actions

- selector taps,
- list-entry taps,
- spatial-object taps delegated to the owning navigator,
- waits and follow-up observation requests,
- bounded fallback transitions for known popups or coarse roots.

### Success Criteria

- destination `ScreenType`,
- required selectors or parsed spatial surface,
- relevant state assertions.

### Failure Handling

- allowed retries or bounded refreshes,
- conditions that delegate to popup/unknown recovery,
- conditions that raise `SelectorResolutionError`.

### Validation

- focused unit coverage for each supported source state,
- evidence-backed selector or parser coverage when a new UI proof is required,
- live smoke guidance when the path crosses emulator/runtime boundaries.

## 9. Documentation Rules

Feature plans should reference canonical flows instead of re-describing shared navigation.

When a feature promotes a new reusable route:

1. add or update the `ScreenFlowPlanner` method,
2. add focused flow tests beside the existing flow/task tests,
3. update this architecture document's implemented flow groups,
4. remove duplicated navigation text from the feature plan,
5. leave feature-specific policy and verification in the feature plan.

When a route moves out of screen-flow ownership, delete the obsolete flow surface or leave only a short compatibility shim during an active migration. The target is always one canonical implementation per concept.

## 10. Related Plans

- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md) is closed and points here.
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md) consumes screen flows from feature slices.
- [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md) consumes bootstrap, popup recovery, and castle targeting flows.
- [PNC_SPATIAL_SURFACE_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_SPATIAL_SURFACE_SUBPLAN.md) owns fixed-selector, dynamic-list, and spatial-surface observation boundaries.
- [PNC_WORLD_MAP_SEARCH_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_WORLD_MAP_SEARCH_SUBPLAN.md) owns world-map-local search and traversal.
- [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_SELECTOR_REFINEMENT_SUBPLAN.md) owns selector maturity needed by flow actions.
- [PNC_MAIL_WORKFLOW_IMPLEMENTATION.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_MAIL_WORKFLOW_IMPLEMENTATION.md) records the mail/profile routes that are now promoted into `ScreenFlowPlanner`.
- [PNC_CHAT_WORKFLOW_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_CHAT_WORKFLOW_SUBPLAN.md) records the chat routes that are now promoted into `ScreenFlowPlanner`.

## 11. Validation References

Primary offline coverage currently lives in:

- [`tests/test_flows_and_tasks.py`](/c:/Users/lebel/pnc/tests/test_flows_and_tasks.py)
- [`tests/test_mail_workflow.py`](/c:/Users/lebel/pnc/tests/test_mail_workflow.py)
- [`tests/test_world_map_search.py`](/c:/Users/lebel/pnc/tests/test_world_map_search.py)
- [`tests/test_automation_framework.py`](/c:/Users/lebel/pnc/tests/test_automation_framework.py)
- [`tests/test_navigation_selector_validator.py`](/c:/Users/lebel/pnc/tests/test_navigation_selector_validator.py)

For code changes touching live runtime boundaries, run the full offline suite and call out the relevant opt-in live smoke flag from the project AGENTS guidelines.
