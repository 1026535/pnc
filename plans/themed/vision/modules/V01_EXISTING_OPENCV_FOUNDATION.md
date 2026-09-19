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
integration specimen. The [navigation baseline](CONTEXT_AND_EVIDENCE.md#navigation-findings-retained-in-these-plans)
now includes the bounded chest-preview recognition/close fix; V11 still owns its
content and feature qualification. V01 must not depend on V11 or expand the
preview to qualify the shared path.

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

## Implementation status and extension contract

Status: **Accepted for stated coverage**, based on
`552bb766619e7997c8d7898ccd7bfd414f7bdf6f`, on `codex/vision-v01-foundation`.
The source trace below is repository-proven; real-capture tests qualify the
existing production path without runtime changes. The lead reviewed one Devin
worker's package and made a small test correction; final affected checks passed.
The user subsequently authorized merging V01. The full portable integration
gate passed before the accepted test/plan changes were committed and landed in
local main. Remote publication remains separate from the local merge.

### Shared production path

1. `CapturedScreenshot` carries the image and `FrameRef`. Both publishers run
   `VisualScreenRecognizer.recognize` independently of the requested OCR family.
   The recognizer reuses one `PreparedFrame` for its profile matching;
   `OpenCvTemplateMatcher` owns normalization and decoded-template caching.
2. The `bag` profile in `app/pnc/vision/data/screen_anchors.json` proves
   `PNC_BAG`, layout `bag`, from two identity anchors. Its separate controls
   measure `PNC_BACK_BUTTON_TOP_LEFT` and `PNC_BAG_SUBTAB_RESOURCE`. An identity
   anchor does not become a click target.
3. `ObservationBuilder.create_ocr_context` supplies frame-owned
   `ObservationOcrContext` instances to both publishers. Guard and content reads
   within one build share the same bounded context. The publishers reconcile
   independent identity with the interruption guard before publishing controls.
4. `ObservationBuilder.build(request=ObservationRequest.source_screen_retry(
   ScreenType.PNC_BAG))` and `NavigationPerception.build(include_content=True)`
   both call `PncObservationEnricher.enrich` with the proved screen/layout,
   current image, measured controls and frame OCR context. The builder can also
   supply already-planned fixed-field reads in `ocr_regions`.
5. `compile_screen_content_ocr_region_plans` supplies Bag header/tab crops.
   `_build_bag_additions` verifies the Resource tab before requesting the body
   through `compile_ocr_region_plans(include_body_rows=True)` and
   `execute_ocr_region_plans`. `resource_inventory.parse_resource_inventory`
   owns card geometry, item facts and measured row actions.
6. `ObservationAdditions` is the shared publication boundary. Both publishers
   retain visually measured controls, publish registry-declared OCR labels via
   `select_content_labels`, and stamp controls/rows with
   `bind_visible_elements` / `bind_list_entry` from `observation_provenance.py`.
   Content cannot contradict the independently proved identity or supply a
   missing template control. COMPLETE Resource rows require measured action
   bounds and a contained action point.

### Where later packets extend the path

| Concern | Canonical registration or implementation owner |
|---|---|
| Screen/layout identity and measured controls | `app/pnc/vision/data/screen_anchors.json`, loaded by `load_visual_screen_recognizer`; keep profile IDs, layout IDs, source provenance and separate control anchors explicit. |
| Selector semantics | `build_default_selector_registry` and the packaged selector catalog; use `UiElementId` and the declared interaction kind. OCR labels must be declared as labels. |
| Content request scope | `ObservationRequest` and `pnc_ocr_capabilities.py`; extend only the family actually supported. |
| Bounded OCR acquisition | `ocr_region_plan.py`: screen content crops, fixed-field/body plans and `execute_ocr_region_plans`; use the supplied context and semantic `required_fact`. |
| Feature conversion | `PncObservationEnricher.enrich` dispatches to one feature parser, returning `ObservationAdditions`. V04 owns shared research parsing; V09 owns Bag parsing. |
| Typed publication/provenance | Existing `ObservationAdditions`, domain observation models and `observation_provenance.py`; any necessary model change migrates both publishers and its consumers together. |
| Reviewed route and action | `reviewed_navigation_edges` in `app/automation/engine/navigation_core.py` owns core edges, executed by the existing navigator. Home enters Bag with `PNC_BOTTOM_NAV_BAG`; Bag returns through its measured Back control. Parsers do not perform navigation or authorize resource actions. |

The existing popup reconciliation and inspection ownership remain in place.
V01 does not introduce new geometry helpers, backend adapters, preview semantics,
Home localization, or Resource-card feature expansion.

### Captured qualification and limits

Qualification date: **2026-09-16 UTC**. Confidence: repository-proven and
artifact-observed for the following captures; no current live route is claimed.
The fixture manifest supplies the capture groups and image hashes; game build
and locale were not recorded for these samples (the visible text is English).

- `tests/data/screen_recognition/bag.png`, 540 × 960: reference from
  `2026-08-30/mega_old_acc`. Both publishers return the same Bag identity/layout,
  measured Back/selected-Resource controls, five complete Resource rows and one
  explicitly unreadable row. Complete rows include 1K Food owned 35,174 and
  500K Food owned 1. The visible 10K Food (Safe), owned 873, remains unresolved
  by this capture's current body OCR and exposes no action. V09 owns any
  improvement to that feature parser; this qualification does not treat the
  unreadable row as a complete item.
- `tests/data/screen_recognition/bag_current_testing.png`, 900 × 1600:
  independent validation from
  `testing/planning_bag/20260910T203309Z_36134e9b`. All six complete rows match
  the existing manual annotations on both publishers: Food packs 1K/10K/10K
  Safe/150K owned 2,011/72/29/1 and Wood packs 1K/10K owned 1,963/66. Measured
  row actions lie in the annotated single-Use buttons.
- `tests/data/screen_recognition/home_city_core.png`: a fresh unrelated frame
  after Bag parsing publishes no Bag controls, Resource rows or Bag body read.
  Its controls retain the new Home frame's provenance.

The new
[`test_bag_foundation_publication.py`](../../../../tests/integration/vision/test_bag_foundation_publication.py)
uses real RapidOCR through the production bounded planner and guards on both
paths. It also verifies demand-driven content, no whole-frame OCR, frame/cache
ownership, same-frame cache reuse, control/row provenance and measured action
geometry. These tests inspect actions without executing them. Existing known
popup, unknown-modal and inspection-owner regressions remain unchanged.

Validation environment: Python 3.13.5, OpenCV 4.13.0.92,
`rapidocr-onnxruntime` 1.2.3, ONNX Runtime 1.24.3. Generated logs and structured
results are local evidence, not new tracked fixtures.

| Command | Result | Evidence relative to the implementation checkout |
|---|---|---|
| `py tools/run_tests.py group unit.core.vision` | Passed: 56 tests | `.local-data/devin-v01/unit_core_vision.log` |
| `py tools/run_tests.py group integration.vision` | Passed: 445; skipped: 6 optional local captures (451 total) | `.local-data/devin-v01/integration_vision.log` |
| `py -3.13 tools/run_tests.py affected --base origin/main --explain --json .test-impact/v01-final-selection.json --results .test-impact/v01-final-results.json` | Final run passed: 198 tests, including all four new tests; no skips or fallback | `.local-data/devin-v01/final-affected.log`, `.test-impact/v01-final-selection.json`, `.test-impact/v01-final-results.json` |
| `git diff --check` and local document-link check | Passed; 53 links checked | Final checkout inspection |
| `py -3.13 tools/run_tests.py full --results .test-impact/v01-integration-full-results.json` | Merge gate passed: 2,186 passed, 7 expected skips (2,193 total) | `.local-data/devin-v01/integration-full.log`, `.test-impact/v01-integration-full-results.json` |

No production integration gap was demonstrated, so V01 adds qualification tests
and documents ownership. A new live Home → Bag → Home run is not required under
this packet's unchanged-boundary rule. The affected selection did not fall back;
the subsequent merge request triggered the separate full portable integration
gate. Its skips were six unavailable optional captures and one Windows symlink
privilege case.
V02–V43 remain separate work; this result does not qualify all Bag tabs, partial
cards, seasonal Home layouts or a current emulator route.
