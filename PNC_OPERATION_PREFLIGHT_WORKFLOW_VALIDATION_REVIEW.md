# Operation Preflight Workflow Validation Review

Review target: `090cf78a207a0abdf74011e6b72c624e9d3e4612` (`Implement operation preflight workflow validation`).

## Findings

### 1. Gathering can continue from non-actionable follow-up screens

Severity: High

Relevant code:
- `pnc_automation/app/automation/tasks/gathering_task.py:52`
- `pnc_automation/app/automation/tasks/gathering_task.py:70`
- `pnc_automation/app/automation/tasks/gathering_task.py:76`
- `pnc_automation/app/pnc/vision/observation_request.py:133`
- `pnc_automation/app/pnc/vision/observation_request.py:144`
- `pnc_automation/app/automation/engine/action_executor.py:189`
- `pnc_automation/app/automation/engine/action_executor.py:325`

`GatheringTask.plan(...)` emits one three-action chain: tap resource node, tap `PNC_GATHER_BUTTON`, tap `PNC_MARCH_CONFIRM_BUTTON`. The new follow-up requests allow intermediate source screens:

- `gather_node_follow_up()` allows `PNC_WORLD_MAP`.
- `march_confirm_follow_up()` allows `PNC_GATHER_NODE`.

`ActionExecutor.validate_follow_up(...)` only checks whether the observed screen is in `candidate_screen_types`. If the resource-node tap is accepted as `PNC_WORLD_MAP`, the executor proceeds to the next action and tries to resolve `PNC_GATHER_BUTTON` on the world map. If the gather button tap is accepted as `PNC_GATHER_NODE`, the executor proceeds to resolve `PNC_MARCH_CONFIRM_BUTTON` on the gather-node screen.

That makes the follow-up validation too weak for a multi-screen action chain: it accepts screens that are not valid for the next action.

Clean fix:
- Prefer refactoring `GatheringTask` into explicit one-screen increments:
  - From `PNC_WORLD_MAP`: choose and tap a resource node; valid next state is `PNC_GATHER_NODE`.
  - From `PNC_GATHER_NODE`: tap `PNC_GATHER_BUTTON`; valid next state is `PNC_MARCH_CONFIRM`.
  - From `PNC_MARCH_CONFIRM`: tap `PNC_MARCH_CONFIRM_BUTTON`; valid next state is `PNC_WORLD_MAP` or a surfaced blocking condition.
- Give each phase a strict follow-up request that only allows the next actionable/proven state for that phase.
- Keep source-screen retry/refresh behavior in the executor or a separate retry policy, not by broadening the success candidate set for chained actions.
- Add tests where the first tap leaves the observation on `PNC_WORLD_MAP` and where the gather tap leaves it on `PNC_GATHER_NODE`; both should stop cleanly as retryable failures or replans, not proceed to selectors that cannot exist on that screen.

### 2. Gathering can falsely report success when no march was dispatched

Severity: High

Relevant code:
- `pnc_automation/app/automation/tasks/gathering_task.py:86`
- `pnc_automation/app/automation/tasks/gathering_task.py:103`

When `before.available_march_slots` is unknown, `GatheringTask.verify(...)` treats any `after.screen_type == PNC_WORLD_MAP` as success:

```python
if after.screen_type == ScreenType.PNC_WORLD_MAP and before.available_march_slots is None:
    return TaskResult.success("Gathering flow returned to the world map.")
```

That success condition is only valid if the task has proven it reached the dispatch phase first. With the current one-shot chain, a missed resource-node tap can leave the task on `PNC_WORLD_MAP` with unknown march slots and still satisfy this condition if execution stops or returns the world-map observation.

I confirmed the behavior directly with a world-map `before` containing one resource node and a world-map `after` with unknown march slots: `verify(...)` returns `success`.

Clean fix:
- Make dispatch success phase-specific. `PNC_WORLD_MAP` with unknown slots should only be accepted after the `PNC_MARCH_CONFIRM` phase has been reached and the confirm action has been sent.
- The cleanest implementation is the same state-machine refactor from finding 1. Then `verify(...)` can validate each transition using the real `before.screen_type`:
  - `PNC_WORLD_MAP -> PNC_GATHER_NODE`: replan.
  - `PNC_GATHER_NODE -> PNC_MARCH_CONFIRM`: replan.
  - `PNC_MARCH_CONFIRM -> PNC_WORLD_MAP`: success when slots decreased, or success with unknown slots only because the before-state proves the confirm step was attempted.
- Add a regression test: `before = PNC_WORLD_MAP` with a visible resource node and unknown slots, `after = PNC_WORLD_MAP` with unknown slots must not be success.

### 3. Campaign opening proof is inconsistent between shortcut and spatial paths

Severity: Medium

Relevant code:
- `pnc_automation/app/pnc/navigation/screen_flows.py:871`
- `pnc_automation/app/pnc/navigation/screen_flows.py:887`
- `pnc_automation/app/pnc/navigation/screen_flows.py:896`
- `pnc_automation/app/pnc/navigation/spatial_navigation.py:1263`
- `pnc_automation/app/pnc/navigation/spatial_navigation.py:1329`
- `tests/test_flows_and_tasks.py:4198`

`ScreenFlowPlanner.open_campaign_map(...)` gives the direct `PNC_HOME_CAMPAIGN_ENTRY` shortcut an action-scoped Campaign follow-up request. The spatial fallback then delegates to `open_home_city_object(...)`, but the shared home-city opening path has no way to carry the Campaign-specific destination proof into the final tap.

The result is two different proof policies for the same concept:

- Shortcut path: strict `ObservationRequest.campaign_map_follow_up()`.
- Spatial/guided/atlas path: broad/default follow-up or generic behavior, depending on the action produced by `HomeCityNavigator`.

This weakens the "single canonical implementation per concept" goal. It also means the new test named as a shared target-opening proof only covers the shortcut branch; the spatial branch test verifies the query but not the destination proof.

Clean fix:
- Extend the shared Home City object-opening API to accept a destination follow-up request for final open taps, while preserving `PNC_HOME_CITY` source-screen retry requests for search/focus swipes.
- Thread that request through:
  - `ScreenFlowPlanner.open_home_city_object(...)`
  - `HomeCityNavigator.plan_open_object(...)`
  - `HomeCityNavigator.tap_visible_object(...)`
  - final guided/atlas tap builders such as `_plan_home_city_map_tap_action(...)`, `_plan_home_city_map_open_route_actions(...)`, and `_materialize_guided_tap_action(...)`
- Keep the campaign-specific method tiny: build the Campaign query once and call the canonical opener with `final_follow_up_request=ObservationRequest.campaign_map_follow_up()`.
- Add a test where Campaign is opened through a visible spatial object and assert the final opening action carries `ObservationRequest.campaign_map_follow_up()`.

### 4. Campaign navigation treats `PNC_BATTLE_PREP` as an owned state, but entry follow-up and initial verification do not

Severity: Medium

Relevant code:
- `pnc_automation/app/automation/tasks/campaign_task.py:51`
- `pnc_automation/app/automation/tasks/campaign_task.py:84`
- `pnc_automation/app/automation/tasks/campaign_task.py:85`
- `pnc_automation/app/pnc/vision/observation_request.py:126`

`CampaignTask.plan(...)` and later verification both include `PNC_BATTLE_PREP` as a campaign-owned screen once already observed. But when the task is opening Campaign from outside the campaign flow, `verify(...)` only accepts `PNC_CAMPAIGN_MAP` and `PNC_CAMPAIGN_STAGE` as successful entry states. `ObservationRequest.campaign_map_follow_up()` also only allows those two screens.

If tapping Campaign resumes directly into an already-open battle-prep state, the task will treat that as a failure even though `PNC_BATTLE_PREP` is otherwise modeled as a valid terminal/owned state.

Clean fix:
- Decide the canonical Campaign entry contract:
  - If `PNC_BATTLE_PREP` is a valid Campaign entry outcome, include it in `campaign_map_follow_up()` and in the non-campaign `verify(...)` success/replan condition.
  - If Campaign entry must only prove `PNC_CAMPAIGN_MAP`, remove `PNC_BATTLE_PREP` from the pre-open owned set and handle battle prep only after explicit stage progression.
- Based on the current task logic, the smaller consistent fix is to include `PNC_BATTLE_PREP` as an accepted Campaign entry outcome and return success/skipped rather than retryable failure.
- Add a test for `before = PNC_HOME_CITY`, `after = PNC_BATTLE_PREP`.

### 5. The new workflow tests cover shape and happy path, but not failure safety

Severity: Medium

Relevant tests:
- `tests/test_flows_and_tasks.py:4140`
- `tests/test_flows_and_tasks.py:4180`
- `tests/test_flows_and_tasks.py:4198`
- `tests/test_runner_end_to_end.py:247`

The added tests assert that the new actions and enum names are emitted, and the end-to-end test covers a perfect observation sequence. They do not cover the cases this plan is specifically trying to make safe:

- A follow-up observation lands on the source screen instead of the next action screen.
- Gathering returns to `PNC_WORLD_MAP` without proven dispatch and unknown march slots.
- Campaign spatial opening uses the same destination proof as the shortcut path.
- Campaign entry lands on `PNC_BATTLE_PREP`.

Clean fix:
- Add focused unit tests for the negative paths above.
- For chained actions, test executor-level behavior with fake observations so the test proves the runner does not continue to impossible selectors after a failed phase.
- Keep the tests aligned with the state-machine phases rather than asserting a long fixed action list; that will make the implementation easier to simplify without rewriting brittle tests.

## Suggested Cleanup Order

1. Refactor `GatheringTask` into phase-specific increments and tighten its follow-up requests.
2. Fix gathering verification so unknown march slots cannot turn an unchanged world-map observation into success.
3. Thread a final destination follow-up request through the shared Home City object-opening path.
4. Make the Campaign entry endpoint set consistent around `PNC_BATTLE_PREP`.
5. Add the negative-path tests, then keep the existing happy-path tests as smoke coverage.

## DRY / Architecture Checklist

- There is still not exactly one canonical implementation of "open this Home City object and prove its destination" because Campaign shortcut opening has a custom proof path that the shared spatial opener cannot express yet.
- Gathering currently mixes three subflow responsibilities into one action list, which makes follow-up validation and verification depend on stale before-state assumptions.
- The new observation request factories are semantically useful, but their screen sets should represent valid next states for each phase, not a blend of retry/source and destination states.
- No obsolete code path from the old `PNC_CAMPAIGN` alias remains in runtime code; remaining mentions are documentation/history only.

## Validation Notes

- `py -m unittest tests.test_flows_and_tasks.FlowAndTaskTests.test_gathering_task_chooses_highest_priority_visible_resource_node tests.test_flows_and_tasks.FlowAndTaskTests.test_campaign_task_uses_shared_home_city_target_opening_with_campaign_map_proof tests.test_flows_and_tasks.FlowAndTaskTests.test_campaign_task_can_open_campaign_from_spatial_home_city_target_without_private_search_logic` passed.
- `pytest` and `python` are not available on this PATH; `py` is available and was used for the targeted unittest run.
- A direct behavior probe confirmed `GatheringTask.verify(...)` currently returns `success` for unchanged `PNC_WORLD_MAP -> PNC_WORLD_MAP` when march slots are unknown.
