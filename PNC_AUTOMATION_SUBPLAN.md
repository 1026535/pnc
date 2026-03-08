# Review: `PNC_AUTOMATION_IMPLEMENTATION.md`

Commit reviewed: `completed PNC_AUTOMATION_IMPLEMENTATION.md` (`ab0e296d8947748366d2b0cf246df6f2e3263203`)

Scope reviewed:

- runtime changes introduced by the commit,
- test coverage added by the commit,
- plan/status documents updated by the commit.

Validation run:

- `py -3.13 -m unittest discover -s tests -p "test_*.py"`: passed (`30` tests)

General assessment:

- The runner and script-preparation refactor is a net improvement.
- The selector-registry merge fix is correct and removes a real defect.
- The main remaining problems are in the new OCR fallback heuristics and in the documentation claiming closure beyond the evidence actually added.

## Findings

### 1. High: the new bottom-nav OCR fallback can misclassify non-home screens as `PNC_HOME_CITY`

Evidence:

- [_build_home_city_additions()` in `pnc_observation_enricher.py`](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py#L124)
- [the fallback is only validated with a positive case](/c:/Users/lebel/pnc/tests/test_capture_and_vision.py#L257)

Why this is a problem:

- The fallback now classifies a screen as `PNC_HOME_CITY` when it sees only two OCR labels near the bottom, as long as one of them is `Alliance` or `More`.
- That is too weak for a fail-fast automation system. Many in-game screens can expose bottom navigation text while not being the city root.
- If template matching misses the real screen, this heuristic can convert an unknown state into a trusted `PNC_HOME_CITY` state and cause the runner to tap city-only selectors on the wrong UI.

Clean fix:

1. Keep `UNKNOWN` unless at least one home-city-specific anchor is also proven.
2. Accept the fallback only when bottom-nav OCR is combined with evidence such as `PNC_HOME_WORLD_SWITCH`, `PNC_HOME_CHARACTER_PANEL`, top resource bar cues, or another city-only visual anchor.
3. Add negative tests for at least Bag, Quest, Hero, and Mail screenshots or OCR fixtures to prove they do not collapse to `PNC_HOME_CITY`.

### 2. High: the new OCR building-detail fallback can fabricate an upgrade button on unrelated screens

Evidence:

- [_build_building_detail_additions()` in `pnc_observation_enricher.py`](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py#L67)
- [the commit only adds a positive test](/c:/Users/lebel/pnc/tests/test_capture_and_vision.py#L222)

Why this is a problem:

- The fallback upgrades any `UNKNOWN` screen to `PNC_BUILDING_DETAILS` when OCR sees a top title plus the word `Upgrade` in the upper-right region.
- It also injects synthetic clickable selectors for both `PNC_BACK_BUTTON_TOP_LEFT` and `PNC_BUILDING_UPGRADE_BUTTON`.
- That is not strong enough evidence for a click-driving screen override. Hero upgrade screens, event/reward modals, or other upgrade-related surfaces can satisfy the same loose pattern.

Clean fix:

1. Require stronger building-specific evidence before overriding the screen type.
2. Prefer a conjunction of cues, for example: building title pattern, known building-detail layout anchors, and upgrade button placement.
3. Add negative tests for at least `PNC_HERO_DETAIL_UPGRADE` and one generic modal containing `Upgrade`.
4. If the evidence is partial, keep the screen `UNKNOWN` instead of fabricating clickable building selectors.

### 3. Medium: the updated plan now claims phases are closed without the selector maturity or validation evidence required by the same plan

Evidence:

- [phase closure language in `PNC_AUTOMATION_IMPLEMENTATION.md`](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md#L928)
- [phase validation requirements in the same document](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md#L1009)
- [critical selectors still marked `planned` in `selectors.py`](/c:/Users/lebel/pnc/pnc_automation/vision/selectors.py#L252)

Why this is a problem:

- The commit marks Phase 2, Phase 2.5, Phase 4, and Phase 5 as closed in the main plan.
- The code added in the same commit does not support that claim yet: several selectors required by login, building, research, gathering, campaign, and popup handling are still `planned`, and the added tests are synthetic unit/integration-style checks rather than the live smoke evidence the plan itself requires.
- That creates a planning inconsistency. Later work will read the architecture doc as if selector refinement and account-navigation validation are finished when they are not.

Clean fix:

1. Change the main plan wording from `closed` to `implemented in baseline form` or `moved to sub-plan ownership`.
2. Add an explicit status table per phase: `implemented`, `validated by unit tests`, `validated by screenshot fixtures`, `validated by live smoke`.
3. Do not mark Phase 2.5, 4, or 5 closed until the required selectors are promoted out of `planned` and the corresponding smoke evidence exists.

### 4. Medium: the commit strengthens fallback classification but does not add the negative coverage needed to make those fallbacks trustworthy

Evidence:

- [positive-only tests for the new OCR fallbacks](/c:/Users/lebel/pnc/tests/test_capture_and_vision.py#L222)

Why this is a problem:

- The new heuristics are exactly the kind of logic that fails by over-matching.
- The added tests prove that the heuristics can recognize one intended case, but they do not prove that the heuristics reject nearby unintended cases.
- For screenshot-driven automation, false positives are more dangerous than false negatives because they replace safe failure with wrong clicks.

Clean fix:

1. Add negative screenshot/OCR tests alongside every new heuristic classifier.
2. For each heuristic, test at least one adjacent screen that shares similar text or layout.
3. Treat negative tests as mandatory whenever a classifier creates synthetic clickable selectors.

### 5. Low: `config/castles.yaml` was converted from a discoverable example into an empty cache file with no companion example

Evidence:

- [`config/castles.yaml`](/c:/Users/lebel/pnc/config/castles.yaml)

Why this is a problem:

- The loader still supports and benefits from a structured castle-roster file, but the repository no longer shows users what that file should look like.
- This is a documentation regression for a newly introduced concept.

Clean fix:

1. Add `config/castles.example.yaml` with the expected schema.
2. Treat `config/castles.yaml` as runtime-owned cache data and either keep it empty intentionally with a short comment or exclude it from authored examples.

### 6. Low: the `PncObservationEnricher.enrich()` docstring is now stale

Evidence:

- [`PncObservationEnricher.enrich()`](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py#L36)

Why this is a problem:

- The method no longer only recognizes the Manage Char screen. It now also injects building-detail and home-city fallbacks.
- The stale docstring will mislead the next person touching the classifier.

Clean fix:

1. Update the docstring to describe all current responsibilities.
2. Mention explicitly that the method performs OCR-based fallback classification and may synthesize visible elements.

## Duplication / Simplification Notes

I did not find problematic duplication in the new `PreparedRunScript` / `TaskRegistry.prepare_script()` / `AutomationRunner._build_context()` refactor. Those changes are cleaner than the previous shape and should stay.

The best simplification opportunity is to keep OCR fallbacks conservative:

- classify less,
- prove more,
- prefer `UNKNOWN` over a guessed actionable screen.

## Recommended Next Order

1. Tighten the two OCR fallback classifiers.
2. Add negative tests for both classifiers.
3. Reconcile phase-closure claims in [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md) with actual selector maturity and validation evidence.
4. Restore schema discoverability for the castle-roster file.
