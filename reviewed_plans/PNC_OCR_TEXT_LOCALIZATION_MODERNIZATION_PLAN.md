# PNC OCR text recognition and localization modernization plan

Date: 2026-09-16. Status: planned; implementation is not authorized by this document alone.

Planning baseline: `a73843cebfcee2105d8efd07706dd7fcb94fda10` (`origin/main`). This is a shared infrastructure plan outside the numbered V01–V43 feature packets. It owns OCR backend, model, packaging, and text-localization qualification; feature packets retain their screen semantics, navigation, and action policy.

[Vision roadmap](PNC_VISION_ROADMAP.md) · [Shared architecture](PNC_VISION_MODULAR_PLAN.md) · [Campaign packet](vision_modules/V13_CAMPAIGN_MAP_AND_CHAPTERS.md)

## Objective

Replace the weak part of the current OCR path for labels and menu text with a local AI text-detection-and-recognition stack that returns measured text positions. Preserve the existing `OcrService`, `ObservationOcrContext`, typed observation publishers, coordinate projection, diagnostics, and action-safety boundaries.

The outcome must improve both exact text recognition and the position associated with that text. A recognizer run against an already localized crop can improve text, but it does not qualify as text localization.

## Scope and non-goals

In scope:

- menu labels, button labels, card titles, and short multiword phrases;
- measured word or phrase geometry suitable for `TextAnchorDetector`;
- bounded numeric and content OCR regression checks for current consumers;
- deterministic, offline Windows packaging of model assets and licenses;
- one atomic promotion and rollback unit for adapter, dependencies, models, dictionaries, preprocessing, decoder configuration, and backend revision.

Out of scope:

- replacing the observation, navigation, or observed-action layers;
- granting click authority from OCR alone;
- a runtime VLM or GUI-grounding service;
- automatic routing between permanent legacy and new OCR stacks;
- fine-tuning before a bounded comparison demonstrates a persistent domain-specific failure;
- polygons or rotated boxes unless measured failures show that axis-aligned `Bounds` are insufficient.

## Repository-proven baseline

- `pnc_automation/core/vision/ocr/ocr_service.py` owns `OcrWord`, `OcrLine`, `OcrResult`, `OcrService`, `ObservationOcrContext`, and `RapidOcrService`.
- `ObservationOcrContext` already owns frame binding, bounded-region reads, caching, diagnostics, backend revision, and exact-once projection to global coordinates. Keep it as the single OCR access path.
- The current dependency is `rapidocr_onnxruntime>=1.2.3,<2.0.0`. RapidOCR returns line quadrilaterals, while `_to_ocr_words()` estimates individual word bounds by distributing line width according to character counts. Those word positions are synthetic rather than measured.
- `TextAnchorDetector` consumes `line.words` and forms spans of up to three words, so inaccurate word geometry can become inaccurate anchor geometry even when the recognized phrase is usable.
- V10 and V15 document observed failures from the accepted backend: a dropped leading digit and a lone `0` that remains unknown.
- A local, unmerged V13 candidate at `124a435e115bc4f3c782e6439b8013b5a8e75e53` contains two relevant review inputs: commit `18049819c3dec5172e60e83a063547b19a20b9d2` migrates to `rapidocr==3.4.5`, and the later commit vendors a PP-OCRv3 recognizer for thin/wide crops. That candidate improved Campaign recognition but still synthesizes word positions. Review and selectively extract useful hunks with source attribution; do not merge the branch wholesale.

## Target design and ownership

Keep a single production OCR adapter behind `OcrService`. Its default candidate is current RapidOCR with explicitly pinned PaddleOCR mobile detection and English recognition ONNX assets, initially evaluating the PP-OCRv5 family. Pin the exact compatible RapidOCR release only after the clean-install compatibility probe; GPT-6 Pro suggested `rapidocr==3.9.2` as a candidate, not an assumed answer.

The adapter must return:

- normalized line text and confidence;
- detector-measured line geometry;
- measured word geometry when the selected engine exposes it;
- otherwise, explicit line/phrase geometry without presenting proportional character slicing as measured word localization;
- deterministic reading order, clamped bounds, and existing global-coordinate projection.

The public `OcrWord`, `OcrLine`, and `OcrResult` contracts may be extended only when necessary to distinguish measured from derived geometry. Callers must not infer provenance from backend-specific dictionaries or string conventions. `ObservationOcrContext` remains the owner of regions, caching, projection, and diagnostics. Feature producers remain responsible for screen identity and independently approved control interiors.

Do not add a permanent fallback router. If the primary candidate misses a material gate, compare one bounded challenger at a time:

1. PP-OCRv6-small detection/recognition, if a compatible export is available and the primary has a measured recognition or localization failure.
2. A single lightweight OnnxTR detector/recognizer pair only if the Paddle-family comparison does not resolve the failure.

A typed label/content profile is justified only by benchmark evidence showing that one configuration cannot meet both label and numeric/content gates.

## Phase 1 — Evidence and contract

1. Build `tests/data/ocr_text_localization/manifest.json` from 15–25 source frames already approved for repository fixtures. Annotate 80–120 label/phrase instances, 30–50 hard negatives, and 40–60 numeric/content fields. Split validation by capture session so near-duplicate frames cannot cross the boundary.
2. Include the known V10 leading-digit and V15 lone-`0` failures, Campaign numerals, compact buttons, disabled labels, outlined text, low-contrast text, and visually similar non-text controls.
3. For every positive, record normalized expected text, source region, text target bounds, owning screen/surface, criticality, and any independently approved control interior. Hard negatives record the region and why no actionable text may be emitted.
4. Add a deterministic comparison harness under the existing test/tool ownership. It must emit machine-readable per-case results and a human-readable report under `.local-data/reports/ocr_text_localization/`.
5. Decompose failures into region/preprocessing, detection, recognition on an oracle crop, grouping/anchor mapping, and publication through both observation publishers. Do not tune recognition to hide a region or projection defect.

## Phase 2 — Bounded engine comparison

1. Capture the current `rapidocr_onnxruntime==1.2.3` baseline on the complete corpus, including latency, cold initialization, peak RSS, missing values, wrong values, false positives, localization error, and downstream anchor matches.
2. Evaluate the primary RapidOCR/Paddle mobile candidate with an explicit dependency lock, detector/recognizer asset hashes, dictionaries, licenses, preprocessing, decoder settings, and backend revision.
3. Run the same corpus and environment for each justified challenger. No challenger proceeds merely because it is newer; it must address a named failure left by the primary.
4. Select the smallest candidate that passes every mandatory gate. Archive the comparison report under ignored `.local-data/`; keep only stable fixtures, manifests, and test expectations in Git.

## Phase 3 — Integration

1. Adapt `RapidOcrService` or replace its internals without creating a second public OCR path. Preserve dependency injection and the existing disabled/fake services used by tests.
2. Remove proportional word-box synthesis from actionable label localization. When only line boxes are available, publish a line/phrase anchor with honest geometry or use detector output plus deterministic grouping; do not fabricate glyph-level precision.
3. Preserve exact-once coordinate projection and cache identity. Include backend/model revision and any behavior-affecting profile in cache and diagnostic identity.
4. Migrate `TextAnchorDetector` and affected publishers to the clarified geometry contract. An OCR match may propose an anchor only inside the requested region; action eligibility still requires the feature producer's screen identity, semantic match, and approved control geometry.
5. Exercise both publication paths that currently consume OCR and add regression coverage for multiword spans, clipped regions, hard negatives, repeated labels, and stale-frame/cache boundaries.

## Phase 4 — Packaging, promotion, and cleanup

1. Vendor or package all runtime model/dictionary assets required for an offline clean install. Record upstream source, version, SHA-256, license, and redistribution terms.
2. Fail clearly if an asset is missing or corrupt. Production must not download models at runtime.
3. Promote adapter code, dependency lock, assets, dictionaries, preprocessing/decoder configuration, and backend revision together. Roll them back together.
4. Remove the obsolete dependency and touched compatibility code after all callers pass. Do not retain a hidden legacy fallback.
5. Update the shared workflow notes with benchmark provenance, selected model versions, observed limits, and the date/build used for any bounded live composition check.

## Acceptance gates

All mandatory fixtures must run; a missing engine or fixture cannot be counted as a qualifying skip.

| Area | Required gate |
|---|---|
| Label recognition | At least 98% exact normalized text overall, at least 95% on every represented surface, and 100% on reproduced blocking cases. |
| Text localization | At least 95% one-to-one matches at IoU ≥ 0.50, with center error reported; 100% of critical anchors must have their center inside the annotated text target and remain inside the requested OCR region. |
| Action safety | Every proposed actionable anchor must also lie inside the feature's independently approved control interior; zero actionable false positives on hard negatives. OCR geometry alone never authorizes a click. |
| Typed anchors | 100% correct for critical anchors and at least 98% overall after grouping and normalization. |
| Numeric/content regression | Preserve 100% of previously correct reviewed values, introduce no increase in missing values, and produce zero new wrong values on the corpus. |
| Determinism | Identical normalized output and geometry across 20 repeated runs and three fresh processes, subject only to explicitly documented numeric tolerance. |
| Warm performance | End-to-end p95 OCR latency no more than 1.25× the accepted baseline on the same machine and corpus. |
| Startup and memory | Cold initialization no more than baseline +2 seconds; peak RSS no more than 1 GiB and no more than baseline +256 MiB. |
| Offline packaging | Clean install and first inference succeed with network disabled; all required asset hashes and licenses are verified. |

The IoU gate measures whether returned text geometry overlaps the annotated text, while target and control containment enforce click safety. A whole crop or whole button rectangle does not qualify as text localization merely because it contains the text.

## Validation sequence

Use the repository runner from a clean environment, with the exact planning base retained for affected-test selection:

```powershell
$Python = ".\.venv\Scripts\python.exe"
$Base = "a73843cebfcee2105d8efd07706dd7fcb94fda10"
& $Python tools/run_tests.py group unit.core.vision
& $Python tools/run_tests.py group unit.app.pnc.vision
& $Python tools/run_tests.py group vision
& $Python tools/run_tests.py affected --base $Base --explain
& $Python tools/run_tests.py full
git diff --check
```

Accuracy qualification is offline and fixture-driven. First verify fresh-process load and observation composition from saved captures. Only if a material BlueStacks/ADB composition fact remains unresolved, use the live-test workflow for one bounded, non-spending observation smoke on the configured testing instance. Do not navigate, click, switch accounts or castles, or use a live smoke as a substitute for the corpus.

## Migration and rollback

- Land fixtures and the benchmark harness before changing the production backend so baseline and candidate results are directly comparable.
- Land the selected backend as one coherent change with its tests and packaged assets. Feature packets consume the existing service contract and should not carry backend-specific conditionals.
- Roll back the complete promotion unit if any safety, numeric/content, deterministic, packaging, or resource gate fails. A recognition gain does not outweigh a new wrong value or unsafe anchor.
- V13 retains Campaign screen semantics and routes. V10 and V15 retain their domain parsing and known-case assertions. This plan owns the shared correction that those packets consume.

## Implementation completion checklist

- [ ] Corpus, manifest, session-separated validation split, and hard negatives are reviewed.
- [ ] Baseline and candidate reports identify detection, recognition, grouping, and publication failures separately.
- [ ] Selected engine and exact assets pass every acceptance gate.
- [ ] Word/phrase geometry provenance is explicit; proportional boxes are not used for actionable localization.
- [ ] Both observation publishers and `TextAnchorDetector` pass focused regression tests.
- [ ] Offline packaging, hashes, dictionaries, and licenses are complete.
- [ ] Narrow groups, affected selection, full suite, and `git diff --check` pass.
- [ ] Any required bounded live composition smoke is recorded with zero spending and no unauthorized actions.
- [ ] Roadmap and feature notes report the integrated commit and qualification evidence.

## ChatGPT Pro consultation

GPT-6 Pro in Chat mode produced the initial plan against verified GitHub commit `a73843cebfcee2105d8efd07706dd7fcb94fda10`. Consultation status: complete on 2026-09-16. No repository overlay was attached. The prompt separately disclosed the local-only V13 candidate commits as Codex-verified facts because they were not accessible from GitHub.

The active Codex task audited the proposal against the repository before saving it. The audit retained Pro's single-adapter design, staged engine comparison, corpus structure, atomic promotion unit, and quantitative gates. It corrected a non-repository placeholder link, made candidate package versions conditional on compatibility proof, and separated text-overlap measurement from safe target/control containment.
