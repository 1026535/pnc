# V01 — Existing OpenCV and observation integration

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Dependency: planning baseline. Deliverable: a verified shared path that later feature packets extend without another engine.

## Current owners

- `pnc_automation/core/vision/template/template_matcher.py`: `OpenCvTemplateMatcher`, prepared-frame matching and reference normalization.
- `pnc_automation/app/pnc/vision/visual_screen_recognizer.py` and `data/screen_anchors.json`: independent profiles, anchors and controls.
- `observation_builder.py`, `navigation_perception.py`, `pnc_observation_enricher.py`: two publishers and shared content production.
- `ocr_region_plan.py`, `core/vision/ocr/ocr_service.py`: bounded requests and frame-owned OCR.
- `app/pnc/domain/observation.py`, `domain/popup.py`: typed facts and popup ownership.

These components already exist. Use the supported Bag Resource layout
(`tests/data/screen_recognition/bag.png` and its current profile) as the small
integration specimen. The [source-fix assessment](CONTEXT_AND_EVIDENCE.md#navigation-findings-retained-in-these-plans)
shows that chest-preview support is absent on the main landing base; V11 owns
that feature. V01 must not depend on V11 or recreate the preview to qualify the
shared path.

## Implementation

1. Trace that specimen through both publishers: capture → independent identity → owned controls → requested content → provenance. Record where each later packet registers its profile, OCR region, parser and navigation edge.
2. Fix only a demonstrated shared integration gap. Reuse current region planning, frame cache, matcher and typed observations. No new engine adapter layer merely to rename existing classes.
3. Establish the narrow extension contract: feature parser inputs are proved screen/layout, image and frame OCR context; outputs are current controls and typed content. Existing `ObservationAdditions` remains the publication boundary. One parser implementation serves both paths.
4. Preserve current unknown-modal handling and inspection ownership. Extract a shared geometry/helper function only if the next concrete Home/research/Bag consumer needs it.
5. Document the final symbol/profile ownership in the plan status. If the current implementation already satisfies this contract, finish with qualification evidence and no production changes.

## Acceptance and proof

Existing tests to target: `tests/unit/core/vision/test_template_matcher.py`,
`tests/integration/vision/test_template_observation.py`,
`test_observation_request_scoping.py` and `test_known_popup_recognition.py`.
Replay the existing Bag reference through both publishers with production bounded
OCR. Require matching identity, requested current controls/content and frame
provenance; an unrelated frame must not acquire Bag controls. Preserve existing
known-popup and unknown-modal guard tests. Preview-specific qualification stays
in V11.

Start with `py tools/run_tests.py group unit.core.vision`; apply the index's affected/integration rule to actual changes. A shared schema change requires its callers and broader contract checks in this packet.

No new live run is needed for qualification of unchanged behavior. If the shared
live publication boundary changes, use one existing read-only Home → Bag → Home
route through the core runtime, retaining frames and guard/observation trace.
Inspect current content without Use/Open. Do not introduce a preview dependency
or extend Bag semantics owned by V09/V11 merely for this shared proof.
