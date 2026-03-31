# PNC Chat Workflow Sub-Plan

## 1. Purpose

This document captures the bounded implementation plan for improving the reusable P&C chat workflow, specifically `open_chat()` and `send_chat_message()`.

It is intentionally separate from:

- [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md), which remains the primary platform architecture plan,
- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md), which owns reusable screen-flow boundaries,
- [PNC_SELECTOR_RESOLUTION_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_SELECTOR_RESOLUTION_SUBPLAN.md), which owns the generic observed-selector fallback model.

## 1.1 Implementation status

Status:

- completed in repo on 2026-03-13,
- post-send follow-up observations now use action-scoped chat requests instead of the broad runtime default,
- `PNC_CHAT` recognition is now geometry-first with OCR fallback instead of OCR-primary,
- repeated sends now skip redundant channel taps when the requested channel is already active and use one canonical clear-and-replace draft policy,
- live smoke on the `testing` BlueStacks instance passed for both `Alliance` and `Kingdom`,
- measured home-city send times were `10.227s` for `Alliance` and `10.297s` for `Kingdom`, both below the prior `10.5s` baseline.

## 2. Current issues

The current chat helper is already close to minimal in action count:

- from home or world: open chat, select channel, type, send,
- from chat: select channel, type, send.

The remaining issues are mostly runtime-cost and reliability issues:

- post-send confirmation currently falls back to the broad runtime observation path instead of a narrow chat-specific observation,
- `PNC_CHAT` classification still depends on OCR as the primary proof of the screen,
- action pacing uses global delays that are conservative for chat,
- the workflow always taps the requested channel even when already selected,
- text-input focus still uses field-center tapping instead of the selector action point,
- repeated sends do not yet have a canonical draft-handling policy.

## 3. Goals

- Keep one canonical reusable chat workflow.
- Make chat opening and sending geometry-first wherever stable geometry is already known.
- Reduce OCR cost to the minimum required for safety and verification.
- Remove redundant taps and overly conservative waits.
- Keep fail-fast behavior for unexpected chat states.
- Preserve one canonical validation path through tests and live smoke checks.

## 4. Work plan

### 4.1 Observation-cost reduction

- Add action-scoped observation requests so non-navigation follow-up observations do not default to the full runtime OCR request.
- Introduce a narrow chat follow-up request for post-send confirmation.
- Keep popup and loading protection only where it is still required for safe recovery.

### 4.2 Chat-screen recognition refinement

- Refactor `PNC_CHAT` recognition so OCR is no longer the primary mechanism for proving the chat screen when geometry-backed controls are already sufficient.
- Keep OCR as fallback or optional verification instead of as the required primary recognizer.
- Ensure the refined design still distinguishes chat from home and world-map screens without duplicating selector logic.

### 4.3 Action-efficiency cleanup

- Split chat-specific pacing from the current global stable-click and observe-after delays.
- Skip the Kingdom or Alliance tab tap when the requested channel is already active.
- Update input focus to use the selector action point when available.
- Define one canonical draft policy for repeated sends: either clear-and-replace or prove-empty-before-type.

### 4.4 Validation

- Add targeted unit tests for narrow post-send observation requests, channel-skip behavior, and action-point-based input focus.
- Re-run live smoke validation on the `testing` BlueStacks instance for both `Kingdom` and `Alliance`.
- Compare end-to-end timing against the current live baseline of roughly 10.5 seconds for a home-city send.

## 5. Expected implementation files

The likely implementation surface is:

- [pnc_automation/pnc/action_requests.py](/c:/Users/lebel/pnc/pnc_automation/pnc/action_requests.py)
- [pnc_automation/pnc/screen_flows.py](/c:/Users/lebel/pnc/pnc_automation/pnc/screen_flows.py)
- [pnc_automation/automation/action_executor.py](/c:/Users/lebel/pnc/pnc_automation/automation/action_executor.py)
- [pnc_automation/automation/observed_action_executor.py](/c:/Users/lebel/pnc/pnc_automation/automation/observed_action_executor.py)
- [pnc_automation/vision/observation_request.py](/c:/Users/lebel/pnc/pnc_automation/vision/observation_request.py)
- [pnc_automation/vision/observation_builder.py](/c:/Users/lebel/pnc/pnc_automation/vision/observation_builder.py)
- [pnc_automation/vision/pnc_observation_enricher.py](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py)
- [tests/test_flows_and_tasks.py](/c:/Users/lebel/pnc/tests/test_flows_and_tasks.py)
- [tests/test_capture_and_vision.py](/c:/Users/lebel/pnc/tests/test_capture_and_vision.py)

## 6. Acceptance criteria

This plan is complete only when all of the following are true:

- the chat workflow no longer pays the broad full-runtime OCR cost for routine post-send confirmation,
- chat recognition is geometry-first or otherwise materially cheaper than the current OCR-primary path,
- repeated sends avoid redundant channel-selection work when the requested channel is already active,
- input focus uses the canonical selector action point when present,
- live sends on `testing` remain reliable for both `Kingdom` and `Alliance`,
- the end-to-end live send path is measurably faster than the current baseline.

