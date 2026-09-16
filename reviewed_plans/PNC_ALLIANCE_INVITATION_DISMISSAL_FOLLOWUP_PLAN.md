# Deferred: Join Alliance invitation dismissal

Date: 2026-09-16. Status: planned for later; not implemented or live-qualified.
The user manually dismissed this popup and explicitly kept it outside V22's
implementation scope. This follow-up is outside the 43 vision-packet count.

## Observed failure and provenance

On `3xx_spies`, after Home had already been recognized, an alliance invitation
showed Cancel and Join/Apply. OCR found Cancel at (380, 891, 112, 35) on a
900×1600 frame. Geometry qualification removed the control and produced
`weak_unmeasured_ocr_popup_cancel_button`; navigation correctly refused to act
on an unresolved screen. Join/Apply was not pressed.

- Source frame: `artifacts/2026-09-16/3xx_spies/20260916T204527Z_core_20260916T204516Z_27f807b6_0003_core_route_source.png`.
- Recognition gap: the same prefix plus `_recognition_gap.json`.
- Runtime trace: `artifacts/2026-09-16/3xx_spies/20260916T204516Z_27f807b6_core_trace.jsonl`.
- Devin's bounded diagnosis: `.local-data/worktrees/vision-v22-blacksmith-gear/.local-data/devin-v22/join-alliance-popup-recognition-gap.md`.
- Reviewed code baseline: `8681194`; installed game build was not recorded.
  Preserve the source image as an authored fixture when implementing; raw
  evidence remains in its configured artifact location.

**Repository-proven, high confidence:** `_qualify_modal_action_geometry` in
`pnc_observation_enricher.py` excludes the neighboring affirmative button only
when the OCR anchor lies outside the middle 40–60% of the image. This Cancel
anchor lies at 48.4%. Its scan therefore includes both footer buttons, while
`resource_inventory.detect_button_runs` accepts only one horizontal segment.

**Artifact-observed, high confidence:** lead replay with the existing detector
on the saved pixels found no button for scan x=184..688, y=804..1012. Narrowing
only the right edge to 560 measured Cancel at (326, 873, 217, 73). The narrowed
constant demonstrates the cause; it is not a proposed production coordinate.

**Repository-proven secondary constraint:**
`PopupRecognitionSessionState.allow` in `visual_screen_recognizer.py` suppresses
alliance-invitation visual profiles after `post_login_proven`. The typed visual
rescue in `observation_builder.py` consequently had no candidate in this session.
Devin observed recovery in a fresh session; matching the earlier exact frame
with that visual profile has not been independently established.

## Smallest implementation

1. Fix measured negative-action selection in the canonical geometry path. Use
   the recognized Cancel anchor to select exactly one real button segment,
   excluding its affirmative neighbor without fixed screen-percentage clipping.
   Reuse the existing pixel predicates; preserve other button-detector callers'
   contracts. Do not add a fallback point tap, new popup framework or lower the
   unresolved-screen guard.
2. Add the captured image and OCR evidence as one deterministic regression.
   Exercise recognition after Home within the same session through both
   production publishers. Require a measured Cancel control confined to its
   blue rectangle; Join/Apply must never become the recovery action. Masked or
   ambiguous Cancel stays unresolved. Verify interruption recovery consumes
   that typed control through the existing action owner.
3. Start with the focused popup/vision checks, then affected selection. Change
   session-family eligibility only if the corrected geometry path still needs
   the visual rescue; do not broaden all popup matching as an incidental fix.
4. Delegate one non-spending live check to Devin when the invitation next
   appears on the authorized `3xx_spies` active castle: capture → typed Cancel →
   confirmed clear Home. Do not trigger an alliance invitation or join merely
   to manufacture evidence. If absent, record live qualification as pending.

Acceptance requires the real captured regression, unchanged affirmative-action
exclusion, both-publisher agreement and the applicable live proof. The user's
manual dismissal is a test prerequisite, not automated-recovery evidence.
