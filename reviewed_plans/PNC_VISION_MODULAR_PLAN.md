# Modular PNC vision and navigation plan

Date: 2026-09-15. Status: prepared for implementation; no implementation is authorized by this document alone.

**Execution order:** use the [43-packet roadmap](PNC_VISION_ROADMAP.md) for delivery waves, dependency gates, next assignments and progress tracking. This index owns scope and shared architecture.

**Shared OCR modernization:** use the [OCR text recognition and localization plan](PNC_OCR_TEXT_LOCALIZATION_MODERNIZATION_PLAN.md) for backend, model, packaging, and measured text-position qualification. It is cross-cutting infrastructure outside the 43-packet count; numbered packets retain feature semantics and action policy.

## Outcome and design

Recognize and navigate the supported Home, research, Bag, Campaign, Trial and building interfaces through one production observation and navigation path. Each numbered packet is a coherent assignment for one assigned implementation worker. A packet owns its feature from screenshot to typed facts, measured controls, navigation, callers and focused proof.

- **Home:** reuse the fixed city atlas; locate the camera with OpenCV landmarks, then verify the current target region. Re-localize after panning. Building artwork and OCR names support identity; they do not define the map.
- **Menus and popups:** use the existing OpenCV screen/control matcher, feature-specific layout/icon parsers, and cropped OCR for changing content. The result answers “which node/item, where can it be clicked, and what state is it in?”
- **World:** retain the separate detector/model work and existing map navigation. Integrate only a qualified output through the same observation contract.
- **Actions:** the existing navigator and observed-action executor remain the only action owners. Recognition of an enabled button does not authorize research, donation, item use, recruitment or battle.

OpenCV is already integrated. V01 adapts and qualifies existing interfaces; it is not a new engine project. Any OCR backend change must follow the bounded shared modernization plan rather than become a feature-packet rewrite. Do not begin a VLM service, screen-plugin framework or rewrite of working profiles.

## Baseline and precedence

Planning checkout: `codex/vision-modular-plan`, based on `4d317dbad066afca989dfa3b09d76bd1f7b82a02`. At planning time `origin/main` was `75153e76e940525dada3b5b4ae98093b5273ef7a`. The planning base includes the reviewed Campaign Chapter 6, Trial Challenge and
Bag chest-preview fix from `codex/vision-navigation-fixes`. The initial plan
landing omitted that runtime fix; the bounded port after `ff38127` now includes
its exact runtime changes and fixtures. The
[retained navigation evidence](vision_modules/CONTEXT_AND_EVIDENCE.md#navigation-findings-retained-in-these-plans)
records provenance and remaining gaps. V11, V13 and V15 preserve this navigation
baseline and implement their remaining content/feature work. This correction does
not complete those packets. V01 still uses the existing Bag Resource layout.

Before dispatch, reconcile the actual current commit and active feature work. Read current AGENTS.md, applicable skills and [core porting instructions](../instructions/CORE_WORKFLOW_PORTING.md). The user's latest fixed-map facts and this scoped vision objective supersede contradictory historical task goals. Existing feature plans retain ownership of their workflow and mutation contracts; this set supplies perception/navigation work within those boundaries. The [remaining feature scope map](PNC_CORE_REMAINING_VISION_BOUNDARY.md) removes overlapping V work from packages 03–06 and identifies their retained deliverables.

[Context and evidence](vision_modules/CONTEXT_AND_EVIDENCE.md) extracts useful findings from **Continue non-YOLO recognition** and **Review improve screen recognition**, identifies stale conclusions, and indexes the live tour. No historical resource budget, account selection, agent ownership or approval is imported.

## Work packets

The set contains **43 implementation packets**. All packets start **not implemented by this plan**. Existing functionality is described inside each packet; do not redo it. The [building coverage map](vision_modules/BUILDING_MENU_COVERAGE.md) assigns every current Home catalog object and the user-confirmed Lost City slot. The [retirement map](vision_modules/PLAN_RETIREMENT.md) records superseded plans and preserved requirements.

| ID | Complete assignment | Dependencies |
|---|---|---|
| [V01](vision_modules/V01_EXISTING_OPENCV_FOUNDATION.md) | Existing OpenCV and observation integration contract | Current baseline |
| [V02](vision_modules/V02_HOME_CAMERA_AND_NAVIGATION.md) | Home camera localization, atlas targets, pan and open | V01 |
| [V03](vision_modules/V03_HOME_APPEARANCES_AND_EVENT_SLOTS.md) | Seasonal references, event occupancy and Sauroi appearance | V02; available variant evidence |
| [V04](vision_modules/V04_INSTITUTE_DEVELOPMENT.md) | Institute, common research tree/detail parsing, Development and queue facts | V01; V02 for automatic Home entry |
| [V05](vision_modules/V05_RESEARCH_ECONOMY.md) | Economy research nodes and details | V04 |
| [V06](vision_modules/V06_RESEARCH_MILITARY.md) | Military research nodes and details | V04 |
| [V07](vision_modules/V07_RESEARCH_FORTIFICATION.md) | Fortification research nodes and details | V04 |
| [V08](vision_modules/V08_ALLIANCE_RESEARCH.md) | Alliance research categories, nodes and donation details | V01; V04's shared node representation if compatible |
| [V09](vision_modules/V09_BAG_SHELL_AND_RESOURCES.md) | Bag tabs, common card contract and Resource inventory | V01 |
| [V10](vision_modules/V10_BAG_SPEEDUPS.md) | Speedup cards and item details | V09 |
| [V11](vision_modules/V11_BAG_TREASURE_AND_PREVIEWS.md) | Treasure cards, chest preview and item details | V09; reuse source preview changes within V11 |
| [V12](vision_modules/V12_BAG_REMAINING_TABS.md) | Remaining Bag tabs discovered on the supported layout | V09; bounded capture inventory |
| [V13](vision_modules/V13_CAMPAIGN_MAP_AND_CHAPTERS.md) | Campaign map/chapter content and navigation | V01; V02 for automatic Home entry |
| [V14](vision_modules/V14_CAMPAIGN_STAGE_AND_FORMATION.md) | Stage details, Hero Formation and return | V13 |
| [V15](vision_modules/V15_TRIAL_CHALLENGE.md) | Trial Challenge cards and one observed detail family | V01; V02 for automatic Home entry |
| [V16](vision_modules/V16_BUILDING_UPGRADE_AND_QUEUES.md) | Building upgrade, prerequisites, queue and confirmation facts | V01; V02 for automatic Home entry |
| [V17](vision_modules/V17_CONSTRUCTION_AND_SLOTS.md) | Construction slot menus and construction details | V16; V02 |
| [V18](vision_modules/V18_HERO_HALL_AND_RESULTS.md) | Hero Hall menu, saved recruitment results and return | V01; V02 for automatic Home entry |
| [V19](vision_modules/V19_WORLD_PERCEPTION_BRIDGE.md) | Qualified World detector output into current observation/navigation | V01; existing model owner's qualification |
| [V20](vision_modules/V20_BARRACKS_TRAINING.md) | Barracks training and unit information | V01; V02 for Home entry; V16 for shared upgrade/speedup presentation |
| [V21](vision_modules/V21_INFIRMARY_HEALING.md) | Infirmary healing menus | V01; V02 for Home entry; V16 for shared costs/queues |
| [V22](vision_modules/V22_BLACKSMITH_AND_GEAR.md) | Blacksmith hub and Gear inventory | V01; V02 for Home entry; V16 for building upgrade presentation |
| [V23](vision_modules/V23_GEM_AND_SAURGEM.md) | Gem and Saurgem inventories | V22 |
| [V24](vision_modules/V24_WARSIGIL.md) | Warsigil menu and details | V22 |
| [V25](vision_modules/V25_HERO_CURIO.md) | Hero Curio inventory and details | V22 |
| [V26](vision_modules/V26_ASCEND.md) | Ascend menu and requirement details | V22 |
| [V27](vision_modules/V27_MARKET_TRANSPORT.md) | Market and resource-transport menus | V01; V02 for Home entry; reuse V09 resource identities |
| [V28](vision_modules/V28_SANCTUM_RELICS.md) | Sanctum and Relics menus | V01; V02 for Home entry; reuse item/card primitives only where they fit |
| [V29](vision_modules/V29_SAUROI_AND_SAUREGG.md) | Sauroi Lair and Sauregg menus | V01; V02 for ordinary Home entry; V03 for variant-specific acquisition |
| [V30](vision_modules/V30_ARENA_VERSUS_CENTER.md) | Arena and Versus Center menus | V01; V02 for Home entry |
| [V31](vision_modules/V31_SACRED_TREE.md) | Sacred Tree and blessing records | V01; V02 for Home entry |
| [V32](vision_modules/V32_DRAGONDOM_EVENT.md) | Dragondom event-building menus | V01; V02–03 for occupied event-slot acquisition |
| [V33](vision_modules/V33_LOST_CITY_HEADQUARTERS.md) | Lost City Headquarters event menus | V01; V02–03 for canonical slot identity and occupancy |
| [V34](vision_modules/V34_WALL_DEFENSE.md) | Wall and Defense Info menus | V01; V02 for Home entry; V16 for common upgrade presentation |
| [V35](vision_modules/V35_WATCHTOWER.md) | Watchtower reports and information | V01; V02 for Home entry; V16 for common upgrade presentation |
| [V36](vision_modules/V36_TRAP_WORKSHOP.md) | Trap Workshop and effect tables | V01; V02 for Home entry; V16 for costs/queues and upgrades |
| [V37](vision_modules/V37_ALLIANCE_HALL_REINFORCEMENT.md) | Alliance Hall and reinforcement menus | V01; V02 for Home entry; V16 for building upgrade facts |
| [V38](vision_modules/V38_HALL_OF_WAR.md) | Hall of War and rally information | V01; V02 for Home entry; V16 for upgrade/glory presentation |
| [V39](vision_modules/V39_PIT_RARE_EARTH.md) | Pit and Rare Earth menus | V01; V02 for Home entry |
| [V40](vision_modules/V40_BANK_TREASURE_CAVE.md) | Bank and current Treasure Cave endpoint | V01; V02 for Home entry |
| [V41](vision_modules/V41_CASTLE_TERRITORY.md) | Castle and Territory Overview | V01; V02 for Home entry; V16–17 for upgrade/construction controls |
| [V42](vision_modules/V42_UTILITY_BUILDING_DETAILS.md) | Warehouse, resource buildings and Recruiting Center details | V01; V02 for Home entry; V16 for shared upgrades |
| [V43](vision_modules/V43_GODDESS_STATUE.md) | Goddess Statue menu and information | V01; V02 for Home entry; V16 for shared upgrades |

“Automatic Home entry” dependencies do not block offline parsing from saved frames. A feature can finish its parser first and leave its automatic entry proof explicitly pending V02. No packet can claim the complete route passed until its dependencies and route are verified.

### Suggested order

The [roadmap](PNC_VISION_ROADMAP.md) is the canonical execution sequence. It starts with V01, then V02 and V04, and separates ordinary feature delivery from appearance/event/model availability. A feature's own prerequisites determine when it can start; an unfinished unrelated packet does not block a whole wave.

## Shared architecture contract

1. **Independent visual identity first.** Extend `VisualScreenRecognizer` and its existing anchor/control catalog. Content OCR cannot establish a conflicting identity or turn an unknown screen into an actionable one.
2. **One capture, one frame context.** Both `ObservationBuilder` and `NavigationPerception` must call the canonical feature producer. Keep `ObservationOcrContext`, bounded OCR requests, source layout and `FrameRef` provenance. Reuse prepared OpenCV frames. No repeated full-frame OCR or whole-screen tiling.
3. **Feature semantics have one owner.** Reuse `DetectedListEntry`, `RowRecognitionStatus`, `SpatialSurfaceObservation` and existing domain item/building models. Add a small typed feature model where existing fields cannot express a consumed fact; migrate changed callers together. Do not create competing metadata key conventions. COMPLETE rows require measured action geometry under the current contract; non-actionable readable facts must not be forced into COMPLETE.
4. **Measured controls only.** Control bounds must belong to the visible, unoccluded surface. Identity anchors are not automatically click controls. Reacquire rows after scroll and buildings after pan; invalidate stale points.
5. **Popup ownership stays explicit.** Inspection/detail screens stay open for the owning workflow. Automatic recovery handles blocking popups only. Keep the existing bounded unknown-modal guard and session/epoch behavior.
6. **Core stays generic.** OpenCV matching primitives belong in core vision; PNC atlas, icon catalogs, layouts and semantic parsers belong in app/pnc. New modules should serve the current feature, not anticipate arbitrary games or backends.
7. **Integrate by symbols and catalog keys.** Each worker owns its feature functions, profile IDs, selectors and tests even when files are shared. V01 owns engine-wide contract changes; V02 owns Home camera/atlas integration; V04 owns common research helpers; V09 owns common Bag helpers. Feature-specific typed additions stay with their feature owner and include migration of affected callers. Merge shared changes before dependent work. Do not recreate the old “wait for recognition agent B” whole-file split.

Each feature parser may be extracted from `pnc_observation_enricher.py` when that keeps the changed feature cohesive. Extraction is not a prerequisite to support every menu and is not permission to reorganize unrelated code.

## Common verification and live protocol

Each packet lists its specific checks and route. Use the current repository runner and test guidance at execution time. At this baseline, start with the relevant component group, then use `py tools/run_tests.py affected --base origin/main --explain` for ordinary source changes. A final combined integration or a shared-schema change warrants the required broader checks; do not run a full suite independently for every data-only menu packet.

Perception acceptance uses real source captures through both production observation paths, including the real bounded OCR planner. Hand-fed OCR tests may isolate semantic conversion but cannot prove that production can obtain the text. Keep reference and validation captures distinct; a resize/crop of the source reference is not independent validation. If a holdout is unavailable, report that limit rather than certify it. Preserve deterministic semantic tests where they still prove a contract.

For a changed live boundary, use the live skill and a **single configured testing instance, active castle**, resolved at execution time. Hold one canonical reservation across dependent steps, use configured ADB discovery and preserve pre-existing instances. Saved artifacts come first. Build any temporary read-only probe under ignored `.local-data/` through `build_core_runtime`, `CoreWorkflowRunner` and reviewed navigation; do not copy a direct screenshot-coordinate tap harness.

Common live stop: at most one listed route attempt after offline checks, stop on an unknown/ambiguous surface, unexpected action boundary or unavailable prerequisite. Retry only after a relevant code or state change. A failed guard is evidence to diagnose, not permission for manual-coordinate automation. Every result records pre/post screenshots, typed observations, frame/action trace and the actual return screen under `.local-data/`. Do not declare success from process exit alone.

Read-only menu opening is the intended proof. Research start, donations, Use/Open items, construction, recruitment and battles are outside these packets' proof budgets. If a needed state can only be created by such an action, use saved evidence or report the exact missing authorization; do not replay a historical transaction.

## Coverage boundaries and overlap with current work

| Area | Disposition |
|---|---|
| Development Research / building package 02 | Coordinate V04 and V16–17 with the current [Research](PNC_CORE_REMAINING_01_RESEARCH_LIVE_PLAN.md) and [Buildings](PNC_CORE_REMAINING_02_BUILDINGS_PLAN.md) owners. Preserve their typed actions/journals. |
| Campaign | V13–14 implement vision/navigation acceptance for the current [Campaign plan](PNC_CORE_REMAINING_04_CAMPAIGN_PLAN.md). Battle automation remains separate. |
| World gathering and formation | V19 connects perception to the [Gathering plan](PNC_CORE_REMAINING_03_GATHERING_PLAN.md); it does not claim dispatch/receipt work complete. |
| Mail, Chat, Alliance membership/manage, castle roster, More/Settings, Daily Quest | Preserve qualified support and existing [Mail/Login](PNC_CORE_REMAINING_05_MAIL_LOGIN_PLAN.md) / [Castle navigation](PNC_CORE_REMAINING_06_CASTLE_NAVIGATION_PLAN.md) work. Reopen only a current, reproduced gap relevant to this goal. |
| Login offers, updates, generic modal guard | Existing shared recognition/recovery stays owned centrally. A new feature popup is delivered in its feature packet, not in a giant “all popups” rewrite. |
| Alliance research | Explicit capture gap; V08 owns discovery and implementation without joining or donating. |
| Remaining building interiors and their owned popups | V20–43 assign dedicated feature packets, including equipment branches, healing/training, defense, Alliance support, utility buildings and separate event hubs. See the building coverage map for exact IDs and capture gaps. Home acquisition does not itself qualify a menu. |

This set assigns the current Home catalog's building menus, the user-confirmed Lost City slot, and the requested research/Bag/Trial/Campaign families. It does not claim implementation is complete or that every future event/progression popup has evidence.

## Dispatch and completion

Use this prompt with one selected packet:

> Implement Vxx from reviewed_plans/PNC_VISION_MODULAR_PLAN.md and its linked packet on the agreed current base. Use Luna with xhigh reasoning. Read current instructions, confirm dependency commits and task ownership, preserve newer landed feature work, and complete this feature through the canonical observation and navigation path. Use saved evidence first, follow the packet's bounded non-spending validation, and report unsupported states explicitly. Do not expand into another packet or inherit historical spending permissions.

Each worker returns: exact commit/base, owned symbols/profile IDs, changed behavior, focused checks, route outcome, evidence path, supported variants, and concrete gaps. Commit/push/integration follow the user's delivery authorization for that implementation task.

The integrator verifies shared contracts once on the combined branch, runs required integration validation, and updates packet status with evidence. If a packet is larger than one coherent feature because capture inventory reveals distinct layouts, split it before implementation; do not silently broaden its promise.
