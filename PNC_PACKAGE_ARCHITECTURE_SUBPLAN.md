# Puzzles & Conquest Package Architecture Sub-Plan

## 1. Purpose

This document defines the target repository arborescence used to isolate reusable framework logic from Puzzles & Conquest business logic.

It is intentionally separate from feature and behavior plans. Feature plans answer "what the bot must do." This document answers "where each responsibility must live so the codebase stays clean while we implement those features."

The goal is not folder cosmetics. The goal is to enforce clean ownership boundaries:

- reusable framework logic must not depend on game-specific concepts,
- P&C domain logic must own game-specific meaning,
- automation must orchestrate use cases instead of owning lower-level semantics,
- authored inputs must stay distinct from runtime domain persistence even when both use YAML.

## 2. Architectural Intent

The first split must be by ownership of rules, not by file format and not by technical vibe:

- `core/` owns framework-like logic that could exist without Puzzles & Conquest,
- `app/` owns Puzzles & Conquest-specific business logic, authored automation content, and application orchestration.

This plan therefore replaces the current mixed top-level layout with two explicit layers:

- `core`: infrastructure, generic vision, generic text helpers, generic errors,
- `app`: P&C domain semantics, P&C screenshot interpretation, P&C navigation, authored YAML, and automation workflows.

## 3. Target Top-Level Tree

```text
pnc_automation/
  core/
    errors.py
    text/
      normalization.py
    infra/
      adb/
      emulator/
      capture/
      storage/
      diagnostics/
    vision/
      image/
      ocr/
      template/
  app/
    authoring/
      config/
      scripts/
    pnc/
      enums/
      domain/
      vision/
      navigation/
      persistence/
    automation/
      engine/
      tasks/
    entrypoints/
```

This tree is the target architecture. It does not require one unsafe commit. It must be reached incrementally with compatibility wrappers and import migration.

## 4. Package Responsibilities

### 4.1 `core/`

`core/` owns code that should remain valid without any P&C screen names, selector ids, mailbox types, or castle semantics.

#### `core/errors.py`

Owns shared typed error definitions used across the platform.

#### `core/text/`

Owns generic text normalization helpers that are not P&C-specific.

#### `core/infra/`

Owns external I/O and platform access:

- process execution,
- ADB,
- emulator transport/session control,
- screenshot acquisition,
- generic artifact persistence,
- diagnostics/logging utilities.

#### `core/vision/`

Owns generic image/OCR/geometry/template logic only.

It must not know:

- `ScreenType`,
- `UiElementId`,
- `MailboxType`,
- `ChatChannel`,
- castle identity,
- P&C observation semantics.

### 4.2 `app/`

`app/` owns game-specific meaning plus the application behavior built on top of `core/`.

#### `app/authoring/`

Owns user-authored application inputs:

- runtime configuration,
- authored automation scripts.

`config` and `scripts` remain separate modules because they describe different concepts, but they share one parent because they are both authored inputs to the application.

#### `app/pnc/enums/`

Owns all P&C enum definitions.

#### `app/pnc/domain/`

Owns P&C business concepts:

- chat and mail models,
- observation model and typed screen facts,
- building catalog and policies,
- action request language,
- other P&C-specific shared data contracts.

#### `app/pnc/vision/`

Owns all P&C-specific screenshot interpretation built on top of generic vision primitives:

- screen classification,
- selector registry semantics,
- observation building,
- OCR enrichment,
- selector discovery/validation,
- P&C-specific text anchors,
- P&C-specific spatial surface inference.

#### `app/pnc/navigation/`

Owns reusable P&C navigation and movement services:

- screen flow planning,
- spatial navigation,
- world map indexing and route helpers.

These are not generic framework utilities. They are game-specific application services.

#### `app/pnc/persistence/`

Owns P&C-specific durable state and archive layout:

- chat archive store,
- mail archive store,
- chat transcript cleanup,
- castle roster cache persistence,
- P&C-specific artifact naming/layout helpers.

#### `app/automation/`

Owns high-level application orchestration:

- runner,
- task engine,
- action execution loop,
- task contracts,
- concrete automation tasks.

`automation` is an application layer, not a generic framework layer.

#### `app/entrypoints/`

Owns the composition root and external entrypoints:

- CLI,
- API facade,
- application wiring/bootstrap.

## 5. Dependency Rules

These rules are the non-negotiable architecture contract.

### 5.1 Core boundary

- `core/*` must not import from `app/*`.

### 5.2 Generic vision boundary

- `core/vision/*` must not import from `app/pnc/*`.
- `core/vision/*` must not import P&C enums or P&C observation types.

### 5.3 P&C boundary

- `app/pnc/*` may depend on `core/*`.
- `app/pnc/*` must not import from `app/automation/*`.

### 5.4 Automation boundary

- `app/automation/*` may depend on `app/pnc/*` and `core/*`.
- `app/automation/*` owns use-case orchestration, not P&C meaning.

### 5.5 Authoring boundary

- `app/authoring/config/*` and `app/authoring/scripts/*` stay separate.
- shared YAML parsing helpers may be extracted, but authored config and authored scripts must not be collapsed into one concept.

### 5.6 Persistence boundary

- generic byte/file persistence belongs in `core/infra/storage/*`,
- P&C-specific archive layout and roster cache semantics belong in `app/pnc/persistence/*`.

## 6. Current Coupling Assessment

### 6.1 Healthy coupling

The current `automation -> pnc` dependency direction is broadly correct.

`automation` should depend on P&C domain/application services because automation is orchestrating game-specific use cases. `pnc` should not depend on `automation`.

That means the existence of imports from `automation` into `pnc` types is not itself the problem.

### 6.2 Actual bad coupling

The real architecture leak is that generic-looking low-level packages currently contain P&C business semantics.

Examples:

- current `vision` contains P&C screen semantics and selector semantics,
- current `capture` contains both generic screenshot acquisition and P&C archive behavior,
- current `config` contains both authored config loading and a P&C roster cache store.

Those are the boundaries that must be corrected first.

## 7. File Move Map

This section defines the intended target home for the current modules.

### 7.1 Current top-level modules

- `pnc_automation/errors.py` -> `pnc_automation/core/errors.py`
- `pnc_automation/text_normalization.py` -> `pnc_automation/core/text/normalization.py`
- `pnc_automation/artifact_naming.py` -> `pnc_automation/app/pnc/persistence/artifact_naming.py`
- `pnc_automation/api.py` -> `pnc_automation/app/entrypoints/api.py`
- `pnc_automation/app.py` -> `pnc_automation/app/entrypoints/app.py`
- `pnc_automation/cli.py` -> `pnc_automation/app/entrypoints/cli.py`

### 7.2 ADB and emulator

- `pnc_automation/adb/*` -> `pnc_automation/core/infra/adb/*`
- `pnc_automation/emulator/*` -> `pnc_automation/core/infra/emulator/*`

These belong together under one infrastructure parent because emulator session control is built on top of ADB transport.

### 7.3 Capture and storage

- `pnc_automation/capture/screenshot_service.py` -> `pnc_automation/core/infra/capture/screenshot_service.py`
- `pnc_automation/capture/artifact_store.py` -> `pnc_automation/core/infra/storage/artifact_store.py`
- `pnc_automation/capture/chat_archive_store.py` -> `pnc_automation/app/pnc/persistence/chat_archive_store.py`
- `pnc_automation/capture/mail_archive_store.py` -> `pnc_automation/app/pnc/persistence/mail_archive_store.py`
- `pnc_automation/capture/chat_transcript_cleanup.py` -> `pnc_automation/app/pnc/persistence/chat_transcript_cleanup.py`

### 7.4 Diagnostics

- `pnc_automation/diagnostics/*` -> `pnc_automation/core/infra/diagnostics/*`

### 7.5 Generic vision

The following modules should remain or become generic vision:

- `pnc_automation/vision/ocr_service.py` -> `pnc_automation/core/vision/ocr/ocr_service.py`
- `pnc_automation/vision/ocr_lines.py` -> `pnc_automation/core/vision/ocr/ocr_lines.py`
- `pnc_automation/vision/template_matcher.py` -> `pnc_automation/core/vision/template/template_matcher.py`

`pnc_automation/vision/image_models.py` must be split:

- generic `TemplateMatch` -> `pnc_automation/core/vision/image/models.py`
- P&C-specific `SelectorMatch` -> `pnc_automation/app/pnc/vision/image_models.py`

### 7.6 P&C-specific vision

These current `vision` modules are not actually generic and must move under P&C:

- `pnc_automation/vision/observation_builder.py` -> `pnc_automation/app/pnc/vision/observation_builder.py`
- `pnc_automation/vision/observation_request.py` -> `pnc_automation/app/pnc/vision/observation_request.py`
- `pnc_automation/vision/screen_classifier.py` -> `pnc_automation/app/pnc/vision/screen_classifier.py`
- `pnc_automation/vision/pnc_observation_enricher.py` -> `pnc_automation/app/pnc/vision/pnc_observation_enricher.py`
- `pnc_automation/vision/pnc_ocr_capabilities.py` -> `pnc_automation/app/pnc/vision/pnc_ocr_capabilities.py`
- `pnc_automation/vision/spatial_surfaces.py` -> `pnc_automation/app/pnc/vision/spatial_surfaces.py`
- `pnc_automation/vision/text_anchors.py` -> `pnc_automation/app/pnc/vision/text_anchors.py`
- `pnc_automation/vision/selectors.py` -> `pnc_automation/app/pnc/vision/selectors.py`
- `pnc_automation/vision/selector_catalog.py` -> `pnc_automation/app/pnc/vision/selector_catalog.py`
- `pnc_automation/vision/selector_discovery.py` -> `pnc_automation/app/pnc/vision/selector_discovery.py`
- `pnc_automation/vision/selector_registry_updater.py` -> `pnc_automation/app/pnc/vision/selector_registry_updater.py`
- `pnc_automation/vision/selector_interactions.py` -> `pnc_automation/app/pnc/vision/selector_interactions.py`
- `pnc_automation/vision/selector_interaction_kind.py` -> `pnc_automation/app/pnc/vision/selector_interaction_kind.py`
- `pnc_automation/vision/navigation_selector_validator.py` -> `pnc_automation/app/pnc/vision/navigation_selector_validator.py`

### 7.7 Authored inputs

These modules belong under one shared authoring parent:

- `pnc_automation/config/loader.py` -> `pnc_automation/app/authoring/config/loader.py`
- `pnc_automation/config/models.py` -> `pnc_automation/app/authoring/config/models.py`
- `pnc_automation/config/validation.py` -> `pnc_automation/app/authoring/config/validation.py`
- `pnc_automation/config/yaml_helpers.py` -> `pnc_automation/app/authoring/config/yaml_helpers.py`
- `pnc_automation/scripts/loader.py` -> `pnc_automation/app/authoring/scripts/loader.py`
- `pnc_automation/scripts/models.py` -> `pnc_automation/app/authoring/scripts/models.py`
- `pnc_automation/scripts/registry.py` -> `pnc_automation/app/authoring/scripts/registry.py`

`pnc_automation/config/castle_roster_store.py` does not belong here long term because it is runtime P&C persistence, not authored config.

It should move to:

- `pnc_automation/app/pnc/persistence/castle_roster_store.py`

### 7.8 P&C domain

The current `pnc` package should be separated by responsibility under `app/pnc/`.

#### Enums

- `pnc_automation/pnc/enums/*` -> `pnc_automation/app/pnc/enums/*`

#### Domain models and services

- `pnc_automation/pnc/chat.py` -> `pnc_automation/app/pnc/domain/chat.py`
- `pnc_automation/pnc/mail.py` -> `pnc_automation/app/pnc/domain/mail.py`
- `pnc_automation/pnc/observation.py` -> `pnc_automation/app/pnc/domain/observation.py`
- `pnc_automation/pnc/action_requests.py` -> `pnc_automation/app/pnc/domain/action_requests.py`
- `pnc_automation/pnc/building_catalog.py` -> `pnc_automation/app/pnc/domain/building_catalog.py`
- `pnc_automation/pnc/building_priority_input.py` -> `pnc_automation/app/pnc/domain/building_priority_input.py`
- `pnc_automation/pnc/policy_models.py` -> `pnc_automation/app/pnc/domain/policy_models.py`
- compatibility wrappers such as `screen_type.py` and `ui_element_id.py` eventually collapse into the canonical `app/pnc/enums/*` package

### 7.9 P&C navigation

These are game-specific navigation services, not low-level framework utilities:

- `pnc_automation/pnc/screen_flows.py` -> `pnc_automation/app/pnc/navigation/screen_flows.py`
- `pnc_automation/pnc/spatial_navigation.py` -> `pnc_automation/app/pnc/navigation/spatial_navigation.py`
- `pnc_automation/pnc/world_map_index.py` -> `pnc_automation/app/pnc/navigation/world_map_index.py`

### 7.10 Automation engine and tasks

- `pnc_automation/automation/runner.py` -> `pnc_automation/app/automation/engine/runner.py`
- `pnc_automation/automation/script_runner.py` -> `pnc_automation/app/automation/engine/script_runner.py`
- `pnc_automation/automation/action_executor.py` -> `pnc_automation/app/automation/engine/action_executor.py`
- `pnc_automation/automation/observed_action_executor.py` -> `pnc_automation/app/automation/engine/observed_action_executor.py`
- `pnc_automation/automation/task.py` -> `pnc_automation/app/automation/engine/task.py`
- `pnc_automation/automation/task_context.py` -> `pnc_automation/app/automation/engine/task_context.py`
- `pnc_automation/automation/observation_mode.py` -> `pnc_automation/app/automation/engine/observation_mode.py`
- `pnc_automation/automation/tasks/*` -> `pnc_automation/app/automation/tasks/*`

## 8. Implementation Strategy

This refactor must be incremental and dependency-ordered.

### Phase 1: Create the target package tree

- add the new directories,
- add package `__init__.py` files,
- keep current modules working through compatibility wrappers,
- do not rewrite all imports in one commit.

### Phase 2: Move obviously generic framework code into `core/`

Start with:

- `errors.py`,
- text normalization,
- ADB,
- emulator,
- screenshot capture,
- generic artifact store,
- diagnostics.

These moves should not require P&C behavior changes.

### Phase 3: Split generic vision from P&C vision

This is the most important architecture correction.

Rules for this phase:

- anything importing `ScreenType`, `UiElementId`, `MailboxType`, `ChatChannel`, or P&C observation types cannot remain in generic `core/vision`,
- move all P&C-aware vision code under `app/pnc/vision/`,
- split mixed files like `image_models.py` into generic and P&C-specific halves.

### Phase 4: Introduce the shared `authoring/` parent

- move authored config modules under `app/authoring/config/`,
- move authored script modules under `app/authoring/scripts/`,
- keep shared YAML helpers only where the concept remains truly shared,
- move the roster cache store out of authored config into P&C persistence.

### Phase 5: Separate P&C domain, navigation, and persistence

- move P&C business models under `app/pnc/domain/`,
- move screen/spatial navigation under `app/pnc/navigation/`,
- move archive and roster persistence under `app/pnc/persistence/`.

### Phase 6: Move automation under `app/automation/`

- move the runner, executors, and task contracts into `app/automation/engine/`,
- move concrete use cases into `app/automation/tasks/`,
- keep `automation` dependent on `app/pnc/*`, not the reverse.

### Phase 7: Move entrypoints and remove wrappers

- move CLI/API/app composition into `app/entrypoints/`,
- once imports are fully migrated and tests are green, remove compatibility wrappers,
- remove any obsolete parallel import paths.

## 9. Refactor Rules

During implementation:

- do not do a big-bang rename of the whole tree,
- do not keep two canonical homes for one concept,
- do not move a file without also stating which layer owns it,
- do not leave generic packages importing P&C semantics,
- do not merge authored config with runtime P&C persistence,
- prefer adding compatibility shims first, then collapsing them after import migration,
- delete obsolete wrapper modules once the migration is complete.

## 10. Acceptance Criteria

This architecture work is done only when all of the following are true:

- there is a single agreed package tree matching this plan,
- `core/*` imports no `app/*` modules,
- `core/vision/*` imports no P&C business types,
- `app/pnc/*` imports no `app/automation/*`,
- `config` and `scripts` live under one shared authoring parent but remain distinct modules,
- P&C-specific archives and roster caches no longer live in generic `capture` or authored `config`,
- the old module paths are either removed or reduced to clearly temporary wrappers with a removal plan,
- tests pass after import migration and no duplicate parallel APIs remain.

## 11. Immediate Execution Source of Truth

If we begin implementation now, the first concrete execution order must be:

1. create `core/` and `app/` package roots,
2. move `errors`, text, ADB, emulator, screenshot capture, and generic artifact storage into `core/`,
3. move P&C-aware `vision` modules into `app/pnc/vision/`,
4. split `image_models.py` into generic and P&C-specific models,
5. create `app/authoring/` and move authored config/scripts under it,
6. move `screen_flows.py`, `spatial_navigation.py`, and `world_map_index.py` into `app/pnc/navigation/`,
7. move chat/mail archives, roster store, and artifact naming into `app/pnc/persistence/`,
8. move the automation runner and tasks into `app/automation/`,
9. migrate imports and remove compatibility wrappers once stable.

That order is the canonical migration sequence for the package architecture refactor.
