# PNC Kingdom Chat Monitor Implementation Document

## 1. Purpose

This document defines the clean implementation plan for a heartbeat-driven Kingdom Chat monitor in the current Puzzles & Conquest automation platform.

The feature must:

- check Kingdom Chat on each heartbeat,
- archive only player chat, not game announcements,
- maintain one daily transcript log,
- persist Kingdom Chat screenshots only when new player chat appeared,
- store transcript and chat screenshots in a durable folder separate from runtime `artifacts/`,
- stay aligned with the existing task, flow, observation, and archive architecture.

This document is intentionally implementation-oriented. It describes the concrete architecture changes required to add this feature without creating a second automation stack, a second scheduler stack, or feature-local file-writing logic.

## 2. Current Repository Context

The repository already has the right major building blocks for this feature:

- one canonical runner and task loop in [pnc_automation/automation/runner.py](/c:/Users/lebel/pnc/pnc_automation/automation/runner.py),
- one script model under [scripts/](/c:/Users/lebel/pnc/scripts),
- one reusable navigation layer in [pnc_automation/pnc/screen_flows.py](/c:/Users/lebel/pnc/pnc_automation/pnc/screen_flows.py),
- one chat-domain module in [pnc_automation/pnc/chat.py](/c:/Users/lebel/pnc/pnc_automation/pnc/chat.py),
- one chat screen parser in [pnc_automation/vision/pnc_observation_enricher.py](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py),
- one observation pipeline in [pnc_automation/vision/observation_builder.py](/c:/Users/lebel/pnc/pnc_automation/vision/observation_builder.py),
- one canonical screenshot pipeline in [pnc_automation/capture/screenshot_service.py](/c:/Users/lebel/pnc/pnc_automation/capture/screenshot_service.py),
- one durable archive pattern already demonstrated by [pnc_automation/capture/mail_archive_store.py](/c:/Users/lebel/pnc/pnc_automation/capture/mail_archive_store.py).

The current architecture is already close to correct. The missing work is not "how do we automate chat at all", but "how do we add one read-only chat-monitor feature without duplicating existing chat navigation, OCR, or persistence concepts."

## 3. Relationship To Existing Planning Documents

This feature should be treated as one dedicated post-navigation feature slice under [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md).

It should consume reusable navigation from [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md) rather than duplicating chat-opening or root-return logic.

Concretely:

- the feature owns Kingdom Chat monitoring behavior,
- reusable chat-channel navigation belongs in `ScreenFlowPlanner`,
- durable chat transcript persistence belongs in one archive store,
- heartbeat scheduling does not belong in the task layer.

## 4. User-Facing Goal

The target behavior is:

1. A Windows-hosted scheduler triggers one heartbeat run.
2. The run ensures the correct account is in game.
3. The run opens chat and lands on the Kingdom tab.
4. The run reads the visible chat rows.
5. The run keeps only player chat rows.
6. The run appends newly seen player messages to the current day's transcript log.
7. The run saves one Kingdom Chat screenshot only if there were new player messages since the last stored heartbeat state.
8. If nothing new was written by players, the transcript is unchanged and no new chat screenshot is written.

The user-facing storage should be durable and easy to inspect manually. It should not be mixed into generic runtime screenshot artifacts.

## 5. Recommended Scheduling Decision

The heartbeat driver should be external.

Recommended first implementation:

- use Windows Task Scheduler,
- keep the automation runtime single-run and idempotent,
- schedule a routine script that performs one bounded Kingdom Chat poll,
- configure Task Scheduler to use `Do not start a new instance` if the previous run is still active.

Recommended scheduled command shape:

```powershell
py -m pnc_automation.cli run --account testing --script scripts/routines/kingdom_chat_heartbeat.yaml
```

Why this is the right boundary:

- the repository already models routines as authored scripts under `scripts/routines/`,
- Windows is explicitly in scope for the project,
- Task Scheduler already owns repetition, boot behavior, and overlap policy,
- the bot does not need an in-process scheduler to perform one heartbeat poll,
- this avoids inventing custom loop, sleep, retry, and lock behavior inside the repo.

The first slice should not add:

- a custom infinite polling loop,
- a Python scheduling library,
- a Windows service wrapper,
- a second scheduler abstraction in the codebase.

If later requirements need cross-platform scheduling, dynamic job definitions, or one always-on process coordinating many jobs, a library such as APScheduler can be reconsidered then. It should not be introduced before there is a real need.

## 6. Scope

## 6.1 In scope

- one routine script for Kingdom Chat heartbeat polling,
- one read-only runtime task that inspects Kingdom Chat,
- one reusable flow addition for ensuring the requested chat channel is active,
- OCR classification that distinguishes player chat from announcements,
- one durable archive store for daily transcript logs and change-driven screenshots,
- one persistence policy that avoids screenshot flooding during heartbeat polling,
- one validation gate with unit, screenshot, and targeted live smoke coverage.

## 6.2 Out of scope for the first slice

- alliance-chat monitoring,
- sending or replying to chat,
- full chat-history scrolling and guaranteed backfill across arbitrarily large message bursts,
- Discord or webhook forwarding,
- in-process scheduling,
- a generic plugin system for chat analytics,
- support for every possible chat announcement layout ever seen in the game.

The first slice should stay bounded: poll the currently visible Kingdom Chat window safely and archive only newly visible player chat.

## 7. Architectural Requirements

This implementation must preserve the repository's existing non-negotiables:

- Single canonical implementation per concept.
- No duplicated logic.
- Fail-fast validation for invalid content.
- Minimal boilerplate.

Feature-specific consequences:

- there must be one canonical heartbeat poll task,
- there must be one canonical durable chat archive store,
- there must be one canonical player-vs-announcement classifier,
- there must be one canonical reusable flow for "ensure chat is open on the requested channel",
- the scheduler boundary must exist once and outside the runtime,
- screenshot dedup must be driven by one canonical transcript-change policy, not by ad hoc file checks scattered through tasks.

## 8. Existing Architecture Gaps That Must Be Fixed

### 8.1 The current runtime has no durable chat archive store

The repository already has [ArtifactStore](/c:/Users/lebel/pnc/pnc_automation/capture/artifact_store.py) for runtime screenshots and [MailArchiveStore](/c:/Users/lebel/pnc/pnc_automation/capture/mail_archive_store.py) for durable mail archives.

There is no corresponding chat archive owner yet.

This must not be solved by writing files directly from a task. One dedicated archive store must own:

- daily directory layout,
- transcript file naming,
- chat screenshot naming,
- heartbeat state persistence,
- dedup and append rules.

### 8.2 Durable archive output is currently mixed conceptually with runtime artifacts

Today mail archives are built under `artifact_root / "mail"`.

That is workable, but it is the wrong ownership boundary for this feature because the user explicitly wants transcript logs and Kingdom Chat screenshots in a folder separate from runtime `artifacts/`.

The clean fix is:

- keep `artifact_root` for runtime debug screenshots,
- add one separate `archive_root` for durable feature outputs,
- move durable archives such as mail and chat under `archive_root`.

This feature is the right time to correct that boundary instead of adding one more feature-specific exception.

### 8.3 Chat-channel selection is currently owned only by send-message planning

Today [send_chat_message()](/c:/Users/lebel/pnc/pnc_automation/pnc/screen_flows.py) owns:

- opening chat,
- selecting the requested channel,
- typing,
- sending.

That is too narrow once a second chat feature needs to land on Kingdom Chat without sending anything.

The channel-selection increment should become one reusable chat flow instead of staying embedded only inside message sending.

### 8.4 The current chat parser does not model announcement filtering explicitly

Today [_extract_chat_message_entries()](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py) groups visible OCR lines into chat entries, but it does not own a typed distinction between:

- player chat,
- game announcements,
- uncertain or unsupported rows.

This feature needs that distinction centrally. The task should consume typed chat-entry meaning, not invent its own OCR heuristics.

### 8.5 The current geometry-first chat shortcut can short-circuit transcript OCR

Today [PncObservationEnricher](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py) can return geometry-proven chat observations before OCR parsing when the request is narrow enough.

That is correct for fast send-flow verification, but a transcript monitor needs OCR-derived chat rows even when geometry already proves `PNC_CHAT`.

The observation request model therefore needs one explicit way to say:

- prove chat cheaply if possible,
- but still parse visible transcript rows because this feature depends on them.

### 8.6 The current runner always persists screenshots for observations

Today [ObservationService.observe()](/c:/Users/lebel/pnc/pnc_automation/vision/observation_builder.py) always writes a screenshot artifact.

That behavior is good for task debugging, but it is wrong for a scheduler-driven monitor that may run every few minutes all day. Even when no player chat changed, it would still create new generic artifact screenshots.

That conflicts directly with the requested behavior:

- do not flood screenshots,
- store the durable chat screenshot only when new player chat appeared,
- keep that durable screenshot outside the generic artifact folder.

The monitor slice therefore needs a shared runtime observation-mode policy rather than blindly reusing "always persist every observation."

### 8.7 The current runtime lacks a clean debug-vs-performance observation switch

Right now the observation behavior is effectively hard-wired:

- routine captures are persisted into `artifacts`,
- many task paths still rely on broad observation behavior,
- there is no explicit runtime mode that says "favor diagnosis" versus "favor throughput."

That is now a broader platform issue, not only a Kingdom Chat issue.

The clean solution is not a chat-specific bypass. It is one canonical runtime observation mode contract that can be toggled:

- `DEBUG` when we want rich evidence and heavier screenshot persistence,
- `LIGHT` when we want performance and minimal screenshot churn.

This should be bundled into this plan because the chat monitor directly depends on it, but it should be implemented first as a prerequisite foundation slice before chat-specific archive work.

## 9. Canonical Target Architecture

## 9.1 Scheduling boundary

Scheduling should stay outside the runtime.

The runtime should expose one bounded routine:

- poll Kingdom Chat once,
- archive any new player messages,
- exit.

Windows Task Scheduler owns:

- heartbeat cadence,
- overlap policy,
- startup behavior,
- retries at the OS scheduling layer if the user wants them.

The automation code owns only one heartbeat execution, not endless repetition.

## 9.2 New runtime task

Add one dedicated task:

- `collect_kingdom_chat`

This task should be the owning runtime concept for the current slice.

It should:

- be read-only with respect to chat content,
- support optional step-level castle targeting through the existing runtime castle policy,
- consume shared flows instead of embedding chat navigation,
- call one archive store instead of writing files directly.

Recommended policy:

- `castle_target_policy = OPTIONAL`

That allows the heartbeat routine to either:

- monitor the currently selected castle, or
- explicitly align to a known castle with `castle_ref` before polling.

## 9.3 New routine script

Add one routine script under [scripts/routines/](/c:/Users/lebel/pnc/scripts/routines):

```yaml
name: kingdom_chat_heartbeat

steps:
  - task: ensure_game_running
  - task: login
  - task: collect_kingdom_chat
    castle_ref: main
```

If the user wants current-castle semantics instead, the `castle_ref` should simply be omitted. The feature must not invent a second targeting contract.

## 9.4 Archive root separation

Add a new top-level config section:

```yaml
artifacts:
  root: artifacts

archives:
  root: archives
```

Recommended ownership:

- `artifact_root`: runtime screenshots and failure diagnostics,
- `archive_root`: durable feature outputs such as mail and chat.

Recommended implementation consequence:

- `MailArchiveStore` should move from `artifact_root / "mail"` to `archive_root / "mail"`,
- new chat archive persistence should live under `archive_root / "chat"`.

This keeps one canonical meaning for each root:

- artifacts are debugging evidence,
- archives are durable harvested content.

## 9.5 Chat archive store

Add a dedicated durable store, for example [pnc_automation/capture/chat_archive_store.py](/c:/Users/lebel/pnc/pnc_automation/capture/chat_archive_store.py).

This store should own:

- daily folder layout,
- transcript file append semantics,
- heartbeat state persistence,
- change-driven screenshot persistence,
- normalization and snapshot fingerprinting,
- per-day rollover.

Recommended layout:

```text
archives/
  chat/
    2026-03-23/
      testing/
        k304_k304554ca2797/
          kingdom/
            transcript.log
            state.json
            screenshots/
              20260323T101500Z_4d81f3c2.png
              20260323T141000Z_9e0c8814.png
```

This path satisfies the user-facing goal:

- one day folder,
- one folder containing both the transcript and screenshots,
- clearly separate from runtime artifacts.

Recommended file responsibilities:

- `transcript.log`: append-only human-readable daily transcript,
- `state.json`: durable dedup and overlap state for heartbeat-to-heartbeat comparisons,
- `screenshots/`: only snapshots where new player chat was appended or a gap/failure diagnostic must be surfaced.

## 9.6 Transcript format

The daily transcript should stay simple and human-readable.

Recommended line format:

```text
[2026-03-23T10:15:00Z] Enemy Bob: Hello there
[2026-03-23T10:15:00Z] Cutie Voj: Need help on rally?
```

Rules:

- one line per appended player message,
- use the capture timestamp for ordering when the game itself does not expose message timestamps reliably,
- keep transcript lines free of announcement rows,
- keep system or gap diagnostics out of the player transcript itself and instead store them in `state.json` or structured logs.

Recommended day boundary:

- archive directory should use host-local day for operator convenience,
- each transcript line should still use an exact UTC timestamp for unambiguous ordering.

## 9.7 Shared chat flow promotion

Promote the channel-selection portion of chat planning into one reusable flow.

Recommended new `ScreenFlowPlanner` helper:

```python
ensure_chat_channel(observation: Observation, channel: ChatChannel) -> list[ActionRequest]
```

Behavior:

- if not on `PNC_CHAT`, call `open_chat()`,
- if already on `PNC_CHAT` but wrong tab is active, emit one `SelectChatChannelAction`,
- if already on the requested tab, return no actions.

Then:

- `send_chat_message()` should consume `ensure_chat_channel()` before typing,
- `collect_kingdom_chat` should consume `ensure_chat_channel(ChatChannel.WORLD)` before transcript parsing.

This is the exact kind of reusable flow that belongs in [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md).

## 9.8 Observation model

The observation layer should continue to use one canonical repeated-entry abstraction through `DetectedListEntry`.

It should not add a second parallel "chat row" collection model inside `Observation`.

Recommended addition in [pnc_automation/pnc/chat.py](/c:/Users/lebel/pnc/pnc_automation/pnc/chat.py):

```python
class ChatEntryKind(StrEnum):
    PLAYER = "player"
    ANNOUNCEMENT = "announcement"
```

Recommended parser behavior:

- continue emitting visible chat rows as `ListEntryKind.CHAT_MESSAGE`,
- add typed metadata describing whether each row is `PLAYER` or `ANNOUNCEMENT`,
- expose a shared helper that projects one `DetectedListEntry` into the typed chat-domain meaning consumed by tasks and archive code.

This keeps:

- one observation list-entry abstraction,
- one typed chat-domain projection,
- no duplicated list models.

## 9.9 Announcement filtering

The feature must archive only player chat.

The parser should therefore classify rows conservatively:

- `PLAYER` when the row has strong sender-plus-message structure,
- `ANNOUNCEMENT` when the row matches known system/announcement structure,
- unsupported rows should not be silently treated as player messages.

Recommended task behavior:

- archive only `PLAYER` rows,
- ignore `ANNOUNCEMENT` rows for transcript-change purposes,
- if the parser encounters unsupported chat structure, surface it through logs and optionally a diagnostic screenshot rather than poisoning the transcript.

Important rule:

- a newly visible announcement must not trigger a durable chat screenshot,
- only newly visible player chat should count as "additional stuff was written."

## 9.10 Monitor-specific observation request

Add one explicit observation request for transcript polling, for example:

```python
ObservationRequest.chat_transcript_observation()
```

It should:

- allow `PNC_CHAT`,
- include chat-state parsing,
- require OCR-backed row extraction for visible chat entries,
- avoid broad full-runtime OCR when narrower chat parsing is sufficient.

This request is necessary because the current chat geometry shortcut is optimized for send verification, not for transcript extraction.

## 9.11 Runtime observation modes

The monitor feature needs one generic way to toggle between heavy debug observation and lighter runtime observation.

Recommended design:

- add one shared runtime observation-mode contract to the runner and observation service,
- allow the mode to be configured globally and overridden from the CLI when needed,
- keep the behavior canonical across features instead of inventing one monitor-specific bypass,
- still let the chat monitor request its own narrow transcript observation request inside that shared runtime mode system.

Recommended policy shape:

```python
class ObservationMode(StrEnum):
    DEBUG = "debug"
    LIGHT = "light"
```

Recommended semantics:

- `DEBUG`
  - preserve the current high-evidence behavior,
  - persist routine observations to `artifacts`,
  - prefer richer follow-up evidence when a task or action path needs it,
  - optimize for diagnosis, screenshot review, and feature bring-up.
- `LIGHT`
  - avoid routine screenshot persistence unless explicitly required,
  - keep failure artifacts and explicit archive screenshots,
  - prefer narrow observation requests wherever the task already has reviewed follow-up scope,
  - optimize for scheduler-driven throughput and low churn.

Rules:

- the mode must be shared runtime infrastructure, not a chat-only flag,
- existing flows and tasks should continue working under both modes,
- `collect_kingdom_chat` should be designed to benefit strongly from `LIGHT`,
- the archive store still persists the user-facing chat screenshot only when the transcript changed,
- the runner still persists a debugging artifact on task failure regardless of mode.

This is the right place to solve the current "too many observations in artifacts" pain because the chat monitor depends on it and the benefit is broader than this one feature.

## 10. Chat Delta Detection

## 10.1 Canonical snapshot model

The archive store should compare snapshots using one canonical normalized visible-window model.

Recommended internal shape:

```python
@dataclass(frozen=True, slots=True)
class VisibleChatSnapshot:
    entries: tuple[NormalizedPlayerChatEntry, ...]
    fingerprint: str
```

Each normalized player entry should include:

- sender name,
- normalized message text,
- stable visible order.

Announcement rows must not participate in the fingerprint.

## 10.2 Append rule

When a new heartbeat snapshot is captured:

1. Load the previous day's stored state.
2. Compare the previous visible player window to the current visible player window.
3. Find the maximum overlap between the previous suffix and current prefix.
4. Treat the non-overlapping tail of the current snapshot as newly visible player messages.
5. Append only those new player messages to `transcript.log`.
6. Persist one screenshot only if at least one player message was appended.

If the current player snapshot is identical to the previous one:

- append nothing,
- persist no screenshot.

## 10.3 Gap handling

The first slice should stay bounded and should not pretend to guarantee recovery from arbitrarily large chat bursts that scrolled completely out of the visible window between heartbeats.

If no overlap can be found with an existing non-empty prior snapshot:

- persist a change screenshot,
- record a `gap_detected` flag and metadata in `state.json`,
- append the current visible player rows so current information is not lost,
- do not silently claim perfect continuity.

This is safer than guessing.

Future work can extend the same archive store and transcript model with bounded backfill scrolling once real traffic justifies it.

## 11. Task Behavior

## 11.1 Applicability

`collect_kingdom_chat` should reject only login-owned states that cannot host in-game chat automation:

- `PNC_LOGIN`
- `PNC_ACCOUNT_SWITCH`

It should recover and replan from:

- `PNC_HOME_CITY`
- `PNC_WORLD_MAP`
- `PNC_CHAT`
- `PNC_LOADING`
- `UNKNOWN`
- popup-interrupted in-game states through centralized popup recovery.

## 11.2 Planning

The task's planning should be minimal:

1. recover unknown or loading states through existing shared behavior,
2. call `ensure_chat_channel(..., ChatChannel.WORLD)`,
3. when already on Kingdom Chat with transcript rows available, emit no further actions and allow verification/archive handling to run.

The task must not:

- type into chat,
- clear the draft,
- send any message,
- scroll the chat window in the first slice,
- create files directly.

## 11.3 Verification

The task should succeed only after:

- the final observation is `PNC_CHAT`,
- the active chat channel is Kingdom,
- visible player rows were parsed successfully enough for the archive logic to evaluate the delta,
- the archive store completed its append-or-no-op decision without inconsistency.

Verification outcomes:

- `success`: transcript appended or no-op because no new player chat existed,
- `replan`: still navigating or still settling after opening chat,
- `failure`: transcript state was invalid, archive persistence failed, or the chat observation was unusable in an unexpected way.

## 11.4 Runtime state

The task should use `TaskContext.runtime_state` only for ephemeral within-run state such as:

- whether the chat screen has already been reached this run,
- whether the task already performed one final transcript observation,
- whether a gap was surfaced during this one run.

Cross-heartbeat state must live in the archive store, not in task runtime memory.

## 12. Config, API, and Script Surface

## 12.1 New config field

Add `archive_root` to [AppConfig](/c:/Users/lebel/pnc/pnc_automation/config/models.py) and load it from the new `archives.root` config section.

## 12.2 New task id

Add to [pnc_automation/automation/task.py](/c:/Users/lebel/pnc/pnc_automation/automation/task.py):

- `COLLECT_KINGDOM_CHAT`

## 12.3 Registry

Register the task in [pnc_automation/scripts/registry.py](/c:/Users/lebel/pnc/pnc_automation/scripts/registry.py).

## 12.4 Python API

Add convenience wrappers in [pnc_automation/api.py](/c:/Users/lebel/pnc/pnc_automation/api.py):

- `collect_kingdom_chat(...)`

The wrapper should remain thin and forward into the canonical task id. It must not create a second monitoring implementation.

## 13. Example Config And Scheduling Shape

Example config:

```yaml
artifacts:
  root: artifacts

archives:
  root: archives

defaults:
  adb_path: adb
  screenshot_format: png
  stable_click_delay_ms: 300
  post_action_observe_delay_ms: 800

instances:
  - id: bs-main
    device_id: 127.0.0.1:5556
    app_package: com.global.tmslg

accounts:
  - id: testing
    instance_id: bs-main
    pnc_account_id: user@example.com
    username_env: PNC_TEST_USER
    password_env: PNC_TEST_PASS
```

Example routine:

```yaml
name: kingdom_chat_heartbeat

steps:
  - task: ensure_game_running
  - task: login
  - task: collect_kingdom_chat
    castle_ref: main
```

Recommended Task Scheduler settings:

- trigger: repeat every chosen heartbeat interval,
- action: run the CLI command for the routine script,
- overlap rule: `Do not start a new instance`,
- run context: the same Windows session that hosts BlueStacks.

## 14. Required Implementation Files

Likely implementation surface:

- [pnc_automation/config/models.py](/c:/Users/lebel/pnc/pnc_automation/config/models.py)
- [pnc_automation/config/loader.py](/c:/Users/lebel/pnc/pnc_automation/config/loader.py)
- [pnc_automation/config/validation.py](/c:/Users/lebel/pnc/pnc_automation/config/validation.py)
- [pnc_automation/app.py](/c:/Users/lebel/pnc/pnc_automation/app.py)
- [pnc_automation/api.py](/c:/Users/lebel/pnc/pnc_automation/api.py)
- [pnc_automation/automation/task.py](/c:/Users/lebel/pnc/pnc_automation/automation/task.py)
- [pnc_automation/automation/task_context.py](/c:/Users/lebel/pnc/pnc_automation/automation/task_context.py)
- [pnc_automation/automation/runner.py](/c:/Users/lebel/pnc/pnc_automation/automation/runner.py)
- [pnc_automation/automation/script_runner.py](/c:/Users/lebel/pnc/pnc_automation/automation/script_runner.py)
- [pnc_automation/automation/tasks/send_chat_message_task.py](/c:/Users/lebel/pnc/pnc_automation/automation/tasks/send_chat_message_task.py)
- [pnc_automation/automation/tasks/collect_kingdom_chat_task.py](/c:/Users/lebel/pnc/pnc_automation/automation/tasks/collect_kingdom_chat_task.py)
- [pnc_automation/scripts/registry.py](/c:/Users/lebel/pnc/pnc_automation/scripts/registry.py)
- [pnc_automation/pnc/chat.py](/c:/Users/lebel/pnc/pnc_automation/pnc/chat.py)
- [pnc_automation/pnc/observation.py](/c:/Users/lebel/pnc/pnc_automation/pnc/observation.py)
- [pnc_automation/pnc/screen_flows.py](/c:/Users/lebel/pnc/pnc_automation/pnc/screen_flows.py)
- [pnc_automation/vision/observation_request.py](/c:/Users/lebel/pnc/pnc_automation/vision/observation_request.py)
- [pnc_automation/vision/observation_builder.py](/c:/Users/lebel/pnc/pnc_automation/vision/observation_builder.py)
- [pnc_automation/vision/pnc_observation_enricher.py](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py)
- [pnc_automation/capture/chat_archive_store.py](/c:/Users/lebel/pnc/pnc_automation/capture/chat_archive_store.py)
- [pnc_automation/capture/mail_archive_store.py](/c:/Users/lebel/pnc/pnc_automation/capture/mail_archive_store.py)
- [scripts/routines/kingdom_chat_heartbeat.yaml](/c:/Users/lebel/pnc/scripts/routines/kingdom_chat_heartbeat.yaml)
- [tests/test_flows_and_tasks.py](/c:/Users/lebel/pnc/tests/test_flows_and_tasks.py)
- [tests/test_capture_and_vision.py](/c:/Users/lebel/pnc/tests/test_capture_and_vision.py)
- [tests/test_automation_framework.py](/c:/Users/lebel/pnc/tests/test_automation_framework.py)
- [tests/test_script_loader.py](/c:/Users/lebel/pnc/tests/test_script_loader.py)

## 15. Implementation Order

This feature should therefore be bundled with the observation-mode work, but the observation-mode slice should be implemented first inside the same effort. It is a prerequisite foundation, not a separate unrelated project.

## 15.1 Phase 1: Observation modes foundation

- add the shared `ObservationMode` contract,
- wire global config plus optional CLI override,
- preserve rich persisted observation behavior for `DEBUG`,
- add lighter ephemeral-by-default behavior for `LIGHT`,
- keep failure artifact persistence explicit and centralized.

Exit condition:

- the runtime can switch between high-evidence debug observation and lighter performance-oriented observation without feature-local special cases.

## 15.2 Phase 2: Archive boundary correction

- add `archives.root`,
- add `archive_root` to `AppConfig`,
- wire durable stores to `archive_root`,
- keep runtime artifacts under `artifact_root`.

Exit condition:

- the repo has one clean boundary between runtime artifacts and durable archives.

## 15.3 Phase 3: Reusable chat flow promotion

- add `ensure_chat_channel()`,
- refactor `send_chat_message()` to consume it,
- keep existing fixed-channel send behavior unchanged.

Exit condition:

- there is exactly one reusable implementation of chat-channel alignment.

## 15.4 Phase 4: Chat observation refinement

- add monitor-specific observation request,
- classify player rows vs announcement rows,
- ensure transcript OCR can still run when geometry already proves chat.

Exit condition:

- screenshot tests can distinguish visible player chat from visible announcements on Kingdom Chat.

## 15.5 Phase 5: Chat archive store and task

- implement `ChatArchiveStore`,
- implement transcript append and overlap logic,
- implement screenshot-on-change policy,
- implement `CollectKingdomChatTask`,
- add API wrapper and routine script.

Exit condition:

- one heartbeat run can poll Kingdom Chat, append only new player messages, and store a screenshot only when player chat changed.

## 15.6 Phase 6: Validation and smoke

- add unit coverage,
- add screenshot integration coverage,
- run targeted live smoke for one account and castle.

Exit condition:

- the feature has automated and live evidence for the bounded slice.

## 16. Validation Plan

## 16.1 Unit tests

Add unit tests for:

- debug-vs-light observation mode selection,
- archive-root config loading and validation,
- chat archive directory naming,
- transcript append behavior,
- no-op behavior when the player snapshot is unchanged,
- screenshot persistence only when new player entries are appended,
- gap detection when overlap is missing,
- `ensure_chat_channel()` reuse from both send and monitor flows,
- light-mode behavior in the runner and observation service.

## 16.2 Screenshot integration tests

Add screenshot-based coverage for:

- Kingdom Chat classification,
- active Kingdom tab parsing,
- player chat row extraction,
- announcement row extraction and exclusion,
- monitor-specific observation request still producing transcript rows when chat is geometry-proven,
- no false player rows from announcement-only screenshots.

Required negative tests:

- an announcement-only change must not count as transcript change,
- ambiguous unsupported rows must not be silently archived as player chat,
- idle repeated Kingdom Chat observations must not create new durable screenshots.

## 16.3 Live smoke validation

Required smoke cases:

1. `ensure_game_running -> login -> collect_kingdom_chat` reaches Kingdom Chat and produces a transcript folder.
2. A second immediate run with no new player messages appends nothing and creates no new durable screenshot.
3. A run after a new player chat line appears appends the line and creates exactly one new durable screenshot.
4. A run where only an announcement changed does not append transcript content and does not create a new durable screenshot.

## 17. Acceptance Criteria

This feature is complete only when all of the following are true:

- heartbeat scheduling is owned externally by Windows Task Scheduler, not by custom in-repo scheduler code,
- the runtime exposes one canonical observation mode toggle with at least `DEBUG` and `LIGHT`,
- there is exactly one canonical `collect_kingdom_chat` runtime task,
- there is exactly one canonical `ChatArchiveStore`,
- durable chat output is written under a root separate from runtime `artifacts`,
- the archive folder for one day contains both the transcript log and the chat screenshots,
- only player chat is appended to the transcript,
- game announcements are excluded from transcript-change decisions,
- no new durable screenshot is written when no new player chat appeared,
- existing chat send flows reuse the promoted shared chat-channel alignment flow instead of duplicating it,
- `DEBUG` mode preserves rich diagnostic observation behavior,
- `LIGHT` mode avoids flooding generic runtime screenshots during idle heartbeat polling,
- failures still persist debugging evidence,
- the feature remains bounded and does not pretend to provide perfect historical backfill beyond the validated first-slice scope,
- obsolete or duplicated archive and flow paths were not left behind.

## 18. Alternatives Rejected

### 18.1 Custom infinite polling loop inside the repo

Rejected because it duplicates scheduling concerns already solved by Windows Task Scheduler and creates a second retry/sleep/lock stack inside the codebase.

### 18.2 Introducing a Python scheduler library in the first slice

Rejected because the current environment is Windows-only and the repo already models routines as externally scheduled one-shot scripts. A library would be extra dependency surface without solving the current core problem better than Task Scheduler.

### 18.3 Writing transcript and screenshot files directly from the task

Rejected because it would duplicate path, dedup, and serialization logic outside a canonical store.

### 18.4 Leaving durable chat output under `artifacts/`

Rejected because it keeps the wrong ownership boundary between debugging evidence and durable harvested content and directly conflicts with the user's requested storage shape.

### 18.5 Reusing `send_chat_message()` as a monitor primitive

Rejected because sending and monitoring are different responsibilities. The correct reusable boundary is channel alignment, not "send but stop early."

## 19. Final Design Summary

The clean solution is:

- use Windows Task Scheduler for heartbeat cadence,
- add one bounded `collect_kingdom_chat` task,
- promote chat-channel alignment into a reusable shared flow,
- add one durable `ChatArchiveStore` under a new archive root separate from `artifacts`,
- classify visible chat rows into player chat vs announcements in the observation layer,
- append only newly seen player messages to one daily transcript log,
- and persist Kingdom Chat screenshots only when player chat actually changed.

That keeps the scheduler outside the runtime, keeps transcript persistence inside one canonical store, keeps chat navigation DRY, and gives the feature a clean extension path for future chat-related work without overbuilding it now.
