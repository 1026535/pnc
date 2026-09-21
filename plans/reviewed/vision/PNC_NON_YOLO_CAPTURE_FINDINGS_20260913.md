# Non-YOLO live capture findings — September 13, 2026

This evidence update supplements the [implementation report](../../completed/vision/PNC_NON_YOLO_RECOGNITION_IMPLEMENTATION.md).
The previously published recognition foundation remains complete. New screenshots
are evidence for the next producer slices, not proof that those slices are implemented.

## Provenance and disposition

Live build: **5.2.76 / 5.0.204.235**, read from Settings capture 0186.
Recovered APK evidence remains **5.0.203 / 233**; it is not silently promoted to the
live build. The canonical leased `mega_old_acc` session captured 250 frames. The
existing K157 castle was the main target; existing K290 and K302 castles supplied
the nonparticipating Alliance layout and construction evidence. No new character
was created. The original K157 castle was restored to Home in frame 0250, and the
process exited successfully and released its reservation. The instance was preserved.

A fresh source-guided barracks probe used a new lease and saved nine frames under
`20260913T051219Z`. It also returned K157 Home and exited/released successfully.
It did not start training or spend resources; opening the barracks automatically
collected pre-existing completed Ace Champion training (visible receipt, might +23,600).

Package, relative to `.local-data/worktrees/non-yolo-recognition-continuation`:
`.local-data/artifacts/capture_gap_exploration/20260913T030954Z/`.
It contains immutable PNGs, `events.jsonl` with frame/input provenance, and
`evidence_sidecar.json` with manual annotations, hashes, source traces and replay
results. The ignored checkpoint is `.local-data/reports/capture-exploration-checkpoint.md`.
Raw private mail/account screens remain ignored; account frames 0199–0202 must
not be copied into tracked fixtures without removing sensitive background content.

## Captured boundaries

| Family | Evidence | Producer/consumer implication |
|---|---|---|
| Player Mail | 0010–0018: populated list, empty Compose, subject and body entry | Actual Compose entry is at bottom left. The working-tree correction replaces the obsolete upper-right geometry with independently matched visual publication; see validation below. No send occurred. |
| Research | 0027–0053: Economy, Military, Fortification trees, normal controls, busy/active/completed details | Broader category evidence now exists. The normal blue Research control can remain visible with **No idle queue**; visible control is not eligibility. Retain strict active-detail verification and premium exclusion. |
| Building upgrade | 0055 blocked Institute; 0061–0063 Farm upgrade/completed level; 0074–0077 Infirmary upgrade/active queue | Requirements, ordinary versus premium action, and an actual active queue are captured. Do not infer a target's completed level solely from an empty queue. |
| Campaign | 0087 stage 6-5; 0088 Hero Formation; 0090–0096 battle; 0097 Victory; 0098 chapter receipt | Hero Formation is a separate layout with its own Challenge control. Current prep frame does not display stage/mode/AP labels. A prior stage observation must not be relabeled as current-frame content. |
| Gathering | 0139 Farm target; 0140 empty/0146 populated formation; 0148 march; 0150/0152 collecting; 0215 report | Correlated ordinary gathering succeeded. Formation values are troop/load capacity, not available march slots. |
| Alliance | 0156 member list; 0157 leader Manage; 0161 ordinary Manage; 0168 allied territory; 0171 Transport; 0181 Hall; 0182 Reinforce list | Role/menu mode changes action geometry. Hall's empty reinforcement state still displays Send Back/Reinforce. Transport is disabled at zero selected resources. No member mutation/transport receipt is claimed. |
| Seasonal layout | 0166 participating K157 after normal-map return; 0193 nonparticipating K290 | Faction tab changes Alliance content position. Map identity alone cannot choose layout. See the [source-backed note](../../../docs/game-reference/workflows/seasonal-alliance-layout.md). |
| Castle selection | 0187, 0210, 0227, 0247 roster selection; destination Home/profile captures | Selecting an existing character row switches immediately. No Continue prompt was observed on this route. |
| Native account UI | 0197–0203 Account Settings → User Center → providers → email form → close | Current email form has one email field and Log In. Password and Continue are absent on this route; do not invent mappings to the legacy username/password chooser contract. No credentials were entered or submitted. |
| Construction | 0233 Build list; 0234 blocked Hall detail; 0238 outdoor list; 0239 available Farm; 0241–0243 completed Farm | New construction is now distinct from upgrade evidence: level 0, normal Build, premium Build Now, requirements/cost, and resulting level 1. The three-second build completed without a captured sustained pending queue. |

## Actual actions and receipts

- K157 normal Research: Food Output I, Wall DEF I, and Siege ATK I were each started
  once. Displayed total cost: **43,685 food and 18,713 wood**. One five-minute
  Research speedup was used; two one-minute Research speedups were returned.
  Economy and Fortification completion and Military active detail were captured.
  Do not repeat these actions during continuation.
- K157 normal upgrades: Farm 7→8 completed; Infirmary 9 upgrade entered the active
  queue. Both displayed zero payable resources. The Farm interaction also collected
  stored food, and opening the barracks collected pre-existing completed training.
  Those incidental collection events are not upgrade receipts.
- Campaign stage 6-5: one successful battle, **20 AP**, with Victory and chapter/AP
  receipt. The user reports progression-dependent AP costs of 10–20 in increments
  of two. Exact progression thresholds remain unverified; read the displayed cost
  rather than hard-coding 20 globally.
- Before leaving Lost City, exactly **one eight-hour Shield of Grace** was used
  (owned count 132→131). Protection was checked before event exit, after normal-map
  return, and after gathering; frame 0221 showed **07:10:48 remaining** at 04:50 UTC.
  No hostile scout or attack was performed.
- Neutral Farm level 6, K157 X231 Y479: one dispatch of **1,000 Buffalo Catapults**,
  no heroes. The current-target report in 0215 records **31.2K food** collected and
  returned. Earlier formation load was 31,279. Rounded report text is not an exact
  integer quantity. No second march was dispatched.
- K302 new Farm: ordinary Build once, **68 wood**, no diamonds; 0242 verifies 1/45.
- No mail/chat was sent, no reinforcement/transport was dispatched, no account
  credentials/configuration were changed, and no diamonds or real money were spent.

## Remaining decisions and acceptance

Replay inventories list missing selectors, which require contract review before
being treated as defects. In particular, the existing building requirement
selectors mean an **unmet** prerequisite with its associated Go action:
`building_workflow_support.building_requirement_is_visible` consumes the header
as a blocking condition. The satisfied Requirement section in Farm frame 0061
must not be published as that blocking condition merely to fill the inventory.
Likewise, missing `PNC_BUILD_OPTION_ROW` is not evidence that Build-menu rows are
unavailable: the replay already publishes the specific building rows. Review the
actual consumer contract before adding a redundant generic selector.

1. Implement and offline qualify the newly evidenced vision families through both
   production observation paths. Capture presence alone must not enable unsupported
   selectors or bypass overlays/provenance. Keep A's workflow/runtime ownership.
2. The working-tree Compose correction now publishes the independently matched
   lower-left control through both production observation paths, preserving frame,
   screen/layout and template provenance. Focused checks passed: 120 vision unit
   tests and 43 selected tests, including absent-control, non-Player and overlay
   negatives. A prepared consumer-fixture correction passes all 11 module tests
   and dispatches the actual scaled point through an offline fake actuator. The
   user authorized this narrow consumer-test exception after review; it is now
   applied. Final affected selection passed: 1,925 tests run, 1,919 passed,
   six skipped, zero failures/errors. Installed-package qualification is still
   outstanding for this working-tree correction; the implementation report records
   the exact base and commands.
3. The available-march-slot number remains unobserved. APK code compares the castle's
   buff-adjusted army limit with current own-army count, but screenshots captured
   troop capacity instead. Do not substitute that value or infer a current count
   from historical frames. A source-backed UI route or an explicit consumer contract
   change is still needed. The recovered `uis/camp/campdatawin.lua:UpdatePanel`
   (lines 73–76) displays busy armies and total limit, reached through
   `campmainpanel.lua:OnBtnMsg` (line 782). The current barracks' information button
   instead opens level unlocks (follow-up frame 0005); its corresponding statistics
   entry was not identified. A precise UI-route question is pending. Do not confuse
   that unlock page or the selected troop count with the required statistics page.
4. Mail send receipt needs the user-specified recipient/kingdom; the question remains
   pending. The prepared message is “Recognition validation — no action needed.”
   No assumed recipient is authorized by this document.
5. The native account-provider/email route and the legacy Login/Continue contract
   differ. Keep the absent legacy controls explicit until their actual route/build
   is established; do not log out or submit credentials merely to manufacture proof.
6. Complete independent holdout/negative annotations, installed-asset checks, focused
   real-builder regressions and affected selection after each implemented slice.
   A still owns combined workflow acceptance. Prior release test counts validate
   that release, not future changes made from this package.
