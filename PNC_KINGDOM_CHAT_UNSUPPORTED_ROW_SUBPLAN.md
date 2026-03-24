# PNC Kingdom Chat Unsupported-Row Sub-Plan

## 1. Purpose

This document defines the bounded follow-up plan for the live Kingdom Chat monitor failure where the transcript parser produced unsupported rows and correctly blocked archive persistence.

It is intentionally separate from:

- [PNC_KINGDOM_CHAT_MONITOR_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_KINGDOM_CHAT_MONITOR_IMPLEMENTATION.md), which owns the overall monitor architecture,
- [PNC_KINGDOM_CHAT_MONITOR_REVIEW.md](/c:/Users/lebel/pnc/PNC_KINGDOM_CHAT_MONITOR_REVIEW.md), which reviews the first implementation slice,
- [PNC_CHAT_WORKFLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_CHAT_WORKFLOW_SUBPLAN.md), which owns reusable chat navigation and send-flow mechanics.

This file owns one parser-quality correction:

- the live Kingdom Chat transcript parser must become robust enough to interpret normal visible chat rows without collapsing into unsupported fragments,
- while still failing fast on truly ambiguous OCR that cannot be archived safely.

## 1.1 Triggering live evidence

On 2026-03-24, a live run against `serious_stuff` on `K226 / please b gentle` reached `PNC_CHAT` and then failed inside `collect_kingdom_chat` with:

- `Kingdom chat observation contained unsupported rows that could not be archived safely.`

The persisted failure artifact was:

- [20260324T143723Z_collect_kingdom_chat_failure_result.png](/c:/Users/lebel/pnc/artifacts/2026-03-24/serious_stuff/20260324T143723Z_collect_kingdom_chat_failure_result.png)

A live transcript-debug observation on that same screen produced:

- one fully parsed player row,
- three sender-only unsupported rows,
- no durable archive output, which was the correct safety behavior.

The visible unsupported rows included sender-only entries such as:

- `[DMG]p2o2i2u2ueu3u47484`
- `[DMG]Toast.`

That means the task's fail-fast gate is working, but the upstream transcript interpretation is still too brittle for the live screen variant.

## 2. Current problem

The current monitor architecture intentionally rejects unsupported transcript rows.

That is the right task-level policy because:

- the archive must not silently drop or invent player chat,
- ambiguous OCR should surface as a failure artifact instead of poisoning transcript history,
- task-local ignore rules would duplicate parser logic and make safety inconsistent.

The real problem is therefore in the vision layer:

- the parser currently projects OCR-backed chat rows too directly into final chat-entry meaning,
- there is no dedicated normalization pass for row fragments, duplicate sender headers, or split sender/message evidence,
- a live row that should be interpretable can therefore degrade into one valid player row plus extra unsupported fragments.

If we "fix" this by teaching the task to ignore unsupported rows, we would weaken the core safety contract. The parser must improve instead.

## 3. Goals

- Keep one canonical parser/classifier for visible Kingdom Chat rows.
- Improve row grouping and normalization before final chat-entry classification.
- Preserve fail-fast behavior when a row still cannot be interpreted safely.
- Avoid task-local heuristics or chat-monitor-only exceptions.
- Add deterministic regression coverage for the March 24, 2026 live failure shape.
- Re-run the live monitor on `please b gentle` and expect either success or a smaller, more precise unsupported failure surface.

## 4. Non-goals

- Silently ignoring unsupported rows inside `CollectKingdomChatTask`.
- Inventing message text for sender-only OCR.
- Implementing full scroll-back history recovery.
- Adding account-specific or alliance-tag-specific parsing exceptions.
- Relaxing archive safety just to make one live poll pass.

## 5. Core architectural decision

The canonical fix belongs in the transcript parsing pipeline, not in the task.

Recommended parser shape:

1. Raw OCR lines should first be grouped into one intermediate chat-row candidate model.
2. That normalization pass should own geometry-aware merging of sender and message fragments when there is exactly one safe interpretation.
3. Only normalized row candidates should then be classified into the existing final meanings:
   - `PLAYER`
   - `ANNOUNCEMENT`
   - `UNSUPPORTED`
4. `CollectKingdomChatTask` should remain strict and unchanged: if final unsupported rows still exist, the task must fail and refuse to archive.

This keeps one canonical implementation per concept:

- vision owns row normalization and classification,
- the chat-domain model owns typed chat meaning,
- the task owns archive safety, not OCR cleanup.

## 6. Recommended parser behavior

### 6.1 Add one normalization phase before classification

The parser should stop collapsing directly from OCR lines to final `ObservedChatEntry` results.

Instead, add one internal intermediate layer that can represent:

- the sender evidence seen for one candidate row,
- the message evidence seen for one candidate row,
- the contributing OCR lines and their ordering,
- whether the candidate was formed by one exact safe merge or remains ambiguous.

### 6.2 Merge only when the interpretation is exact

The normalization phase may merge fragments only when geometry and ordering prove one interpretation cleanly.

Examples of acceptable merges:

- sender line plus adjacent message line that clearly belong to the same visible row,
- duplicate sender fragment that is fully absorbed by a neighboring already-proven player row,
- split message continuation lines that belong to one visible player row.

Examples that must remain unsupported:

- sender-only rows with no attributable message,
- message-only rows with no attributable sender,
- candidates that could attach to more than one neighboring row,
- noisy OCR that still cannot prove whether the row is player chat or announcement content.

### 6.3 Keep announcement classification strict

This plan should preserve the review document's earlier direction:

- announcement classification must require real announcement evidence,
- unsupported content must not be silently downgraded into `ANNOUNCEMENT`.

That means the normalization pass should make player rows more robust without weakening the distinction between `ANNOUNCEMENT` and `UNSUPPORTED`.

## 7. Work plan

### 7.1 Capture the live failure shape as a regression target

- Preserve the March 24, 2026 failure screenshot and the associated structured unsupported-row output as the reference case.
- Extract the raw OCR-line pattern from that screen so tests can cover the actual fragment shape instead of only synthetic happy paths.
- Keep any committed fixture sanitized and minimal if a cropped screenshot or OCR dump is added to the repo.

### 7.2 Refactor transcript parsing around normalized row candidates

- Introduce one internal candidate-building helper in [pnc_automation/vision/pnc_observation_enricher.py](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py).
- Move row grouping, fragment absorption, and safe merge rules into that one helper.
- Keep the public chat-domain model in [pnc_automation/pnc/chat.py](/c:/Users/lebel/pnc/pnc_automation/pnc/chat.py) unchanged unless a genuinely necessary typed surface change emerges.

### 7.3 Tighten unsupported-row diagnostics

- Keep `CollectKingdomChatTask` strict, but improve the diagnostics it emits when unsupported rows remain.
- Include enough row preview detail to tell whether the remaining unsupported content is sender-only, message-only, or ambiguous merged OCR.
- Preserve the existing persisted failure-artifact path in `LIGHT` mode so live parser regressions stay debuggable.

### 7.4 Validation

- Add transcript-parser unit tests for live-like sender-only fragment patterns.
- Add tests for safe merges that should now become one valid player row.
- Keep tests for truly ambiguous content that must still surface as `UNSUPPORTED`.
- Re-run the live monitor on `serious_stuff` at `K226 / please b gentle` after the parser change.

## 8. Expected implementation files

The likely implementation surface is:

- [pnc_automation/vision/pnc_observation_enricher.py](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py)
- [pnc_automation/pnc/chat.py](/c:/Users/lebel/pnc/pnc_automation/pnc/chat.py)
- [pnc_automation/pnc/observation.py](/c:/Users/lebel/pnc/pnc_automation/pnc/observation.py) if the intermediate row metadata needs to surface through existing list-entry structures
- [pnc_automation/automation/tasks/collect_kingdom_chat_task.py](/c:/Users/lebel/pnc/pnc_automation/automation/tasks/collect_kingdom_chat_task.py) only if diagnostics need small message-level improvements
- [tests/test_capture_and_vision.py](/c:/Users/lebel/pnc/tests/test_capture_and_vision.py)
- [tests/test_chat_monitor.py](/c:/Users/lebel/pnc/tests/test_chat_monitor.py)
- one optional sanitized fixture under [tests](/c:/Users/lebel/pnc/tests) if the live row shape needs a committed screenshot or OCR dump

## 9. Acceptance criteria

This plan is complete only when all of the following are true:

- the parser can normalize the March 24, 2026 live fragment pattern more accurately than it does today,
- clearly attributable sender/message fragments become one canonical player row before final classification,
- truly ambiguous rows still surface as `UNSUPPORTED`,
- `CollectKingdomChatTask` still refuses to archive when unresolved unsupported rows remain,
- a live rerun on `please b gentle` no longer fails solely because a normal visible player row was split into parser fragments.
