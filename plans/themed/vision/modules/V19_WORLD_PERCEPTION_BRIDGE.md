# V19 — Qualified World detections into current navigation

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V01 and the current detector owner's qualification. Align with [Gathering feature03](../../gameplay/PNC_CORE_REMAINING_03_GATHERING_PLAN.md). Deliverable: one supported World object class published through the canonical spatial observation and consumed for non-spending inspection.

## Scope and current boundary

Tour01 identified standard World but published no objects in that observation path. This does not establish whether the cause was model availability, request scoping or publication. The task **Assess YOLO training progress** owns newer model evidence; inspect its current result before choosing work.

Existing owners: `core/vision/detection/yolo_onnx.py`, `app/pnc/vision/yolo_shadow.py`, `spatial_surfaces.py`, `world_map_coordinates.py`, `domain/observation.py`, World navigation helpers and `navigation_core.py`. Shadow detections are not automatically actionable. This packet does not retrain a model or replace map movement.

## Implementation

1. Establish the actual request/model/publication path on the saved World frame. Reconcile current model export, class mapping, runtime output contract and held-out PNC evidence with the model owner.
2. If a qualified PNC class is available, map its current bounds/confidence to the existing typed spatial object. Preserve explicit unknown class/level/relationship fields; crop OCR only for fields the selected inspection needs.
3. Enable that qualified output through the same production publishers where requested. Do not promote arbitrary generic pretrained labels or all shadow classes into actions.
4. Keep existing coordinate reading, calibrated movement and target query ownership. After a pan or coordinate move, reacquire on a fresh frame; do not reuse old boxes.
5. Bind a supported object's measured selection to its recognized non-spending detail and return. Dispatch, gathering, battle and march receipts remain feature03 work.

## Acceptance and proof

Target `test_world_spatial_objects.py`, `test_world_spatial_observation.py`, World coordinate tests and affected navigation/consumer contracts. Use held-out PNC class captures and a relevant negative; verify class mapping, frame geometry, unknown field handling and invalidation after movement through the production path.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then affected checks. One core-runtime route: Home → World → acquire one qualified current object → its known read-only detail → World → Home. Include a single bounded pan only if needed to exercise changed reacquisition. Save model identity/class map, screenshots, typed detections and trace. Stop before attack, scout, dispatch or gathering.

If no qualified checkpoint/class contract is available, deliver the diagnosed publication gap and exact prerequisite to the model owner; keep actionable integration pending. V02 and all menu packets continue independently.
