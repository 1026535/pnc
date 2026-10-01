# Campaign navigation surfaces

**Build:** [PNC 5.0.203 / 233](../PROVENANCE.md) for recovered client source; later live builds are noted separately. **Evidence:** client source verified for Campaign chapter and stage state ownership; offline saved transitions and fixture geometry checked. Later live actions are dated below.

This note covers the bounded Chapter 10 navigation evidence represented by the portable fixtures. It does not establish a general Campaign catalog, mode eligibility, battle-prep reachability, or server acceptance.

## Saved transitions and source correspondence

The saved transition frames are the Campaign map, Chapter 10 path, and stage 10-3 detail captures in the `2026-09-12/serious_stuff/campaign_navigation` group. Their portable counterparts and source crops are recorded in [`replacement_core_provenance.json`](../../../tests/data/screen_recognition/replacement_core_provenance.json): `campaign_map.png`, `campaign_chapter_10.png`, and `campaign_stage_10_3.png` retain the reviewed map, title/path, and stage-detail regions.

The recovered client source keeps the same distinctions. `scenes/copyzonesmap/control/copyzoneschapterlayer.lua`, `CopyZonesChapterLayer:refreshChapterFunc` at line 88 and `refreshChapterItemFunc` at line 108, populates chapter items from `CopyZonesData` and their open state. `scenes/copyzonesmap/clip/copyzoneschapteritem.lua`, `CopyZonesChapterItem:OnMouseClick` at line 241, sends the selected chapter position and chapter id into the Chapter path surface. `commands/copyzones/copyzonescommand.lua`, `CopyzonesSend.RequireAttack` at line 132 and `command.Attack` at line 294, owns the later stage attack request and response updates. The shared `handler/slgwar/handler/slgwarbasehandler.lua`, `SlgWarBaseHandler:UpdateFightingPower` at line 35, distinguishes Campaign attack kinds while updating formation power; it does not prove that a visible Challenge control is safe to activate.

## Automation implications

The visual profiles independently identify the map, Chapter 10, and stage 10-3 layouts. OCR content enrichment publishes only the observed `10 Grandia Ruins` Chapter row on the map and the observed stage `3` row on the Chapter 10 surface, each with measured action geometry. The stage detail profile publishes the measured Challenge control. These facts are frame-bound and remain separate from battle-prep or action-success observations.

The saved frames prove no mode label or mode-specific eligibility. Producers therefore omit `mode`, locked nodes, unobserved stages, and any inferred battle-prep transition. The generic Campaign map entry selector remains unsupported until an independent producer is reviewed.

**Confidence:** high for the three saved visual identities and the measured Chapter 10/stage 3 geometry; medium for mapping the visible labels to the recovered `CopyZones` source because the source build and saved transitions are separate evidence layers. **Remaining uncertainty:** current account progress, mode variants, disabled or locked state changes, server-side prerequisites, and the exact post-Challenge flow require separate evidence.

## Formation and attack boundary inspected September 13

**Client source verified, same packaged build:**
`uis/copyzones/copyzonesfightwin.lua`,
`CopyZonesFightWin:openHeroBattlePosWin`, opens
`CommonSelectHeroBattlePosPanel` with the selected `passId` and a selection
callback. That callback invokes `sendChanegeCmdFunc`, which checks current power,
builds the hero positions and calls `CopyzonesSend.RequireAttack`. The request
wrapper supplies the pass and heroes; `command.Attack` updates stage data and
starts the battle from the response. Opening formation and requesting an attack
are distinct client operations.

This supports a bounded automation contract ending at independently recognized
hero formation. It does not identify the current pixels of either Challenge
control. The saved live sequence in the
[capture findings](../../../plans/reviewed/vision/PNC_NON_YOLO_CAPTURE_FINDINGS_20260913.md)
separates stage 6-5, Hero Formation, battle and Victory; its formation frame has no
current stage/mode/AP labels. Preserve prior stage identity as transition context,
never as content observed on formation. The recorded 20 AP battle is one historic
receipt, not a global cost or a reason to repeat a battle for a navigation port.

**Confidence:** high for the inspected packaged client call boundary; current
control recognition, mode/eligibility and the selected live route still need
qualification. The later live build differs from the recovered package.


## Chapter 5 qualification, September 16

**Live-observed:** on `mega_old_acc`, the current active castle's persisted
southern map has a complete chapter-5 marker. One current-frame measured tap
opened `Ch.5 Costa Dorad`; the next capture showed nine numbered stage cores.
No stage, Challenge, battle, or spending action was taken. Build is unknown.
The source is runtime `20260916T094904Z_0fcbdd92` under the lead
`vision-v13-live/.local-data/devin-v13/live_chapter5_capture` artifacts.

The tracked `campaign_chapter_5_path_20260916.png` is the settled source;
`campaign_chapter_5_loading_20260916.png` is a separate earlier capture with
the same title/coastline and no visible nodes. Two independent identity anchors
qualify this chapter only. Their loading-frame scores are 0.975/0.989; other
saved Campaign appearances score below 0.357/0.177. The reused measured Back
control scores 0.842/0.860 on these captures, with a profile-specific 0.82 floor
and saved map negatives below 0.217.

**Offline-proven:** both publishers bind the observed chapter 5 and nine
measured stage markers using RapidOCR 3.4.5 with the vendored PP-OCRv3
recognizer at its canonical `[3, 48, 0]` input shape. Seven markers publish
credible numbers — 1, 2, 3, 5, 6, 8, 9 — while the stage-4 badge reads only
`4` at 0.70451 and the stage-7 badge reads nothing credible, both below the
unchanged 0.80 numeral floor, so they stay UNREADABLE with `number=None` and
no action geometry rather than guessed values. They retain unknown mode and
completion.
The thin stage-1 numeral covers 0.0895 of its badge interior; the 0.08
white-foreground cutoff admits this measured badge without adding a candidate
on the other saved Campaign frames. Loading contains no inferred stage nodes.
The first measured Back returned to a recentered map. Its fixed-position map
identity failed, and the runtime stopped without another tap. The retained
`campaign_map_southern_view` profile now searches the same two distinct
chapter-label anchors within the observed map body. Recentered positive scores
are 0.928/0.932 against other Campaign-surface maxima 0.629/0.529, using a
0.90 floor for each anchor. The actual native return capture is tracked as
`campaign_map_recentered_20260916.png`; both publishers retain its frame-bound
Home portal. Final live return and integrated V13 acceptance remain pending.

## Shared Campaign entry recognition

**Artifact-observed:** own157_farm runtime `20260922T232718Z_26f6cf57`, captures
0041/0043, is a clear Campaign map that the prior broad node/terrain patch missed
during animation (node score0.9249 below0.93 while scene score0.9982 passed).
Cropping the existing reference patch to the Grandia Ruins label yields
0.9451/0.9490 on those frames without lowering its0.93 threshold. The independent
scene anchor and measured Home portal are unchanged. The two native map fixtures share one correlated validation group. The shared Home-to-Campaign entry and Home return passed the independently reviewed V44 turn012 route. Campaign chapter/stage parsing and formation remain separately owned.

## Early Chapter 2 map on K226, September 30

**Artifact-observed:** the M1 continuation discovery on `testing`/K226 saved a
native 900×1600 Campaign map at
`20260930T224605Z_core_20260930T224553Z_84d7c398_0003_d4_return_source.png`.
Misty Bay is a gold available row, Costa Dorad is locked, and the blue Home
portal is visible. The installed game build is unknown. The later-progress
southern-map Costa/Misty row anchors score 0.54352/0.60857 against their 0.90
bounds on this frame, while the existing Home portal scores 0.98280 against
0.95. Both observation publishers previously returned UNKNOWN and withheld the
portal. The original 900×1600 image is tracked as
`campaign_map_early_chapter2_20260930.png` with source hash in the manifest.

**Offline qualification:** a separate `campaign_map_early_chapter2` profile
requires the visually distinct locked Costa Dorad text and gold Misty Bay row,
both cropped from the observed map body outside the tutorial arrow, promotions,
and HUD. Both score 1.0 on the source against 0.95 and 0.9999997/0.99849 on a
second native frame captured seven seconds earlier during a changing promotion.
The second frame is same-session correlated validation, not an independent
holdout. Existing later map, Chapter, Stage, Home, and World fixtures do not
qualify the new anchors. The measured Home portal selector and Campaign-to-Home
edge are unchanged.

**Automation implication:** the saved frame can now publish a typed Campaign
map and fresh portal control. This does not prove a live portal tap or Home
return from K226. The next distinct live case is one observed portal action from
a freshly verified early map, followed by fresh Home and castle identity proof;
no stage, battle, or spending action follows from this profile.

## Chapter 10 locked path, September 30

**Live-observed:** V44 turn025 on `157_farm` opened Campaign and tapped the
uniquely observed Chapter 10 map row with a confirmed physical receipt. Native
capture 0040 visibly shows `Ch.10 Grandia Ruins`, one available gold stage-1
node, eight locked nodes, and the curved chapter Back. Captures 0040–0048 are
one session; 0048 is temporal confirmation, not an independent holdout. The
runtime classified the destination UNKNOWN and stopped before a stage tap.
The current game build is unknown. The unmodified 900×1600 capture 0040 is
tracked as `campaign_chapter_10_locked_20260930.png`, with artifact name and
hash in the screen-recognition manifest.

**Offline-proven:** the old Chapter 10 identity crop contained progress-dependent
numbered nodes and scored 0.50351 on 0040. The unchanged exact title anchor
scored 0.99246 and the measured Back scored 0.99744. A static mountain-terrain
crop from the older Chapter 10 reference scores 0.9984 on 0040 and 0.1147 on
the preceding Campaign map 0038; the older unlocked reference remains positive.
Title, terrain, and Back thresholds are unchanged. The gold stage-1 glow makes
the Hough circle cover a 65-pixel outer halo whose white-numeral fraction fails
the existing badge-core check. Testing its concentric inner disc against the
same gold and numeral thresholds yields stage 1; both production publishers
now expose only that measured stage as actionable and the other eight as locked.
Map and wrong-chapter negatives remain rejected.

**Automation implication:** fresh Chapter 10 recognition may confirm the prior
row dispatch and admit the current, measured stage-1 row. A read-only stage
detail/title observation and canonical return still require live proof; no
Challenge, formation, battle, or spending action is established here.

## Chapter 6 qualification, September 22

**Live-observed:** on the parked `testing` M1 run, the current castle's Chapter 6
marker opened `Ch.6 Marsh of Tear` with five numbered stage cores and four
padlocked nodes. The live diagnostic classified that visible path as UNKNOWN.
Canonical offline replay isolated the missed terrain anchor: 0.929546 against
its 0.95 bound; the title (0.991448) and Back (0.863272) anchors qualified. No stage, Challenge,
battle, or spending action was taken, and the refused Back dispatch was correct
while the frame stayed UNKNOWN. Sources are runtime `20260922T202247Z_d3962b64`
captures 0037/0038 under `2026-09-22/testing`, tracked as
`campaign_chapter_6_path_20260922.png` and
`campaign_chapter_6_path_holdout_20260922.png`.
These frames were captured seconds apart in one session. They share a capture
group and establish correlated temporal consistency, not independent-session
generalization, despite the second file's historical `holdout` name.

**Scoped calibration:** the `campaign_chapter_6` terrain anchor is bound at
0.92 — the only change; title identity stays 0.95 and Back stays 0.85. Both
native frames now score title 0.991448/0.991899, terrain 0.929546/0.929546,
Back 0.863272/0.863272, and the original mega_old_acc reference keeps
0.996420/0.999439/0.875636. Other saved surfaces stay far outside: worst
terrain 0.2764 (world map), worst title 0.3392 (Chapter 5 path), so no
other-chapter, map, World, Home, or popup appearance reaches the profile.
This remains a Chapter-6-only claim with no all-chapter generalization.

**Offline-proven:** both publishers classify both native RGBA frames as
`PNC_CAMPAIGN_CHAPTER` with a clear guard and the frame-bound Back control.
RapidOCR 3.4.5 binds chapter 6 and measured stages 1-4; the pulsing current
stage-5 node publishes no row rather than a guessed value, and the four locked
nodes stay `no_action` with `number=None`. No completion, AP, formation, or
battle state is inferred from the path frame. Live return acceptance and any
formation proof remain pending with the lead.

## Native stage ownership and map animation, September 22

**Artifact-observed:** M1 runtime `20260922T234747Z_82d60eea`, capture 0045
(`tests/data/screen_recognition/campaign_stage_6_5_20260922.png`), shows the
opened `[6-5] Marsh of Tear` detail, AP126/120 and Challenge cost12. The trace
classified it as `PNC_POPUP`, then recovery tapped its Close at 812,370;
capture 0046 shows the chapter after dismissal. The stage-entry tap succeeded
visually. Missing feature identity caused the task-owned modal to be dismissed;
the post-recovery chapter screenshot is not evidence that the tap did nothing.
Installed build was not recorded. Confidence is high for this captured sequence,
with no claim about other stage appearances or formation entry.

The `campaign_stage_chapter_6` profile qualifies the observed Chapter 6 stage
appearance using separate title and Enemy lineup patches. Existing Close and
Challenge controls are measured independently. No Chapter 6 stage number, battle
mode, completion or Auto-next state is inferred from the profile name. Stage
content still comes from bounded OCR.
Native gauge/cost crops need single-line normalization: the original900x1600
detector split the gauge into overlapping `126/` and `5/120` reads and missed the
cost. The gauge region now excludes the adjacent add-AP icon, and larger numeric
strips use the canonical context's28px preprocessing with native frame/region
provenance retained. Saved native reads are126/120 and12; reference reads remain
150/120 and12. No resource action is authorized by this evidence.

**Artifact-observed:** M1 runtime `20260922T233517Z_4ad73851`, capture0012
(`tests/data/screen_recognition/campaign_stage_6_4_20260922.png`), shows
`[6-4] Marsh of Tear` with the same AP and cost, but Challenge is to the left of
Blitz. The shared Chapter 6 identity anchors qualify this frame without a new
profile or lower threshold. Challenge is searched across the two observed
positions, and cost OCR is derived from its matched bounds. When Challenge is
not measured, its cost remains unknown. Blitz is not exposed as Challenge.
The two stage captures come from distinct runs on the same account/build, not
independent account validation. Corrected-candidate live acceptance is pending.

**Artifact-observed:** own157_farm runtime `20260922T232718Z_26f6cf57`, captures
0041/0043, is a clear Campaign map that the prior broad node/terrain patch missed
during animation (node score0.9249 below0.93 while scene score0.9982 passed).
Cropping the existing reference patch to the Grandia Ruins label yields
0.9451/0.9490 on those frames without lowering its0.93 threshold. The independent
scene anchor and measured Home portal are unchanged. The two native map fixtures
share one correlated validation group; the stage image is a reference, not a
holdout. Corrected-candidate live stage/return acceptance remains required.

## Chapter 6 stage reflow, September 27

**Artifact-observed:** M1 runtime `20260927T161139Z_cb7d3149` on `testing`,
candidate `d07b2d8f`, captured stages 6-4 and 6-5 in frames 0057 and 0069.
The native 900x1600 captures are retained unchanged as
`tests/data/screen_recognition/campaign_stage_6_4_20260927.png` and
`campaign_stage_6_5_20260927.png`; their manifest records original paths and
hashes. The title, lineup and Close moved upward while the footer moved down;
Challenge is still left of Blitz for 6-4 and centered for 6-5. AP126/120 is
centered above the footer. Installed build was not recorded. These two frames
share one session and are regression examples, not independent holdouts.

The Chapter 6 profile retains two independent identity anchors at 0.95.
Its existing title artwork is cropped to the invariant `Marsh of Tear` words,
excluding the bracketed ordinal. Title and lineup search bounds cover their
two observed positions; controls are still measured on the current frame.
The new captures score title 0.9670, lineup 0.9801, Close 0.9784 and Challenge
0.9813/0.9832. Neither anchor alone qualifies the stage. Ordinals remain
bounded OCR facts, with no stage number inferred from the profile.

**Offline-proven:** replay through both observation publishers retains clear
stage identity, frame-bound Close and Challenge, stages 6-4/6-5, AP126/120 and
cost12 on both September 22 and 27 native captures. Title OCR covers the
observed reflow. Gauge OCR first uses the existing right-hand numeric strip,
then the measured centered strip only when no credible pair was found;
conflicting credible pairs within a strip still abstain. Cost remains tied to
the measured Challenge bounds. No Blitz control, formation state or spending
permission is inferred. Corrected-candidate live C2/C3 validation remains with
the M1 owner.

## Challenge formation preparation, September 29

**Artifact-observed:** M1 runtime `20260929T050725Z_37cfd0b9` on `testing`,
candidate `8e1fa8dd`, capture0084
(`tests/data/screen_recognition/hero_formation_challenge_preparation_20260929.png`).
An authorized non-spending stage 6-5 Challenge tap opened the Hero Formation
preparation surface — the packaged `openHeroBattlePosWin` /
`CommonSelectHeroBattlePosPanel` path documented in the September 13 boundary
section — but the exact `8e1fa8dd` runtime classified it `UNKNOWN` with no
layout or controls. A later manual tap on the panel's top-left gold diamond
Back glyph returned to the typed 6-5 stage detail, and the reviewed chain then
reached Home at 05:18:41Z with no spending or formation mutation. The reconcile
capture `hero_formation_challenge_preparation_reconcile_20260929.png` decodes
identically to the reference frame; both share one invocation and are
correlated, not an independent holdout. Installed build was not recorded.

The `hero_formation_challenge_preparation` profile now qualifies this variant
on two independent invariant anchors — the `Hero Formation` title and the
`Deployable Heroes` section heading — plus the identity-only `Challenge`
caption to distinguish it from Save Form, all at the unchanged 0.95 floor, and
publishes only its measured Back control
(`PNC_CAMPAIGN_FORMATION_BACK_BUTTON`), withheld on the OCR-driven SaveForm and
any other Hero Formation appearance. The reviewed navigation graph gains the
non-spending edge PNC_HERO_FORMATION Back -&gt; PNC_CAMPAIGN_STAGE; any other
observed destination stops after that one owned tap. Formation
Challenge/GoFight/Save, hero edit, Auto, and continuation controls remain
unpublished, and no stage/AP facts are projected onto formation.

**Live-observed, September 30:** Final integrated candidate `4d26d721`
passed the zero-spend testing-instance run documented at
`.local-data/devin-live-test/runs/m1-v14-resume-preentry-20260927/turn-012/lead_review.md`.
The public Campaign operation normalized from a freshly measured zoom 1.0
Home view and reached the typed Campaign map in 38.86 seconds under an
explicit 45-second Home policy. Current Stage 6-4 and 6-5 detail, guarded
Hero Formation preparation and its dedicated Back to the same Stage 6-5,
then canonical Home, were observed on the same candidate. No final battle
action, hero edit, Auto toggle or resource spend occurred. Continuation
remains unknown, so no full-plan acceptance or mode availability is implied.
The bounded stage-title reader reported `of Tear Marsh` while the actual UI
read `Marsh of Tear`; current stage ordinals, AP, cost and owned controls were
correct. V owns review of the name field before name-based authority uses it.

## Current Chapter 10 stage detail, September 30 live028

**Live-observed:** V44 integrated turn028 on `157_farm`, candidate
`e9b99779`, frame0046 in
`artifacts/2026-09-30/C__Users_lebel_pnc_artifacts_devin-live-test_v44-4-integrated-turn028-20260930/`.
The public Campaign and Chapter 10 transitions succeeded. One confirmed tap
on the observed stage-1 row opened a dialog visibly titled `[10-1] Grandia
Ruins`, with Enemy lineup, 120/120 action points, a 12-energy Challenge, and
the top-right X. The running candidate classified it as blocking `PNC_POPUP`
and sent no subsequent tap; this was a stage identity failure, not a failed
row dispatch. Installed game build was not recorded. Frame0047 is a correlated
same-session final capture, not an independent holdout.

**Offline-proven on the saved native pixels:** The new
`campaign_stage_10_1_live028` variant requires its exact stage title and a
separate Enemy lineup anchor at the retained 0.95 threshold. It publishes
only the currently matched X as `PNC_CAMPAIGN_CLOSE_BUTTON` for the existing
Stage-to-Chapter return. Bounded OCR on both observation publishers reads
chapter 10, stage 1, `Grandia Ruins`, and 120/120 from the same frame. The
Challenge cost stays unknown because this read-only variant does not publish
the Challenge action. Erasing either required stage anchor removes this
variant, and the existing real popup fixture does not match it. An independent
current-build holdout and the actual Close-to-Chapter-to-Map-to-Home live return
remain pending.
