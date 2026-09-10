# Reviewed selector templates

`pnc_home_right_rail_gift_center_icon.png` is the interior of the blue/gold Gift Center shortcut, excluding its notification badge and background. It was cropped from the active testing castle's 900 × 1600 capture at `artifacts/2026-09-10/testing/20260910T204524Z_navigation_validation_1_before_case_1_post_action_1.png` and confirmed by the live Gift Center navigation report under `artifacts/navigation_audit/repaired/`.

The selector matcher currently uses native screenshot pixels for this catalog. This template is validated at 900 × 1600 only; a missing match at another resolution must remain a missing match. Do not infer visibility from a stored coordinate or lower the threshold to force a match. The normalized, multi-anchor screen identity profiles are separately owned by `app/pnc/vision/data/screen_anchors.json`.

The animated Event shortcut candidate remains under the audit artifacts, outside the runtime catalog, because it did not pass live validation. Missing template declarations are listed by `tools/audit_navigation_evidence.py` rather than populated with unverified crops.
