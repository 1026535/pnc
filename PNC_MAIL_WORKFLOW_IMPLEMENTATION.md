# PNC Mail Workflow Implementation Document

## 1. Purpose

This document defines the complete implementation plan for mail automation in the current P&C automation platform.

It covers:

- writing direct player mail from the mail mailbox,
- writing alliance mail from the alliance screen,
- writing personal mail from remote player profiles reached through the currently approved profile-entry routes,
- reading player and alliance mail,
- archiving received mail into a structured local store for later integrations such as Discord.

This document is intentionally implementation-oriented. It describes the concrete architecture changes required to add mail support cleanly to the existing runtime rather than describing the feature as a loose wishlist.

## 2. Current repository context

The current repository already has a strong canonical runtime shape:

- one selector catalog in [pnc_automation/vision/data/selector_registry.yaml](/c:/Users/lebel/pnc/pnc_automation/vision/data/selector_registry.yaml),
- one typed `Observation` model in [pnc_automation/pnc/observation.py](/c:/Users/lebel/pnc/pnc_automation/pnc/observation.py),
- one `ScreenType` enum in [pnc_automation/pnc/screen_type.py](/c:/Users/lebel/pnc/pnc_automation/pnc/screen_type.py),
- one `UiElementId` enum in [pnc_automation/pnc/ui_element_id.py](/c:/Users/lebel/pnc/pnc_automation/pnc/ui_element_id.py),
- one `ScreenFlowPlanner` in [pnc_automation/pnc/screen_flows.py](/c:/Users/lebel/pnc/pnc_automation/pnc/screen_flows.py),
- one declarative action vocabulary in [pnc_automation/pnc/action_requests.py](/c:/Users/lebel/pnc/pnc_automation/pnc/action_requests.py),
- one observed execute-and-verify loop in [pnc_automation/automation/runner.py](/c:/Users/lebel/pnc/pnc_automation/automation/runner.py),
- one artifact pipeline through [pnc_automation/capture/artifact_store.py](/c:/Users/lebel/pnc/pnc_automation/capture/artifact_store.py) and [pnc_automation/capture/screenshot_service.py](/c:/Users/lebel/pnc/pnc_automation/capture/screenshot_service.py).

That architecture is already correct for mail. Mail must be added by extending those canonical layers, not by creating a separate mail-specific automation stack.

## 3. User-facing goal

The target behavior is:

### 3.1 Mail writing

There are three supported composition entry paths:

1. Direct player mail from the mail mailbox
   - open the mail mailbox,
   - open the edit-mail popup,
   - manually provide the target player name.
2. Alliance mail from the alliance home screen
   - tap `Alliance Mail`,
   - open the edit-mail popup,
   - verify the target field is auto-filled with the alliance recipient.
3. Personal mail from a remote player profile
   - reach a remote player profile,
   - tap `Mail`,
   - open the edit-mail popup,
   - verify the target field is auto-filled with that player's displayed name.

For this document, remote player profiles are reached through the following currently approved routes:

1. `Player Territory -> Player Info -> Player Profile`
2. `Chat bubble -> player popup -> player-name button -> Player Profile`
3. `Alliance Member -> Manage -> Personal Info -> Player Profile`
4. `Alliance Rank -> magnifier -> Player Profile`

Other profile-entry routes are explicitly out of scope for this slice and should fail fast rather than being guessed.

### 3.2 Sending behavior

To send mail:

- the edit-mail popup must be open,
- the target field must contain the intended target,
- the subject field must contain the intended title,
- the body field must contain the intended content,
- the send button must be tapped,
- the post-send observation must first prove the compose popup closed and did not remain in an invalid state,
- the flow must then go into the corresponding `Player Mail` or `Alliance Mail` mailbox and verify that the written mail is present there.

### 3.3 Mail reading

To read received mail:

- open the mail hub,
- open either `Player Mail` or `Alliance Mail`,
- handle the empty state `No report yet` as a valid empty mailbox,
- otherwise parse the visible thread rows,
- open a thread row and capture the thread content.

### 3.4 Archiving

Received mail must be archived automatically into a dedicated structure organized by:

- active castle,
- sender,
- date,
- mailbox type,
- message or thread identity.

The archive must support:

- screenshot evidence,
- extracted text evidence,
- or both,

so later integrations can consume the stored data without needing to re-open the live game UI.

## 4. Architecture requirements

This implementation must preserve the repository's existing non-negotiables:

- Single canonical implementation per concept.
- No duplicated logic.
- Fail-fast validation for invalid content.
- Minimal boilerplate.

The feature-specific consequences are:

- there must be one canonical mail-send task shape,
- there must be one canonical mail-collection task shape,
- there must be one canonical compose-popup model,
- remote player profiles must not reuse self-profile ownership incorrectly,
- input-field clearing logic must not be copied for each text field,
- mail archive persistence must not be ad hoc file writing scattered through tasks.

## 5. Existing architecture gaps that must be fixed first

Mail can be added cleanly only if the following existing ownership problems are addressed.

### 5.1 `PNC_LORD_INFO` currently means "self castle validation", not "any player profile"

Today [pnc_automation/vision/pnc_observation_enricher.py](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py) parses `PNC_LORD_INFO` into `current_castle`, and [pnc_automation/vision/observation_builder.py](/c:/Users/lebel/pnc/pnc_automation/vision/observation_builder.py) carries that value back onto home-adjacent screens as the validated current castle.

That behavior is correct only for the self-owned profile screen reached from the home-city shortcut.

It is incorrect for remote-player mail routes. If a remote player profile reused `PNC_LORD_INFO`, the runtime would treat the remote player's name as the active castle identity and would poison castle-selection verification.

This must not be patched with task-local exceptions. The screen model must be corrected.

### 5.2 Current mail screen naming is too narrow and partially misleading

Today:

- `PNC_MAIL_LIST` is really the mail hub with mailbox categories,
- `PNC_SYSTEM_MESSAGE` is really a mailbox sub-screen pattern, not only system mail.

That naming is tolerable for the current seed scope, but it becomes wrong once player mail, alliance mail, compose, and thread parsing are implemented.

The screen model should be normalized now instead of layering more mail behavior onto misleading names.

### 5.3 Replace-existing text input is chat-specific

Today `InputTextAction.replace_existing` is only implemented for `PNC_CHAT_INPUT_FIELD` in [pnc_automation/automation/action_executor.py](/c:/Users/lebel/pnc/pnc_automation/automation/action_executor.py).

Mail compose requires the same capability for:

- target field,
- subject field,
- body field.

This must become one shared field-state abstraction rather than three new special cases.

### 5.4 The generic artifact store is not enough for mail archives

Current screenshot persistence is per-day plus one flat `artifact_directory` segment.

That is sufficient for live runtime screenshots, but it is not enough for a durable mail archive keyed by castle, sender, mailbox, and message identity.

The mail archive must therefore be implemented as a dedicated domain store built on top of the same root and sanitization rules, not as improvised manual folder creation inside tasks.

## 6. Canonical target architecture

## 6.1 Screen model

The clean screen model is:

- keep `PNC_LORD_INFO` for the self-owned profile used in current-castle validation,
- add a distinct remote profile screen,
- normalize the mail hub and mailbox screens,
- add the compose popup and thread screens explicitly.

### 6.1.1 Required screen refactor

Rename:

- `PNC_MAIL_LIST` -> `PNC_MAIL_HUB`
- `PNC_SYSTEM_MESSAGE` -> `PNC_MAILBOX_LIST`

Delete the obsolete names after migration. Do not keep aliases.

### 6.1.2 Required new `ScreenType` values

Add:

- `PNC_MAIL_THREAD`
- `PNC_MAIL_COMPOSE_POPUP`
- `PNC_PLAYER_TERRITORY`
- `PNC_PLAYER_PROFILE`
- `PNC_CHAT_PLAYER_ACTION_POPUP`
- `PNC_ALLIANCE_MEMBER_LIST`
- `PNC_ALLIANCE_MEMBER_MANAGE_POPUP`
- `PNC_MIGHT_RANK`

### 6.1.3 Screen ownership rules

- `PNC_LORD_INFO` owns self-profile current-castle validation only.
- `PNC_PLAYER_PROFILE` owns remote profile identity only.
- `PNC_MAIL_HUB` owns mailbox-category navigation only.
- `PNC_MAILBOX_LIST` owns mailbox thread rows and empty-state facts.
- `PNC_MAIL_THREAD` owns one opened mailbox thread.
- `PNC_MAIL_COMPOSE_POPUP` owns recipient, subject, body, and send controls.

That ownership split keeps the observation model coherent and prevents castle-state contamination.

## 6.2 Mail domain model

Add a dedicated P&C mail-domain module, for example [pnc_automation/pnc/mail.py](/c:/Users/lebel/pnc/pnc_automation/pnc/mail.py), parallel to [pnc_automation/pnc/chat.py](/c:/Users/lebel/pnc/pnc_automation/pnc/chat.py).

It should define:

- `MailboxType`
- `MailRecipientKind`
- `MailArchiveMode`
- `PlayerProfileRouteKind`
- `MailThreadFingerprint`
- `MailArchiveRecord`

Recommended enums:

```python
class MailboxType(StrEnum):
    PLAYER = "player"
    ALLIANCE = "alliance"

class MailRecipientKind(StrEnum):
    PLAYER = "player"
    ALLIANCE = "alliance"

class MailArchiveMode(StrEnum):
    SCREENSHOT = "screenshot"
    TEXT = "text"
    BOTH = "both"

class PlayerProfileRouteKind(StrEnum):
    PLAYER_TERRITORY = "player_territory"
    CHAT_MESSAGE = "chat_message"
    ALLIANCE_MEMBER = "alliance_member"
    MIGHT_RANK = "might_rank"
```

The first slice should keep mailbox scope to `PLAYER` and `ALLIANCE`. System mail and report categories can be added later through the same enum and flow structure.

## 6.3 Task model

There should be exactly two new runtime tasks:

- `send_mail`
- `collect_mail`

Do not create one task per entry path. The entry paths are navigation strategies, not task concepts.

### 6.3.1 `send_mail`

`send_mail` should accept one typed request model with:

- recipient kind,
- optional direct player name,
- optional remote profile route,
- subject,
- body.

Recommended typed params:

```python
@dataclass(frozen=True, slots=True)
class PlayerProfileRoute:
    kind: PlayerProfileRouteKind
    player_name: str | None = None

@dataclass(frozen=True, slots=True)
class SendMailParams:
    recipient_kind: MailRecipientKind
    player_name: str | None = None
    profile_route: PlayerProfileRoute | None = None
    subject: str
    body: str
```

Validation rules:

- `ALLIANCE` must reject `player_name` and `profile_route`.
- `PLAYER` must require exactly one of `player_name` or `profile_route`.
- `subject` and `body` must be non-empty after trimming.
- unsupported route kinds must fail in parameter parsing, not during live execution.

### 6.3.2 `collect_mail`

`collect_mail` should accept one typed request model with:

- target mailboxes,
- archive mode,
- optional per-mailbox item limit,
- optional `only_new` behavior.

Recommended typed params:

```python
@dataclass(frozen=True, slots=True)
class CollectMailParams:
    mailboxes: tuple[MailboxType, ...]
    archive_mode: MailArchiveMode = MailArchiveMode.BOTH
    limit_per_mailbox: int = 25
    only_new: bool = True
```

Validation rules:

- `mailboxes` must contain at least one entry,
- `limit_per_mailbox` must be positive,
- duplicate mailbox requests should be collapsed during parsing.

## 6.4 Observation model

Extend `Observation` in [pnc_automation/pnc/observation.py](/c:/Users/lebel/pnc/pnc_automation/pnc/observation.py) with the minimum facts mail needs.

### 6.4.1 Keep `current_castle` unchanged

`current_castle` must remain owned by:

- `PNC_LORD_INFO`,
- `PNC_CASTLE_SELECTION`,
- carry-forward logic for home-adjacent screens.

Remote profile parsing must not populate it.

### 6.4.2 Add remote-profile facts

Add:

- `profile_player_name: str | None`

This field is populated only on `PNC_PLAYER_PROFILE`.

### 6.4.3 Add mailbox facts

Add:

- `mailbox_type: MailboxType | None`
- `mailbox_empty: bool | None`

These allow tasks to distinguish:

- player mailbox,
- alliance mailbox,
- empty mailbox,
- unclassified mailbox-like screens.

### 6.4.4 Add generic observed text-field state

Add one canonical text-field state map:

```python
@dataclass(frozen=True, slots=True)
class ObservedTextFieldState:
    selector_id: UiElementId
    text: str | None
    empty: bool | None

text_field_states: Mapping[UiElementId, ObservedTextFieldState]
```

This must be generic and shared by:

- chat input,
- mail target field,
- mail subject field,
- mail body field.

The current chat-specific fields:

- `chat_draft_empty`
- `chat_draft_text`

may stay for compatibility during migration, but the target design should converge on the generic field-state map and then remove the parallel chat-only state once the dependent code is updated.

### 6.4.5 Extend `ListEntryKind`

Add:

- `MAIL_THREAD`
- `MAIL_MESSAGE`
- `CHAT_MESSAGE`
- `ALLIANCE_MEMBER`
- `RANKED_PLAYER`

This keeps dynamic mail rows and player-selection rows inside the existing canonical repeated-entry abstraction instead of inventing separate ad hoc data structures.

## 6.5 Selector model

The selector catalog remains canonical. Mail must add selector ids and catalog entries, not bypass the registry.

### 6.5.1 Required selector refactor

Rename:

- `PNC_SYSTEM_MESSAGE_MARK_AS_READ_BUTTON` -> `PNC_MAILBOX_MARK_ALL_AS_READ_BUTTON`
- `PNC_SYSTEM_MESSAGE_MANAGE_BUTTON` -> `PNC_MAILBOX_MANAGE_BUTTON`

Delete the obsolete ids after migration. Do not support both names.

### 6.5.2 Required new selectors

Add at minimum:

- `PNC_BOTTOM_NAV_MAIL`
- `PNC_MAIL_HEADER`
- `PNC_MAIL_COMPOSE_BUTTON`
- `PNC_MAILBOX_EMPTY_LABEL`
- `PNC_MAIL_THREAD_ROW`
- `PNC_MAIL_THREAD_SENDER_REGION`
- `PNC_MAIL_THREAD_PREVIEW_REGION`
- `PNC_MAIL_THREAD_DATE_REGION`
- `PNC_MAIL_THREAD_DELETE_BUTTON`
- `PNC_MAIL_COMPOSE_HEADER`
- `PNC_MAIL_COMPOSE_CLOSE_BUTTON`
- `PNC_MAIL_COMPOSE_TARGET_FIELD`
- `PNC_MAIL_COMPOSE_SUBJECT_FIELD`
- `PNC_MAIL_COMPOSE_BODY_FIELD`
- `PNC_MAIL_COMPOSE_SEND_BUTTON`
- `PNC_PLAYER_TERRITORY_HEADER`
- `PNC_PLAYER_TERRITORY_PLAYER_INFO_BUTTON`
- `PNC_PLAYER_PROFILE_HEADER`
- `PNC_PLAYER_PROFILE_NAME_LABEL`
- `PNC_PLAYER_PROFILE_MAIL_BUTTON`
- `PNC_CHAT_PLAYER_ACTION_PROFILE_BUTTON`
- `PNC_ALLIANCE_MEMBER_ROW`
- `PNC_ALLIANCE_MEMBER_MANAGE_BUTTON`
- `PNC_ALLIANCE_MEMBER_MANAGE_PERSONAL_INFO_BUTTON`
- `PNC_MIGHT_RANK_ROW`
- `PNC_MIGHT_RANK_PROFILE_BUTTON`

Use collection selectors for repeated rows. Do not add one selector id per sender name, alliance member, or ranked player.

### 6.5.3 Navigation selectors that must be click-mapped

The following must become reviewed navigation selectors:

- `PNC_BOTTOM_NAV_MAIL` -> `PNC_MAIL_HUB`
- `PNC_BOTTOM_NAV_ALLIANCE` -> `PNC_ALLIANCE_HOME`
- `PNC_ALLIANCE_BOTTOM_TAB_MAIL` -> `PNC_MAIL_COMPOSE_POPUP`
- `PNC_PLAYER_TERRITORY_PLAYER_INFO_BUTTON` -> `PNC_PLAYER_PROFILE`
- `PNC_PLAYER_PROFILE_MAIL_BUTTON` -> `PNC_MAIL_COMPOSE_POPUP`
- `PNC_CHAT_PLAYER_ACTION_PROFILE_BUTTON` -> `PNC_PLAYER_PROFILE`
- `PNC_ALLIANCE_MEMBER_MANAGE_PERSONAL_INFO_BUTTON` -> `PNC_PLAYER_PROFILE`
- `PNC_MIGHT_RANK_PROFILE_BUTTON` -> `PNC_PLAYER_PROFILE`
- mailbox thread row action point -> `PNC_MAIL_THREAD`

### 6.5.4 Input-field selectors remain `ACTION`

The compose fields and send button are not navigation selectors. They remain `ACTION` selectors with stable geometry and optional action points.

## 6.6 Archive model

Add a dedicated archive store, for example [pnc_automation/capture/mail_archive_store.py](/c:/Users/lebel/pnc/pnc_automation/capture/mail_archive_store.py).

This store should own:

- path layout,
- deduplication,
- text serialization,
- screenshot persistence for archived mail,
- metadata normalization.

Recommended archive layout:

```text
artifacts/
  mail/
    2026-03-15/
      k157_tiny_npc/
        player/
          aas_cutie_voj/
            20260315T075304Z_1f3d0c6a/
              metadata.json
              thread.txt
              thread.png
        alliance/
          smol_nyanko/
            20260315T081122Z_6bcd9ef2/
              metadata.json
              thread.txt
              thread.png
```

The path key should be:

- date,
- active castle,
- mailbox,
- sender or thread partner,
- stable fingerprint.

The fingerprint should be derived from stable mail content such as:

- mailbox type,
- sender name,
- observed thread timestamp text,
- normalized visible message text.

This prevents repeated collection runs from creating uncontrolled duplicate archives.

## 7. Flow design

Mail must be implemented as a composition of new and existing flows inside [pnc_automation/pnc/screen_flows.py](/c:/Users/lebel/pnc/pnc_automation/pnc/screen_flows.py).

## 7.1 New canonical flows

Add:

- `open_alliance_home()`
- `open_mail_hub()`
- `open_mailbox(mailbox: MailboxType)`
- `open_player_profile(route: PlayerProfileRoute)`
- `open_mail_compose(...)`
- `send_mail(...)`

These flows are reusable and belong in `ScreenFlowPlanner`, not inside task implementations.

## 7.2 `open_alliance_home()`

Purpose:

- navigate from home-adjacent screens to `PNC_ALLIANCE_HOME`.

Entry assumptions:

- `PNC_HOME_CITY`
- `PNC_ALLIANCE_HOME`
- any screen that `ensure_home_city()` can safely reduce to home city

Behavior:

- if already on alliance home, return no actions,
- otherwise use `ensure_home_city()` and then tap `PNC_BOTTOM_NAV_ALLIANCE`.

Fail-fast rule:

- if the account is on `PNC_ALLIANCE_JOIN`, alliance-home-only flows must not pretend success.

This flow is reusable beyond mail and should be treated as canonical shared navigation.

## 7.3 `open_mail_hub()`

Purpose:

- navigate to the main mail category screen.

Entry assumptions:

- `PNC_HOME_CITY`
- `PNC_MAIL_HUB`
- any screen reducible to home city through `ensure_home_city()`

Behavior:

- if already on `PNC_MAIL_HUB`, return no actions,
- otherwise ensure home city and tap `PNC_BOTTOM_NAV_MAIL`.

## 7.4 `open_mailbox(mailbox)`

Purpose:

- navigate from the mail hub or existing mailbox screen to the requested mailbox list.

Supported initial mailbox scope:

- `PLAYER`
- `ALLIANCE`

Behavior:

- if already on the requested mailbox list, return no actions,
- otherwise open mail hub and tap the requested mailbox category row.

Verification:

- post-navigation observation must prove `PNC_MAILBOX_LIST`,
- `observation.mailbox_type` must equal the requested mailbox,
- `mailbox_empty` may be either `True` or `False`.

## 7.5 `open_player_profile(route)`

Purpose:

- navigate from one supported visible route to a remote player profile.

This flow is route-driven but canonical.

### 7.5.1 Route: `PLAYER_TERRITORY`

Scope:

- the first slice begins from an already-open `PNC_PLAYER_TERRITORY`.

Rationale:

- tapping an arbitrary world-map castle to first reach `PNC_PLAYER_TERRITORY` depends on spatial-surface targeting that is not yet the mail feature's responsibility.

Behavior:

- if not on `PNC_PLAYER_TERRITORY`, fail fast,
- tap `PNC_PLAYER_TERRITORY_PLAYER_INFO_BUTTON`,
- verify `PNC_PLAYER_PROFILE`.

### 7.5.2 Route: `CHAT_MESSAGE`

Behavior:

- require `PNC_CHAT`,
- require a visible `CHAT_MESSAGE` entry matching the target sender when one was provided,
- tap the chat-message entry action point,
- verify `PNC_CHAT_PLAYER_ACTION_POPUP`,
- tap `PNC_CHAT_PLAYER_ACTION_PROFILE_BUTTON`,
- verify `PNC_PLAYER_PROFILE`.

### 7.5.3 Route: `ALLIANCE_MEMBER`

Behavior:

- require `PNC_ALLIANCE_MEMBER_LIST`,
- require a visible `ALLIANCE_MEMBER` entry matching the target name,
- tap that row's `Manage` action point,
- verify `PNC_ALLIANCE_MEMBER_MANAGE_POPUP`,
- tap `PNC_ALLIANCE_MEMBER_MANAGE_PERSONAL_INFO_BUTTON`,
- verify `PNC_PLAYER_PROFILE`.

### 7.5.4 Route: `MIGHT_RANK`

Behavior:

- require `PNC_MIGHT_RANK`,
- require a visible `RANKED_PLAYER` entry matching the target name,
- tap that row's magnifier action point,
- verify `PNC_PLAYER_PROFILE`.

### 7.5.5 Route constraints

The first implementation should support only visible target entries for:

- chat messages,
- alliance members,
- rank rows.

If the target row is not visible, fail fast with a clear reason. Do not add list-guessing heuristics in the first slice.

## 7.6 `open_mail_compose(...)`

This should be a single dispatching flow, not three unrelated helpers.

Dispatch rules:

- `recipient_kind == ALLIANCE`
  - call `open_alliance_home()`
  - tap `PNC_ALLIANCE_BOTTOM_TAB_MAIL`
  - verify `PNC_MAIL_COMPOSE_POPUP`
  - verify target field OCR equals `Alliance Mail`
- `recipient_kind == PLAYER` and `player_name is not None`
  - call `open_mailbox(MailboxType.PLAYER)`
  - tap `PNC_MAIL_COMPOSE_BUTTON`
  - verify `PNC_MAIL_COMPOSE_POPUP`
  - type the target field with the provided name
- `recipient_kind == PLAYER` and `profile_route is not None`
  - call `open_player_profile(profile_route)`
  - tap `PNC_PLAYER_PROFILE_MAIL_BUTTON`
  - verify `PNC_MAIL_COMPOSE_POPUP`
  - verify target field OCR equals the visible profile name

The flow must never accept a compose popup whose target field does not match the intended recipient.

## 7.7 `send_mail(...)`

This should be the canonical flow consumed by the `send_mail` task.

Behavior:

1. Open the compose popup through `open_mail_compose(...)`.
2. Clear and replace the subject field.
3. Clear and replace the body field.
4. Tap send.
5. Observe with a narrow mail-specific follow-up request to confirm the compose popup closed cleanly.
6. Reopen the corresponding mailbox immediately after send:
   - `MailboxType.PLAYER` for direct and personal player mail,
   - `MailboxType.ALLIANCE` for alliance mail.
7. Verify the written mail is present in that mailbox.
8. When mailbox-row evidence is not strong enough on its own, open the matching thread and confirm the visible content matches the sent mail.
9. Treat the send as failed if the flow cannot find a matching mailbox row or matching opened thread content.

Recommended success states:

- the compose popup closes and the runtime lands on a stable non-error screen,
- the corresponding mailbox contains a new row or thread matching the sent mail after the send flow reopens that mailbox,
- and, when needed, the opened thread confirms the sent subject or body content.

Compose-popup closure is therefore only an intermediate success condition. Final task success requires mailbox-level verification.

## 8. Observation and OCR design

Mail must use the same observation pipeline as the rest of the runtime.

## 8.1 Narrow observation requests

Do not use the full runtime OCR request for every mail action.

Add dedicated narrow requests in [pnc_automation/vision/observation_request.py](/c:/Users/lebel/pnc/pnc_automation/vision/observation_request.py), for example:

- `mail_navigation_follow_up(...)`
- `mailbox_observation(mailbox)`
- `mail_thread_observation()`
- `mail_compose_follow_up()`
- `player_profile_follow_up()`

These requests should explicitly opt in only to the OCR-backed facts the next step needs.

## 8.2 Mailbox list parsing

Implement one shared mailbox parser in [pnc_automation/vision/pnc_observation_enricher.py](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py).

It should:

- detect the mailbox header text,
- distinguish `Player Mail` from `Alliance Mail`,
- detect `No report yet`,
- extract visible `MAIL_THREAD` rows,
- populate `mailbox_type` and `mailbox_empty`.

Do not create separate duplicated parsers for player and alliance mail if the structure is the same.

## 8.3 Mail thread parsing

Implement one shared thread parser that:

- detects the opened thread header,
- reads visible message bubbles,
- extracts visible timestamp text when available,
- exposes `MAIL_MESSAGE` list entries for archive generation.

The first slice can be limited to the visible viewport. Full thread scrolling can be added later through the same thread-entry model.

## 8.4 Compose popup parsing

Implement one compose-popup parser that:

- proves `PNC_MAIL_COMPOSE_POPUP`,
- materializes target, subject, body, close, and send selectors,
- populates generic observed text-field state for all three fields.

The field-state model must be shared with chat rather than duplicated for mail.

## 8.5 Profile parsing

Keep two profile parsers:

- self profile parser for `PNC_LORD_INFO`,
- remote profile parser for `PNC_PLAYER_PROFILE`.

They should share a helper that reads the displayed profile name from the common profile band, but they must emit different screen evidence and different observation fields.

Shared helper:

- `read_profile_name(...)`

Self profile output:

- `screen_type = PNC_LORD_INFO`
- `current_castle = ...`

Remote profile output:

- `screen_type = PNC_PLAYER_PROFILE`
- `profile_player_name = ...`

That shared-helper plus split-output design keeps the OCR logic DRY without mixing ownership.

## 9. Generic text-entry refactor

Mail requires a small but important runtime refactor.

## 9.1 One generic clear-and-replace policy

Replace the chat-only clearing logic in [pnc_automation/automation/action_executor.py](/c:/Users/lebel/pnc/pnc_automation/automation/action_executor.py) with one generic helper:

- resolve field state from `Observation.text_field_states`,
- fail if the requested selector has no observed field state when `replace_existing=True`,
- skip clearing when the field is already empty,
- otherwise move to end and send the delete budget.

This logic must work for:

- `PNC_CHAT_INPUT_FIELD`
- `PNC_MAIL_COMPOSE_TARGET_FIELD`
- `PNC_MAIL_COMPOSE_SUBJECT_FIELD`
- `PNC_MAIL_COMPOSE_BODY_FIELD`

## 9.2 Multiline body support

Mail body text should be allowed to contain newline characters.

Current low-level ADB input rejects multiline values in [pnc_automation/emulator/session.py](/c:/Users/lebel/pnc/pnc_automation/emulator/session.py).

The clean fix is:

- keep `BlueStacksSession.input_text()` as the single-line primitive,
- add a higher-level action-executor text entry helper that splits multiline text into lines,
- input each line through `input_text()`,
- send `KEYCODE_ENTER` between lines only for selectors whose field capability is multiline.

Do not add a separate mail-only text-input path.

If multiline support cannot be safely validated immediately, the first implementation may temporarily reject multiline mail bodies during parameter parsing, but that should be treated as a temporary bounded limitation, not the target design.

## 10. Mail archive design

## 10.1 One archive store

`collect_mail` should write through one dedicated `MailArchiveStore`.

Task code should never write files directly.

## 10.2 Archive payloads

For each archived thread snapshot, persist:

- `metadata.json`
  - account id
  - pnc account id
  - active castle
  - mailbox type
  - sender name
  - observed thread timestamp text
  - archive fingerprint
  - source artifact paths
- `thread.txt`
  - normalized visible thread content
- `thread.png`
  - screenshot of the opened thread when screenshot mode is enabled

## 10.3 Deduplication

`only_new=True` should mean:

- compute the canonical fingerprint,
- if the archive store already contains that fingerprint for the same castle and mailbox, skip persistence,
- still allow the task to continue scanning remaining rows.

## 10.4 Discord integration boundary

The archive store should be treated as the integration boundary for future Discord posting.

That future integration should consume archive records from disk or a later queue, not reach back into live mail task logic.

This keeps mail automation and outbound integrations decoupled.

## 11. Runtime task behavior

## 11.1 `send_mail` applicability

`send_mail` should reject:

- login screens,
- account-switch screens,
- unknown screens that are not safely reducible,
- alliance-recipient requests when the account is at `PNC_ALLIANCE_JOIN`.

It should replan through reusable flows from:

- home city,
- mail hub,
- alliance home,
- supported route screens,
- mail compose popup.

## 11.2 `collect_mail` applicability

`collect_mail` should:

- allow `PNC_HOME_CITY`, `PNC_MAIL_HUB`, `PNC_MAILBOX_LIST`, and `PNC_MAIL_THREAD`,
- replan from any screen that can be reduced back to home city,
- reject login-owned states.

## 11.3 `collect_mail` runtime state

Use `TaskContext.runtime_state` to hold:

- remaining mailboxes to visit,
- current mailbox,
- collected fingerprints during this step,
- current mailbox row index or visible sender key when iterating,
- whether the task is returning from a thread back to the mailbox list.

This matches the existing runner design and avoids new loop orchestration code.

## 12. API and script surface

## 12.1 Runtime task ids

Add to [pnc_automation/automation/task.py](/c:/Users/lebel/pnc/pnc_automation/automation/task.py):

- `SEND_MAIL`
- `COLLECT_MAIL`

## 12.2 Registry

Register the two new tasks in [pnc_automation/automation/scripts/registry.py](/c:/Users/lebel/pnc/pnc_automation/automation/scripts/registry.py).

## 12.3 Python API

Add convenience methods in [pnc_automation/api.py](/c:/Users/lebel/pnc/pnc_automation/api.py):

- `send_mail(...)`
- `send_alliance_mail(...)`
- `send_personal_mail(...)`
- `collect_mail(...)`

The canonical task remains `send_mail`. The fixed-shape helpers are convenience wrappers only.

## 12.4 Script examples

Direct player mail by explicit name:

```yaml
steps:
  - task: send_mail
    castle:
      kingdom: K157
      castle_name: Tiny NPC
    params:
      recipient_kind: player
      player_name: "Lawa z kszaka"
      subject: "Test"
      body: "Hello from automation."
```

Alliance mail:

```yaml
steps:
  - task: send_mail
    params:
      recipient_kind: alliance
      subject: "Rally"
      body: "Join the rally at reset."
```

Personal mail from alliance-member route:

```yaml
steps:
  - task: send_mail
    params:
      recipient_kind: player
      profile_route:
        kind: alliance_member
        player_name: "BuNiCu F"
      subject: "Welcome"
      body: "Please check alliance mail."
```

Collect player and alliance mail:

```yaml
steps:
  - task: collect_mail
    params:
      mailboxes: [player, alliance]
      archive_mode: both
      limit_per_mailbox: 20
      only_new: true
```

## 13. Required implementation files

Likely implementation surface:

- [pnc_automation/pnc/screen_type.py](/c:/Users/lebel/pnc/pnc_automation/pnc/screen_type.py)
- [pnc_automation/pnc/ui_element_id.py](/c:/Users/lebel/pnc/pnc_automation/pnc/ui_element_id.py)
- [pnc_automation/pnc/observation.py](/c:/Users/lebel/pnc/pnc_automation/pnc/observation.py)
- [pnc_automation/pnc/action_requests.py](/c:/Users/lebel/pnc/pnc_automation/pnc/action_requests.py)
- [pnc_automation/pnc/screen_flows.py](/c:/Users/lebel/pnc/pnc_automation/pnc/screen_flows.py)
- [pnc_automation/pnc/mail.py](/c:/Users/lebel/pnc/pnc_automation/pnc/mail.py)
- [pnc_automation/automation/action_executor.py](/c:/Users/lebel/pnc/pnc_automation/automation/action_executor.py)
- [pnc_automation/automation/tasks/send_mail_task.py](/c:/Users/lebel/pnc/pnc_automation/automation/tasks/send_mail_task.py)
- [pnc_automation/automation/tasks/collect_mail_task.py](/c:/Users/lebel/pnc/pnc_automation/automation/tasks/collect_mail_task.py)
- [pnc_automation/automation/scripts/registry.py](/c:/Users/lebel/pnc/pnc_automation/automation/scripts/registry.py)
- [pnc_automation/api.py](/c:/Users/lebel/pnc/pnc_automation/api.py)
- [pnc_automation/vision/observation_request.py](/c:/Users/lebel/pnc/pnc_automation/vision/observation_request.py)
- [pnc_automation/vision/screen_classifier.py](/c:/Users/lebel/pnc/pnc_automation/vision/screen_classifier.py)
- [pnc_automation/vision/pnc_observation_enricher.py](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py)
- [pnc_automation/vision/data/selector_registry.yaml](/c:/Users/lebel/pnc/pnc_automation/vision/data/selector_registry.yaml)
- [pnc_automation/capture/mail_archive_store.py](/c:/Users/lebel/pnc/pnc_automation/capture/mail_archive_store.py)
- [pnc_automation/artifact_naming.py](/c:/Users/lebel/pnc/pnc_automation/artifact_naming.py)
- [tests/test_flows_and_tasks.py](/c:/Users/lebel/pnc/tests/test_flows_and_tasks.py)
- [tests/test_capture_and_vision.py](/c:/Users/lebel/pnc/tests/test_capture_and_vision.py)
- [tests/test_selectors.py](/c:/Users/lebel/pnc/tests/test_selectors.py)
- [tests/test_screen_classifier.py](/c:/Users/lebel/pnc/tests/test_screen_classifier.py)

## 14. Implementation order

## 14.1 Phase 1: Normalize screen and selector ownership

- rename `PNC_MAIL_LIST` and `PNC_SYSTEM_MESSAGE`,
- add new screen types for remote profile, compose popup, thread, and route popups,
- add selector ids and catalog entries,
- add classifier rules.

Exit condition:

- the runtime can classify the new screens without confusing them with existing self-profile or generic popup screens.

## 14.2 Phase 2: Observation and field-state refactor

- add generic `ObservedTextFieldState`,
- populate compose fields and migrate chat to the shared abstraction,
- keep `current_castle` ownership limited to self-profile and castle-selection logic.

Exit condition:

- mail compose and chat both use one shared clear-and-replace text policy,
- remote player profiles never populate `current_castle`.

## 14.3 Phase 3: Reusable flows

- implement `open_alliance_home`,
- implement `open_mail_hub`,
- implement `open_mailbox`,
- implement `open_player_profile`,
- implement `open_mail_compose`,
- implement canonical `send_mail`.

Exit condition:

- every mail entry path is expressed through `ScreenFlowPlanner` with no task-local navigation duplication.

## 14.4 Phase 4: Task and API layer

- implement `SendMailTask`,
- implement `CollectMailTask`,
- register them,
- expose API wrappers.

Exit condition:

- one script can send mail and verify it in the corresponding mailbox,
- one script can collect and archive mail,
- both run through the existing runner and task contract.

## 14.5 Phase 5: Archive persistence

- implement `MailArchiveStore`,
- add fingerprint dedup,
- write metadata, text, and screenshots.

Exit condition:

- repeated collection runs skip already archived thread snapshots,
- new mail produces deterministic archive records.

## 14.6 Phase 6: Validation and hardening

- add unit tests,
- add screenshot integration fixtures,
- run targeted live smoke validation for each supported entry path,
- collect real artifact evidence for player and alliance mail collection.

Exit condition:

- the runtime has both automated and live evidence for the supported paths.

## 15. Validation plan

## 15.1 Unit tests

Add unit tests for:

- `SendMailParams` parsing,
- `CollectMailParams` parsing,
- remote-profile route validation,
- generic text-field clear-and-replace behavior,
- multiline body splitting if implemented,
- mail archive fingerprinting and deduplication,
- flow planning from each supported entry path.

## 15.2 Screenshot integration tests

Add screenshot-based coverage for:

- `PNC_MAIL_HUB`,
- `PNC_MAILBOX_LIST` player mailbox,
- `PNC_MAILBOX_LIST` alliance mailbox,
- empty mailbox state,
- `PNC_MAIL_THREAD`,
- `PNC_MAIL_COMPOSE_POPUP`,
- `PNC_PLAYER_TERRITORY`,
- `PNC_PLAYER_PROFILE`,
- `PNC_CHAT_PLAYER_ACTION_POPUP`,
- `PNC_ALLIANCE_MEMBER_LIST`,
- `PNC_ALLIANCE_MEMBER_MANAGE_POPUP`,
- `PNC_MIGHT_RANK`.

Required negative tests:

- remote player profile must not set `current_castle`,
- `PNC_LORD_INFO` and `PNC_PLAYER_PROFILE` must not classify interchangeably,
- compose popup must not be mistaken for a generic popup,
- empty mailbox must not be mistaken for unknown just because there are no thread rows.

## 15.3 Live smoke validation

Required smoke cases:

1. `home -> mail hub -> player mailbox -> compose popup`
2. `home -> alliance home -> alliance mail compose popup with auto-filled target`
3. `player territory -> player profile -> compose popup with auto-filled target`
4. `chat bubble -> player popup -> player profile`
5. `alliance member -> manage -> player profile`
6. `might rank -> player profile`
7. `player mailbox -> open thread -> archive thread`
8. `alliance mailbox -> open thread -> archive thread`
9. one controlled end-to-end `send_mail` run that reopens `Player Mail` or `Alliance Mail`, finds the sent row, and confirms the message content when row evidence alone is not sufficient
10. one controlled end-to-end `collect_mail` run with dedup confirmed on a repeat pass

## 16. Acceptance criteria

The mail workflow is complete only when all of the following are true:

- there is exactly one canonical `send_mail` task,
- there is exactly one canonical `collect_mail` task,
- there is exactly one canonical compose-popup model,
- mail entry paths are expressed through shared flows instead of task-local navigation,
- remote player profiles never write into `current_castle`,
- self-profile current-castle validation still works unchanged,
- direct player mail, alliance mail, and profile-based personal mail all work through the same compose/send flow,
- successful sends are verified by reopening `Player Mail` or `Alliance Mail` and confirming the written mail is present, with thread-level confirmation when mailbox-row evidence alone is ambiguous,
- player and alliance mailbox collection both archive deterministic records,
- archive records are organized by date, castle, sender, mailbox, and fingerprint,
- duplicate collection runs do not produce duplicate archive entries,
- unsupported routes or invisible target rows fail fast with clear errors,
- obsolete screen and selector names introduced by the refactor are deleted, not kept in parallel.

## 17. Final design summary

The clean solution is not three separate mail features.

The clean solution is:

- one normalized mail screen model,
- one remote-profile model distinct from self `PNC_LORD_INFO`,
- one generic text-field-state abstraction shared by chat and mail,
- one canonical `send_mail` task,
- one canonical `collect_mail` task,
- one dedicated mail archive store,
- and one set of reusable flows added to the existing `ScreenFlowPlanner`.

That preserves the current repository architecture, fixes the known ownership issues before they become bugs, and provides a lean extension path for future mail-related work such as additional profile-entry routes, thread scrolling, direct thread replies, and Discord forwarding.
