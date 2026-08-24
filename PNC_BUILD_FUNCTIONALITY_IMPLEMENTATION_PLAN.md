# PNC Build Functionality Implementation Plan

## Context

The repository has a mature home-city navigation and building-upgrade path, but `build` currently means `upgrade an already-owned building`. The direct `build` CLI command and authored `building_upgrade` task both route to `BuildingUpgradeTask`; construction from an empty fixed, large, or small slot is not executable yet.

The historical [PNC_BUILDING_ACTIONS_SUBPLAN.md](abandonned/PNC_BUILDING_ACTIONS_SUBPLAN.md) is useful inventory, but is explicitly abandoned and must not be revived without revalidation. This plan is intentionally narrower: finish construction and preserve the existing upgrade behavior. Training, research, crafting, territory attacks, and other building-owned actions remain separate follow-up work.

## Goals

- Construct one explicitly requested building from an already available home-city slot.
- Support the three existing construction families: dedicated fixed slots, the flexible large slot, and unlocked repeatable small slots.
- Reuse the canonical home-city catalog, atlas navigation, observation service, selector registry, task runner, and artifact policy.
- Verify that construction actually started, distinguish a busy builder from an unmet prerequisite, and never spend speedups or premium currency implicitly.
- Treat the resource popup as an insufficient-resources result only; a sufficient-resources construction path must not wait for or require that popup.
- Expose the behavior through authored YAML, the Python API, and a clear direct CLI entry point.
- Add deterministic regression coverage for all state transitions and a bounded live validation path for the final construction selector/postcondition.

## Non-Goals

- Automatically unlocking the territory below the Wall. A locked territory must produce a clear blocked result until an explicit territory-unlock workflow is designed.
- Speeding up construction, spending diamonds, requesting alliance help, or collecting a finished build.
- Training troops, crafting traps, repairing the Wall, Glory, research, or other building actions listed in the abandoned inventory.
- Replacing the existing `open_building` read-only task.
- Guessing final construction controls from screenshots or using raw coordinates when a selector or spatial object abstraction can be used.

## Current State

The relevant ownership boundaries are already present:

- [building_catalog.py](../pnc_automation/app/pnc/domain/building_catalog.py) defines exact building ids, slot roles, supported actions, primary screens, and build-menu option selectors. It does not yet define the source slot for each constructable building, and construction actions are incomplete in the action vocabulary.
- [spatial_surfaces.py](../pnc_automation/app/pnc/vision/spatial_surfaces.py) recognizes labeled buildings and generic `BUILD`/`EMPTY` home-city objects. Live small plots can appear as unlabeled circular foundations: four were visible while the spatial surface reported zero empty slots, so both detection and slot-family metadata are incomplete.
- [spatial_navigation.py](../pnc_automation/app/pnc/navigation/spatial_navigation.py) and [screen_flows.py](../pnc_automation/app/pnc/navigation/screen_flows.py) can tap a visible empty slot, but there is no target-building-to-slot resolution or construction-specific route.
- [building_upgrade_task.py](../pnc_automation/app/automation/tasks/building_upgrade_task.py) owns a detailed, tested upgrade state machine, including builder-busy detection, requirement panels, confirmation, queue fallback, and level/timer verification. Its reusable predicates should be extracted before construction adds a second copy.
- [pnc_observation_enricher.py](../pnc_automation/app/pnc/vision/pnc_observation_enricher.py) and `selector_registry.yaml` recognize the three `Build` menu screen families and building option rows. They have no confirmed final `Build`/`Construct` action selector, construction confirmation state, or construction-specific queue identity. The live Build Queue is also currently rejected because its centered header falls below the parser's top-18% header window.
- [open_building_task.py](../pnc_automation/app/automation/tasks/open_building_task.py) intentionally accepts only owned buildings and repeatable building ids; it cannot target reserved or flexible source slots.
- [registry.py](../pnc_automation/app/authoring/scripts/registry.py), [task.py](../pnc_automation/app/automation/engine/task.py), [api.py](../pnc_automation/app/entrypoints/api.py), and [cli.py](../pnc_automation/app/entrypoints/cli.py) register and expose upgrades, but no construction task.
- Existing build-batch files under `scripts/manual/build_batches/` are upgrade-priority files, not construction plans.

Baseline evidence: the focused build/task/vision tests pass (`314` tests, `1` skipped), and the full offline suite passes (`786` tests, `15` skipped). The resumed planning pass reran the two highest-value vision/task modules (`297` tests, `1` skipped). No construction transition was attempted; the final construction control and post-start proof remain unknown.

## Live Evidence Disposition

The bounded read-only inspection used configured account and BlueStacks display name `testing`, accepting whichever castle was already active. The instance was already running from the preceding inspection. Lord Info identified the active castle as `K287e40c0a989`; no account or castle switch was performed. The resumed pass used two transitions: Back to Home City, then the observed Home City Build shortcut. It stopped when the resulting Build Queue overlay was classified as `unknown`.

| Evidence question | Disposition | Evidence and planning consequence |
| --- | --- | --- |
| Can the configured emulator and active castle be observed through canonical runtime services? | `live_observed` | `20260821T221055Z_build_plan_resume_baseline.png` was classified `pnc_lord_info` and exposed active-castle name `K287e40c0a989`. Back navigation produced `20260821T221101Z_build_plan_resume_root_post_action_1.png`, classified `pnc_home_city`. |
| Does Home City expose the Build shortcut and an idle builder? | `live_observed` | Home City exposed `PNC_HOME_BUILD_BUTTON` with visible text `Build (0/1)`. Tapping it opened a Build Queue overlay showing `1st Build Queue — Idle` and a locked/inactive second queue. The second queue's `Activate` control is a forbidden mutation/monetization boundary. |
| Are visible empty small plots represented by the current spatial surface? | `live_blocked` | `20260821T221120Z_build_plan_resume_home_surface.png` visibly contains multiple circular empty plots, but the typed spatial surface returned two Infirmary buildings and zero `HOME_EMPTY_SLOT` objects. The current OCR-only `BUILD`/`EMPTY` rule cannot address unlabeled live plots safely. |
| Is the live Build Queue overlay classified by the current OCR contract? | `live_blocked` | `20260821T221156Z_build_plan_resume_queue_post_action_1_runtime_retry.png` visibly shows Build Queue, but runtime classification remained `unknown`. OCR found `Build Queue` at Y=428 on a 1600-pixel image; `_build_build_queue_additions()` currently limits the header to the top 18% (Y<=288), so the centered overlay is rejected. |
| What are the fixed, large, and small slot menu transitions and option labels? | `live_blocked` | The visible small plots could not be selected through a typed spatial object, and the Build Queue classifier failure triggered the mandatory stop condition before safe-root recovery. Fixed/large menu evidence remains unknown. |
| Is the resource popup part of every construction transition? | `artifact_answered` | User-provided behavior establishes that it appears only when resources are insufficient. Its absence is therefore expected on the sufficient-resources path and cannot be used as a required confirmation. |
| What final control starts construction, and what proves success? | `mutation_boundary` | Read-only planning authorization does not permit option selection, construction, second-queue activation, resource spending, or post-start mutation. These controls require a later explicitly authorized smoke test after deterministic recognition is implemented. |

No construction, queue activation, resource spending, raw-coordinate tap, account switch, or castle switch occurred. The live defect screenshots and OCR sidecar under `artifacts/2026-08-21/testing/` should seed deterministic regression fixtures before another live attempt.

## Target Design

### Canonical task and policy

Add a distinct `TaskId.BUILDING_CONSTRUCT` and `BuildingConstructionTask`. Keep `BuildingUpgradeTask` as the canonical upgrade implementation: construction and upgrade have different target discovery and different success proofs, so merging them prematurely would make “success” ambiguous. Both tasks should consume shared building workflow helpers extracted from the upgrade task rather than duplicate queue, home-city, and transient-state predicates.

Add a strict `BuildingConstructionPolicy` with:

- `building: HomeCityObjectId`, required and restricted to constructable building ids;
- optional explicit slot-family/instance metadata only if live evidence proves it is necessary;
- no implicit speedup or premium action flags;
- fail-fast validation for non-constructable ids, linked screens, reserved slots passed as buildings, and unsupported parameters.

The canonical target remains the intended building, not a generic “empty slot.” The catalog resolves that building to its legal source family:

| Target family | Source object | Menu | Initial behavior |
| --- | --- | --- | --- |
| Institute, Warehouse, Trap Workshop, Goddess Statue | dedicated reserved slot | fixed `Build` menu | choose the target’s exact option |
| Alliance Hall, Blacksmith, Market | flexible large slot | large `Build` menu | choose the target’s exact option |
| Farm, Lumber Camp, Moon Well, Recruiting Center, Infirmary, Iron Mine, Gold Mine | an unlocked small slot | small `Build` menu | choose any eligible visible small slot, then the exact option |

### Catalog and spatial metadata

Extend `HomeCityObjectDefinition` with canonical construction-source metadata and add catalog helpers such as `construction_source_for_building()` and `constructable_home_city_object_ids()`. Keep exact building ids and family grouping; do not collapse all empty plots into one type.

Extend empty-slot observation metadata with a slot family/source id and, where required, an atlas coordinate or stable geometry classification. Fixed and large slots should be deterministic. Detect small slots from stable plot geometry/atlas placement as well as explicit `BUILD`/`EMPTY` OCR; the live evidence proves text cannot be required. Small slots may remain instance-less and be selected from the currently visible set only when exactly one eligible typed candidate is resolved. Add import-time/catalog validation that every constructable building has exactly one legal source family and menu option.

### Shared construction flow

The construction task should follow one observed state machine:

1. Ensure the requested account/castle is in Home City.
2. If the builder is already occupied, return `SKIPPED` with the observed timer/queue reason.
3. Find or focus the correct source slot using the existing atlas/spatial navigator.
4. Open the slot and require the expected `Build` menu family.
5. Tap the target-specific option selector only when that option is observed.
6. Require the live-confirmed construction control; treat this action as potentially starting construction immediately and execute it only in an explicitly authorized run. Do not infer a harmless confirmation step from the option-row tap.
7. Branch on the immediate post-action observation:
   - if target-specific queue/timer/foundation evidence appears, continue success verification without waiting for a popup;
   - if the resource popup appears, classify the result as insufficient resources, capture the typed deficits when possible, and return blocked without buying, opening, or spending resources;
   - if a prerequisite or locked-territory panel appears, return the corresponding structured blocked result; or
   - if the result is unknown or unverifiable, fail without retrying the construction action.
8. Verify construction start with one canonical proof selected during live discovery: preferably a target-specific active build-queue row, otherwise a home-city timer plus target foundation/identity evidence.
9. Return success only after the proof is observed. The resource popup is never a success prerequisite and its absence is not an error.

All transitions should use `ActionRequest` with `observe_after=True` and narrow `ObservationRequest` follow-ups. No blind retry of a construction tap is allowed.

## Implementation Phases

### Phase 1 — Convert the observed live gaps into deterministic contracts

Files/components: `config/`, canonical runtime helpers, `artifacts/`, selector-discovery tooling.

The emulator launch, active-castle identity, Home City classification, Build shortcut, idle first queue, inactive second queue, unlabeled small plots, and centered Build Queue layout are observed. Before another live run, preserve safe screenshot/OCR fixtures for the two concrete gaps and make them pass offline. Future inspection may use whichever castle is already active on `testing`; do not switch castles. Then use only safe read-only navigation to available fixed/large/small Build menus and stop before any option or final construction control that could mutate state. Record:

- how each slot family is reached and classified;
- the exact option-row and final construction labels;
- whether an intermediate building-details or non-resource confirmation screen exists;
- busy-builder, insufficient-resource popup, locked-territory, and queue-row text;
- the strongest post-start proof.

Acceptance: the centered idle Build Queue classifies as `PNC_BUILD_QUEUE`; visible unlabeled small plots become typed `HOME_EMPTY_SLOT` objects without misclassifying ordinary terrain; every required selector/control is marked `live_observed`, `artifact_answered`, `live_blocked`, `mutation_boundary`, or explicitly `unknown`; and no plan decision relies on an unlabeled coordinate.

### Phase 2 — Complete the canonical model

Files: `building_catalog.py`, `observation.py`, `spatial_surfaces.py`, `spatial_navigation.py`, `screen_flows.py`, relevant enum files.

- Add construction capability/source metadata and legal mappings.
- Classify empty slots into fixed, large, and small source families using observed stable evidence.
- Add queries and navigator helpers for source slots, including visible-small-slot selection.
- Keep `open_building` behavior unchanged for owned buildings and build-menu inspection.
- Add fail-fast validation for inconsistent catalog mappings and unsupported construction targets.

Acceptance: unit tests prove every supported target resolves to exactly one source family/menu/option; generic `BUILD`/`EMPTY` labels alone cannot select a semantically different slot.

### Phase 3 — Add observation and selector contracts

Files: `screen_type.py`, `ui_element_id.py`, `selector_registry.yaml`, `pnc_observation_enricher.py`, `observation_request.py`, `pnc_ocr_capabilities.py`.

- Add only the final construction screen/control ids justified by Phase 1 evidence.
- Add distinct insufficient-resource popup, non-resource confirmation, busy, and queue-row evidence where needed; do not model the resource popup as a mandatory construction screen.
- Expand Build Queue header geometry to cover the observed centered overlay, while requiring queue-row support text so generic modal headers cannot produce false positives.
- Add focused follow-up requests for build menus and post-construction verification.
- Update selector-registry status and run the repository selector validator.

Acceptance: saved deterministic images/OCR fixtures classify each build menu and final construction state without broadening unrelated screen families; ambiguous or missing controls remain non-actionable.

### Phase 4 — Implement the task and refactor shared ownership

Files: new `building_construction_task.py`, `building_upgrade_task.py`, shared task support module, `task.py`, `registry.py`.

- Extract common home-city/build-queue/requirement/settling helpers from `BuildingUpgradeTask` into one canonical support module.
- Implement `BuildingConstructionTask` with bounded replan budget, explicit runtime state, idempotent option selection, and the state machine in Target Design.
- Register the task and ensure task results distinguish `SUCCESS`, `SKIPPED` (builder busy), and retryable/final failure (blocked or unverifiable).
- Audit the existing `allow_speedups` parameter: either implement an explicitly tested supported behavior or reject it clearly; it must not remain silently ignored.

Acceptance: construction cannot start without an observed source slot, menu option, and authorized construction control; an active queue cannot be double-started; the sufficient-resources path verifies direct start without requiring a popup; the insufficient-resources popup returns blocked without spending; and failed verification never reports success.

### Phase 5 — Expose and document the feature

Files: `api.py`, `cli.py`, `scripts/README.md`, `scripts/manual/`, routine examples.

- Add bound and unbound Python API methods for construction.
- Add a clear direct CLI path, preferably `construct --building <id>`, while keeping `build`’s current upgrade meaning explicit in help text.
- Add one minimal authored YAML example and one construction target example per slot family; do not create one wrapper script per building.
- Document that construction does not unlock territory, speed up, spend premium currency, or collect finished output.

Acceptance: CLI/YAML/API all produce the same typed policy and reject invalid target/parameter combinations before runtime actions.

### Phase 6 — Deterministic and live validation

Files: `tests/test_flows_and_tasks.py`, new construction-focused tests if appropriate, `tests/data/`, live smoke module, `tools/` only if a helper is necessary.

Offline coverage must include:

- policy parsing and catalog mapping for all construction families;
- visible-slot selection and atlas focusing;
- every menu option mapping;
- builder-busy skip;
- locked territory and unmet requirements;
- sufficient-resources direct start with no resource popup;
- insufficient-resources popup parsing and a no-purchase/no-spend result;
- any non-resource confirmation and transient `UNKNOWN` recovery;
- queue/timer/foundation success proofs;
- duplicate/repeated small-slot handling;
- centered idle/inactive Build Queue classification and false-positive rejection;
- CLI/API/script registry integration;
- regression coverage proving existing upgrade tests still pass.

Then run the narrowest opt-in live smoke against a configured target. A live construction smoke is state-changing and requires explicit authorization before execution; without that authorization, run only read-only selector/navigation validation and report the construction command that remains.

## Data, Config, and Migration Notes

- Do not modify real account, castle, or secret-bearing config files. Only update examples and authored scripts if needed.
- Existing `building_upgrade` scripts and build-priority files remain upgrade inputs. Construction gets an exact `building` parameter; it must not reuse an ordered upgrade-priority file.
- Prefer committed deterministic fixtures derived from safe captured observations. Do not commit credentials, live account identifiers, or unnecessary screenshots.
- If live evidence reveals a different final action or queue shape, update the typed contract and fixture together; do not add a permissive fallback parser.

## Validation Plan

1. `py -m unittest tests.test_flows_and_tasks tests.test_script_loader tests.test_script_runner tests.test_capture_and_vision`
2. New construction-focused targeted tests.
3. `py -m unittest discover -s tests`
4. `py tools/validate_navigation_selectors.py` and any selector-registry validator required by changed selectors.
5. Read-only live selector/navigation validation using the configured runtime.
6. Authorized construction smoke only after the user confirms the target and accepts the state change.

Completion requires a recorded artifact path for each live boundary exercised and a clear statement of any live step skipped because authorization or a configured target was unavailable.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Empty slots look identical in OCR | Use catalog geometry/atlas metadata and observed slot-family evidence; refuse ambiguous targets. |
| Live empty plots have no OCR label | Add deterministic geometry/atlas-backed detection, require an unambiguous typed candidate, and retain OCR as supporting evidence rather than a prerequisite. |
| Centered Build Queue is classified `UNKNOWN` | Expand the header search region with queue-row support requirements and add the captured layout as a regression fixture. |
| The option-row tap starts construction immediately on some versions | Treat the next observation as authoritative and make the final action conditional; never blindly tap twice. |
| Builder queue is occupied or changes while planning | Re-observe immediately before the final action and verify target identity in the queue/timer. |
| Construction finishes too quickly for a timer proof | Use the target-specific queue row or before/after foundation/building evidence selected during Phase 1. |
| Requirement text varies by building/progression | Model typed requirement evidence conservatively and return blocked, not success, when it cannot be parsed. |
| Code waits for a resource popup on the success path | Model direct start as the normal sufficient-resources branch and treat the popup only as insufficient-resource evidence. |
| Seasonal art or camera layout changes | Keep recognition label/metadata/atlas-based and avoid raw art templates or fixed coordinates. |
| Existing upgrade behavior regresses during extraction | Preserve all current upgrade tests, add shared-helper contract tests, then run the full offline suite before live validation. |
| Live smoke mutates the game unexpectedly | Keep planning/read-only evidence bounded; require explicit authorization for final construction clicks and preserve pre/post artifacts. |

## Open Questions

- What exact control starts construction, and is there any separate non-resource confirmation panel?
- Does the newly constructed building appear immediately as a foundation, or only in the build queue until completion?
- Can a construction target be selected from any visible small slot, or does the game bind the target to a particular slot instance?
- What exact OCR evidence identifies a construction queue row without confusing an upgrade row?
- Which stable geometry or atlas anchors distinguish an empty small plot from decorative circular terrain and from fixed/large source slots?
- Should territory unlock become a separate task later, or remain an explicit prerequisite outside construction?

## Execution Checklist

- [x] Prove canonical emulator launch, popup handling, Home City classification, Build-shortcut visibility, and Lord Info identity navigation.
- [x] Capture the active castle's idle/inactive Build Queue layout and visible unlabeled small plots.
- [ ] Add deterministic fixtures for the centered Build Queue and unlabeled small plots before resuming live navigation.
- [ ] Capture bounded read-only Build-menu evidence for one safely typed source slot of each family on any active `testing` castle.
- [ ] Add and validate canonical source-slot mappings and empty-slot metadata.
- [ ] Add evidence-backed construction selectors and observation follow-ups.
- [ ] Implement and test direct-start and insufficient-resource popup branches without purchasing or spending resources.
- [ ] Extract shared building workflow predicates without changing upgrade semantics.
- [ ] Implement/register/test `BuildingConstructionTask`.
- [ ] Add API, CLI, YAML examples, and documentation.
- [ ] Add deterministic fixtures and targeted regressions.
- [ ] Run selector validation and the full offline suite.
- [ ] Obtain explicit authorization before any state-changing live construction smoke.
- [ ] Record final artifacts, skipped live commands, and remaining unknowns.
