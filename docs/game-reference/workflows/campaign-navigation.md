# Campaign navigation surfaces

**Build:** [PNC 5.0.203 / 233](../PROVENANCE.md). **Evidence:** client source verified for Campaign chapter and stage state ownership; offline saved transitions and fixture geometry checked. No Campaign action was performed for this note.

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
[capture findings](../../../reviewed_plans/PNC_NON_YOLO_CAPTURE_FINDINGS_20260913.md)
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
