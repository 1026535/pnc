# Remaining non-YOLO recognition checklist

Baseline for work package 1 of `PNC_NON_YOLO_RECOGNITION_PLAN.md`, reviewed September 13, 2026. Inputs: `.local-data/reports/non_yolo_recognition_coverage_20260912.json` (saved report: 47 samples, 19 source groups), active `tests/data/screen_recognition/manifest.json` (51 samples, 23 source groups), `tests/data/screen_recognition/manual_annotations.json`, current callers/tests, and `.local-data/artifacts/capture_gap_exploration/20260913T030954Z/`.

Path legend: all paths are relative to this worktree. `V/` means `tests/integration/vision/`; `W/` means `tests/integration/workflows/`; `U-T/` means `tests/unit/app/automation/tasks/`; `U-D/` means `tests/unit/app/automation/daily_maintenance/`; `U-N/` means `tests/unit/app/pnc/navigation/`; `U-V/` means `tests/unit/app/pnc/vision/`. Every listed test filename was verified under its prefix. Unless a producer file is shown, `_build_*`, `_add_*`, and `_build_observed_text_field_state` mean `pnc_automation/app/pnc/vision/pnc_observation_enricher.py`; `load_visual_screen_recognizer` means `pnc_automation/app/pnc/vision/visual_screen_recognizer.py`.

**Proved working** requires a current production-path regression plus reviewed visual/fixture evidence. **Reproduced gap** is captured or caller-visible work still needed. **Pre-existing unsupported** has no approved producer/evidence. Enums, planned catalog entries, static references, and screenshot presence alone never promote a case. New raw account/mail frames stay ignored and sanitized.

## Global contract

- [ ] Both `ObservationBuilder.build` and `NavigationPerception.build` validate frame provenance, independently resolve screen/layout and foreground guards, then read approved semantic regions. Shared owners: `PncObservationEnricher.recognize_guards`, `detect_interruption`, `enrich`.
- [ ] Remove whole-viewport OCR at the observation boundary: builder guard/fallback branches; `pnc_automation/app/pnc/vision/ocr_region_plan.py::compile_ocr_region_plans` unsupported-aspect fallback; `pnc_automation/app/pnc/vision/pnc_ocr_capabilities.py` guarded-full-frame families; and enricher full-frame region-resegmentation/reuse. OpenCV whole-image inspection and screenshots remain allowed.
- [ ] Missing facts publish unknown/missing while preserving independent facts; unresolved screen/layout/overlay makes background actions ineligible and emits a local gap report with zero additional OCR. Parsed content never creates controls.

First-slice progress: shared diagnostics now export already acquired OCR, unknown decisions, unresolved guards and terminal missing/error reads through both production paths without additional OCR, including zero-read unknown frames. Explicit required-field coverage remains part of region migration; this does not claim every parser-level missing fact is diagnosed. Evidence: `V/test_observation_diagnostics.py`, `tests/unit/core/vision/test_ocr_diagnostic_snapshot.py`, and the current section of the [implementation report](PNC_NON_YOLO_RECOGNITION_IMPLEMENTATION.md).

## Shared navigation and blockers

Screen/layout/facts: Home, More, Settings, loading/reconnect, update/invitation, generic popup, and return-home candidate-scope negatives; visual anchors prove identity and measured dismiss controls. Producers: `visual_screen_recognizer.load_visual_screen_recognizer`; enricher `_build_home_city_additions`, `_build_more_menu_additions`, `_build_more_settings_menu_additions`, `_build_loading_additions`, `_build_reconnect_popup_additions`, `_build_update_required_popup_additions`, `_build_popup_additions`.

Consumer/tests: `pnc_automation/app/pnc/navigation/screen_flows.py`, `pnc_automation/app/automation/engine/observed_action_executor.py`; `V/test_visual_screen_recognizer.py`, `V/test_navigation_screen_disambiguation.py`, `V/test_popup_observation.py`, `V/test_visual_popup_ownership.py`, `V/test_popup_close_rejection.py`, `V/test_loading_observation.py`, `V/test_observation_request_scoping.py`. Fixtures: `home_city_core.png`, `home_negative.png`, `more_overlay.png`, `more_sep01.png`, `more_sep04.png`, `more_live_b0.png`, `settings.png`, `settings_live_b0.png`, `loading_publisher_splash.png`, `update_over_bag.png`, `alliance_invitation.png`, `disconnect_negative.png`.

Expected/negative: candidate scope cannot suppress global guards; an overlay owns the frame and hides background controls; unresolved blockers never permit actions. Status: **proved working** identities/ownership and zero-additional-OCR unknown/gap reports; **reproduced gap** guard migration. Missing independent annotations for every blocker/layout and bounded both-path guard proof.

## Research

Screen/layout/facts: Institute and Research Tree, Development rows, normal blue Research, busy/active/completed detail, and premium Research Now exclusion. Producers: enricher `_build_research_tree_additions`, `_build_research_queue_popup_additions`, `_build_text_screen_additions`; visual profiles `research_tree_development`, `research_tree_node_detail`, `research_tree_node_detail_active`.

Consumer: `pnc_automation/app/automation/tasks/research_task.py` (`ResearchTask.plan`/`verify`) and research edges in `pnc_automation/app/pnc/navigation/screen_flows.py`. Fixtures: `research_tree_development.png`, `research_node_detail.png`, `research_node_detail_active.png`, `research_node_detail_active_reloaded.png`, `research_queue_core.png`, `institute_audit.png`. Tests: `V/test_research_observation.py`, `V/test_research_tree_visual_controls.py`, `V/test_research_queue_navigation.py`, `V/test_institute_visual_controls.py`, `U-T/test_research.py`.

Expected/negative: blue control may remain visible with no idle queue but is not eligibility; active detail has identity without Start; gold Research Now never supplies normal Start; update popup suppresses controls. Status: **proved working** portable Development/detail/queue and negatives; **contract-disposition pending** for Economy, Military, Fortification captures 0027–0053 until their existing ResearchTask producer/consumer contract is explicitly qualified (no defect is claimed from an unqualified variant). Missing tree/header/control/queue regions and independent holdouts for those variants.

## Building construction and upgrade

Screen/layout/facts: level labels (`1/45`, `7/45`, `8/45`), construction level 0/1, upgrade 7/8, unmet prerequisite + Go, active queue/timer, ordinary/premium controls, warning/confirmation overlays. Producers: enricher `_build_building_detail_additions`, `_add_shared_building_level_label`, `_add_upgrade_requirement_controls`, `_build_building_construction_additions`, `_build_build_queue_additions`.

Consumers: `pnc_automation/app/automation/tasks/building_upgrade_task.py` (`_building_level_from_screen`, completion/queue verification), `pnc_automation/app/automation/tasks/building_construction_task.py`, `pnc_automation/app/automation/tasks/building_workflow_support.py`. Tests: `V/test_building_confirmation_observation.py`, `V/test_building_requirements_observation.py`, `V/test_building_speedup_observation.py`, `V/test_build_queue_observation.py`, `U-T/test_building_upgrade_confirmation.py` (deterministic OCR; `update_over_bag.png` overlay).

New evidence: capture frames 0055, 0061–0063, 0074–0077, 0233–0243; raw building frames are not tracked. Expected/negative: publish level through both paths as non-actionable provenance; only unmet row aligned with Go is blocking; satisfied `Requirement` must not produce `building_workflow_support.building_requirement_is_visible`; empty queue cannot prove level; overlay suppresses background facts.

Status: **proved working** generic builder label/requirement/queue/overlay regressions and shared non-actionable label publication on the independently recognized Institute `8/45` capture through both production paths (`V/test_content_label_publication.py`). Generic Farm has no independent visual profile and retains navigation abstention. **Contract-disposition pending** for newly captured construction/upgrade variants and their consumer qualification. Missing sanitized fixtures, semantic regions, independent visual identity for remaining supported building variants, and independent level/queue holdouts.

## Alliance and seasonal layout

Screen/layout/facts: participating K157 tabbed Alliance/Faction versus compact nonparticipating K290; member list, leader/ordinary Manage, Hall Reinforce rows, and Transport disabled with zero selected resources. Producers: enricher `_build_alliance_home_additions`, `_build_alliance_member_list_additions`, `_build_alliance_member_manage_popup_additions`; `pnc_automation/app/pnc/navigation/screen_flows.py` (`open_alliance_home`, `open_alliance_member_list`, `open_alliance_member_manage_popup`).

Consumers/tests: alliance compose route in `pnc_automation/app/automation/tasks/send_mail_task.py`; `V/test_alliance_mail_observation.py`, `V/test_mailbox_member_observation.py`, `V/test_visual_layout_variants.py`, `W/test_popup_recovery.py`. Fixtures: `alliance_home_aug30.png` (historical), `alliance_invitation.png`, raw 0156–0182 plus seasonal 0166/0193.

Expected/negative: geometry binds to tab/role/menu/layout/frame; leader Personal Info is not ordinary Manage and Manage is not Hall Reinforce; no mutation/receipt. Status: **contract-disposition pending** for newly captured visual controls (existing typed member/mail parsing is proved working; no mutation/receipt contract is asserted). Missing sanitized fixtures, independent layout annotations, region/control proof; source note `docs/game-reference/workflows/seasonal-alliance-layout.md`.

## Mail and working text fields

Screen/layout/facts: Mail Hub, Player/Alliance/System mailbox/thread rows, Player Compose recipient/subject/body, empty/focused fields, and corrected lower-left Compose control. Producers: enricher `_build_mail_hub_additions`, `_build_mailbox_additions`, `_build_mail_thread_additions`, `_build_mail_compose_additions`, `_build_observed_text_field_state`; `_build_player_profile_additions`.

Consumers/tests: `pnc_automation/app/automation/tasks/send_mail_task.py` (`SendMailTask.plan`/`verify`), `pnc_automation/app/pnc/navigation/screen_flows.py`; `V/test_mail_compose_observation.py`, `V/test_mailbox_member_observation.py`, `V/test_mail_profile_observation.py`, `V/test_alliance_mail_observation.py`, `W/test_mail_action_follow_up.py`. Fixtures: `collect_mail_hub.png`, `collect_mail_system_list.png`, `collect_mail_system_thread.png`, `mail_player_list.png`, `mail_player_list_no_compose.png`; raw 0010–0018 has populated/empty Compose and subject/body, no send receipt.

Expected/negative: owned-region reads only; missing subject is unknown, not empty; non-Player/overlay abstains; mailbox mismatch is unknown; Compose keeps provenance. Status: **proved working** mailbox/profile parsers and corrected control/field tests; **contract-disposition pending** independent populated-Compose qualification. Send/delivery receipt is **pre-existing unsupported** pending authorized recipient/kingdom and evidence.

## Campaign

Screen/layout/facts: Campaign map, Chapter 10 path/row, stage 10-3 row/detail, Challenge/Close, and separate Hero Formation/battle/result. Producers: visual profiles and enricher `_build_campaign_additions`; consumer `pnc_automation/app/automation/tasks/campaign_task.py` (`CampaignTask.plan`/`verify`) plus campaign edges in `pnc_automation/app/pnc/navigation/screen_flows.py` and `pnc_automation/app/automation/engine/navigation_core.py`.

Fixtures/tests: `campaign_map.png`, `campaign_chapter_10.png`, `campaign_stage_10_3.png`; `V/test_campaign_visual_profiles.py`, `U-T/test_campaign.py`, `U-N/test_navigation_core.py`. Raw frames 0087–0098 show stage 6-5, Formation, battle, Victory/chapter receipt; current prep lacks mode/AP labels (observed AP cost 20).

Expected/negative: measured controls/rows and overlay suppression; no mode, eligibility, battle preparation, global AP cost, or success inferred from Challenge. Status: **proved working** three portable profiles; **contract-disposition pending** Formation/battle/AP producer contracts until an existing CampaignTask consumer contract is identified and qualified. Missing sanitized result/formation annotations; source note `docs/game-reference/workflows/campaign-navigation.md`.

## Gathering and March UI

Screen/layout/facts: selected neutral node, empty/populated formation, Dispatch, active collection, and exact target/report association. Producers: visual profiles `gather_node_selected_resource`/`march_confirm_gather`; enricher spatial/content producers; `pnc_automation/app/pnc/vision/observation_builder.py::ObservationBuilder._publish` and `pnc_automation/app/pnc/vision/navigation_perception.py::NavigationPerception.build`.

Consumer/tests: `pnc_automation/app/automation/tasks/gathering_task.py` (`GatheringTask.plan`/`verify`), `pnc_automation/app/pnc/navigation/world_map_search.py`; `V/test_gathering_march_visual_profiles.py`, `U-T/test_gathering.py`, `V/test_world_spatial_observation.py`. Fixtures: `gather_node.png`, `march_confirm.png`, `march_confirm_empty.png`; raw 0139–0152 and report 0215 show one ordinary Farm dispatch/collection (31.2K rounded report; 31,279 capacity).

Expected/negative: missing control preserves identity without fabrication; wrong screen/overlay suppresses controls; troop/load capacity is not march slots; report alone is not dispatch correlation. Status: **proved working** visual controls/negatives; **contract-disposition pending** active/report producer qualification. March-slot count is **pre-existing unsupported**: no statistics-page frame/consumer contract; retain `docs/game-reference/workflows/neutral-gathering.md` dependency.

## Remaining proved OCR families

Quest/Bag producers `_build_quest_additions`/`_build_bag_additions`; daily/resource consumers under `pnc_automation/app/automation/daily_maintenance/`; fixtures `quest_main*.png`, `quest_daily*.png`, `bag.png`, `bag_current_testing.png`; tests `U-D/test_daily_quest_vision.py`, `U-D/test_daily_quest_catalog.py`, `U-D/test_quest_tab_controls.py`, `U-V/test_resource_inventory_vision.py`, `V/test_menu_observation.py`. Preserve row progress/quantities, selected Resource tab, and clipped-row negatives.

Chat producers `_build_chat_additions`, `_build_proven_chat_state_additions`, `_build_chat_overlay_additions`; consumers `pnc_automation/app/automation/collect_kingdom_chat.py`, `pnc_automation/app/automation/send_chat.py`; fixtures `chat_alliance.png`, `chat_kingdom.png`, three composer states; tests `V/test_chat_observation_requests.py`, `V/test_chat_row_observation.py`, `V/test_chat_fragment_observation.py`, `V/test_kingdom_chat_composer_controls.py`. Preserve sender/message association and announcement/message-only unsupported rows.

Profile/coordinates producers `_build_lord_info_additions`, `_build_player_profile_additions`, `_build_world_map_coordinate_dialog_additions`; consumers `pnc_automation/app/pnc/navigation/screen_flows.py`, `pnc_automation/app/pnc/navigation/world_map_search.py`; tests `V/test_castle_selection_observation.py`, `V/test_coordinate_dialog_local_fixtures.py`, `V/test_coordinate_bar_local_fixtures.py`, `U-V/test_world_coordinate_parsing.py`. Preserve exact names/coordinates and coordinate-only action ineligibility. These are **proved working** on listed fixtures/tests, but guard/content migration is a **reproduced gap**.

Current reviewed region owners are `PNC_BAG`, `PNC_CHAT`, `PNC_MAIL_COMPOSE_POPUP`, `PNC_QUEST_MAIN/DAILY`, coordinate dialog, and world map. Other families still use `GUARDED_FULL_FRAME_REUSE` in `pnc_automation/app/pnc/vision/pnc_ocr_capabilities.py`; they need explicit regions before zero-full-screen enforcement. Catalog counts remain inventory only.

## Dependencies and first slices

- [ ] Keep unobserved march slots, actual mail-send receipt, and native-account versus legacy `Login`/`Continue` route blocked. Native raw evidence is 0197–0203; legacy regression is `V/test_login_observation.py`. Do not fabricate credentials/recipients.
- [x] First coding slice: explicit OCR-label publication on independently recognized Institute through both paths, plus zero-extra-OCR diagnostics. Shared owners: `pnc_automation/app/pnc/vision/observation_provenance.py::select_content_labels`, `pnc_automation/app/pnc/vision/observation_diagnostics.py::ObservationDebugArtifactCollector`, existing builder/navigation publication boundaries, and `pnc_automation/core/vision/ocr/ocr_service.py`. New tests: `V/test_content_label_publication.py`, `V/test_observation_diagnostics.py`, `tests/unit/core/vision/test_ocr_diagnostic_snapshot.py`. Review fixes enforce canonical label denial in the existing action executor and preserve planned-read identity across failure/success. Final affected full fallback: **1,947 run, 1,941 passed, six skipped, zero failures/errors** for the reviewed slice prepared on `f3b88f7`, main base `850bdb7`. This checkbox does not qualify all building variants or complete the global OCR contract.
- [ ] Then migrate shared guards/regions, qualify each family through both paths, add independent holdouts/negatives, run affected selection, and finish `git diff --check`.
