# Step 5: Puzzles & Conquest Account Navigation Sub-Plan

## 1. Purpose

This document is the dependency-ordered fifth plan and covers account bootstrap, login, and castle-targeting design for former Phase 4 and Phase 5.

It is intentionally separate from:

- [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md), which remains the primary platform architecture plan,
- [PNC_AUTOMATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_SUBPLAN.md), which covers generic orchestration,
- [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SELECTOR_REFINEMENT_SUBPLAN.md), which covers selector maturity,
- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md), which covers reusable navigation,
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md), which covers post-navigation task behavior.

This file owns only the work required to bring a configured BlueStacks instance and Puzzles & Conquest account to the intended verified castle.

## 2. Former implementation phases now owned here

These phases are transferred here for ownership and validation tracking, but they are not yet closed in the primary implementation plan.

### Former Phase 4: Account login

- implement `EnsureGameRunningTask`,
- implement `PopupRecoveryTask`,
- implement `LoginTask`.

Exit condition:

- one configured Puzzles & Conquest account can be brought from Android home to a verified in-game state.

Status:

- ownership moved here from the primary implementation plan,
- phase closure depends on completion of this sub-plan's work and validation evidence.

### Former Phase 5: Castle targeting

- implement castle-roster observation,
- implement `SelectCastleTask`,
- verify the configured castle can be selected reliably.

Exit condition:

- one configured P&C account with many castles can be brought to one verified selected castle.

Status:

- ownership moved here from the primary implementation plan,
- phase closure depends on completion of this sub-plan's work and validation evidence.

## 3. Scope

This sub-plan should define:

- how the runtime ensures the Android device is responsive,
- how Puzzles & Conquest is started or foregrounded,
- how Android home, loading, login, popup, account-switch, and already-in-game states are interpreted,
- how credentials or account switching are applied when required,
- how the configured `instance_id`, `pnc_account_id`, and `selected_castle` are verified,
- how castle-roster observation and castle selection are interpreted and executed,
- how account-navigation-specific retry, recovery, and fail-fast rules are applied.

## 4. Task ownership

This sub-plan owns:

- `EnsureGameRunningTask`,
- `PopupRecoveryTask`,
- `LoginTask`,
- `SelectCastleTask`.

This sub-plan does not own:

- the generic runner or script parser,
- the canonical selector registry,
- reusable navigation flows,
- city, world-map, research, or campaign feature tasks.

## 5. Current dependency status

The following account-navigation areas still belong here when deeper refinement resumes:

- Android home to Puzzles & Conquest foreground recovery variants,
- login-screen and account-switch variants,
- blocking popup, reward, and notice variants during bootstrap,
- loading and reconnect states,
- manage-character and castle-roster variants,
- wrong-account detection and correction before castle selection,
- wrong-castle detection and correction before post-navigation tasks begin.

### 5.1 Feature-scoped selector growth

Account-navigation work does not wait for a globally finished selector registry.

Rules:

- refine only the selectors needed for the current bootstrap or castle-targeting slice,
- when a new login, popup, account-switch, or castle-selection UI element must be clicked, add it through the reviewed selector-refinement workflow first,
- treat registry growth here as incremental maintenance driven by concrete account-navigation needs, not as a one-time prerequisite to finish up front.

## 6. Per-task template

Each account-navigation task section should follow one canonical template:

### Task purpose

- what the task is responsible for,
- what it must not own.

### Entry conditions

- required `ScreenType`,
- required selectors,
- required script or account inputs,
- invalid preconditions that must fail fast.

### Observations required

- visual facts needed from `vision`,
- game meaning derived by `pnc`,
- OCR fields or account identifiers required.

### Planned actions

- navigation sequence,
- selector-based taps,
- text entry,
- roster selection,
- optional waits,
- verification checkpoints.

### Verification

- expected destination screen,
- required selector state,
- account, character, or castle evidence,
- negative conditions that indicate failure.

### Failure handling

- allowed retries,
- popup recovery interaction,
- when to stop the run.

### Validation gate

- screenshot integration coverage,
- targeted smoke validation requirements,
- required artifacts on mismatch.

## 7. Shared flow dependencies

Account-navigation work should consume shared navigation flows from [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md), especially:

- `ensure_android_home()`,
- `ensure_pnc_foreground()`,
- `ensure_correct_castle_selected()`,
- `ensure_home_city()`,
- `close_blocking_popup()`,
- `return_to_safe_root_screen()`.

Rules:

- account-navigation tasks should reuse shared flows instead of embedding duplicate navigation logic,
- if bootstrap or castle targeting needs a new reusable path, add it to the screen-flow sub-plan first, then reference it here.

## 8. Validation requirement

No account-navigation task should be considered complete without explicit validation evidence.

Minimum evidence:

- screenshot integration tests for login-screen interpretation and other bootstrap-only states,
- screenshot or OCR validation for castle-roster interpretation and selected-castle verification,
- targeted smoke validation that opens the castle-management (`manage-character`) screen, switches castles successfully, and verifies the newly selected castle,
- targeted smoke validation for a full bootstrap path to the configured selected castle,
- artifact capture when credential entry, popup recovery, castle selection, or verification fails.

## 9. Relationship to other plans

- [PNC_AUTOMATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_SUBPLAN.md) owns generic runner and orchestration behavior and should consume these tasks.
- [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SELECTOR_REFINEMENT_SUBPLAN.md) owns account-navigation-related selector maturity and click validation.
- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md) owns reusable navigation shared by bootstrap, castle targeting, and later tasks.
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md) starts after the configured castle has been verified and must not duplicate account-navigation task design.
