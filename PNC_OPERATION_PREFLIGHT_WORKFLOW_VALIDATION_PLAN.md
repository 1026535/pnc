# PNC Operation Preflight Workflow Validation Plan

## 1. Purpose

This plan validates that every automation operation follows the intended workflow ownership model:

- root preflight proves the starting root once before the operation body starts,
- intermediate proof checkpoints validate meaningful state changes during the operation,
- the operation body performs only the work it owns,
- subflows declare the state that means their owned work is complete,
- in-surface movement stays below screen flow,
- post-action observation proof is allowed,
- repeated root navigation inside operation loops is avoided unless the operation truly leaves its root screen.

This is separate from `PNC_TEST_CODEPATH_PARITY_AUDIT_PLAN.md`.

The parity audit asks:

- "Does the test exercise the same codepath as production?"

This workflow validation plan asks:

- "Does each operation use the correct root-preflight, intermediate-proof, and ownership model?"

The rule is not "look only once." The rule is: do not repeatedly re-enter root navigation when a smaller owner can prove the next state.

## 2. Canonical Workflow

### 2.1 Root-owned operations

For operations whose body truly starts from a stable root screen:

1. The task/tool declares or requests a root preflight state.
2. The runner/tool proves that state before the operation body starts.
3. The operation body assumes that root contract and fails fast if it is violated.
4. Repeated internal loops do not call screen-flow root entry on every iteration.

Examples:

- `ResearchTask` starts from Home City.
- `GatheringTask` starts from World Map.
- world-map search starts from a proven `PNC_WORLD_MAP` observation.

### 2.2 Subflow-owned operations

For operations that may resume from meaningful in-progress screens:

1. The operation does not force unconditional root preflight.
2. The operation owns its subflow boundary explicitly.
3. The operation declares its definition-of-done state for the subflow.
4. Its resolver checks whether the current observation already satisfies that done state before planning more actions.
5. The done-state proof becomes an additional success criterion for the subflow, not a runner-owned root preflight.
6. It may navigate to a root only when that is the correct recovery or completion path.

Examples:

- `BuildingUpgradeTask`
- `OpenBuildingTask`

These should not be mechanically migrated to root preflight unless their ownership changes.

Definition-of-done examples:

- building upgrade is complete when one of the task-owned success proofs is visible, such as a home-city build timer, build-queue upgrading row, speedup control on the building screen, or a verified level increase;
- open-building is complete when the target building-owned screen or building-details screen is proven;
- a subflow that is blocked by an unmet requirement is done only if that blocked outcome is one of the declared terminal outcomes.

The runner should not interpret those details. The runner only executes actions, captures requested follow-up observations, and enforces task-loop budgets. The task or feature resolver owns the done-state predicate because it knows which intermediate screens are valid, terminal, recoverable, or unexpected.

### 2.3 Intermediate proof checkpoints

For operations that require multiple UI state changes after the root is proven:

1. The owner of the next transition emits an action with a narrow follow-up observation request when the next action depends on the resulting UI.
2. The follow-up observation is validated against the transition's expected state or against the subflow's definition of done.
3. Missing expected UI fails fast or replans through the same owner, rather than silently falling back to broad root navigation.
4. Broad root recovery is reserved for cases where the operation truly left its owned surface or subflow.

Examples:

- world-map coordinate jump: prove world map, open magnifier/search UI, prove coordinate entry UI, submit coordinates, prove world-map viewport landed at the requested coordinate;
- building upgrade: reach home city if needed, open/focus building, prove building details or exact building-owned screen, prove upgrade button, requirement panel, confirmation, speedup, build queue, or home-city timer as appropriate, then prove the declared completion state.

### 2.4 In-surface operations

For operations already inside a spatial surface:

1. Entry to the screen/surface is proven before traversal begins.
2. Movement and interaction are owned by spatial navigation or feature-specific in-surface logic.
3. The operation can refresh/re-prove the post-action observation as the same surface.
4. It should not repeatedly invoke screen-flow entry/readiness per movement step.

Examples:

- world-map checkpoint movement
- world-map search sweeps
- world-map visible-object tapping
- home-city camera/object focus once Home City surface ownership is established

## 3. Ownership Boundaries

- `AutomationRunner` owns task-declared root preflight, account/castle alignment, and popup recovery before task execution.
- `ScreenFlowPlanner` owns cross-screen navigation increments and their action-scoped follow-up requests.
- Domain services such as `WorldMapSearchService` and the future coordinate-jump navigator own in-surface movement and coordinate-jump proof.
- Subflow tasks such as `BuildingUpgradeTask` own building-detail, confirmation, speedup/build-queue, requirement-panel, definition-of-done, and success verification checkpoints.
- `ObservedActionExecutor` owns generic `observe_after` execution, selector fallback, and follow-up-request matching only; it must not own feature semantics.
- `ObservationService` owns parsing/classification only; it does not decide workflow ownership.

Use precise terms:

- root preflight: entry proof before an operation body starts;
- transition proof or intermediate proof: action-scoped proof after a state-changing step inside an operation;
- done-state proof: subflow-owned proof that the operation's declared terminal state is present.

## 4. Architecture Direction

High-level tasks represent user intent, such as upgrading a building, searching for a castle, or writing mail. Each high-level task has:

- one optional root preflight condition that determines whether the runner must prove a starting root before the task body begins;
- a task-owned execution flow that may be split into subflow increments;
- task-owned runtime state that records which subflow increment is active or pending;
- task-owned verification that consumes each post-action observation, updates runtime state, and returns success, skip, replan, or failure.

Subflow increments should be modeled consistently, even if they remain implemented as task helpers instead of a formal class:

- before condition: the observation state required before the increment can plan its action;
- execution content: the action or action sequence to perform, with narrow `observe_after` follow-up requests when the next step depends on the resulting UI;
- success condition: the observation state that proves the increment completed;
- failure/replan policy: the bounded behavior when the expected postcondition is missing.

The client runner executes the flow and propagates results, but it should not own subflow semantics:

- it calls task `plan(...)`,
- executes returned actions through the observed action executor,
- passes `before` and `after` observations to task `verify(...)`,
- advances to the next loop only when the task returns `REPLAN`,
- finishes only when the task returns `SUCCESS` or `SKIPPED`,
- fails fast when the task returns `FAILED` or exceeds its bounded replan/retry policy.

This matches the current architecture direction: `AutomationTask` already exposes `preflight`, `is_applicable`, `plan`, `verify`, and `max_replans_per_step`; `TaskContext.runtime_state` already carries task-owned subflow state; `ActionRequest.observe_after` plus `ObservationRequest` already provides transition-scoped observation. The remaining design goal is to make subflow before/action/success contracts more explicit and DRY where tasks currently encode them as scattered `plan`/`verify` branches.

The architecture should stay lightweight:

- do not introduce a second workflow engine beside `AutomationRunner`;
- do not move feature semantics into the runner;
- prefer small reusable resolver/helper contracts that tasks call from `plan(...)` and `verify(...)`;
- only extract a formal helper when two or more tasks or branches share the same before/action/success concept.

### 4.1 Missing simplification targets

The current code already has the raw pieces, but these concepts should be made explicit during refactors:

- **Reusable subflow contract helpers**: shared helpers should bundle the before condition, planned actions, expected follow-up request, success predicate, and failure/replan policy for one repeated subflow. Examples: Home City target opening, active-castle resolution, fixed-channel chat send, mail compose entry, mailbox/thread verification, world-map resource acquisition, and march dispatch handoff.
- **Typed task endpoint contracts**: tasks that produce reusable outcomes should expose either a final observation endpoint or a structured data endpoint. The current runner starts each script step with a fresh observation and `StepRunResult` does not carry typed payloads, so structured endpoints must be persisted in a canonical store or added as an explicit runner-visible output before later tasks depend on them. Examples: castle search can end with player profile open, or can persist/return a castle coordinate result for a later mail task; gathering acquisition can end with a resource-node details endpoint handed to march management.
- **Runtime-state ownership discipline**: raw string keys in `TaskContext.runtime_state` should stay encapsulated inside the owning task/subflow helper. Callers should not read or mutate another helper's private keys; shared helpers should provide named getters/setters or typed state objects when state crosses helper boundaries.
- **Root preflight stays small**: `TaskPreflight` should remain a runner-owned root/surface entry contract, not grow into every intermediate screen. Screens such as Campaign map, research detail, mail compose, research speedup, and march confirmation are subflow before/done states owned below the task body.
- **Observation endpoint reuse**: when one step intentionally leaves the device on a useful endpoint screen, the next task should be able to accept that observation as a valid starting point rather than navigating away and back again.

### 4.2 Subflow categories as discovery tags

Do not introduce a formal subtask category hierarchy yet. The current task set is large enough to reveal patterns, but not yet stable enough to justify a second abstraction layer.

Instead, audit each subflow with lightweight category tags. Use the tags to find repeated procedural contracts, then extract a shared helper only when the same category repeats with the same before/action/success shape.

Useful category dimensions:

- **Before requirement type**: root screen, owned subflow screen, spatial surface, popup/modal, list surface, structured stored data, or active runtime state.
- **Execution type**: tap selector, tap spatial object, tap list row, input text, swipe/focus, wait/settle, capture-only observation, or multi-action sequence.
- **Follow-up proof type**: same-surface refresh, destination screen proof, field-state proof, list-entry proof, status-banner proof, timer/queue proof, persisted-data proof, or endpoint observation proof.
- **Final validation type**: success state, skipped/no-op state, blocked terminal state, retryable transient miss, or fail-fast invalid state.
- **Output type**: none, reusable endpoint observation, structured in-memory result, persisted store record, or runtime-state handoff.

Initial subflow categories to track:

- **Root entry**: runner/tool proves Home City or World Map once.
- **Home City target opening**: client supplies target selector/query; shared helper focuses/taps; client proves target screen.
- **Cross-screen navigation**: one screen-flow increment with action-scoped follow-up proof.
- **In-surface traversal**: movement/search inside World Map, Home City, Campaign map, research tree, or list-like surfaces.
- **Target acquisition**: find/select a resource node, castle, building, research tech, campaign node, mail row, or chat row.
- **Form entry**: type fields and prove text-field state when later logic depends on it.
- **Queue/timer handling**: observe active research/build/march queue, speedup surface, timer, or completion.
- **Dispatch handoff**: transfer from feature-specific target selection to shared march-management dispatch.
- **Archive/capture**: perform a transcript/thread capture and persist a structured record.
- **Terminal proof**: validate success, no-op, blocked, no-target, or completed state.
- **Recovery**: popup close, unknown-screen recovery, loading wait, or bounded retry.

This keeps the architecture simple: categories guide refactoring, but `AutomationRunner`, `AutomationTask.plan(...)`, `AutomationTask.verify(...)`, `TaskContext.runtime_state`, and `ActionRequest` remain the execution model.

### 4.3 Refactor target

Refactors should reshape existing tasks into this mold instead of adding a parallel workflow system. When an existing task already owns a useful subflow, keep that task as the public entry point and extract shared subflow contracts only where they remove real duplication.

Home-city object opening should be one shared subflow used by tasks that begin by clicking a home-city object. The client task supplies the target; the reusable subflow supplies the common Home City search/focus/tap mechanics:

- before condition: proven Home City surface;
- target input owned by client: requested object id, selector id, spatial query, or shortcut strategy;
- selector/query owned by client target: for example Blacksmith uses the Blacksmith object/query, Campaign uses `PNC_HOME_CAMPAIGN_ENTRY`, Institute/research uses `PNC_HOME_RESEARCH_BUTTON` or the Institute object/query;
- action owned by shared subflow: focus/tap the supplied target through the shared home-city object/navigation helper;
- success condition owned by client target: the target screen is proven by the consumer's own screen contract.

Consumers should not each reimplement "find object in Home City, tap it, wait for screen" logic. They should differ by target object and by the target-screen/done-state proof that follows.

Examples:

- Any building upgrade: `BuildingUpgradeTask` requests the specific building target from policy, such as Blacksmith, Castle, Institute, or another upgradeable building; the shared city-navigation subflow opens that requested building; building-upgrade then owns eligibility, upgrade, confirmation, speedup, and done-state proof.
- Campaign task: the campaign consumer requests the Campaign target/shortcut; the shared city-navigation subflow opens Campaign; the Campaign/Arena owner handles campaign-map semantics after `PNC_CAMPAIGN_MAP` is proven.
- Research task: `ResearchTask` requests Institute/research entry; the shared city-navigation subflow opens Institute; research then owns category/tree/detail/start/speedup behavior.

For mail, `SendMailTask` should become a clearer composition of shared subflows:

- compose-entry resolution: reach the correct source, open compose, and prove the compose popup;
- recipient proof/repair: verify the target field against the recipient strategy, repairing only when the strategy allows manual entry;
- body entry and send: type subject/body and submit from a proven compose popup;
- sent-mail verification: reopen the correct mailbox/thread and prove the sent content when required.

Alliance mail and direct-player mail should share the procedural compose/send/verify machinery where their UI path is the same. They should differ through explicit strategy/done-state definitions:

- alliance mail expects the alliance compose destination and verifies through the alliance mailbox path;
- direct player mail expects the individual player destination and verifies through the player mailbox/thread path;
- profile-route player mail may begin from an already-open lord/player profile and should not re-run earlier route acquisition when the profile is already proven.

World-map castle search should expose composable endpoints rather than hard-wiring the next task:

- a found castle can end with lord/player info open; that observation can become the starting point for direct-player mail because mail can be opened from lord info/profile;
- a found castle can end as cached structured data, including coordinate and identity evidence; alliance mail can then compose a report containing that coordinate without requiring the search UI to stay open;
- future search consumers should consume the same canonical search result object or endpoint observation, not duplicate castle-search traversal or profile-opening logic.

### 4.4 Supported task refactor targets

Refactor targets for the currently registered tasks:

- `EnsureGameRunningTask`: keep as bootstrap-owned, with explicit subflow contracts for unknown recovery, Android-home launch, launch/loading wait, and in-game proof. Its done state is any non-Android, non-unknown game-owned screen.
- `PopupRecoveryTask`: keep as runner-invoked utility task. Its single subflow contract is dismiss blocking popup; done state is `not after.blocking_popup`. It should remain feature-agnostic.
- `LoginTask`: split current branches into account/session subflows: account-switch correction, credential submission, loading/reconnect wait, in-game session verification, and roster/Lord Info verification. Its done state is configured-account proof or trusted accessible-session proof, not merely reaching Home City.
- `SelectCastleTask`: make the Manage Char/Lord Info switching flow explicit: return to root-adjacent screen, open verification surface, select target castle, wait through switch/loading, and revalidate current castle. Its done state is exact target-castle proof on Home City or Lord Info; ambiguous name-only proof remains a replan to Manage Char.
- `RefreshCastleRosterTask`: keep the existing phase machine but name each phase as a subflow contract: open Manage Char, seek top, scan forward with duplicate-window detection, persist full scan, return Home City. Its done state is persisted full-scan ordering plus Home City return.
- `SendAllianceChatMessageTask` / `SendWorldChatMessageTask`: preserve the shared base as the canonical fixed-channel chat-send subflow. The strategy difference is only the target channel; shared contracts are reach chat-ready surface, select channel, send message, prove empty draft on the expected channel.
- `SendMailTask`: extract shared compose/send/verification subflows behind recipient strategies. Alliance, direct-player, and profile-route mail should share compose-popup proof, subject/body entry, send submission, and mailbox/thread verification where applicable; they differ by recipient proof, allowed target repair, start endpoint, and sent-mail done state.
- `CollectMailTask`: keep mailbox collection as a task-owned scanner, but extract explicit subflows for active-castle label resolution, mailbox open, row selection, thread archive, mailbox return, scroll/advance, and all-mailbox completion. Share active-castle resolution with chat collection through the existing helper.
- `CollectKingdomChatTask`: keep heartbeat polling as a compact composition of active-castle exact resolution, chat channel alignment, transcript-grade capture, unsupported-row validation, and archive persistence. Its done state is archive persistence result for the visible Kingdom Chat delta.
- `OpenBuildingTask`: keep as the canonical non-mutating home-city object opener. Its subflows are home-city recovery/search, target focus, visible-object tap, and requested-screen proof. Its done state is `requested_home_city_object_observation_matches(...)`.
- `BuildingUpgradeTask`: keep it not-root-preflight-owned because it may validly resume from building details, requirement, confirmation, build queue, or post-start verification screens. Refactor the existing state machine into named subflow contracts: active-build/help precheck, Home City target discovery/focus, target open, eligibility/requirement proof, upgrade-start tap, confirmation tap, post-start settle, success verification via home timer/build queue/speedup/level increase, and optional post-start help. The Home City surface is the before-condition for target discovery, not the runner-level preflight for the entire task. Its done state must be one declared success or terminal blocked outcome.
- `ResearchTask`: keep root preflight as Home City, but split the task body into explicit research subflows. The first subflow is Home City -> Institute proof by tapping the Institute/research building entry. The second subflow is Institute -> target research detail by choosing the requested category, navigating the tech tree, scrolling/focusing if needed, and opening the target tech popup. The third subflow is target-action/result handling from the research detail, research queue, or research speedup screen. Supported modes should be explicit: start research only; start research then speed up until completion; speed up an already-started research. Speedup may begin from the active research queue or from the active/current research tech in the tree, and both should converge on the same research-speedup screen contract. Done states differ by mode: research started, research completed, already active research sped up/completed, or no eligible research.
- `GatheringTask`: keep root preflight as World Map. Split target acquisition from shared march dispatch. Target acquisition has two supported paths: visible-node acquisition by selecting a resource node already present in the viewport, and search-driven acquisition by using either world-map viewport iteration or the built-in world-map search UI. Once a resource node is opened, gathering should hand off to the shared march-management layer for march-open, troop/slot confirmation, dispatch, and post-dispatch proof. Its done state is a march-management dispatch proof, march-slot decrease, or a declared no-target/no-march terminal state.
- `CampaignTask`: treat the campaign map/screen as the real task-body preflight. Opening Campaign from Home City is a reusable Home City object-opening subflow, similar to opening Institute for research or opening a building before building upgrade. Once `PNC_CAMPAIGN_MAP` is proven, hand off campaign-map node semantics, progression gates, stage navigation, Arena sibling behavior, and future battle/match solving to `PNC_CAMPAIGN_ARENA_MATCH_SOLVER_SUBPLAN.md`.
- world-map search consumers: keep search traversal in `WorldMapSearchService`. Search tasks should consume either a structured search result endpoint or an endpoint observation such as open player profile/lord info; they should not duplicate traversal, castle inspection, coordinate jump, or survey-index logic.

### 4.5 Registered task category coverage

This coverage map is validated against `build_default_task_registry()` in `pnc_automation/app/authoring/scripts/registry.py` and the concrete task classes under `pnc_automation/app/automation/tasks`. Every registered task must appear here before the refactor is considered complete. Future task additions must update this section and either reuse an existing category/helper or explain the new category being introduced.

Registered task coverage:

| Registered task | Root/preflight posture | Primary category tags | Refactor ownership target |
| --- | --- | --- | --- |
| `EnsureGameRunningTask` | Bootstrap/root-adjacent, no feature root required. | Recovery, root entry/bootstrap, wait/settle, terminal proof. | Own launch/unknown-screen recovery and prove any valid in-game endpoint without feature semantics. |
| `PopupRecoveryTask` | Runner utility, no feature root required. | Recovery, popup/modal, terminal proof. | Own only generic blocking-popup dismissal; never own feature-specific recovery. |
| `LoginTask` | Session/account entry, not just Home City. | Cross-screen navigation, form entry, recovery, terminal account proof. | Own login/account/castle alignment checkpoints and prove configured account or trusted accessible session. |
| `SelectCastleTask` | Root-adjacent castle alignment flow. | Cross-screen navigation, target acquisition, list selection, wait/settle, terminal proof. | Own Manage Char/Lord Info switching and prove the selected castle after loading. |
| `RefreshCastleRosterTask` | Root-adjacent roster capture flow. | Cross-screen navigation, list traversal, archive/capture, persisted-data proof, terminal proof. | Own full roster scan, duplicate-window detection, persistence, and Home City return. |
| `SendAllianceChatMessageTask` | Chat surface owned by shared chat helper. | Cross-screen navigation, form entry, fixed-channel proof, terminal proof. | Share the fixed-channel chat-send subflow; differ only by Alliance channel strategy. |
| `SendWorldChatMessageTask` | Chat surface owned by shared chat helper. | Cross-screen navigation, form entry, fixed-channel proof, terminal proof. | Share the fixed-channel chat-send subflow; differ only by World channel strategy. |
| `SendMailTask` | Recipient strategy decides entry endpoint. | Cross-screen navigation, endpoint observation reuse, form entry, recipient proof, mailbox/thread proof, terminal proof. | Own mail intent while reusing compose/send/verify subflows across alliance, direct-player, and profile-route mail. |
| `CollectMailTask` | Mailbox scanner, no broad root injected inside scan. | Active-castle resolution, cross-screen navigation, list traversal, archive/capture, persisted-data proof, terminal proof. | Own mailbox/thread scanning and share active-castle resolution with chat collection. |
| `CollectKingdomChatTask` | Chat capture scanner, no broad root injected inside capture. | Active-castle resolution, channel alignment, archive/capture, persisted-data proof, terminal proof. | Own Kingdom Chat delta capture and archive persistence; reject unsupported row states explicitly. |
| `OpenBuildingTask` | Subflow-owned Home City object opener. | Home City target opening, in-surface traversal, target acquisition, endpoint observation proof. | Be the canonical non-mutating Home City object-opening consumer. |
| `BuildingUpgradeTask` | Subflow-owned, not unconditional Home City root-owned. | Home City target opening, target acquisition, popup/modal, queue/timer handling, requirement proof, terminal proof. | Own building details, requirements, confirmation, speedup/build-queue, and final upgrade result checkpoints. |
| `ResearchTask` | Currently root-owned Home City entry, then research-owned subflows. | Home City target opening, in-surface tech-tree traversal, target acquisition, popup/modal, queue/timer handling, speedup, terminal proof. | Own Institute/category/tree/detail/start/speedup modes and converge all speedup entries on one speedup-screen contract. |
| `GatheringTask` | Root-owned World Map entry before target acquisition. | World-map root entry, in-surface traversal, target acquisition, built-in search, status-banner proof, dispatch handoff, terminal proof. | Own resource target acquisition and hand the opened gathering endpoint to march management for dispatch. |
| `CampaignTask` | Migration target: Home City target opening, then Campaign-map endpoint. | Home City target opening, campaign-map endpoint proof, in-surface traversal handoff, terminal proof. | Own only entry to/proof of Campaign map until campaign-map semantics are delegated to `PNC_CAMPAIGN_ARENA_MATCH_SOLVER_SUBPLAN.md`. |

Unregistered but covered infrastructure:

- `_BaseSendChatMessageTask` is the canonical shared fixed-channel chat-send subflow for `SendAllianceChatMessageTask` and `SendWorldChatMessageTask`; it is not a standalone task.
- `active_castle_resolution.py` is shared subflow infrastructure for exact active-castle proof and must remain owned by its callers through explicit before/action/success contracts.
- `open_building_support.py`, Home City object navigation, and building catalog selectors are shared Home City target-opening infrastructure; upgrade, research, campaign, and explicit open-building tasks should call the same concept instead of duplicating target focus/tap/proof logic.

## 5. Required Behavior

### 5.1 World-map search

World-map search is the most important immediate case.

Required model:

1. Caller or runner proves `PNC_WORLD_MAP` before search starts.
2. `WorldMapSearchService.execute_search(...)` requires a proven world-map observation.
3. Checkpoint traversal uses search/spatial-navigation movement only.
4. After each swipe, the search layer may use bounded post-action refresh to prove a parsed world-map surface.
5. The checkpoint loop must not call `ScreenFlowPlanner.ensure_world_map_ready(...)` as routine per-step navigation.

Clean validation:

- Add a multi-checkpoint production-path test for `WorldMapSearchService.execute_search(...)`.
- Instrument or fake the screen-flow planner so the test fails if `ensure_world_map_ready(...)` is called during checkpoint traversal.
- Still allow `_require_proven_world_map_observation(...)` or equivalent post-action surface refresh when the follow-up frame is coarse/unknown/transient.

### 5.2 Magnifier / coordinate jump

Required model:

1. Caller or runner proves `PNC_WORLD_MAP` once.
2. The coordinate-jump owner verifies the world-map surface before opening the magnifier/search UI.
3. After tapping magnifier/search, it observes the coordinate input UI.
4. After entering coordinates and pressing go, it observes/proves world map again.
5. It verifies the viewport coordinate moved to the requested target or fails fast.
6. It must not call `ensure_world_map_ready(...)` as routine navigation between internal steps unless the flow truly left world-map ownership.

### 5.3 Building upgrade

Required model:

1. No unconditional root preflight unless the task is redesigned as root-owned.
2. The task/subflow owns each checkpoint:
   - reach or recover to Home City when needed,
   - focus/open target building,
   - prove building details or exact building-owned screen,
   - prove upgrade button, requirement panel, confirmation, speedup, build queue, or home-city timer as appropriate,
   - verify the declared final result.
3. Intermediate observations are expected after state-changing clicks, but they should be narrow and tied to the expected next state.
4. Success requires a declared done-state proof, not merely successful execution of the last click.

### 5.4 Long operations with one starting proof

Required model:

1. Keep runner/tool root preflight once.
2. Inner loops may refresh the same surface after movement/action.
3. Inner loops must not repeatedly invoke broad root-entry flows unless they actually left the owned surface.

### 5.5 Campaign entry boundary

Campaign should be treated as a home-city-object entry plus a campaign-owned subtree:

1. Home City -> Campaign map:
   - before condition: proven Home City surface;
   - action: use the shared home-city object-opening subflow to tap the Campaign object/shortcut;
   - success condition: `PNC_CAMPAIGN_MAP` is proven.
2. Campaign map and below:
   - owner: `PNC_CAMPAIGN_ARENA_MATCH_SOLVER_SUBPLAN.md`;
   - includes campaign-map classification, progression-gate detection, node taxonomy, stage navigation, Arena sibling behavior, and future battle/match solving.

Campaign-map identification should use positive campaign evidence first and world-map negative evidence only as support:

- positive evidence: home/city return icon, campaign region labels or numbered zones, locked region icons, special destination labels such as `Neptune's Labyrinth`, map-node labels such as `Misty Bay`, and campaign-only map artwork/region boundaries;
- negative/supporting evidence: no world coordinate bar, no `X:/Y:` coordinate text, no world-map coordinate magnifier, and no world-map bottom-left built-in search panel state;
- fail-fast rule: do not classify as Campaign from "not world map" alone.

Relevant selector/screen targets for the boundary:

- existing selectors to keep using: `PNC_HOME_CAMPAIGN_ENTRY`, `PNC_CAMPAIGN_MAP_REGION_NODE`, `PNC_CAMPAIGN_MAP_SPECIAL_STAGE_NODE`;
- selectors to add or strengthen: `PNC_CAMPAIGN_HOME_CITY_BUTTON`, `PNC_CAMPAIGN_REGION_LABEL`, `PNC_CAMPAIGN_REGION_LOCK_BADGE`, `PNC_CAMPAIGN_STAGE_LABEL`, `PNC_CAMPAIGN_SPECIAL_STAGE_LABEL`, `PNC_CAMPAIGN_MAP_PAGE_OR_ZONE_MARKER`;
- target screen proof: `PNC_CAMPAIGN_MAP` should require campaign-positive evidence and must reject frames that still prove `PNC_WORLD_MAP`.

### 5.6 Gathering target acquisition

Gathering should be modeled as world-map target acquisition plus shared march dispatch:

1. World Map preflight:
   - before condition: proven `PNC_WORLD_MAP` with parsed world-map surface;
   - owner: runner/tool root preflight;
   - success condition: addressable world-map viewport.
2. Visible-node acquisition:
   - before condition: proven world-map viewport;
   - action: select an already visible resource node matching policy;
   - success condition: `PNC_GATHER_NODE` or equivalent resource-node details surface.
3. Search-iteration acquisition:
   - before condition: proven world-map viewport;
   - action: use `WorldMapSearchService`/survey traversal to iterate viewports and find matching resource nodes;
   - success condition: matching resource node visible and selectable, then opened into resource-node details.
4. Built-in search acquisition:
   - before condition: proven world-map viewport;
   - action: tap the lower-left world-search/magnifier control, choose resource type, choose target level, optionally enable full-resource-only filtering, and confirm;
   - success condition: viewport moves to a matching highlighted resource tile or a status banner declares no matching resource nearby.
5. Resource-node details -> march handoff:
   - before condition: opened matching resource node;
   - action: tap gather/open-march;
   - success condition: shared march-management surface is reached.

Built-in search failure is a terminal target-acquisition outcome when the game reports no matching resources, for example "Can't find resources at the target level in the vicinity of your territory." The viewport may not move in that case; the task must treat the status banner as the proof instead of trying to infer failure from unchanged coordinates.

Relevant selector/screen targets from the current screenshots:

- existing selectors to keep using: `PNC_WORLD_SEARCH_BUTTON`, `PNC_GATHER_BUTTON`, `PNC_MARCH_CONFIRM_BUTTON`, `PNC_STATUS_BANNER`;
- screen types to add or make first-class if currently folded into generic world-map parsing: `PNC_WORLD_SEARCH_PANEL`, `PNC_WORLD_SEARCH_RESULT_HIGHLIGHT`, `PNC_GATHER_NODE`;
- selectors to distinguish the two world-map search controls: `PNC_WORLD_COORDINATE_SEARCH_BUTTON` for the coordinate-bar magnifier and `PNC_WORLD_BUILTIN_SEARCH_BUTTON` for the lower-left search/magnifier;
- selectors for built-in search: `PNC_WORLD_SEARCH_RESOURCE_TYPE_TAB`, `PNC_WORLD_SEARCH_RESOURCE_FOOD_OPTION`, `PNC_WORLD_SEARCH_RESOURCE_WOOD_OPTION`, `PNC_WORLD_SEARCH_RESOURCE_IRON_OPTION`, `PNC_WORLD_SEARCH_RESOURCE_GAS_OPTION`, `PNC_WORLD_SEARCH_LEVEL_MINUS_BUTTON`, `PNC_WORLD_SEARCH_LEVEL_PLUS_BUTTON`, `PNC_WORLD_SEARCH_LEVEL_SLIDER`, `PNC_WORLD_SEARCH_LEVEL_VALUE`, `PNC_WORLD_SEARCH_FULL_RESOURCE_ONLY_CHECKBOX`, `PNC_WORLD_SEARCH_CONFIRM_BUTTON`;
- selectors for result proof: `PNC_WORLD_SEARCH_HIGHLIGHT_ARROW`, `PNC_WORLD_SEARCH_DISTANCE_BUBBLE`, `PNC_GATHER_NODE_TITLE`, `PNC_GATHER_NODE_LEVEL_LABEL`, `PNC_GATHER_NODE_RESOURCE_TYPE_LABEL`.

March-slot, troop-selection, dispatch, and post-dispatch proof belong in `PNC_MARCH_MANAGEMENT_SUBPLAN.md`; gathering should consume that shared march layer after target acquisition.

### 5.7 Research start and speedup

Research should be modeled as subflow-owned after the Home City root preflight:

1. Home City -> Institute:
   - before condition: proven Home City;
   - action: open Institute/research building;
   - success condition: `PNC_INSTITUTE`.
2. Institute -> research detail:
   - before condition: `PNC_INSTITUTE` or `PNC_RESEARCH_TREE`;
   - action: choose category, navigate/focus the category-specific tech tree, open the requested tech;
   - success condition: a typed research-detail popup/screen for the requested tech.
3. Research detail -> active research:
   - before condition: requested tech detail with `Research` or `Research Now`;
   - action: start research, optionally confirm paid instant-start only when policy allows it;
   - success condition: active research timer/progress is visible on the tech detail, research queue, or speedup screen.
4. Active research -> speedup screen:
   - before condition: active research exists either in the research queue or on the active/current tech detail;
   - action: tap `Speedup`;
   - success condition: `PNC_RESEARCH_SPEEDUP`.
5. Speedup screen -> completion:
   - before condition: `PNC_RESEARCH_SPEEDUP`;
   - action: use allowed speedups or `Auto Speedup` according to policy;
   - success condition: research timer reaches completion, active queue clears, or the completed tech level/progress is proven.

Supported use cases:

- start research without spending speedups;
- start research and speed it up until completion;
- speed up an already-started research, whether discovered from the research queue or from the current tech in the tree.

Research-tree traversal must support all visible Institute categories, not just the currently well-covered trees:

- Development
- Economy
- Military
- Fortification

Each category should have a category-specific traversal contract:

- root/header proof for the active category;
- visible tech-node parsing with title, current/max level, lock state, and action point;
- bottom pagination/position markers when they are needed to detect movement or coverage;
- scroll/focus movement within the category tree;
- completion stop when the requested tech is found, when every visible/scrollable stop has been exhausted, or when the category is fully maxed/locked and no eligible target exists.

Complete-tree and missing-category stops should be explicit:

- a fully completed or maxed visible tree is a valid terminal skip only when no requested speedup or active research target exists in that tree;
- a missing/unavailable category is a terminal skipped or failed outcome depending on policy, not a reason to guess another category;
- locked category rows on the Institute screen, such as level-gated categories, should be parsed as locked/unavailable with their requirement text.

Relevant selector/screen targets from the current screenshots:

- existing selectors to keep using: `PNC_HOME_RESEARCH_BUTTON`, `PNC_INSTITUTE_HEADER`, `PNC_INSTITUTE_DEVELOPMENT_BUTTON`, `PNC_INSTITUTE_ECONOMY_BUTTON`, `PNC_INSTITUTE_MILITARY_BUTTON`, `PNC_INSTITUTE_FORTIFICATION_BUTTON`, `PNC_INSTITUTE_RESEARCH_QUEUE_PANEL`, `PNC_RESEARCH_AVAILABLE_BADGE`, `PNC_RESEARCH_START_BUTTON`;
- screen types to add or make first-class if currently folded into generic popup/tree parsing: `PNC_RESEARCH_DETAIL`, `PNC_RESEARCH_QUEUE`, `PNC_RESEARCH_SPEEDUP`;
- selectors to add for Institute/queue entry: `PNC_INSTITUTE_RESEARCH_QUEUE_BUTTON`, `PNC_RESEARCH_QUEUE_ACTIVE_ROW`, `PNC_RESEARCH_QUEUE_SPEEDUP_BUTTON`, `PNC_RESEARCH_QUEUE_CLOSE_BUTTON`;
- selectors to add for the category tech trees: `PNC_RESEARCH_TREE_CATEGORY_HEADER`, `PNC_RESEARCH_TECH_NODE`, `PNC_RESEARCH_TECH_NODE_TITLE`, `PNC_RESEARCH_TECH_NODE_LEVEL_LABEL`, `PNC_RESEARCH_TECH_NODE_LOCKED_BADGE`, `PNC_RESEARCH_TREE_PAGE_MARKER`, `PNC_RESEARCH_TREE_MASTER_RESEARCHER_BUTTON`;
- selectors to add for the tech detail popup: `PNC_RESEARCH_DETAIL_PANEL`, `PNC_RESEARCH_DETAIL_TITLE`, `PNC_RESEARCH_DETAIL_LEVEL_LABEL`, `PNC_RESEARCH_DETAIL_RESEARCH_BUTTON`, `PNC_RESEARCH_DETAIL_RESEARCH_NOW_BUTTON`, `PNC_RESEARCH_DETAIL_SPEEDUP_BUTTON`, `PNC_RESEARCH_DETAIL_TIMER`, `PNC_RESEARCH_DETAIL_REQUIREMENT_ROW`;
- selectors to add for the speedup screen: `PNC_RESEARCH_SPEEDUP_HEADER`, `PNC_RESEARCH_SPEEDUP_ITEM_USE_BUTTON`, `PNC_RESEARCH_SPEEDUP_ITEM_USE_IN_BULK_BUTTON`, `PNC_RESEARCH_SPEEDUP_RESEARCH_NOW_BUTTON`, `PNC_RESEARCH_SPEEDUP_AUTO_SPEEDUP_BUTTON`, `PNC_RESEARCH_SPEEDUP_TIME_LEFT_BAR`.

## 6. Operation Inventory To Validate

### 6.1 Runner-owned root preflight

Validate these operations use runner/tool root preflight before the body:

- `ResearchTask`: `TaskPreflight.HOME_CITY`
- `GatheringTask`: `TaskPreflight.WORLD_MAP`
- external live calibration tool: explicit world-map preflight before calibration phases
- future world-map search consumers: explicit or runner-owned `WORLD_MAP` preflight

Audit note:

- `CampaignTask` currently declares `TaskPreflight.HOME_CITY`, but the desired model is Home City target opening followed by a proven Campaign-map endpoint. Treat this as a migration target, not as evidence that every campaign-related body should be Home-City-owned.

Expected tests:

- runner-level test proving the body receives the required root observation,
- negative test proving the body fails fast or runner preflight activates when the root is absent,
- no repeated root-entry call inside the operation's inner loop.

### 6.2 Not-root-owned subflow tasks

Validate these operations do not force root preflight unless redesigned:

- `BuildingUpgradeTask`
- `OpenBuildingTask`

Expected tests:

- can continue from owned in-progress screens,
- does not discard valid subflow state by forcing Home City first,
- resolver recognizes declared done states before planning more actions,
- done-state proof is required for success rather than relying only on "last action executed",
- uses root navigation only for completion/recovery when appropriate.

### 6.3 World-map in-surface operations

Validate these operations use one-time world-map entry plus in-surface movement:

- `WorldMapSearchService.execute_search(...)`
- `WorldMapMovementCalibrationService.validate_sweep(...)`
- `WorldMapMovementCalibrationService.run_cardinal_calibration(...)`
- `WorldMapMovementCalibrationService.run_dead_zone_verification(...)`
- `GatheringTask` visible-node interaction
- future relic/castle search consumers

Expected tests:

- start from proven `PNC_WORLD_MAP`,
- no routine per-checkpoint `ensure_world_map_ready(...)`,
- bounded post-action observation refresh is allowed,
- movement failures surface as movement/parser issues, not hidden root-navigation churn.

### 6.4 Home-city in-surface operations

Validate these operations use one-time Home City entry plus home-city spatial/navigation ownership:

- opening visible home-city objects,
- home-city object focus/search,
- building/research entry after root preflight.

Expected tests:

- screen-flow proves Home City before root-owned tasks,
- home-city camera movement/object focus does not become generic root navigation,
- missing home-city surface can trigger bounded same-root refresh, not broad recovery loops.

## 7. Audit Checklist

For each operation, record:

- Operation name
- Registry coverage: exact `TaskId`, registered class, or explicit note that the operation is shared infrastructure only
- Required root preflight state, if any
- Whether it can resume from subflow screens
- Declared definition-of-done states, if the operation owns a subflow
- Subflow increments and their before/action/success contracts
- Lightweight subflow category tags
- Production entry point
- Inner loop owner
- Whether inner loop calls screen-flow root entry
- Whether post-action same-surface refresh exists
- Whether intermediate proof checkpoints are action-scoped and narrowly observed
- Whether the operation has endpoint outputs that another task may consume
- Runtime-state owner/helper for each persistent subflow state key
- Tests proving the intended workflow
- Missing tests or refactors

## 8. Required New Tests

### 8.1 World-map search does not re-enter world map per checkpoint

Add a test around `WorldMapSearchService.execute_search(...)` with multiple checkpoints.

The test should:

- start from a proven world-map observation,
- use a screen-flow planner test double that records calls to `ensure_world_map_ready(...)`,
- execute at least two checkpoint moves,
- assert the call count remains zero during traversal,
- assert post-action observations were still refreshed/proven through the search movement path.

### 8.2 Sweep validation uses the same in-surface traversal contract

After refactoring `validate_sweep(...)` to share the search checkpoint movement seam:

- assert sweep validation starts from a proven world-map observation,
- assert it does not invoke screen-flow root entry per checkpoint,
- assert it uses the same configured coordinate mover/runtime state as search.

### 8.3 Root-owned task bodies receive preflighted observations

For each root-owned task:

- build a runner scenario where the initial observation is not the required root,
- prove the runner reaches the required root,
- assert the task body only starts after the preflight proof.

### 8.4 Subflow-owned tasks are not forced back to root

For each subflow-owned task:

- start from an owned in-progress screen,
- assert the task can continue without root preflight,
- assert the task recognizes its declared done state without planning unnecessary actions,
- assert success requires a declared done-state proof or terminal blocked-state proof,
- assert no unconditional root-navigation action is emitted first.

### 8.5 Multi-step flows perform necessary intermediate observations

Add tests proving multi-step flows perform necessary intermediate observations:

- coordinate jump opens coordinate UI, submits target, then verifies landing;
- building upgrade observes building detail, confirmation, speedup/build queue, and result stages.

### 8.6 Intermediate failures fail fast

Add negative tests proving intermediate failures fail fast:

- magnifier popup missing,
- coordinate jump rejected by status banner,
- building detail opens without upgrade/speedup/requirement evidence,
- expected post-action screen is not reached.

### 8.7 Intermediate validation does not become broad root recovery

Add call-count tests proving intermediate validation does not become repeated broad root recovery:

- no per-checkpoint `ensure_world_map_ready(...)` during normal world-map traversal;
- no unconditional Home City preflight injected into subflow-owned building upgrade.

### 8.8 Task endpoints compose without duplicate navigation

Add tests for endpoint reuse between tasks and subflows:

- castle search ending on player profile/lord info can be followed by direct-player mail without reopening the profile route;
- castle search producing structured coordinate data can feed alliance mail body composition without re-running search traversal;
- Home City target-opening helper can open Campaign, Institute, and arbitrary upgradeable buildings using different client-supplied targets/selectors while sharing the same navigation implementation;
- gathering acquisition endpoint hands resource-node details to march management without duplicating march-slot or dispatch logic in `GatheringTask`.

## 9. Refactor Guidance

When an operation violates the workflow:

- do not patch around it with another special case,
- decide who owns the boundary,
- move root entry to runner/tool preflight when the body starts from a root,
- define subflow done states when the operation owns a multi-step subflow,
- extract repeated subflow before/action/success logic into one canonical resolver/helper instead of duplicating predicates across task branches,
- define explicit endpoint outputs when a task result is intended to feed a later task,
- encapsulate runtime-state keys inside the owning task/subflow helper,
- keep transition proof in the smallest owner that knows the expected postcondition,
- keep in-surface traversal below screen flow,
- delete obsolete compatibility paths after migration.

## 10. Assumptions

- "Preflight" should mean root-entry proof only.
- Intermediate validation should be owned by the smallest component that knows the expected postcondition.
- Extra observations are acceptable when a later action depends on the newly visible UI or when a result must be verified.
- Broad observations and root recovery are fallback tools, not the normal proof mechanism inside a well-owned subflow.
- Inter-task composition should prefer explicit endpoint observations or structured persisted data over hidden assumptions about where a previous task happened to leave the UI.

## 11. Success Criteria

This workflow validation is complete when:

- every operation has an explicit entry/root-preflight contract,
- every task registered in `build_default_task_registry()` is present in the registered task category coverage map,
- every task-like helper not registered as a task is explicitly classified as shared infrastructure or removed,
- every subflow-owned operation with terminal semantics has an explicit definition of done,
- repeated subflow contracts have one canonical resolver/helper instead of duplicated before/action/success predicates,
- reusable task endpoints are explicit when later tasks depend on them,
- runtime-state keys are owned and encapsulated by the task/subflow that creates them,
- root-owned operations use runner/tool root preflight once before the body,
- subflow-owned operations keep their subflow ownership and are not forced to root,
- intermediate proof checkpoints are narrow and action-scoped,
- world-map search checkpoint traversal never performs routine screen-flow world-map entry,
- in-surface movement failures surface as movement/parser issues,
- broad root recovery remains fallback-only inside owned subflows,
- and tests exist for each operation category proving the workflow contract.
