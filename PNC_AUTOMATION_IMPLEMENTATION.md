# Step 1: Puzzles & Conquest Automation Implementation Document

## 1. Context

### 1.1 Project state

The current repository contains a small ADB spike in [main.py](/c:/Users/lebel/pnc/main.py). It can:

- connect to a BlueStacks ADB endpoint,
- execute raw ADB commands,
- tap the screen,
- input text,
- press key events,
- print basic device information.

That script is a transport prototype only. It is not yet a clean automation system for **Puzzles & Conquest**.

### 1.2 Actual target

The target application is **Puzzles & Conquest** running inside one or more BlueStacks instances. The goal is to automate routine castle-management tasks for multiple accounts, using screenshots as the authoritative source of truth for the current game state.

### 1.3 Identity model

The system must distinguish three different identities:

- BlueStacks instance or Android session,
- Puzzles & Conquest login account,
- castle character within that P&C account.

These are separate concepts and must not be collapsed into one config object by accident.

For the first implementation:

- one automation target maps to one BlueStacks instance,
- that target uses one intended P&C login account,
- that P&C account may contain many castles,
- but automation manages exactly one configured castle from that account.

### 1.4 Business intent

The desired automation outcomes are:

- log into different Puzzles & Conquest accounts,
- select the intended castle within each account,
- manage that selected castle with repeatable automation,
- auto-upgrade buildings,
- auto-start research,
- auto-gather resources,
- auto-progress campaign-related content where it is safe and well-defined,
- capture screenshots to disk,
- interpret screenshots and use that interpretation to drive GUI clicks,
- keep username and password data in configuration, without hardcoding them in scripts,
- keep runnable automation instructions outside account config, in dedicated script files.

### 1.5 Architectural constraints

The implementation must satisfy these non-negotiables:

- Single canonical implementation per concept.
- No duplicated logic.
- Fail-fast validation for invalid or unsupported states.
- Minimal boilerplate.

This matters more for a screenshot-driven game bot than for ordinary scripting. If coordinates, screen detection, retry logic, or account rules get duplicated, the project becomes fragile immediately.

## 2. Product vision

Build a small Puzzles & Conquest automation platform with one canonical observation and action loop.

The automation should operate like this:

1. Select the account and BlueStacks instance.
2. Ensure BlueStacks and Puzzles & Conquest are ready.
3. Ensure the correct account is logged in.
4. Capture a screenshot.
5. Interpret the screenshot into typed P&C UI facts.
6. Select the next valid castle-management task.
7. Execute the required GUI actions through ADB.
8. Re-observe and verify the result from a new screenshot.

Everything should plug into that loop:

- login,
- home-city navigation,
- building upgrades,
- academy research,
- world-map gathering,
- campaign progression,
- recovery from popups or interrupted flows.

## 3. Puzzles & Conquest domain framing

### 3.1 Relevant game concepts

The automation design should model the actual Puzzles & Conquest domain rather than invent generic MMO abstractions. The core concepts here are:

- account,
- castle roster,
- selected castle,
- castle,
- home city,
- building,
- academy research,
- world map,
- march slot,
- resource node,
- campaign screen,
- popup or modal interruption.

### 3.2 Important consequence

Different P&C tasks may begin from different screens, but they should all share the same reusable navigation and observation primitives. For example:

- both research and building automation need canonical "return to city" behavior,
- gathering and campaign both need reliable exit handling for modal screens,
- login and campaign reward claiming both require popup detection,
- login completion and castle targeting both require castle-roster interpretation.

That shared infrastructure must exist once, centrally.

## 4. Goals

### 4.1 Functional goals

- Support multiple BlueStacks instances.
- Support multiple Puzzles & Conquest accounts.
- Launch or foreground Puzzles & Conquest on the selected emulator instance.
- Log in using account-specific credentials.
- Capture screenshots and store them on disk.
- Interpret screenshots into typed screen state and UI elements.
- Automatically upgrade eligible buildings according to policy.
- Automatically start valid research according to policy.
- Automatically dispatch gathering marches according to policy.
- Automatically progress configured campaign flows according to policy.

### 4.2 Non-functional goals

- Deterministic behavior.
- Explicit state transitions.
- Strong debugging artifacts.
- Minimal hardcoded coordinates.
- Fast failure when the UI no longer matches expectations.
- Lean extension model for new P&C tasks.

## 5. Scope

### 5.1 In scope

- Windows host machine.
- BlueStacks control through ADB.
- Screenshot capture through ADB.
- OCR and template-based P&C UI interpretation.
- P&C-specific task automation.
- Local configuration and artifact storage.

### 5.2 Out of scope for the first version

- Generic support for arbitrary Android games.
- Emulator vendors other than BlueStacks.
- Memory inspection, packet inspection, or game process hooks.
- Backward compatibility for many historic P&C UI layouts.
- Parallel account execution before single-account stability is proven.

The initial implementation should target one validated Puzzles & Conquest client layout and one known BlueStacks setup.

## 6. Canonical architecture principle

The whole system should be built around one pipeline:

`Account Config + Run Script -> Emulator Session -> Screenshot -> P&C Observation -> Task Decision -> GUI Action -> Verification`

Each stage owns one concept:

- `Account Config` owns stable account and emulator inputs.
- `Automation Script` owns which tasks run and with what task-specific parameters.
- `Emulator Session` owns connectivity and app readiness.
- `Screenshot` owns evidence collection.
- `P&C Observation` owns interpretation of visible game state.
- `Task Decision` owns prioritization.
- `GUI Action` owns ADB-level execution.
- `Verification` owns success and failure detection.

If a building task, research task, or gathering task bypasses this pipeline, the design is becoming duplicated.

## 7. Proposed module structure

Use a package structure like:

```text
pnc_automation/
  __init__.py
  app.py
  cli.py
  config/
    models.py
    loader.py
    validation.py
  adb/
    client.py
    command_result.py
  emulator/
    bluestacks_instance.py
    session.py
  capture/
    screenshot_service.py
    artifact_store.py
  vision/
    image_models.py
    template_matcher.py
    ocr_service.py
    selectors.py
    screen_classifier.py
    observation_builder.py
  pnc/
    screen_type.py
    ui_element_id.py
    observation.py
    screen_flows.py
    action_requests.py
    policy_models.py
  automation/
    runner.py
    script_runner.py
    scripts/
      models.py
      loader.py
      registry.py
    task.py
    task_context.py
    tasks/
      ensure_game_running_task.py
      login_task.py
      select_castle_task.py
      popup_recovery_task.py
      building_upgrade_task.py
      research_task.py
      gathering_task.py
      campaign_task.py
  diagnostics/
    logging_setup.py
```

This structure is split by ownership, not by arbitrary script size.

## 8. Canonical responsibilities

### 8.1 `config`

Loads configuration once, validates it once, and produces typed models once.

No other module should:

- parse YAML directly,
- read raw secrets from random locations,
- interpret run instructions,
- infer task sequencing from ad hoc dictionaries.

`config` should contain only stable data such as:

- BlueStacks instance binding,
- login username reference,
- login password reference,
- selected castle identity.

### 8.2 `adb`

Owns:

- ADB command execution,
- process invocation,
- timeouts,
- stdout and stderr handling,
- shell escaping rules,
- low-level command failures,
- account-targeted or device-targeted ADB invocation wrapping.

No other module should construct raw `adb` command strings.

### 8.3 `emulator`

Owns:

- BlueStacks instance targeting,
- connection establishment,
- emulator readiness checks,
- ensuring Puzzles & Conquest is foregrounded.

### 8.4 `capture`

Owns:

- screenshot acquisition,
- screenshot validation,
- screenshot naming,
- artifact directory creation,
- artifact retention rules if added later.

### 8.5 `vision`

Owns:

- template matching,
- OCR,
- screen classification,
- selector resolution,
- conversion from pixels to detected visual facts.

No automation task should do image matching or OCR directly.

### 8.6 `pnc`

Owns game-specific models:

- screen types,
- known element identifiers,
- interpretation of visual facts into game meaning,
- reusable navigation flows,
- action request types,
- P&C task parameter models.

### 8.7 `automation`

Owns:

- loading runnable automation scripts,
- parsing and validating script YAML,
- mapping step names such as `building_upgrade` into registered task identifiers,
- task applicability,
- task planning,
- execution of the script-defined task sequence,
- task execution loop,
- verification and retry policy.

## 9. Typed configuration model

## 9.1 Canonical account configuration file

Use one typed account configuration file, for example `config/accounts.yaml`.

Example:

```yaml
artifacts:
  root: artifacts

defaults:
  adb_path: adb
  screenshot_format: png
  stable_click_delay_ms: 300
  post_action_observe_delay_ms: 800

instances:
  - id: bs-main
    device_id: 127.0.0.1:5555
    app_package: com.global.ztmslg

accounts:
  - id: account_a_main_castle
    instance_id: bs-main
    username_env: PNC_CASTLE_A_USER
    password_env: PNC_CASTLE_A_PASS
    selected_castle:
      kingdom: K230
      castle_name: Lv.5 Hellhound
      castle_level: 8
```

### 9.2 Secret handling

The config file should reference environment variable names, not raw credentials. For example:

- `PNC_CASTLE_A_USER`
- `PNC_CASTLE_A_PASS`

Missing secrets must fail startup for any account that has login enabled.

### 9.3 Validation rules

Startup validation must confirm:

- each account references a known BlueStacks instance,
- required credentials exist,
- each configured automation target declares exactly one selected castle for v1,
- artifact root is writable.

Any invalid configuration must stop execution immediately.

## 9.4 Run script model

Run instructions should live in YAML files under a top-level `scripts/` folder in the repo, but they should be loaded and interpreted only by the `automation` module.

Example:

```yaml
name: daily_castle_maintenance

steps:
  - task: login
  - task: select_castle
  - task: building_upgrade
    params:
      priority: [castle, wall, academy, barracks]
      allow_speedups: false
  - task: research
    params:
      priority: [economy, development, military]
  - task: gathering
    params:
      preferred_resources: [food, wood, iron]
      max_parallel_marches: 2
  - task: campaign
    params:
      enabled_modes: [standard]
```

The command-line shape should be:

```powershell
python -m pnc_automation.cli --account account_a_main_castle --script scripts/daily_castle_maintenance.yaml
```

This split keeps credentials and account identity stable, while allowing task plans to change independently.

## 10. Runtime domain model

Create authoritative types for:

- `AppConfig`
- `BlueStacksInstanceConfig`
- `AccountConfig`
- `SelectedCastleConfig`
- `Observation`
- `ScreenType`
- `UiElementId`
- `VisibleElement`
- `DetectedListEntry`
- `TaskId`
- `RunScript`
- `ScriptStep`
- `TaskDecision`
- `ActionRequest`
- `TaskResult`
- `AutomationErrorKind`

Use enums rather than raw strings once configuration is loaded.

For v1, `AccountConfig` should represent one automation target. That target bundles:

- emulator binding,
- login credentials,
- one selected castle identity,
- no task sequencing or task-specific parameters.

For dynamic list-based screens, observation data should not collapse everything into fixed selector ids. It should support repeated entries such as:

- row bounds,
- title text,
- subtitle text,
- timer text,
- badge presence,
- action-button presence.

## 11. Puzzles & Conquest screen model

The automation should treat the P&C UI as a set of known screen states, not as unstructured images.

Suggested `ScreenType` values:

- `UNKNOWN`
- `ANDROID_HOME`
- `PNC_LOADING`
- `PNC_LOGIN`
- `PNC_ACCOUNT_SWITCH`
- `PNC_CASTLE_SELECTION`
- `PNC_HOME_CITY`
- `PNC_BAG`
- `PNC_QUEST_DAILY`
- `PNC_HERO_LIST`
- `PNC_HERO_DETAIL_UPGRADE`
- `PNC_HERO_DETAIL_ENHANCE`
- `PNC_MAIL_LIST`
- `PNC_SYSTEM_MESSAGE`
- `PNC_ALLIANCE_HOME`
- `PNC_CASH_MALL`
- `PNC_GIFT_CENTER`
- `PNC_EVENT_CENTER`
- `PNC_BUILDING_DETAILS`
- `PNC_ACADEMY`
- `PNC_RESEARCH_TREE`
- `PNC_WORLD_MAP`
- `PNC_GATHER_NODE`
- `PNC_MARCH_CONFIRM`
- `PNC_CAMPAIGN`
- `PNC_CAMPAIGN_STAGE`
- `PNC_BATTLE_PREP`
- `PNC_POPUP`

This model should stay lean. Only create distinct screen types that matter for decision-making or navigation.

Based on the screenshots currently provided, the first validated screen set is:

- `PNC_HOME_CITY`
- `PNC_BAG`
- `PNC_QUEST_DAILY`
- `PNC_HERO_LIST`
- `PNC_HERO_DETAIL_UPGRADE`
- `PNC_HERO_DETAIL_ENHANCE`
- `PNC_MAIL_LIST`
- `PNC_SYSTEM_MESSAGE`
- `PNC_ALLIANCE_HOME`
- `PNC_CASH_MALL`
- `PNC_GIFT_CENTER`
- `PNC_EVENT_CENTER`
- `PNC_WORLD_MAP`

The following screen types remain planned but not yet screenshot-validated:

- `PNC_LOGIN`
- `PNC_CASTLE_SELECTION`
- `PNC_BUILDING_DETAILS`
- `PNC_ACADEMY`
- `PNC_RESEARCH_TREE`
- `PNC_GATHER_NODE`
- `PNC_MARCH_CONFIRM`
- `PNC_CAMPAIGN`
- `PNC_CAMPAIGN_STAGE`
- `PNC_BATTLE_PREP`
- `PNC_POPUP`

## 12. Selector registry

All selectors must live in one canonical registry. No task may embed its own coordinate tables or duplicate templates.

The screenshots currently documented in this file are an initial registry seed only. They are not the final selector map.

The iterative click-mapping and selector-refinement process now lives in [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SELECTOR_REFINEMENT_SUBPLAN.md).

The selector registry is the authoritative catalog of UI elements the system can detect, interpret, and click. Each selector entry should define:

- selector id,
- screen applicability,
- detection mode such as template, OCR region, or anchored region,
- optional click target,
- optional OCR extraction region,
- confidence threshold,
- normalization or scaling rule if needed.

For dynamic-content screens, the registry must define reusable collection selectors rather than hardcoded row identities. In practice, that means:

- define the list row container once,
- define subregions within a row such as title, timer, badge, and primary action,
- extract row content with OCR or anchored matching,
- let `pnc` interpret row meaning from extracted content.

Do not create selector ids for temporary event names such as one specific promotion or rotating event row unless the game proves that the row identity is structurally stable across time.

General-purpose selectors already supported by the current screenshots:

- `PNC_BOTTOM_NAV_HOME`
- `PNC_BOTTOM_NAV_HERO`
- `PNC_BOTTOM_NAV_QUEST`
- `PNC_BOTTOM_NAV_BAG`
- `PNC_BOTTOM_NAV_MAIL`
- `PNC_BOTTOM_NAV_ALLIANCE`
- `PNC_BOTTOM_NAV_MORE`
- `PNC_BACK_BUTTON_TOP_LEFT`

Home-city selectors visible in the current screenshots:

- `PNC_HOME_BUILD_BUTTON`
- `PNC_HOME_RESEARCH_BUTTON`
- `PNC_HOME_CAMPAIGN_ENTRY`
- `PNC_HOME_WORLD_SWITCH`
- `PNC_HOME_CHARACTER_PANEL`
- `PNC_HOME_TOP_RESOURCE_FOOD`
- `PNC_HOME_TOP_RESOURCE_WOOD`
- `PNC_HOME_TOP_RESOURCE_DIAMOND`
- `PNC_HOME_RIGHT_RAIL_CASH_MALL_ICON`
- `PNC_HOME_RIGHT_RAIL_GIFT_CENTER_ICON`
- `PNC_HOME_RIGHT_RAIL_EVENT_CENTER_ICON`

The following home-screen icon mappings are now screenshot-validated:

- `PNC_HOME_RIGHT_RAIL_CASH_MALL_ICON` -> opens `PNC_CASH_MALL`
- `PNC_HOME_RIGHT_RAIL_GIFT_CENTER_ICON` -> opens `PNC_GIFT_CENTER`
- `PNC_HOME_RIGHT_RAIL_EVENT_CENTER_ICON` -> opens `PNC_EVENT_CENTER`

Bag selectors visible in the current screenshots:

- `PNC_BAG_MAIN_TAB_BAG`
- `PNC_BAG_MAIN_TAB_DIAMOND_SHOP`
- `PNC_BAG_SUBTAB_RESOURCE`
- `PNC_BAG_SUBTAB_SPEEDUP`
- `PNC_BAG_SUBTAB_MILITARY`
- `PNC_BAG_SUBTAB_TREASURE`
- `PNC_BAG_SUBTAB_MISC`
- `PNC_BAG_ITEM_ROW`
- `PNC_BAG_USE_BUTTON`
- `PNC_BAG_USE_IN_BULK_BUTTON`

Quest selectors visible in the current screenshots:

- `PNC_QUEST_TAB_MAIN`
- `PNC_QUEST_TAB_DAILY`
- `PNC_QUEST_TAB_ALLIANCE_ACTIVITY`
- `PNC_QUEST_REWARD_CHEST`
- `PNC_QUEST_ROW`
- `PNC_QUEST_GO_BUTTON`
- `PNC_QUEST_CLAIMED_LABEL`
- `PNC_QUEST_RESET_TIMER`

Hero selectors visible in the current screenshots:

- `PNC_HERO_TAB_HERO`
- `PNC_HERO_TAB_UNOBTAINED`
- `PNC_HERO_TAB_BAG`
- `PNC_HERO_CARD`
- `PNC_HERO_FILTER_BUTTON`
- `PNC_HERO_DETAIL_TAB_UPGRADE`
- `PNC_HERO_DETAIL_TAB_ENHANCE`
- `PNC_HERO_DETAIL_TAB_TROOP_SKILL`
- `PNC_HERO_DETAIL_TAB_HERO_SKILL`
- `PNC_HERO_EVOLVE_BUTTON`
- `PNC_HERO_ENHANCE_BUTTON`

Mail selectors visible in the current screenshots:

- `PNC_MAIL_ROW_SYSTEM_MESSAGE`
- `PNC_MAIL_ROW_PLAYER_MAIL`
- `PNC_MAIL_ROW_ALLIANCE_MAIL`
- `PNC_MAIL_ROW_BATTLELOG`
- `PNC_MAIL_ROW_HUNT_REPORT`
- `PNC_MAIL_ROW_HELL_FORTRESS`
- `PNC_MAIL_ROW_GATHERING_REPORT`
- `PNC_MAIL_ROW_TRANSPORT_REPORT`
- `PNC_SYSTEM_MESSAGE_MARK_AS_READ_BUTTON`
- `PNC_SYSTEM_MESSAGE_MANAGE_BUTTON`

Alliance selectors visible in the current screenshots:

- `PNC_ALLIANCE_TILE_TERRITORY`
- `PNC_ALLIANCE_TILE_GIFT_LEVEL`
- `PNC_ALLIANCE_TILE_WAR`
- `PNC_ALLIANCE_TILE_TECH`
- `PNC_ALLIANCE_TILE_TREASURY`
- `PNC_ALLIANCE_TILE_RANK`
- `PNC_ALLIANCE_TILE_EVENT`
- `PNC_ALLIANCE_TILE_MEMBER`
- `PNC_ALLIANCE_BOTTOM_TAB_SHOP`
- `PNC_ALLIANCE_BOTTOM_TAB_MAIL`
- `PNC_ALLIANCE_BOTTOM_TAB_HELP`
- `PNC_ALLIANCE_BOTTOM_TAB_OPERATIONS`

Cash Mall selectors visible in the current screenshots:

- `PNC_CASH_MALL_TAB_DAILY_SALE`
- `PNC_CASH_MALL_TAB_MONTHLY_GIFT`
- `PNC_CASH_MALL_TAB_TIME_LIMITED_SPECIAL_OFFER`
- `PNC_CASH_MALL_TAB_HERO`
- `PNC_CASH_MALL_ENTRY_ROW`
- `PNC_CASH_MALL_ENTRY_TITLE_REGION`
- `PNC_CASH_MALL_ENTRY_TIMER_REGION`
- `PNC_CASH_MALL_ENTRY_PRICE_BUTTON`
- `PNC_CASH_MALL_ENTRY_HOT_BADGE`

Gift Center selectors visible in the current screenshots:

- `PNC_GIFT_CENTER_ENTRY_ROW`
- `PNC_GIFT_CENTER_ENTRY_TITLE_REGION`
- `PNC_GIFT_CENTER_ENTRY_SUBTITLE_REGION`
- `PNC_GIFT_CENTER_ENTRY_EXPIRY_REGION`
- `PNC_GIFT_CENTER_ENTRY_ALERT_BADGE`

Event Center selectors visible in the current screenshots:

- `PNC_EVENT_CENTER_TAB_REGULAR_EVENTS`
- `PNC_EVENT_CENTER_TAB_HOLIDAY_EVENTS`
- `PNC_EVENT_CENTER_TAB_ABOUT_TO_START`
- `PNC_EVENT_CENTER_EVENT_ROW`
- `PNC_EVENT_CENTER_ENTRY_TITLE_REGION`
- `PNC_EVENT_CENTER_ENTRY_TIMER_REGION`
- `PNC_EVENT_CENTER_ENTRY_ALERT_BADGE`

For `PNC_CASH_MALL`, `PNC_GIFT_CENTER`, and `PNC_EVENT_CENTER`, row content is variable and event-driven. The registry should therefore model those screens as collections of entries, and `pnc` should interpret entries by extracted text and badges rather than by fixed row ids.

World-map selectors visible in the current screenshots:

- `PNC_WORLD_COORDINATE_BAR`
- `PNC_WORLD_MY_TERRITORY_LABEL`
- `PNC_WORLD_HOME_NAV`
- `PNC_WORLD_SEARCH_BUTTON`
- `PNC_WORLD_EXPAND_BUTTON`
- `PNC_WORLD_TARGET_CASTLE`

Still-planned selectors that require more screenshots before they should be locked:

- `ANDROID_HOME_PNC_ICON`
- `PNC_LOGIN_USERNAME_FIELD`
- `PNC_LOGIN_PASSWORD_FIELD`
- `PNC_LOGIN_SUBMIT_BUTTON`
- `PNC_CASTLE_LIST_ENTRY`
- `PNC_CASTLE_SELECTED_CHECKMARK`
- `PNC_HOME_BUILDING_UPGRADE_BADGE`
- `PNC_HOME_ACADEMY_BUILDING`
- `PNC_BUILDING_UPGRADE_BUTTON`
- `PNC_RESEARCH_AVAILABLE_BADGE`
- `PNC_RESEARCH_START_BUTTON`
- `PNC_WORLD_MAP_BUTTON`
- `PNC_GATHER_BUTTON`
- `PNC_MARCH_CONFIRM_BUTTON`
- `PNC_CAMPAIGN_ENTRY_BUTTON`
- `PNC_CAMPAIGN_BATTLE_BUTTON`
- `PNC_POPUP_CLOSE_BUTTON`

Example selector shape:

```yaml
id: PNC_QUEST_GO_BUTTON
screens: [PNC_QUEST_DAILY]
detect:
  kind: template
  asset: templates/pnc/quest/go_button.png
  threshold: 0.92
click:
  anchor: center
ocr:
  enabled: false
```

The selector registry should own the canonical definition for:

- template asset references,
- optional OCR regions,
- click target definitions,
- confidence thresholds,
- screen-type applicability,
- selector status such as `validated_from_screenshots` or `planned`.

If resolution normalization is needed, scaling rules must also live here centrally.

Selectors should not be considered fully ready from screenshots alone. For clickable elements, refinement must also map:

- source screen,
- click target,
- resulting screen or state,
- verification evidence after click.

## 13. Screenshot and perception pipeline

### 13.1 Screenshot capture

Use `adb exec-out screencap -p` as the canonical screenshot path.

The screenshot service should:

- capture bytes,
- decode them into an image,
- fail if decode is invalid,
- write the artifact to disk,
- return both the image object and artifact metadata.

Suggested artifact layout:

```text
artifacts/
  2026-03-07/
    castle_a/
      20260307T213015Z_home_scan.png
      20260307T213109Z_research_before.png
      20260307T213113Z_research_after.png
      20260307T213440Z_campaign_failure.png
```

### 13.2 Interpretation strategy

Use a layered perception strategy:

1. classify the current screen from strong anchors,
2. detect known buttons or icons through template matching,
3. OCR only specific regions that matter,
4. derive typed facts from those results.

Example typed facts:

- current screen is `PNC_HOME_CITY`,
- a castle-selection list is visible,
- visible castles were parsed from the roster,
- the configured castle is selected or not selected,
- visible event-center entries were extracted as dynamic list items,
- an upgrade badge is visible,
- the academy is visible,
- a generic popup is blocking interaction,
- a gather button is visible,
- a march confirm button is enabled.

Tasks should consume these facts only. They should never reason directly over pixel data.

### 13.3 Fail-fast screen handling

If a task expects `PNC_HOME_CITY` and the observation is `UNKNOWN` or a mismatched screen, the task must stop and persist artifacts. It must not guess and click anyway.

## 14. Canonical action model

Define a small action vocabulary:

- `Tap(selector_id)`
- `TapPoint(x, y)`
- `InputText(selector_id, text_source)`
- `KeyEvent(key_code)`
- `Wait(milliseconds)`
- `Swipe(direction, distance_ratio)`

Most actions should be selector-based. `TapPoint` should exist only for carefully centralized cases where a stable selector does not yet exist.

The action executor must be the only layer that translates those requests into ADB commands.

## 15. Dependency-Ordered Follow-Up Plans

The plan files should be completed in this order, based on component dependency:

1. [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md)
   This primary architecture plan defines ownership, core models, registry rules, and implementation phases.
2. [PNC_AUTOMATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_SUBPLAN.md)
   Automation orchestration is already implemented in code. This sub-plan remains as the canonical reference for the generic execution loop, task contract, script runner, and retry or stop policy used by later work.
3. [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SELECTOR_REFINEMENT_SUBPLAN.md)
   Selector refinement follows because screen flows and concrete tasks depend on validated clickable UI mappings, especially for unique buildings and empty building slots.
4. [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md)
   Reusable navigation flows should be defined after selector refinement, because flows depend on trustworthy selectors and known source-to-destination transitions.
5. [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md)
   Account-navigation planning follows screen-flow design because bootstrap, popup recovery, verified in-game entry, and castle targeting depend on reusable navigation plus refined selectors.
6. [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md)
   Post-navigation task design should come last because those tasks depend on the automation contract, refined selectors, reusable screen flows, and a defined account-navigation plan.

## 16. Logging and diagnostics

### 16.1 Structured logs

Every meaningful operation should include fields such as:

- timestamp,
- account_id,
- instance_id,
- task_id,
- screen_type,
- action_type,
- selector_id,
- result,
- artifact_path,
- error_kind.

### 16.2 Required screenshot artifacts

Persist screenshots:

- at task start,
- after task completion,
- on verification failure,
- on screen-classification failure,
- on selector-resolution failure,
- on unexpected popup handling.

Without these artifacts, debugging UI automation becomes guesswork.

## 17. Error handling

Use typed failures:

- `ConfigurationError`
- `DeviceConnectionError`
- `GameLaunchError`
- `ScreenshotCaptureError`
- `ScreenClassificationError`
- `SelectorResolutionError`
- `TaskVerificationError`

Recover only from known transient failures:

- reconnecting ADB,
- retrying a truncated screenshot once,
- retrying one action after a short stabilization wait.

Do not silently continue after:

- missing credentials,
- unknown screen,
- missing selector,
- impossible task precondition,
- repeated verification mismatch.

These must stop the current task and persist artifacts.

## 18. Clean refactor plan from current code

The current `BlueStackController` in [main.py](/c:/Users/lebel/pnc/main.py) currently mixes:

- raw ADB execution,
- BlueStacks connection,
- primitive actions,
- console output,
- demo orchestration.

That should be split into:

- `AdbClient`,
- `BlueStacksSession`,
- `ScreenshotService`,
- `ActionExecutor`,
- `ObservationBuilder`,
- `ApplicationRunner`.

Then `main.py` should become a thin CLI entry point only.

## 19. Recommended implementation phases

### Phase 1: Foundation

- create package structure,
- move ADB logic into `AdbClient`,
- add typed config loader,
- add secret resolution,
- add structured logging,
- add screenshot capture and artifact store.

Exit condition:

- one configured account can connect to BlueStacks and persist a screenshot to disk.

### Phase 2: P&C observation baseline

This phase is now owned by [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SELECTOR_REFINEMENT_SUBPLAN.md) and is considered closed in this primary implementation plan.

### Phase 2.5: Selector refinement

This phase is now owned by [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SELECTOR_REFINEMENT_SUBPLAN.md) and is considered closed in this primary implementation plan.

### Phase 3: Automation framework

This phase is implemented in code and is considered closed in this primary implementation plan.

### Phase 4: Account login

This phase is now owned by [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md) and is considered closed in this primary implementation plan.

### Phase 5: Castle targeting

This phase is now owned by [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md) and is considered closed in this primary implementation plan.

### Phase 6: Castle-management features

- implement building upgrade task,
- implement research task,
- implement gathering task,
- implement the first bounded campaign task.

Exit condition:

- each feature runs through the same script-runner and verification pipeline with no feature-specific scripting stack.

### Phase 6.5: Secondary task-design plan

- collect real screenshots for selector-registry definition,
- write and refine [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SELECTOR_REFINEMENT_SUBPLAN.md),
- write and refine [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md),
- write and refine [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md),
- write and refine [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md),
- lock exact flows for login, castle selection, building, research, gathering, and campaign before implementation refinement.

Exit condition:

- each concrete task has a screenshot-informed task-design spec.

### Phase 7: Hardening

- tune selectors,
- add recorded-screenshot test fixtures,
- add maintenance windows and per-account limits,
- add safe stop conditions,
- consider concurrency only after single-thread stability.

## 20. Validation and testing strategy

### 20.1 Mandatory validation rule

Every implementation task must end with the smallest relevant validation gate before it is considered complete.

Rules:

- pure logic changes must end with unit tests,
- selector or vision changes must end with screenshot integration tests,
- live clickable-flow changes must end with smoke validation,
- mixed changes must run every relevant gate, not just one,
- phase completion must run the broader phase exit suite,
- no feature is considered complete without explicit validation evidence.

The plan must therefore treat testing as part of task completion, not as a later cleanup step.

### 20.2 Validation matrix

Use the following mapping:

- config, script parsing, runner logic, retry policy, typed models: unit tests,
- selector parsing, screen classification, OCR extraction, observation building: screenshot integration tests,
- source-screen to destination-screen click mapping: screenshot integration tests plus targeted live smoke checks,
- reusable screen flows: targeted live smoke checks plus screenshot evidence where possible,
- end-to-end feature flows such as login, castle selection, building, research, gathering, and campaign: live smoke checks plus any supporting unit or screenshot tests for their internal logic.

### 20.3 Phase exit validation gates

Each implementation phase should be considered complete only when its required validation gate has been run:

- Phase 1: unit tests for config and foundation logic, plus smoke check for emulator connection and screenshot persistence,
- Phase 2: owned by [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SELECTOR_REFINEMENT_SUBPLAN.md) and treated as closed in this plan,
- Phase 2.5: owned by [PNC_SELECTOR_REFINEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SELECTOR_REFINEMENT_SUBPLAN.md) and treated as closed in this plan,
- Phase 3: implemented in code, validated by unit tests for runner, script loading, and task contract behavior, and treated as closed in this plan,
- Phase 4: owned by [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md) and treated as closed in this plan,
- Phase 5: owned by [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md) and treated as closed in this plan,
- Phase 6: smoke validation per implemented feature, plus lower-level unit or screenshot tests for any logic extracted from the feature,
- Phase 7: broader regression pass across the relevant unit, screenshot, and smoke suites.

### 20.4 Unit tests

Test pure logic:

- config validation,
- secret resolution,
- script-step ordering,
- policy selection,
- selector lookup,
- observation-to-task applicability mapping,
- task-step validation logic,
- runner stop and retry decisions.

### 20.5 Screenshot integration tests

Use recorded Puzzles & Conquest screenshots to test:

- screen classification,
- popup detection,
- selector matching,
- OCR extraction,
- task planning,
- selector click-mapping expectations,
- building-slot and unique-building screen interpretation once those screenshots are available.

This should be the most important automated test layer because it validates the screenshot-driven architecture without requiring a live BlueStacks session.

### 20.6 Live smoke tests

Create smoke checks for:

- connect to BlueStacks,
- capture screenshot,
- detect Android home,
- open Puzzles & Conquest,
- detect home city,
- close a popup,
- click one known button,
- verify one source-screen to destination-screen mapped selector,
- run each newly implemented feature flow at least once in a controlled environment.

## 21. Final architecture checklist

Before implementation is considered correct, confirm:

- there is exactly one ADB execution abstraction,
- there is exactly one screenshot service,
- there is exactly one selector registry,
- there is exactly one P&C observation model,
- there is exactly one script loader and runner,
- popup handling is centralized,
- navigation flows are centralized,
- each feature is a task invoked by scripts, not a standalone automation stack,
- each implementation task ended with the smallest relevant validation gate,
- each feature has explicit validation coverage,
- unknown screens fail fast,
- credentials are externalized,
- `main.py` is only entry-point wiring.

## 22. Conclusion

The correct solution for this repository is a **Puzzles & Conquest-specific automation platform**, not a larger version of the current one-file ADB script.

The system should be built around one canonical screenshot-driven loop, one typed account-configuration model, one script model, one selector registry, one observation model, one script runner, and one task framework. That keeps the design lean, DRY, extensible, and well integrated while still matching the real P&C workflows you want to automate.

