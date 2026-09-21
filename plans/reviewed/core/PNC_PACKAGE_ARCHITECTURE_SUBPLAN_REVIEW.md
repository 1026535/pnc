# PNC Package Architecture Review

Review target: commit `11045d38e5c75d46925bd7b98c8c6a69d8c04172` (`Complete PNC_PACKAGE_ARCHITECTURE_SUBPLAN`)

## Findings

### 1. High: `build_default_selector_registry()` now resolves its default template root from the wrong directory

- File: `pnc_automation/app/pnc/vision/selectors.py:258`
- Problem:
  - The refactor moved `selectors.py` from `pnc_automation/vision/` to `pnc_automation/app/pnc/vision/`, but the default template-root calculation still uses `Path(__file__).resolve().parents[2] / "templates" / "pnc"`.
  - From the new location, `parents[2]` resolves to `pnc_automation/app`, not `pnc_automation`.
  - That means the default path is now `pnc_automation/app/templates/pnc`, which is not the old package-root-relative location and is currently nonexistent in this workspace.
- Why it matters:
  - Any runtime path that relies on the default selector registry template location will silently stop using template-backed selectors because `selector.template_path.is_file()` will be false.
  - The current tests pass because they either inject `template_root` or never assert that the default template path is valid.
- Clean fix:
  - Change the default root calculation to the actual intended package root.
  - If templates are meant to live under `pnc_automation/templates/pnc`, use `parents[3]`.
  - If templates are no longer part of the canonical runtime, remove the misleading default path entirely and require an explicit template root.
  - Add a regression test that asserts the default root resolves to the intended canonical location after package moves.

### 2. Medium: the new architecture test is too weak to reliably enforce the boundary rules it was added to protect

- File: `tests/test_package_architecture.py:61`
- Problem:
  - `_find_import_violations()` scans raw text lines and only looks for forbidden substrings in lines beginning with `from ` or `import `.
  - This misses important cases:
    - relative imports,
    - future multiline import formatting variations,
    - imports hidden behind aliases or indirect package imports,
    - syntax that is valid Python but not caught by substring matching.
- Why it matters:
  - This test is supposed to be the architectural safety net for the entire refactor.
  - A brittle text scan gives a false sense of protection and can let boundary regressions land unnoticed.
- Clean fix:
  - Replace the text scan with an AST-based import walker.
  - Resolve both `ast.Import` and `ast.ImportFrom`, including relative imports against the current module path.
  - Keep the same policy assertions, but make the detection semantic instead of string-based.
  - Add focused tests proving the checker rejects both absolute and relative forbidden imports.

### 3. Medium: the refactor introduced two canonical rectangle models with the same shape, and the observation builder now has a conversion shim because of it

- Files:
  - `pnc_automation/core/vision/image/models.py:8`
  - `pnc_automation/core/vision/image/models.py:23`
  - `pnc_automation/app/pnc/vision/observation_builder.py:500`
- Problem:
  - `Region` and `Bounds` now both represent the same `(x, y, width, height)` rectangle with the same `center()` behavior.
  - `ObservationBuilder` needs `selector_to_bounds()` just to convert one rectangle type into the other.
  - The helper also uses a delayed import and loose `object` typing even though there is no real semantic benefit in keeping the types separate here.
- Why it matters:
  - This is direct duplication of one concept under two names.
  - It adds conversion code, weaker typing, and extra mental overhead right after an architecture cleanup whose goal was a single canonical home per concept.
- Clean fix:
  - Collapse to one canonical rectangle type in `core.vision.image.models`.
  - Either:
    - remove `Region` and use `Bounds` everywhere, or
    - keep one class and alias the other name only if the API vocabulary still matters.
  - Delete `selector_to_bounds()`.
  - Tighten the related type signatures in `SelectorMatch`, OCR helpers, and observation-building code.

### 4. Low: `app.authoring.config` now depends on a P&C runtime persistence naming helper

- File: `pnc_automation/app/authoring/config/models.py:9`
- Problem:
  - `AccountConfig.artifact_directory_name` depends on `pnc_automation.app.pnc.persistence.artifact_naming.format_account_artifact_directory`.
  - That pulls the authored-config layer into a P&C runtime persistence package.
- Why it matters:
  - It weakens the ownership split introduced by the architecture refactor.
  - Account artifact-directory formatting is not really P&C persistence behavior; it is either generic storage naming or runtime assembly logic.
- Clean fix:
  - Move the account directory formatter into a neutral package, likely `core.infra.storage` or a small `app.shared` helper if it is application-specific but not P&C-specific.
  - Alternatively, remove `artifact_directory_name` from `AccountConfig` and compute it in the runtime wiring layer that actually owns artifact persistence.

## Recommended Cleanup Order

1. Fix the selector template-root path and add a regression test.
2. Replace the architecture text scan with an AST-based boundary checker.
3. Collapse `Region` and `Bounds` into one canonical rectangle model and remove `selector_to_bounds()`.
4. Move account artifact-directory naming out of `app.pnc.persistence` or compute it at runtime instead of in authored config models.

## Validation Notes

- Confirmed locally:
  - `py -3 -m unittest tests.test_package_architecture tests.test_app`
- Not run:
  - `pytest` is not installed in this environment, so I could not use the repo's pytest entry path for broader validation.
