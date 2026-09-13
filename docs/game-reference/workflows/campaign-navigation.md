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
