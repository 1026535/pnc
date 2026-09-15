# Remaining non-YOLO recognition checklist

> **Status: DROPPED — superseded 2026-09-15.** This is historical evidence, not an active execution plan. Use the [modular vision plan](../reviewed_plans/PNC_VISION_MODULAR_PLAN.md) and [replacement/retained-requirement map](../reviewed_plans/vision_modules/PLAN_RETIREMENT.md). Historical ownership, accounts, budgets and resume instructions below are inactive. Retirement does not claim every historical defect is fixed.

## Popup-recognition correction status (September 15, 2026)

The popup slice is now implemented as demand-driven work shared by
`ObservationBuilder` and `NavigationPerception`: ordinary base identity is
established first with blocking popup profiles excluded. A recognized base screen
skips named popup matching and generic modal/X recovery. It runs the single bounded
exact guard scan only after coherent compact foreground panel geometry is measured.
An UNKNOWN base considers session/epoch-eligible known popup profiles and runs that
same bounded exact guard scan. The scan retains
semantic precedence; generic visual fallback runs from that same pass only when
neither named visual evidence nor an exact semantic guard owns the frame.

Catalog schema v4 validates typed controls for every blocking profile that dismisses
its surface (`close_x`, `popup_back`, `close_text`, or `cancel`). `PopupOverlayObservation` carries
measured current-frame controls through both publishers. Generic X fallback requires
a coherent modal boundary and one unique in-modal X; partial, multiple, outside-modal,
HUD, navigation, and Home evidence remains `UNRESOLVED` with no action. The shared
session owner keeps login families eligible through pre-login screens and disarms
them only after a proved in-game base transition; the session epoch re-arms them.

Savannah uses the original 540 reference as its sole named-profile reference plus two
900 holdouts. The named anchors contain only stable icon/artwork/panel chrome; the
price, timer, reward count, mutable VIP level, countdown, and controls remain outside
identity anchors. VIP uses a static crest wing and VIP wordmark, qualified against
one earlier and two fresh `serious_stuff` holdouts; Valiant uses reviewed static
artwork. Both retain separate typed close controls. A later authorized `main` / `K157 Sword NPC` capture closes
the Lucifer gap: two independent static artwork regions establish its identity,
while its separate gold upper-left arrow publishes popup-owned `POPUP_BACK`. The
canonical executor tapped the measured point once and received a newer Home frame;
subsequent exact roster preflight verified `K157 / Sword NPC / level 29` and returned
Home. No Android Back, price, reward, resource, or castle-switch action was used.

Current continuation of [the active plan](PNC_NON_YOLO_RECOGNITION_PLAN.md), September 13–14, 2026. This replaces the earlier first-slice inventory and its stale full-frame/Farm/Alliance claims. Work resumed in the original dirty `codex/non-yolo-recognition-continuation` worktree at HEAD `93798a6`; the handoff's 29 modified tracked files and untracked implementation work were preserved.

All paths below are worktree-relative. `V/` means `tests/integration/vision/`. **Producer qualified** means the stated saved-capture contract has a current production-path regression; it does not mean independent holdout accuracy, workflow success, or combined-main acceptance. Synthetic parser tests establish semantic parsing only. New source-adjacent and resized examples remain reference evidence.

## Shared contract

- [x] Both observation paths establish visual screen/layout and global foreground ownership before ordinary semantic content reads. UNKNOWN, unsupported viewport, conflicting identity, and unresolved guards abstain before content enrichment. Late contradictory content evidence is rejected.
- [x] Whole-screen OCR is removed from the PNC observation boundary, guard/content/fallback plans, region context, discovery, and diagnostic publication. The frame-bound context rejects unbounded/full-capture reads. Generic OCR outside this boundary and whole-image visual inspection remain available.
- [x] Exact warning/update/reconnect ownership remains a bounded guard scan. UNKNOWN frames run it directly; recognized bases run it only after coherent compact foreground panel geometry is measured. Generic modal/X fallback is UNKNOWN-only; startup uses reviewed visual identity or near-black pixels. Screenshot filenames and hypothetical loading text are not evidence.
- [x] Visual controls retain measured bounds and current frame/screen/layout. Semantic additions publish only registry-declared OCR labels, typed fields, and rows. They cannot invent or overwrite a measured control or replace independent identity.
- [x] Known modal Confirm/Cancel candidates require current panel/button geometry or an independently proved visual layout and its measured control. OCR padding cannot supply an action. Missing compact-panel geometry remains UNRESOLVED; the full-width portrait invitation has its own visual profile and Cancel template. Missing Cancel retains the blocking identity without an action.
- [x] Missing required fields retain independent facts and diagnostics. Castle name diagnostics identify each row separately, so a later success cannot hide an earlier missing name. Diagnostics/discovery export only already-acquired OCR, including zero-read unknown frames. No diagnostic OCR or replacement tiling exists.
- [x] Blocking visual popup profiles publish typed `CLOSE_X`, `CLOSE_TEXT`, or `CANCEL` candidates only from current-frame measured controls. Alliance invitation Join/Apply controls never become dismissal candidates; known identity without a control remains blocking with no action.

Proof: `V/test_guard_captured_regions.py`, `V/test_content_label_publication.py`, `V/test_observation_diagnostics.py`, `V/test_observation_request_scoping.py`, `V/test_selector_discovery.py`, the screen-decision contract, and bounded-context/region-plan unit tests. Both production paths use the same native-frame OCR context.

## Required producer cases

| Case and consumer facts | Current producer qualification | Relevant negative and evidence |
|---|---|---|
| Home, More, Settings; global blockers | Existing visual layouts retained. Update, reconnect and Shield warning have bounded message reads and measured foreground controls. Android launcher has a captured visual profile. | Missing panel/button, conflicting overlay, wrong candidate scope, and unknown frame suppress actions. Publisher/near-black loading are visual; the saved commercial offer is explicitly not loading. `V/test_loading_observation.py`, `test_system_popup_observation.py`, `test_popup_observation.py`, `test_visual_popup_ownership.py`, `test_guard_captured_regions.py`. |
| Research and Institute | Development rows, normal blue Research, detail/active identities, settled Economy/Military/Fortification detail variants, and reviewed queue controls preserved. Detail OCR is confined to its content panel. | Premium Research Now cannot supply normal Start; busy blue Research does not prove idle-queue eligibility; active detail cannot supply Start; overlay hides background controls. `V/test_research_captured_variants.py`, `test_research_tree_visual_controls.py`, `test_research_queue_navigation.py`. Non-Development tree-node selection remains a consumer/producer dependency below. |
| Farm detail and construction | Independent Farm profiles now exist. Levels 1/45 and 7/45, construction level 0/1, title and ordinary Build/Upgrade controls are qualified through both paths. Earlier “Farm has no profile” is obsolete. | Missing title/level preserves independent controls; construction cannot become upgrade; premium controls remain distinct; satisfied Requirement does not publish unmet facts. `V/test_farm_visual_profile.py`, `test_building_captured_flows.py`, `test_building_level_publication.py`; raw 0061–0063 and 0233–0243. |
| Institute unmet prerequisite | Raw 0055 proves layout `institute_upgrade_detail`, level 22/45, unmet Castle level 23, and measured prerequisite Go. Both paths publish labels only when that aligned control remains visible. | Erasing the first Go suppresses unmet facts/action even when the lower Builder Set Go survives. Red/ineligible Upgrade and category controls are absent. `V/test_institute_prerequisite_captured.py`; independently annotated native bounds. APK source corroborates distinct prerequisite/equipment controls in `docs/game-reference/workflows/building-upgrade.md`. |
| Build Queue and warning/confirmation | Centered queue identity, active building/timer row, idle-row abstention, and warning foreground ownership qualified from saved captures through both paths. | Empty/idle queue does not establish a building level or completion. Missing field cannot invent title/timer; premium speedups and confirmation are separate. `V/test_building_captured_flows.py`, `test_build_queue_observation.py`, `test_building_confirmation_observation.py`, `test_upgrade_warning_guard.py`. |
| Alliance compact/tabbed home | Participating tabbed and compact layouts have separate visual profiles, measured member/tab controls, and bounded status text. | Wrong layout cannot inherit another layout's geometry; a seasonal tab is not a universal unlock rule. `V/test_alliance_captured_layouts.py`, `test_alliance_remaining_visual_contracts.py`; seasonal source note retained. |
| Alliance member and Hall Reinforce rows | Separate screen/layout identity, native complete-card boundaries, bounded name reads and measured blue actions. Raw 0156 has four complete Manage rows; 0182 has six Reinforce rows. Captured both-path tests cover 540/900 viewports. | Clipped/shifted cards abstain; Reinforce cannot publish Manage; missing identity cannot gain row controls from text. `vision/alliance_member_rows.py`, `V/test_alliance_member_captured_rows.py`. Sanitized fixtures retain only safe static identity pixels from their own source. |
| Alliance Manage, Hall, remote profile | Leader/ordinary Manage profiles remain distinct. Hall level 22/45 and its static controls are qualified. Remote Gear profile uses independent Gear/Alliance Info chrome and a bounded exact name field. | Profile name survives missing Mail; ambiguous/missing name remains missing. Personal Info is not Manage; Hall Reinforce is not ordinary member management. `V/test_alliance_remaining_visual_contracts.py`; raw 0158, 0178/0179, 0181. |
| Actual game loading and portrait invitation | The new 3xx capture's logo/tools establish passive loading. Builder stops before extra selector OCR after the global foreground guard. Separate portrait/message anchors establish the invitation footer; only its current Cancel template is published. The legacy invitation shares the same layout with independent identity anchors. | Missing loading anchor, commercial offer, foreground Update, erased invitation identity, erased Cancel and foreign unresolved guard preserve abstention/foreground ownership. `V/test_loading_observation.py`, `test_alliance_invitation_captured.py`; real RapidOCR both-path postfix replay passes. These are correction references. |
| Unjoined Alliance landing | Saved 3xx pixels independently establish `PNC_ALLIANCE_JOIN` / `alliance_join_landing` from Odin and the Join Alliance banner, with no control or content OCR. Both real-RapidOCR paths preserve the identity and use one bounded global guard crop. The existing `open_alliance_home` consumer now stops with its intended not-joined error. | Missing anchor, invitation/Home negatives and foreground Update prevent false ownership. This corrects the prior unsupported-onboarding disposition; an enum-only explanation was insufficient once the actual consumer dependency was identified. No Join/Create action is inferred. |
| Mail and Compose | Player/Alliance/System mailbox semantics and supported thread rows retained. Captured centered Compose reads only requested recipient, subject and body interiors after independent layout proof. Empty/focused/populated states have native provenance. | Missing is distinct from empty; wrong mailbox, erased field and foreign overlay abstain. No Send is created by OCR. `V/test_mail_compose_captured_fields.py`, `test_chat_mail_captured_content.py`, `test_mailbox_member_observation.py`; raw 0010–0018. A sanitized mailbox body cannot prove emptiness. |
| Exact castle identity | Saved core frames 0042 and 0108 both publish selected K157 / `0 sticker NPC` / level 15 through both paths. Roster text locates the name; a tightly bounded single-line field read preserves the visible internal space. The new 3xx capture exposed a complete eighth card below the old list crop; the corrected semantic viewport now includes it and publishes exact K303 / level 5. | Missing/fragmented name removes selected identity while Back remains. `0 stickerNPC` stays unequal; no alias, fuzzy matching or expected-target rewrite. `V/test_castle_identity_captured_fields.py`; only the core handoff's referenced replay evidence was consulted. The new bottom-card failure became a correction reference, not an independent accuracy success. |
| Coordinates | Canonical coordinate bar reads use its prepared crop. June 13/14 coordinate-dialog captures now have independent K/X/Y/panel profiles and measured Go. Existing zero-glyph and missing-label numeric cases retained. | Coordinate-only observations remain action-ineligible and cannot invent Search. Missing dialog identity/Go, wrong label and incomplete numeric evidence abstain. `V/test_coordinate_bar_local_fixtures.py`, `test_coordinate_dialog_local_fixtures.py`, `test_coordinate_dialog_observation.py`. |
| Campaign | Existing map, Chapter 10 and stage 10-3 profiles preserve measured row/Challenge/Close controls. Stage has no consumed semantic fields and therefore uses only the global guard read. | Missing control, wrong row and blocking overlay abstain. Challenge does not imply mode, AP cost, battle readiness or victory. `V/test_campaign_visual_profiles.py`; Formation/result dispositions below. |
| Gathering/March | Selected resource node and empty/populated formation profiles preserve measured Gather/Dispatch controls and content provenance. | Empty formation or missing control cannot invent Dispatch; troop capacity is not march slots; overlay suppresses actions. `V/test_gathering_march_visual_profiles.py`; active/report receipt disposition below. |
| Quest/Bag and Chat | Existing row quantity/progress, Resource-tab ownership, sender/message association and composer contracts remain. Real-OCR replays cover six Bag rows, five Daily rows and requested Chat transcript content in both paths. | Clipped rows, unsupported announcement/message-only rows, foreign tabs and overlays retain explicit abstention. Cheap Chat navigation requests intentionally omit transcript rows. `V/test_chat_mail_captured_content.py`, Chat request/fragment/row tests, daily/resource unit tests. |

## OCR-region review

The former `GUARDED_FULL_FRAME_REUSE` policy is gone. Capability gating now requires the exact independently accepted screen. Content plans do not serve as screen discovery.

Removed unused broad reads include World Map bottom HUD/navigation text, Compose header/Send text, Settings/More controls, Alliance static controls, Hall capacity/empty-state text, Stage body, and the unused Castle/Warehouse/Goddess body regions. Castle's exact level uses a 97×40 reference field with one RGB 3× enlargement; the strict `17/45` parser remains unchanged. Real RapidOCR confirms the Castle, Warehouse and Goddess levels at both supported sizes through both paths. The existing World Map coordinate-rejection consumer fact retains its own small status crop; it survives a coordinate miss and is suppressed by an overlay. Remote profile name and selected castle name are narrowly owned fields. Dynamic scroll bodies remain bounded semantic viewports where the existing parser consumes the complete list; they are not arbitrary screen tiles. Unqualified enum-only families do not acquire content merely because a region table exists. Research detail uses its detail panel rather than the full tree viewport.

The prior centered modal crop statement belongs to the pre-popup-change OCR design and is retained as stale historical evidence. The current contract runs that bounded exact scan only after the base pass is UNKNOWN, then lets the same scan fall through to generic visual X detection when no known visual evidence exists. No second exact OCR/parser pass is performed. Real-OCR reports record exact bounds, call counts, processed area and cache outcomes; production-path lifecycle tests also assert that an expired popup phase performs no popup-anchor preparation or template matching.

## Failure triage and validation

The saved run's **108 failures and 11 errors are not an accepted baseline**. The case-by-case audit is `.local-data/reports/vision_failure_triage_continuation.md`. Those counts and the earlier **2,052-test acceptance are pre-popup-change/stale historical evidence**, retained for auditability. Dispositions:

- Captured profile-name, building publication, exact castle field, coordinate dialog, launcher and current modal geometry gaps were implemented and retained as captured production regressions.
- Missing WIP assets/catalog references and stale method signatures were repaired.
- Uniform-background OCR positives were moved to explicit canonical semantic-parser tests. Their meaningful row/field/identity comparisons remain. Actual captured positive/negative tests separately prove screen and control ownership.
- OCR-only popup words no longer prove a popup on a uniform or unchanged background. Overlay tests now use actual captured panel/button pixels and retain foreground suppression assertions.
- No previously failing run, newly unknown required fact, or reduced test count is accepted as evidence of success.

Focused checks and the final validation commands are recorded in the implementation report and `.local-data/.test-impact`. The pre-popup-change run above remains historical. Current popup acceptance covers named Savannah reference plus two holdouts, Lucifer live reference and typed popup-back, three independent VIP holdouts, Valiant, Alliance typed Cancel, generic Savannah fallback, recognized-base ownership, session/epoch eligibility, and partial-evidence abstention through both production publishers. The quiescent focused results are: `integration.vision` **447 passed, six skipped** and `integration.workflows` **201 passed**. `affected --base origin/main --explain` selected all 306 portable modules and passed **2,184 tests with seven skips**; `full` independently passed **2,184 tests with seven skips**. Installed catalog/asset validation and hashes remain part of the final handoff.

The Lucifer live report is `.local-data/reports/popup_live_lucifer_main_20260915.json`.
Its before frame is `artifacts/2026-09-15/main/20260915T040726Z_live_lucifer_main_before.png`;
the fresh Home frame is `artifacts/2026-09-15/main/20260915T040732Z_live_lucifer_main_popup_1.png`.
Their fingerprints differ, and the measured popup-back bounds are
`(30, 13, 100, 95)` with action point `(80, 60)`.

The opt-in `3xx_spies` smoke captured an Alliance invitation, published one typed
`CANCEL` at measured bounds `(327, 873, 216, 72)`, dispatched it through the
canonical observed-action executor, and obtained a newer Home frame with a distinct
decoded fingerprint. The before/action/after record is
`.local-data/reports/popup_live_smoke_20260915T030844Z.json`; the corresponding
captures are `artifacts/2026-09-15/3xx_spies/20260915T030844Z_live_gift_center_3xx_home_start.png`
and `artifacts/2026-09-15/3xx_spies/20260915T030848Z_live_gift_center_3xx_home_live_gift_center_3xx_home_interruption_popup_1.png`.
No resource spending, Join/Apply, message, account switch, or castle switch occurred.

## Explicit integration and acceptance dependencies

- **Exact castle consumer identity:** A must reconcile its target/journal exact string with the saved evidence `0 sticker NPC`. It must not make `0 stickerNPC` equal through fuzzy matching or producer aliases. The recognition replay is qualified; the core's mutation authorization/journal acceptance remains A-owned.
- **World coordinate selector:** the measured magnifier now publishes the existing `PNC_WORLD_SEARCH_BUTTON`. `PNC_WORLD_COORDINATE_BAR` remains only a parsed, non-actionable label. A must change its coordinate-dialog edge at `navigation_core.py:1038` from the label to the measured Search selector, then verify opening the dialog with fresh frame proof. No workflow edge was edited here.
- **Research:** `ResearchTask.plan` selects a row before Start, and queued Start still lacks an explicit idle-queue predicate. Busy blue-button captures do not establish eligibility. Economy/Military/Fortification tree-node selection remains outside the existing Development row producer.
- **Campaign:** `CampaignTask.verify` expects `PNC_BATTLE_PREP`; raw 0088 is Hero Formation with Challenge, whereas the existing Formation parser recognizes Save Form. A owns that workflow mismatch. No stage-specific AP value is copied into a global cost or Formation contract.
- **Gathering:** the existing consumer verifies returned World Map or a proved slots decrease, not active-collection/report receipts. Raw 0148–0152/0215 remain correlated evidence. Available march slots remain unknown.
- **Unsupported routes/receipts:** Transport Resources zero-selection form is not the Alliance Member recipient list. Native account UI is not the legacy Login/Continue route. Actual mail send/delivery receipt, unsupported Formation/result contracts and march-slot statistics remain unsupported; no credentials, recipients or success signals were invented.
- **Cross-task tests:** preserve the existing `tests/unit/app/pnc/navigation/test_navigation_core.py` adaptation and review it during integration. It now uses the bounded guard plan, current layout-aware enricher signature and captured update panel. Core runtime test doubles received the same signature and temporary artifact-path correction. No navigation/core/workflow production behavior or other worktree was edited.
- **Independent evidence:** newly captured same-session Alliance/member/profile, Farm/construction/queue, Institute, Compose and castle variants are reference evidence. Resizes and neighboring frames are not independent holdouts. The manifest and annotations record provenance honestly; missing independent holdout groups remain an explicit promotion gate.
- [x] Historical pre-popup post-review gate for the earlier three reproduced fixes: 2,052 run / 2,046 passed / six skipped / zero failures or errors. The current popup gate is the 2,150-test result above.
- [x] Installed-package asset qualification; the review corrections do not change the verified catalog or assets.
- [ ] Independent holdout acceptance for newly qualified layouts that currently have only reference captures.
- [ ] A-owned combined-main/consumer acceptance.

The user's later authorization permits in-game actions on `3xx_spies` with an unlimited resource budget. Bounded captures used that configured `live_testing` target and the canonical lease. The initial launcher foreground parser failed on `mCurrentFocus`; a reviewed launcher capture and the existing configured `session.launch_app()` allowed continuation. Normal in-game foreground and fresh-frame checks then worked. Across two interactive scopes, 14 inputs were dispatched: two configured launches and twelve inspected navigation/dismiss actions. The final scope returned to Home and released its lease. Stale input attempts were refused and required fresh review. No resource spending, join, message send or account/castle switch occurred. The subsequent review corrections and verification are entirely offline; the user authorized delivering them on the existing feature branch before integration.

The active K303 castle is level 5 and unjoined on build `5.2.77 / 5.0.201.227`. It supplied new Home/More/Settings/roster/idle Build Queue captures, loading, invitation, and Alliance onboarding. Idle Queue preserves Idle/Inactive without inventing upgrades. The roster, loading, invitation and unjoined landing failures were corrected and qualified as reference evidence, including real RapidOCR through both paths. A joined castle target was requested for independent member/Manage/Hall/profile evidence; none has been supplied. The initial launcher parser defect remains A-owned, but is no longer a blanket blocker to capture. Offline implementation readiness and integration/promotion readiness remain separate.
