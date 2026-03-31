# Review: selector refinement discovery workflow

Commit reviewed: `Implement selector refinement discovery workflow` (`b74a3fea51e55235dfabcf2ffeb5068a7429fc6a`)

Scope reviewed:

- the new static selector catalog and offline updater path,
- the new discovery analyzer and discovery scripts,
- the OCR-backed selector-refinement additions,
- the plan documents affected by this milestone.

Note on scope:

- completing the full registry was too large for this milestone,
- the review therefore treats feature-by-feature registry growth as the intended model and flags only the places where the implementation or plans still contradict that model.

## Findings

### 1. High: the offline updater still allows invalid or regressive catalog writes

Evidence:

- [load_selector_update_spec()](/c:/Users/lebel/pnc/pnc_automation/vision/selector_registry_updater.py#L53)
- [apply_selector_updates()](/c:/Users/lebel/pnc/pnc_automation/vision/selector_registry_updater.py#L63)
- [_load_click_outcomes()](/c:/Users/lebel/pnc/pnc_automation/vision/selector_registry_updater.py#L285)
- [_create_click_outcome()](/c:/Users/lebel/pnc/pnc_automation/vision/selectors.py#L241)

Why this is a problem:

- One update spec can repeat the same selector id multiple times and the updater will merge them sequentially instead of failing fast.
- An explicit `click: null` clears previously reviewed click metadata because `update_click` is driven only by field presence.
- Click-outcome `verification_selectors` are only regex-validated, so unknown ids can be written successfully and fail later only when the typed runtime registry is rebuilt.

That is too permissive for a reviewed offline refinement path. The updater should move selector definitions forward safely, not silently accept destructive or runtime-invalid content.

Clean fix:

1. Reject duplicate selector ids inside one update spec before any merge starts.
2. Treat click-metadata removal as invalid in the current workflow, or require a separate explicit destructive flag instead of overloading `click: null`.
3. Validate every `verification_selector` against the final selector-id set, not only against the enum-safe regex.
4. Add updater tests for duplicate ids, click clearing, and invalid verification selectors.

### 2. High: live discovery can promote a selector to `click_mapped` even when the click outcome is still unknown

Evidence:

- [_build_click_mapping_draft()](/c:/Users/lebel/pnc/pnc_automation/vision/selector_discovery.py#L362)
- [_build_click_definition()](/c:/Users/lebel/pnc/pnc_automation/vision/selector_discovery.py#L453)

Why this is a problem:

- Probe drafts always promote to `click_mapped`.
- When the destination observation is `UNKNOWN`, the generated click outcome stores `target_screen: null`.
- The same path also accepts weak verification evidence, including an empty selector set.

That conflicts with the selector lifecycle defined in the plan. `click_mapped` means the destination is known and can be verified. Unknown destinations should remain probe evidence only.

Clean fix:

1. Only emit a `click_mapped` draft when the destination screen is known and the destination has explicit verification evidence.
2. If the destination stays `UNKNOWN`, keep the probe in the report only and require manual follow-up instead of generating an updater-spec entry.
3. Add a negative discovery test that proves unknown-destination probes do not produce promotable drafts.

### 3. Medium: `discover_selector_registry.py --catalog` does not actually control the runtime registry used during discovery

Evidence:

- [_build_runtime()](/c:/Users/lebel/pnc/tools/discover_selector_registry.py#L135)
- [build_application_runner()](/c:/Users/lebel/pnc/pnc_automation/app.py#L41)

Why this is a problem:

- The discovery tool accepts a `--catalog` path.
- That catalog is only used by the analyzer to suppress already-refined drafts.
- The observation builder still comes from `build_application_runner()`, which always loads the default selector catalog.

That creates a split-brain discovery run: report suppression uses one catalog while screenshot classification and selector detection can still use another.

Clean fix:

1. Thread `catalog_path` all the way into the runtime `build_default_selector_registry()` call.
2. Make the analyzer and the observation builder consume the same catalog path in one run.
3. Add a discovery test that uses a non-default catalog and proves both suppression and observation use the same source of truth.

### 4. Medium: the static catalog is still only a partial canonical registry, so future features can still leak selector metadata back into code conventions

Evidence:

- [SelectorCatalogEntry](/c:/Users/lebel/pnc/pnc_automation/vision/selector_catalog.py#L60)
- [build_default_selector_registry()](/c:/Users/lebel/pnc/pnc_automation/vision/selectors.py#L113)
- [_create_selector()](/c:/Users/lebel/pnc/pnc_automation/vision/selectors.py#L139)
- [selector-registry requirements in the implementation plan](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md#L538)

Why this is a problem:

- The YAML catalog currently stores `id`, `screens`, `status`, `detection_kind`, `click`, and `notes`.
- Template asset paths are still inferred from `selector_id.lower()`.
- Thresholds still default to `0.98`.
- OCR-region metadata is still not catalog-backed.

Given the stated scope, this is an acceptable deferral, but it should stay explicit. Otherwise later feature work will keep reintroducing registry metadata as Python-side conventions instead of extending the catalog cleanly when the next clickable UI slice needs it.

Clean fix:

1. Treat this as deferred scope, not as an implicit assumption that the registry is already complete.
2. When the next feature needs template-path, threshold, or OCR-region metadata, add those fields to the catalog and updater together in one change.
3. Keep current implicit defaults only as temporary fallbacks, not as the long-term canonical storage format.

### 5. Medium: the plan set is still inconsistent about phase closure and about how selector coverage should grow

Evidence:

- [PNC_ACCOUNT_NAVIGATION_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_ACCOUNT_NAVIGATION_SUBPLAN.md#L29)
- [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md#L944)
- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md#L108)
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md#L20)

Why this is a problem:

- The primary implementation plan says Phase 4 and Phase 5 are owned by the account-navigation sub-plan but are not yet closed.
- The account-navigation sub-plan still says those same phases are already closed in the primary plan.
- The remaining unfinished plans do not yet state clearly enough that selector coverage grows feature by feature as new clickable UI elements become necessary.

That planning mismatch makes it harder to reason about what is actually done and what should happen next.

Clean fix:

1. Keep closure wording consistent across the plans: ownership moved, closure still depends on the sub-plan evidence.
2. State explicitly that registry coverage expands feature by feature as new clickable UI elements are needed.
3. Update each unfinished downstream plan to depend on the selector slice needed for its current feature, not on a hypothetical fully completed registry.

## Duplication / simplification notes

- [selector_catalog.py](/c:/Users/lebel/pnc/pnc_automation/vision/selector_catalog.py#L130) and [selector_registry_updater.py](/c:/Users/lebel/pnc/pnc_automation/vision/selector_registry_updater.py#L184) duplicate most of the YAML mapping and click-outcome parsing logic. That should be collapsed into one shared schema-validation path before the catalog format grows further.
- The discovery path currently performs OCR twice per screenshot: once inside the runtime observation pipeline and once again inside the analyzer. That is acceptable for now, but it is a good cleanup target after the updater invariants and catalog/runtime consistency issues are fixed.

## Recommended next order

1. Tighten the updater invariants so reviewed specs cannot regress or corrupt the catalog.
2. Stop auto-promoting unknown probe destinations to `click_mapped`.
3. Make the discovery runtime use the same catalog everywhere in one run.
4. Keep the registry-growth model explicitly feature-scoped in the remaining plans, and extend the catalog schema only when the next feature actually needs new metadata.

