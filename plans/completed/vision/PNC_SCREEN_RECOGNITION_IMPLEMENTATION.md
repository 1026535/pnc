# Screen recognition implementation

Follow-up: the Windows journal denial investigated below now has a bounded replacement retry and deterministic regression coverage. See `PNC_FINDINGS_FOLLOW_UP.md` for the current findings status and validation; the earlier failed test runs below are retained as historical evidence.

Implemented the fixed-menu portion of `PNC_SCREEN_RECOGNITION_EXPLORATION.md` on September 10, 2026. This is a guarded visual-evidence layer, not a trained general game detector or an OCR-free replacement.

## Runtime contract

- `ObservationBuilder` remains the observation entry point. It gathers global visual evidence independently of the requested OCR content families. Coordinate-only world-map proofs retain their existing dedicated path.
- `VisualScreenRecognizer` loads a versioned packaged catalog. Each profile requires at least two region-constrained anchors. Unsupported aspect ratios and competing screen interpretations abstain. Scores measure similarity, not probability.
- One `OpenCvTemplateMatcher` replaces the Pillow pixel matcher everywhere. It supports reference-size normalization, bounded regions, alpha masks, and correlation plus an absolute-color guard. It checks at most the 256 highest-correlation positions.
- `ScreenClassifier` still owns the final state. Positive visual evidence forces the independent popup/loading OCR guards. A topmost blocking overlay owns the controls; conflicting visual identity clears actionable elements and content rather than materializing a guessed screen.
- Existing selector, OCR-content, navigation, and observed-action owners remain in use. The visual layer never executes an action or treats screen identity as proof that a resource-spending control is enabled.
- `PNC_SETTINGS` now identifies the full Settings grid. `PNC_MORE_MENU` identifies the More overlay. Callers, outcomes, and tests were migrated. Settings retains `PNC_MORE_MANAGE_CHAR`; a distinct overlay control ID prevents sharing that geometry.
- Header Back geometry is limited to supported header screens and excludes Home and the More overlay. Hero Hall Recruit 1x no longer appears merely because geometry exists. A manually reviewed arrow interior verifies the Back click point at two resolutions.
- Daily return-to-home begins with a full observation request, fixing the reproduced Quest-only request that hid Hero Hall.

The nine initial profiles cover Hero Hall, Event Center, Quest Main, Quest Daily, Bag, Settings, More, Manage Char, and the alliance invitation. Unsupported screens continue through existing OCR recognition. Invitation absence is not used to infer alliance membership.

## Evidence and acceptance results

`tests/data/screen_recognition/manifest.json` contains 18 manually reviewed, decoded-image-hash-checked frames: nine reference, two validation, and seven holdout. Reference and holdout groups and image hashes are disjoint. The two validation negatives share a source day/account with references and are explicitly not counted as independent holdout evidence. Not every profile has an independent holdout; this remains a small initial dataset.

`py tools/benchmark_screen_recognition.py` passed: 18 expected final states, zero wrong actionable classifications, and one expected Store abstention. The OCR baseline missed Event Center; guarded visual evidence recovered it. An update dialog over an undarkened Bag header matches the raw Bag anchors but correctly becomes a blocking popup in the guarded pipeline. Raw visual output alone is therefore unsuitable for action authorization.

Benchmark: `artifacts/screen_recognition/benchmark.json`. The tool compares independent canonical OCR builders with and without visual evidence and records raw visual evidence separately. It rejects malformed manifests and reference/holdout leakage and exits unsuccessfully on a wrong actionable classification. Timing is diagnostic: concurrent CPU load, single replays, and mandatory OCR prevent an overall speedup claim.

The live proof tool uses the configured `testing` instance, launches/foregrounds PNC, observes the currently active castle without switching, and refuses spending controls, list-row selections, raw taps, text input, and update confirmation. Each run has a unique directory and append-only pre-action/post-action trace. It disables roster persistence so observing identity does not rewrite local config.

The initial proof passed eight actions: Home → More → Settings → Manage Char → Settings → Home → Quest Main → Quest Daily → Home. Two transitional unknown observations were retried through the existing executor before continuing. Raw visual profiles confirmed More, Settings, Manage Char, and both Quest tabs. Evidence: `artifacts/screen_recognition/live/20260910T194959Z_bf9d5bf9/summary.json` and `trace.jsonl`.

`py tools/validate_navigation_selectors.py --account testing --selector PNC_BOTTOM_NAV_MORE --selector PNC_MORE_SETTINGS --output-dir artifacts/screen_recognition/navigation` passed all three applicable outcomes, zero failures/skips. Report: `artifacts/screen_recognition/navigation/20260910T195642Z_testing_navigation_validation.yaml`.

## Validation record

- Matcher and benchmark tests: passed 13 tests.
- Settings migration targeted suite: passed 375 tests, one skip; post-Home-geometry correction passed 164 tests, one skip.
- Visual identity/guard/click-point tests: passed nine tests.
- Live-probe action allowlist tests: passed two tests.
- Final combined recognition/navigation regression: `py -m unittest tests.test_template_matcher tests.test_benchmark_screen_recognition tests.test_visual_screen_recognizer tests.test_validate_visual_navigation tests.test_daily_live_session tests.test_screen_classifier tests.test_selectors tests.test_flows_and_tasks tests.test_capture_and_vision tests.test_navigation_selector_validator` passed 390 tests with one skip. Log: `artifacts/recognition_implementation/recognition_final.log`.
- Initial `py -m unittest discover -s tests`: 987 tests, 17 skips, one Windows `os.replace` permission error in an unrelated journal test. Its exact targeted rerun passed. No journal production code was changed.
- Final `py -m unittest discover -s tests`: **not clean**, 990 tests, 17 skips, two `WinError 5` errors at the unchanged journal store's atomic `os.replace`. The affected tests were `test_daily_hero_hall.HeroHallRecruitmentExecutorTests.test_commits_exactly_five_singles_and_waits_between_them` and `test_resource_item_canary.ResourceItemCanaryTests.test_unchanged_inventory_cannot_pass_or_replay`. Log: `artifacts/recognition_implementation/unittest_final.log`. Neither failure was a recognition assertion.
- Journal isolation: `py -m unittest tests.test_daily_run_journal` also encountered the same permission error (one of eight tests). A final three-test replay passed the resource-item and journal lifecycle cases but still failed the Hero Hall case at `os.replace`. The Windows file-access issue remains unresolved; the full suite is not reported as passed. No unrelated journal retry policy or persistence behavior was changed.
- Final `py tools/validate_visual_navigation.py --account testing`: passed eight actions after the Home-geometry correction, verified both navigation postconditions and returned Home with no Back selector. Evidence: `artifacts/screen_recognition/live/20260910T195757Z_cfa84a53/summary.json` and `trace.jsonl`.
- `git diff --check`: passed.

## Scope limits

No trained classifier or YOLO model was added: no defined moving-object requirement or comparative result justified training in this fixed-menu slice. No claims, recruitment, alliance joins, purchases, messages, or castle switches were performed. Repeated-row association and resource-spending workflows retain their existing contracts and need separate authorized proofs before changing them.

The prior exploration and review remain historical evidence. Existing user changes to skills, AGENTS, and browser instructions were preserved. No local account/castle configuration was intentionally edited.
