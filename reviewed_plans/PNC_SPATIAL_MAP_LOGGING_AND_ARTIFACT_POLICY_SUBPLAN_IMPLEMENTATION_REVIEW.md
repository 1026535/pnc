# Spatial Map Logging / Artifact Policy Implementation Review

Reviewed commit: `576148d47a808a0a82ce0db99a527f0a6a26b362` (`Implement shared observation artifact policy`)

## Overall

The commit adds the core building blocks cleanly:

- shared artifact-kind selection,
- a world-map survey snapshot export,
- a dedicated survey debug store,
- a survey recorder/checkpoint owner,
- focused unit coverage for the new policy surface.

The main problem is that the new world-map survey path is still isolated from the actual runtime. The result is a good internal design slice that is not yet fully wired into production behavior.

## Findings

### 1. High: the world-map survey recorder/store are not wired into any production flow

Relevant code:

- `pnc_automation/app/pnc/navigation/world_map_survey_recorder.py:49`
- `pnc_automation/app/pnc/persistence/world_map_survey_debug_store.py:21`
- `pnc_automation/app/entrypoints/app.py:102`
- `pnc_automation/app/automation/engine/script_runner.py:241`

Problem:

- The new `WorldMapSurveyRecorder` and `WorldMapSurveyDebugStore` are defined, but the runtime composition root still only builds `ArtifactStore -> ScreenshotService -> ObservationService`.
- Repository search shows no production instantiation or use of `WorldMapSurveyRecorder` or `WorldMapSurveyDebugStore`; they are exercised only by tests.
- That means the new `WORLD_MAP_SURVEY_STATE` path is not reachable from the real world-map workflow yet, so no survey JSON dumps will be emitted during normal execution.

Why this matters:

- This is the main behavior promised by the plan.
- The ownership split is designed correctly, but today it exists only as unused infrastructure.

Clean fix:

- Identify the real world-map survey/checkpoint owner and instantiate one `WorldMapSurveyRecorder` there for the lifetime of the survey loop.
- Construct `WorldMapSurveyDebugStore` from the existing runtime artifact root in the same composition layer that currently builds `ArtifactStore`.
- Route checkpoint captures and profile-name annotations through the recorder instead of talking to `ObservationService` and `WorldMapSurveyIndex` separately.
- Add one integration-style test that runs the real survey/checkpoint path and asserts that requesting `WORLD_MAP_SURVEY_STATE` produces a JSON artifact under `artifacts/<date>/<artifact_directory>/world_map_surveys/`.

### 2. Medium: artifact-policy ownership is still partially duplicated across layers

Relevant code:

- `pnc_automation/app/runtime/observation_artifacts.py:21`
- `pnc_automation/app/pnc/vision/observation_builder.py:420`
- `pnc_automation/app/pnc/navigation/world_map_survey_recorder.py:67`
- `pnc_automation/app/pnc/navigation/world_map_survey_recorder.py:108`
- `pnc_automation/app/pnc/navigation/world_map_survey_recorder.py:159`

Problem:

- The shared resolver exists, but the policy is still being re-resolved and manually projected in multiple places.
- `WorldMapSurveyRecorder.capture_checkpoint()` resolves the full selection once, then `persist_checkpoint()` resolves it again.
- The recorder also needs a local `_observation_service_artifact_selection()` helper because `ObservationService` can only accept screenshot-owned kinds and otherwise throws.
- This keeps the behavior correct today, but it is not yet one canonical implementation per concept. The caller has to know how to strip unsupported kinds before crossing service boundaries.

Why this matters:

- Adding a third artifact kind or another owner will repeat the same filtering pattern again.
- It makes the boundary easier to misuse: calling `ObservationService` directly with a mixed selection still raises instead of being naturally projected into the right owner-specific subset.

Clean fix:

- Resolve the artifact selection exactly once per checkpoint flow and carry that resolved value through the call chain.
- Replace the ad-hoc `_observation_service_artifact_selection()` projection with one shared owner-projection helper or a small resolved-policy object, for example:
  - `resolved.for_observation_service()`
  - `resolved.for_world_map_survey()`
- Let `persist_checkpoint()` accept the already-resolved selection instead of recomputing it from `request` and `artifact_selection`.
- Keep `ObservationService` fail-fast validation, but have that validation consume the same shared owner-projection helper so the policy shape stays DRY.

### 3. Medium: `FakeObservationService` no longer mirrors production artifact behavior

Relevant code:

- `tests/test_support.py:293`
- `tests/test_support.py:309`
- `tests/test_support.py:327`
- `pnc_automation/app/pnc/vision/observation_builder.py:369`

Problem:

- `FakeObservationService.observe()` discards `artifact_selection`.
- `FakeObservationService.capture_observation()` always resolves artifacts with `mode=ObservationMode.DEBUG`, regardless of the scenario being tested.
- Production `ObservationService` uses its actual runtime mode when resolving artifact defaults.

Why this matters:

- Tests that rely on `FakeObservationService` can now drift from real behavior, especially around `LIGHT` mode and explicit empty selections.
- That weakens confidence in the new shared artifact policy precisely where the commit is trying to tighten semantics.

Clean fix:

- Add `mode: ObservationMode = ObservationMode.DEBUG` to `FakeObservationService`.
- Resolve artifacts with `self.mode`, not a hard-coded debug mode.
- Record the received `artifact_selection` in the fake so tests can assert which policy was requested when needed.
- Add one focused test proving the fake matches production defaults for both `DEBUG` and `LIGHT`.

## Recommended Cleanup Order

1. Wire `WorldMapSurveyRecorder` and `WorldMapSurveyDebugStore` into the real survey/checkpoint runtime path.
2. Refactor artifact-policy projection so the selection is resolved once and reused across owners.
3. Fix `FakeObservationService` so tests keep matching production behavior as the policy evolves.

## Validation

Performed:

- Reviewed the full patch for commit `576148d47a808a0a82ce0db99a527f0a6a26b362`.
- Compared the implementation against `reviewed_plans/PNC_SPATIAL_MAP_LOGGING_AND_ARTIFACT_POLICY_SUBPLAN.md`.
- Ran `py -m unittest tests.test_observation_artifact_policy tests.test_world_map_index` successfully.

Could not run in this environment:

- `dotnet test Tests/CoreTests/CoreTests.csproj` because no .NET SDK was available.
- `Tools/validate-asmdefs.ps1` with `pwsh` because `pwsh` was not installed in this shell environment.
