# Standalone plan: Join Alliance invitation dismissal verification

Created: 2026-09-16. Updated: 2026-09-17.
Status: fix implemented and merged in `4f1e119`; live verification deferred.

This is the sole follow-up plan for the Join Alliance popup bug, outside the
entire 43-plan vision epic. On September 17 the user explicitly removed its
verification from the epic's worker assignments and acceptance gates. Resume
the original epic without waiting for this popup. This plan is retained for
later scheduling; its extraction does not claim the pending check passed.

The original failure target is configured account `3xx_spies`, instance
`bs-3xx-spies`, kingdom `K303`, castle **`K3033849ba8778`** (historical level 5).
Resolve current configuration, role, lease and identity before any future
test. Naming the historical castle does not authorize switching to it.

## Current implementation and remaining work

`4f1e119ae3f7a6d9e5e8891c81347a3656fbf4d3` (already on main) fixes
the canonical OCR geometry path by selecting the unique detected button
segment containing the Cancel anchor. It adds the post-Home captured fixture
and both-publisher regression in
`tests/integration/vision/test_alliance_invitation_captured.py`.
Do not reimplement that fix or broaden popup eligibility without new evidence.

Devin live turn 005 in
`.local-data/worktrees/vision-v01-foundation/.local-data/devin-live-test/runs/home-atlas-route-refresh/`
tested candidate `e3edc7d` containing the fix on the original target. The
invitation did not naturally appear after Home, so this regression was
`not_run`, not passed. The user's earlier manual dismissal and a startup-only
dismissal do not prove automated post-Home recovery.

When this standalone plan is scheduled:

1. Confirm the candidate contains the existing fix; reuse valid captured
   regression evidence. Investigate and change code only if actual evidence
   reveals a remaining defect. Review any corrections independently and run
   the relevant offline checks before live validation.
2. Delegate one bounded non-spending check through `devin-live-test` on the
   original target when the invitation naturally appears after Home. Require
   both publishers to expose a measured Cancel excluding Join/Apply, then one
   canonical Cancel action and a newer clear-Home observation. Preserve the
   exact revision, screenshot/observation/action evidence and lease cleanup.
3. If absent, retain pending status without relogin or reproduction loops.
   If failed, retain expected/actual behavior and the recognition gap, fix the
   proven defect, and review/retest that boundary before accepting it.

No joining, spending, account/castle switching or forced invitation is
authorized. Preserve pre-existing instances and release the canonical lease.

V20, V22 and V30 acceptance no longer includes this dedicated regression.
Their own feature routes, content and return checks remain required. A popup
that actually obstructs one of those routes is still recorded as an external
obstruction; do not bypass guards or call an unexecuted route passed. Continue
independent packets. V08/V37 Alliance feature work remains in the vision epic.

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

## Original implementation scope (historical)

Steps 1–3 describe the original design now implemented by `4f1e119`; step 4
is the outstanding standalone live proof. The diagnosis above refers to the
pre-fix baseline and is retained for provenance.

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
