# Puzzles & Conquest Building Actions Sub-Plan

## 1. Purpose

This document starts the canonical feature plan for home-city building automation beyond the current narrow `building_upgrade` tracer bullet.

It records:

- the known interactable buildings from user notes and screenshots,
- the exact screens and actions currently visible for those buildings,
- the current modeling assumptions we should implement against,
- the next implementation slices required to support those buildings cleanly.

This file is intentionally separate from:

- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md), which owns feature-planning rules,
- [PNC_SCREEN_FLOW_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_SUBPLAN.md), which owns reusable navigation,
- [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md), which owns the broader platform architecture.

## 2. Scope

This plan currently covers only the building set already named or shown:

- Castle
- Wall
- Defense Info as the screen linked from Wall
- Institute
- Warehouse
- Trap Workshop
- Watchtower
- unlockable territory below the wall
- territory lock control
- repeatable small build slots
- Farm
- Lumber Camp
- Moon Well
- Recruiting Center
- Infirmary
- Iron Mine
- Gold Mine
- Blacksmith
- Alliance Hall
- Market
- Infantry Barracks
- Cavalry Barracks
- Ranged Barracks
- Siege Factory
- Hall of War
- Hero Hall
- Sanctum
- Tower of Trial
- Trial Challenge as the screen linked from Tower of Trial
- Sauroi Lair
- Sauregg as the egg-form screen linked from Sauroi Lair
- Campaign
- campaign map as the screen linked from Campaign
- Arena
- Versus Center as the screen linked from Arena
- Goddess Statue
- reserved Goddess Statue build spot
- dedicated fixed build slots for Institute, Warehouse, and Trap Workshop
- flexible large build slots for Alliance Hall, Blacksmith, and Market
- Territory Overview as the screen linked from Castle
- barracks effect table as the screen linked from each barracks
- trap workshop effect table as the screen linked from Trap Workshop
- Sacred Tree
- Blessing Record as the screen linked from Sacred Tree
- other-lord Sacred Tree as the visit screen linked from Blessing Record
- Alliance Member reinforce list as the screen linked from Alliance Hall
- Alliance Member transport list as the screen linked from Market
- Pit
- Rare Earth Field as the screen linked from Pit

This plan does not yet claim that the above list is complete. It is the current seeded inventory only.

## 3. Canonical modeling decisions

The current implementation in [policy_models.py](/c:/Users/lebel/pnc/pnc_automation/pnc/policy_models.py), [building_upgrade_task.py](/c:/Users/lebel/pnc/pnc_automation/automation/tasks/building_upgrade_task.py), and [spatial_surfaces.py](/c:/Users/lebel/pnc/pnc_automation/vision/spatial_surfaces.py) is too coarse because it collapses multiple buildings into generic categories such as `barracks`.

The building feature should instead follow these rules:

- Every interactable home-city building gets one exact canonical building id.
- Shared families such as barracks may still have a common family/group, but each building remains individually addressable.
- A building is not defined only by "upgradeable" or "not upgradeable". Each building declares a set of supported actions.
- Reserved or prebuild home-city slots may also need exact semantic ids when they are not generic empty plots.
- Dedicated fixed slots and flexible multi-build slots are different concepts and should not be collapsed into one generic `build_spot` model.
- Unlockable territory regions and the small build slots revealed inside them are different concepts and should not be collapsed into one generic `empty plot` model.
- `Institute` must not be collapsed into the current coarse `academy` category once this plan is implemented.
- The current internal `academy` naming should be treated as a legacy bug or placeholder alias for `Institute`, not as evidence of a second research building.
- One building may legitimately expose different owned screens in different progression states, such as `sauroi_lair -> sauregg` before tutorial completion and `sauroi_lair -> awakened_detail_screen` after unlock.
- Permanent fixed-position buildings such as `wall`, `campaign`, and `arena` can be always present while still being either upgradeable or non-upgradeable according to their own rules.
- `Pit` is a home-city building. `Rare Earth Field` is the linked destination screen reached from Pit, not a second building in the city.
- For now, the visible Hall of War buttons should be treated as real actions.
- Dynamic row actions visible on a building screen should be modeled as actions on that building screen, not as separate pseudo-buildings.
- Visible labeled panels are not automatically actions. For example, Sacred Tree `Growth Reward` is currently display-only content, not a navigable button.
- Glory support should be modeled as a building capability surfaced by a visible `Glory Level` button on the building screen, not as a separate building type.
- For upgradeable building detail screens, the primary building-upgrade control is stateful: idle buildings show `Upgrade`, while buildings already upgrading show `Speedup` in that same control position.
- Linked screens may be valid navigation destinations even when they are info-only and expose no follow-up actions, such as Castle `Territory Overview`.
- The barracks family and Trap Workshop should share one canonical production-surface model with tier selection, quantity controls, an optional quantity-lock state, a normal production button, a diamond-rush button we do not plan to use, and a speedup state while production is in progress.
- Navigation helpers such as Daily To-Do `Go` can focus a building without completing the building-owned action itself; automation must still enter the building and perform the collect/train action on the owned screen.
- Home-city building recognition and tapping should not depend on seasonal building art, because holiday reskins can change appearance. Stable labels, spatial position, and stable overlay markers are safer than raw building art matching.

## 4. Evidence levels

This document uses three evidence levels:

- `confirmed_by_user`: the user explicitly stated the behavior,
- `confirmed_by_screenshot`: the current screenshot visibly shows the screen or action,
- `assumed_for_now`: a temporary implementation assumption until more screenshots confirm it.

## 5. Canonical building inventory

| Building id | Home-city label | Role | Upgradeable | Known actions | Evidence | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `castle` | Castle | home_city_building | yes | `upgrade`, `open_territory_overview`, `open_glory_level` | `confirmed_by_user`, `confirmed_by_screenshot` | Always present at one fixed home-city position. User confirmed Castle Glory unlocks at level 15, and the `Glory Level` button should only be expected once that feature is unlocked. |
| `wall` | Wall | home_city_building | yes | `upgrade`, `open_glory_level`, `open_defense_info`, `open_repair_wall` | `confirmed_by_user`, `confirmed_by_screenshot` | Always present at one fixed home-city position; `Repair Wall` remains clickable and turns red when the wall is damaged. |
| `institute` | Institute | home_city_building | yes | `upgrade`, `open_glory_level`, `open_development_research`, `open_economy_research`, `open_military_research`, `open_fortification_research` | `confirmed_by_user`, `confirmed_by_screenshot` | Current code still folds `INSTITUTE` into `academy`; this should be treated as legacy naming drift and migrated to `institute`. |
| `warehouse` | Warehouse | home_city_building | yes | `upgrade`, `open_glory_level` | `confirmed_by_user`, `confirmed_by_screenshot` | Fixed-position utility building with protected-resource summary rows. |
| `trap_workshop` | Trap Workshop | home_city_building | yes | `upgrade`, `open_glory_level`, `open_trap_effect_table`, `craft_traps`, `speedup_crafting`, `collect_crafted_traps` | `confirmed_by_user`, `confirmed_by_screenshot` | Fixed-position utility building that shares the barracks-style production surface but unlocks trap tiers on a different level schedule. `Craft Now` is visible as a diamond-rush action and should not be used. |
| `watchtower` | Watch Tower | home_city_building | yes | `upgrade`, `open_glory_level` | `confirmed_by_user`, `confirmed_by_screenshot` | Fixed-position building with warning tabs and passive information; current evidence does not indicate any primary action beyond Glory and Upgrade. |
| `farm` | Farm | repeatable_small_building | yes | `construct_from_small_slot`, `upgrade` | `confirmed_by_screenshot`, `confirmed_by_user` | Small-slot food production building available from unlocked territory build menu. |
| `lumber_camp` | Lumber Camp | repeatable_small_building | yes | `construct_from_small_slot`, `upgrade` | `confirmed_by_screenshot`, `confirmed_by_user` | Small-slot wood production building available from unlocked territory build menu. |
| `moon_well` | Moon Well | repeatable_small_building | yes | `construct_from_small_slot`, `upgrade` | `confirmed_by_screenshot`, `confirmed_by_user` | Small-slot soulstone production building available from unlocked territory build menu. |
| `recruiting_center` | Recruiting Center | repeatable_small_building | yes | `construct_from_small_slot`, `upgrade` | `confirmed_by_screenshot`, `confirmed_by_user` | Small-slot support building available from unlocked territory build menu. |
| `infirmary` | Infirmary | repeatable_small_building | yes | `construct_from_small_slot`, `upgrade` | `confirmed_by_screenshot`, `confirmed_by_user` | Small-slot support building available from unlocked territory build menu. |
| `iron_mine` | Iron Mine | repeatable_small_building | yes | `construct_from_small_slot`, `upgrade` | `confirmed_by_screenshot`, `confirmed_by_user` | Small-slot iron production building available from unlocked territory build menu. |
| `gold_mine` | Gold Mine | repeatable_small_building | yes | `construct_from_small_slot`, `upgrade` | `confirmed_by_screenshot`, `confirmed_by_user` | Small-slot gold production building is visible in the build menu and should use the same slot family. |
| `blacksmith` | Blacksmith | home_city_building | yes | `upgrade`, `open_glory_level`, `open_gear_screen`, `open_gem_screen`, `open_saurgem_screen`, `open_hero_curio`, `open_warsigil_screen`, `open_ascend_screen` | `confirmed_by_user`, `confirmed_by_screenshot` | Built large-slot building with a fixed action list. Gear, Gem, and Saurgem are currently considered redundant with Lord Info for implementation priority. Saurgem and Ascend destination screens are now screenshot-confirmed. |
| `alliance_hall` | Alliance Hall | home_city_building | yes | `upgrade`, `open_glory_level`, `send_back_reinforcements`, `open_reinforcement_member_list` | `confirmed_by_user`, `confirmed_by_screenshot` | Built large-slot building showing current reinforcement state and opening an Alliance Member reinforce list distinct from the Alliance screen. |
| `market` | Market | home_city_building | yes | `upgrade`, `open_glory_level`, `open_transport_member_list` | `confirmed_by_user`, `confirmed_by_screenshot` | Built large-slot building showing transport fee and total resources, then opening an Alliance Member transport list distinct from the Alliance screen. |
| `infantry_barracks` | Infantry Barracks | home_city_building | yes | `upgrade`, `open_glory_level`, `open_unit_unlock_table`, `train_units`, `speedup_training`, `collect_trained_units` | `confirmed_by_user`, `confirmed_by_screenshot` | Barracks-family production building. T1 is always available; higher tiers unlock through building levels. |
| `cavalry_barracks` | Cavalry Barracks | home_city_building | yes | `upgrade`, `open_glory_level`, `open_unit_unlock_table`, `train_units`, `speedup_training`, `collect_trained_units` | `confirmed_by_user`, `confirmed_by_screenshot` | Shares the barracks production surface and level-based tier unlock structure with building-specific unit names. |
| `ranged_barracks` | Ranged Barracks | home_city_building | yes | `upgrade`, `open_glory_level`, `open_unit_unlock_table`, `train_units`, `speedup_training`, `collect_trained_units` | `confirmed_by_user`, `confirmed_by_screenshot` | Shares the barracks production surface and level-based tier unlock structure with building-specific unit names. |
| `siege_factory` | Siege Factory | home_city_building | yes | `upgrade`, `open_glory_level`, `open_unit_unlock_table`, `train_units`, `speedup_training`, `collect_trained_units` | `confirmed_by_user`, `confirmed_by_screenshot` | Same barracks-family production surface for siege units. User earlier referred to this building as Siege Barracks. |
| `hall_of_war` | Hall of War | home_city_building | yes | `upgrade`, `open_glory_level`, `set_prioritized_unit_type`, `join_rally_attack`, `reinforce_allies`, `set_troop_formation` | `confirmed_by_user`, `confirmed_by_screenshot`, `assumed_for_now` | Upgrade button and action rows are visible in the provided screenshot. |
| `hero_hall` | Hero Hall | home_city_building | no | `open_hero_hall_recruit_tab`, `select_hero_recruit_banner`, `recruit_heroes_1x`, `recruit_heroes_10x`, `open_hero_hall_exchange_tab`, `exchange_hero_fragments` | `confirmed_by_user`, `confirmed_by_screenshot` | Recruit and Exchange are fixed top tabs. Token-based `Recruit 10x` for 9 tokens should be favored when available. Recruit token inventory is visible externally under `Bag -> Misc`. Deeper recruit-priority policy is deferred to [PNC_HERO_HALL_POLICY_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_HERO_HALL_POLICY_SUBPLAN.md). |
| `sanctum` | Sanctum | home_city_building | no | `open_artifact_collection`, `open_relics` | `confirmed_by_user`, `confirmed_by_screenshot` | Home-city overlay shows two entry icons labeled `Artifact` and `Relic`. |
| `tower_of_trial` | Tower of Trial | home_city_building | no | `open_trial_challenge` | `confirmed_by_user`, `confirmed_by_screenshot` | Building opens the `Trial Challenge` screen. |
| `sauroi_lair` | Sauroi Lair | home_city_building | yes | `upgrade`, `obtain_life_essence` | `confirmed_by_user`, `confirmed_by_screenshot` | Fixed-position building with stateful presentation: egg form before tutorial completion, awakened lair form after tutorial unlock. Tutorial-owned transition details are deferred to [PNC_TUTORIAL_ROUTINE_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TUTORIAL_ROUTINE_SUBPLAN.md). |
| `campaign` | Campaign | home_city_building | no | `open_campaign` | `confirmed_by_user`, `confirmed_by_screenshot` | Always present fixed-position portal building. |
| `arena` | Arena | home_city_building | no | `open_versus_center` | `confirmed_by_user`, `confirmed_by_screenshot` | Home-city label is `Arena`; owned screen title is `Versus Center`. |
| `goddess_statue` | Goddess Statue | home_city_building | yes | `upgrade`, `open_glory_level`, `speedup_upgrade` | `confirmed_by_user`, `confirmed_by_screenshot`, `assumed_for_now` | Screenshot shows `Glory Level` and `Speedup`; `upgrade` remains the intended non-busy action when not already upgrading. |
| `sacred_tree` | Sacred Tree | home_city_building | no visible upgrade | `open_blessing_record`, `harvest` | `confirmed_by_screenshot`, `confirmed_by_user` | Unlocks at `Castle : Lv.9 required`; `Growth Reward` is visible display-only reward content, and `Harvest` becomes enabled only when blessing progress is full. |
| `pit` | Pit | home_city_building | no visible upgrade | `open_rare_earth_field` | `confirmed_by_screenshot`, `confirmed_by_user` | User clarified Pit links to Rare Earth Field. |

### 5.1 Reserved home-city slot inventory

| Slot id | Visible label | Role | Intended building | Known actions | Evidence | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `reserved_institute_slot` | none visible in current screenshots | reserved_home_city_slot | `institute` | `open_fixed_build_menu` | `confirmed_by_user`, `assumed_for_now` | Dedicated fixed-position slot for Institute before construction. |
| `reserved_warehouse_slot` | none visible in current screenshots | reserved_home_city_slot | `warehouse` | `open_fixed_build_menu` | `confirmed_by_user`, `assumed_for_now` | Dedicated fixed-position slot for Warehouse before construction. |
| `reserved_trap_workshop_slot` | none visible in current screenshots | reserved_home_city_slot | `trap_workshop` | `open_fixed_build_menu` | `confirmed_by_user`, `assumed_for_now` | Dedicated fixed-position slot for Trap Workshop before construction. |
| `reserved_goddess_statue_slot` | none visible in current screenshot | reserved_home_city_slot | `goddess_statue` | `open_fixed_build_menu` | `confirmed_by_user`, `confirmed_by_screenshot` | The shown circular platform is not a generic empty plot; it is reserved for Goddess Statue and opens a single-option fixed-slot `Build` menu. |
| `large_support_build_slot` | none visible in current screenshots | flexible_large_build_slot | `alliance_hall`, `blacksmith`, `market` | `open_large_build_menu` | `confirmed_by_user`, `confirmed_by_screenshot` | Large square plots below Bulletin can host one of the large utility buildings. |

### 5.2 Unlockable territory and small-slot inventory

| Slot or region id | Visible label | Role | Intended buildings | Known actions | Evidence | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `locked_territory_region_below_wall` | none visible inside fog | locked_territory_region | `farm`, `lumber_camp`, `moon_well`, `recruiting_center`, `infirmary`, `iron_mine`, `gold_mine` | `unlock_territory_region` | `confirmed_by_screenshot`, `confirmed_by_user` | Fogged region below the wall that becomes buildable after unlocking. |
| `territory_unlock_lock_icon` | none | territory_unlock_control | `locked_territory_region_below_wall` | `unlock_territory_region` | `confirmed_by_screenshot`, `confirmed_by_user` | Clicking the visible lock icon unlocks the territory region. |
| `small_territory_build_slot` | none | flexible_small_build_slot | `farm`, `lumber_camp`, `moon_well`, `recruiting_center`, `infirmary`, `iron_mine`, `gold_mine` | `open_small_build_menu` | `confirmed_by_screenshot`, `confirmed_by_user` | Small circular build spots become available after the below-wall territory is unlocked. |

## 6. Linked screen inventory

These are not separate home-city buildings, but they must still be modeled as building-owned interaction screens.

| Screen id | Reached from | Known actions | Evidence | Notes |
| --- | --- | --- | --- | --- |
| `build_menu_fixed_slot` | `reserved_institute_slot`, `reserved_warehouse_slot`, `reserved_trap_workshop_slot`, `reserved_goddess_statue_slot` | `construct_fixed_building` | `confirmed_by_screenshot`, `confirmed_by_user` | Fixed-slot `Build` menus are single-option destination screens. Current evidence covers Institute, Trap Workshop, and Goddess Statue directly, with Warehouse user-confirmed to follow the same one-option layout. |
| `build_menu_large_slot` | `large_support_build_slot` | `construct_alliance_hall`, `construct_blacksmith`, `construct_market` | `confirmed_by_screenshot`, `confirmed_by_user` | `Build` menu shows the three large-slot candidates in one list. |
| `build_menu_small_slot` | `small_territory_build_slot` | `construct_farm`, `construct_lumber_camp`, `construct_moon_well`, `construct_recruiting_center`, `construct_infirmary`, `construct_iron_mine`, `construct_gold_mine` | `confirmed_by_screenshot`, `confirmed_by_user` | Build menu shows the full small-slot building family available in unlocked territory below the wall, including per-row `Owned` counts. The same option family should be expected from every unlocked small build spot. |
| `territory_overview` | `castle` | none | `confirmed_by_screenshot`, `confirmed_by_user` | Opened from the round icon with three vertical bars in a circle next to the green `Territory Overview` label; current evidence shows an info-only statistics screen with no follow-up actions. |
| `barracks_unlock_table` | `infantry_barracks`, `cavalry_barracks`, `ranged_barracks`, `siege_factory` | none | `confirmed_by_screenshot`, `confirmed_by_user` | Effect table showing which building levels unlock higher troop tiers. Structure is shared across the barracks family, while unlocked unit names differ by barracks type. |
| `trap_workshop_effect_table` | `trap_workshop` | none | `confirmed_by_screenshot`, `confirmed_by_user` | Effect table showing trap capacity, trap crafting cap, and unlocked trap tiers. Unlock schedule differs from the barracks family. |
| `defense_info` | `wall` | `add_wall_defender` | `confirmed_by_screenshot`, `confirmed_by_user` | Wall-linked screen showing up to five hero slots; empty slots can be filled by clicking the `+` button. |
| `sacred_tree_blessing_record` | `sacred_tree` | `open_blessing_record_lord_tree` | `confirmed_by_screenshot`, `confirmed_by_user` | Modal titled `Blessing Record` listing player names, times, and a tree/arrow visit control for each lord who blessed the tree. |
| `other_lord_sacred_tree` | `sacred_tree_blessing_record` | `bless_other_lord_tree` | `confirmed_by_screenshot`, `confirmed_by_user` | Visiting another lord's tree keeps the title `Sacred Tree`, shows that lord's name, and exposes a stateful `Bless` button. |
| `sanctum_artifact_collection` | `sanctum` | `browse_artifacts`, `inspect_artifact` | `confirmed_by_screenshot`, `assumed_for_now` | Documented for completeness, but user requested that the Sanctum artifact subtree be skipped for the current implementation plan. |
| `relics` | `sanctum` | `browse_relic_sets`, `open_event_relic_tab`, `open_private_collection_tab`, `inspect_relic_set` | `confirmed_by_screenshot`, `assumed_for_now` | Screen title is `Relics`; screenshot shows top tabs and repeated relic-set cards. Detailed row-destination follow-up is deferred to [PNC_RELICS_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_RELICS_SUBPLAN.md). |
| `alliance_member_reinforce` | `alliance_hall` | `reinforce_ally` | `confirmed_by_screenshot`, `confirmed_by_user` | Context-specific Alliance Member list reached from Alliance Hall. Repeated rows expose `Reinforce` buttons. |
| `alliance_member_transport` | `market` | `transport_resources_to_ally` | `confirmed_by_screenshot`, `confirmed_by_user` | Context-specific Alliance Member list reached from Market. Repeated rows expose `Transport` buttons. |
| `gear` | `blacksmith` | none | `confirmed_by_screenshot`, `confirmed_by_user` | Blacksmith destination screen currently considered redundant with Lord Info `Gear`. |
| `gem` | `blacksmith` | none | `confirmed_by_screenshot`, `confirmed_by_user` | Blacksmith destination screen currently considered redundant with Lord Info `Gem`. |
| `saurgem` | `blacksmith` | `get_saurgem` | `confirmed_by_screenshot`, `confirmed_by_user` | Screen title `Saurgem`; visible controls include a bottom `Get Saurgem` button and a `Cabinet` entry. |
| `warsigil` | `blacksmith` | none | `confirmed_by_screenshot`, `confirmed_by_user` | Blacksmith destination screen currently considered lower priority than core building actions. |
| `hero_curio` | `blacksmith` | none | `confirmed_by_screenshot`, `confirmed_by_user` | Blacksmith destination screen marked useful for later work. |
| `ascend` | `blacksmith` | `ascend_item` | `confirmed_by_screenshot`, `confirmed_by_user` | Screen title `Ascend`; visible controls show an item-selection surface and bottom `Ascend` button. |
| `trial_challenge` | `tower_of_trial` | `open_trial_exchange`, `open_trial_progress`, `open_trial_total_rank`, `open_trial_entry_rank`, `open_trial_entry_stats`, `start_trial_stage` | `confirmed_by_screenshot`, `confirmed_by_user` | Screen title is `Trial Challenge`; rows stay in fixed positions, while accessibility changes by day/state. Detailed row/state follow-up is deferred to [PNC_TRIAL_CHALLENGE_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TRIAL_CHALLENGE_SUBPLAN.md). |
| `sauregg` | `sauroi_lair` | `obtain_life_essence` | `confirmed_by_screenshot`, `confirmed_by_user` | Egg-form owned screen shown before tutorial completion; title is `Sauregg`. The tutorial-governed transition out of this state is deferred to [PNC_TUTORIAL_ROUTINE_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TUTORIAL_ROUTINE_SUBPLAN.md). |
| `campaign_map` | `campaign` | `open_campaign_region`, `open_campaign_special_stage` | `confirmed_by_screenshot`, `assumed_for_now` | The provided screenshot shows region nodes such as `Dawn Forest`, `Misty Bay`, and `Neptune's Labyrinth`. Detailed Campaign, Arena, and shared match-solver follow-up is deferred to [PNC_CAMPAIGN_ARENA_MATCH_SOLVER_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_CAMPAIGN_ARENA_MATCH_SOLVER_SUBPLAN.md). |
| `versus_center` | `arena` | `open_arena_tab`, `open_exchange_shop_tab`, `open_hero_showdown`, `open_hero_championship` | `confirmed_by_screenshot`, `confirmed_by_user` | Home-city building label is `Arena`; owned screen title is `Versus Center`. Detailed Campaign, Arena, and shared match-solver follow-up is deferred to [PNC_CAMPAIGN_ARENA_MATCH_SOLVER_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_CAMPAIGN_ARENA_MATCH_SOLVER_SUBPLAN.md). |
| `rare_earth_field` | `pit` | `exchange_rare_earth`, `enter_field`, `switch_mine`, `attack_mine` | `confirmed_by_screenshot`, `confirmed_by_user` | Screen title is `Rare Earth Field`. Mine rows are fixed level slots in a sequential progression ladder, with row actions changing by unlock/selection state. |
| `dispatch` | `rare_earth_field` | `dispatch_attack` | `confirmed_by_screenshot`, `confirmed_by_user` | Screen title `Dispatch`; opened when attacking pit guards from a Rare Earth mine row. |

## 7. Interaction details from screenshots and user confirmation

### 7.1 Castle

Observed home-city building label:

- `Castle`

Observed home-city behavior:

- Castle is always present at one fixed home-city position

Observed screen title:

- `Castle`

Observed visible controls:

- `Territory Overview`
- `Upgrade`
- `Glory Level` on one provided Castle screen

Observed Territory Overview entry evidence:

- green `Territory Overview` label beside a round icon with three vertical bars in a circle

Observed supporting text:

- `The foundation of your great cause. Upgrade to unlock more buildings.`
- `Level Effect`
- `Next Level`

Observed state evidence:

- one provided Castle screen labeled `2/45` shows `Territory Overview` and `Upgrade`
- one provided Castle screen labeled `12/45` shows `Territory Overview`, `Glory Level`, and `Upgrade`
- user clarified Castle Glory truly unlocks at level 15

Observed Territory Overview screen behavior:

- screen title `Territory Overview`
- information sections such as `Fortif. Record`, `Fortif. Overview`, and `Resource Statistics`
- current evidence shows no linked actions on the Territory Overview screen

Current implementation assumptions:

- Castle is a fixed-position upgradeable home-city building.
- `Territory Overview` should be modeled as a real Castle action.
- `territory_overview` should be modeled as an info-only linked screen reached from Castle.
- Buildings that support Glory should be expected to show the `Glory Level` button on their building screens.
- Castle Glory unlock should be modeled at Castle level 15.

### 7.2 Hall of War

Observed screen title:

- `Hall of War`

Observed primary controls:

- `Prioritized Unit Type`
- `Glory Level`
- `Upgrade`

Observed row actions:

- `Join Rally Attack` with a `Go` button
- `Reinforce Allies` with a `Go` button
- `Troop Form. Set` with a `Go` button

Observed supporting text:

- `A facility that allows you to initiate a rally attack.`
- `Applicable legion size: 550,000`

Current implementation assumption:

- The visible Hall of War controls and `Go` buttons should be treated as actionable controls, not decorative labels.

### 7.3 Sacred Tree

Observed screen title:

- `Sacred Tree`

Observed main-screen controls and content:

- `Blessing Record`
- `Growth Reward`
- `Harvest`

Observed supporting text:

- `Lv.58`
- `Seek blessings from other Lords in chat to complete harvest.`

Observed unlock evidence:

- home-city overlay `Castle : Lv.9 required`

Observed progress and readiness states:

- full blessing progress is shown with lit yellow nodes and an enabled `Harvest` button
- partial blessing progress keeps `Harvest` greyed out until the progress nodes are full
- a later screenshot shows `Harvest` greyed out with only two lit nodes out of four
- user-confirmed Sacred Tree ready state also shows a gift indicator above the building
- user-confirmed `Harvest` becomes grey again after harvesting is already done
- user-confirmed harvest rewards are granted automatically when `Harvest` is pressed rather than opening a separate reward-claim flow

Observed Blessing Record behavior:

- overlay title `Blessing Record`
- columns `Player Name` and `Time`
- repeated lord rows with portrait, player name, time text such as `Today`, and a tree/arrow visit control

Observed visited other-lord tree behavior:

- screen title still `Sacred Tree`
- visible owner name such as `Rosalie` or `jodesiles7`
- message `You may bless the same Lord once per day.`
- a `Bless` button that can be yellow/enabled or grey/disabled
- yellow progress nodes when that lord's tree is still blessable
- fully lit progress nodes when that lord's tree is already ready to harvest

Observed Growth Reward behavior:

- reward panel visible on the right side with reward items such as diamonds, speedups, and food
- user-confirmed `Growth Reward` is not interactable and only shows the harvest rewards

Current implementation assumption:

- Sacred Tree is interactable and should be modeled as a non-upgrade primary building.
- `Growth Reward` should be modeled as display-only state on the Sacred Tree screen, not as a clickable action.
- Blessing progress should be modeled as a stateful progress meter, not as decorative art.
- The visible progress-node count is not fixed at one constant value; current screenshots show both six-node and four-node layouts, and user confirmation says the total node count grows with long-term Sacred Tree progression tied to cumulative harvest history rather than with the current day's blessing state alone.
- `Harvest` should be modeled as a stateful action that is enabled only when progress is full and disabled both before completion and after the daily harvest is consumed.
- Pressing `Harvest` should be modeled as an immediate claim action that grants rewards automatically and then leaves `Harvest` greyed out for the rest of the day.
- `Blessing Record` should be modeled as a Sacred Tree-owned list/overlay that can navigate to other lords' Sacred Tree screens.
- Visiting another lord's Sacred Tree should expose a stateful `Bless` action that is unavailable when the tree is already harvest-ready or that lord has already been blessed for the day.
- The home-city gift above Sacred Tree should be treated as a stable ready-state marker across holiday reskins, but automation should still prefer stable spatial or label-based targeting for entering the building rather than clicking the gift itself or relying on the building art.

### 7.3 Pit and Rare Earth Field

Observed home-city building label:

- `Pit`

Observed linked screen title:

- `Rare Earth Field`

Observed top-level controls:

- `Exchange`

Observed contextual or side controls:

- `Gold Pickaxe (Inactive)`

Observed row actions:

- `Enter Field`
- `Switch Mine`
- `Attack`

Observed supporting text:

- `Rare Earth Ore`
- `Excavation time`
- `Pit gathering time`
- output-per-hour values by row
- prerequisite text such as `You must defeat the previous guards first.`

Observed row-state behavior:

- one mine row is the currently selected active mine and exposes `Enter Field`
- previously unlocked non-selected mine rows expose `Switch Mine`
- the next progression row exposes `Attack` to unlock that mine level
- later rows remain blocked with prerequisite text until the previous guards are defeated
- in an all-unlocked screenshot, non-selected rows all expose `Switch Mine` while the selected row exposes `Enter Field`
- user confirmed mine levels unlock sequentially by clearing the previous level's `Attack` flow successfully, such as unlocking level 2 only after defeating level 1 guards

Observed `Attack` follow-up screen behavior:

- screen title `Dispatch`
- top hero lineup with a `Clear Hero` button
- repeated troop rows such as `Dragon Warmaster`, `Dragon Bowmaster`, `Dragon Templar`, and `Whale Catapult`
- bottom `Dispatch` button
- explanatory text `Attacking pit guards won't occupy your troops. No casualties.`
- visible `Applicable Stats` entry
- a `Skip` checkbox

Current implementation assumption:

- Pit itself is the city building target.
- Rare Earth Field is the destination screen opened from Pit.
- The `Gold Pickaxe` control should be treated as actionable but still owned by the `Rare Earth Field` surface rather than as a separate linked-screen subtree.
- Mine rows on Rare Earth Field should be modeled as fixed level-keyed progression slots in a sequential unlock ladder.
- Exactly one row is the current selected mine and should surface `Enter Field`.
- Already unlocked alternative mine rows should surface `Switch Mine`.
- The next unlockable row should surface `Attack`.
- Higher rows may remain hard-locked with prerequisite text until the previous guards are defeated.
- `Attack` should be modeled as the sequential unlock action for the next mine level rather than as a generic row action that stays available after every level is already unlocked.
- `Attack` should open a dedicated `Dispatch` screen for the pit-guard battle setup.

### 7.4 Sanctum, Artifact, and Relics

Observed home-city building label:

- `Sanctum`

Observed home-city entry icons:

- `Artifact`
- `Relic`

Observed artifact-side screen title:

- `Sanctum`

Observed artifact-side content:

- selected artifact title `Portal Scroll`
- selected item owner text `BigBoss`
- coordinate text such as `X:292, Y:546`
- a grid of artifact cards with inspect/magnifier overlays
- stat sections such as `Special Stats` and `Basic Stats`

Observed relic-side screen title:

- `Relics`

Observed relic-side primary tabs:

- `Set List`
- `Event Relic`
- `Private Collection`

Observed relic-side repeated content:

- relic-set cards such as `Lv.1 Gale Instrument (2/8)`
- state labels such as `Lv.1 Set Stats (Inactive)`
- repeated list/detail buttons on each row

Current implementation assumptions:

- Sanctum is a non-upgrade home-city building.
- The Sanctum home-city overlay exposes two primary actions: open Artifact and open Relic.
- The artifact-side screenshot should currently be modeled as a Sanctum-owned artifact collection screen, even though the visible title remains `Sanctum`.
- The Sanctum artifact subtree is intentionally deferred from the current implementation plan.
- Artifact cards and relic-set rows should be modeled as repeated dynamic entries rather than as fixed selector ids.

### 7.5 Tower of Trial and Trial Challenge

Observed home-city building label:

- `Tower of Trial`

Observed linked screen title:

- `Trial Challenge`

Observed top-level controls:

- `Exchange`
- `Progress`
- `Total Rank`

Observed trial rows:

- `Hero Trial`
- `Curio Trial`
- `Tech Trial`
- `Gear Trial`
- `Rune Trial`
- `Sauroi Trial`

Observed repeated row actions:

- `Rank`
- `Stats`
- `Trial`

Observed supporting text:

- row-local progress values such as `Progress: 43/140`
- lock or requirement text such as `Require Lv.31 Castle`
- a visible countdown on the `Sauroi Trial` row

Current implementation assumptions:

- Tower of Trial is a non-upgrade home-city building.
- Trial rows on `Trial Challenge` should be modeled as fixed canonical entries in stable positions, not as free-scrolling dynamic content.
- Trial accessibility is stateful by day or progression, but the row identity and row position remain stable.
- Row actions such as `Rank`, `Stats`, and `Trial` should resolve relative to the selected trial entry.
- Detailed row/state follow-up for Trial Challenge should be owned by [PNC_TRIAL_CHALLENGE_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TRIAL_CHALLENGE_SUBPLAN.md).

### 7.6 Goddess Statue and the reserved build spot

Observed home-city building label:

- `Goddess Statue`

Observed building screen title:

- `Goddess Statue`

Observed visible controls:

- `Glory Level`
- `Speedup`

Observed supporting text:

- `Make a wish and it might come true.`
- a visible level line such as `Lv.13 Goddess Statue`
- a visible timer such as `00:35:40`

Observed reserved-slot evidence:

- a circular home-city platform on the castle approach
- user clarification that the spot is reserved for Goddess Statue

Current implementation assumptions:

- Goddess Statue is upgradeable even though the provided screenshot shows an in-progress state with `Speedup` instead of an idle `Upgrade` button.
- The shown round platform should be modeled as a dedicated reserved Goddess Statue slot rather than a generic empty build plot.
- The reserved slot should use the same single-option fixed-slot `Build` flow family as Institute, Warehouse, and Trap Workshop, with `Goddess Statue` as the only build option.

### 7.7 Fixed utility buildings and dedicated build slots

Observed home-city building labels:

- `Institute`
- `Warehouse`
- `Trap Workshop`

Observed dedicated fixed-slot build screens:

- `Build` with one `Institute` entry
- `Build` with one `Trap Workshop` entry

Observed shared fixed-slot build messaging:

- `Owned: 0`
- `Requirements not met. Tap to view.`

Current implementation assumptions:

- Institute, Warehouse, and Trap Workshop are fixed-position utility buildings.
- When unbuilt, each one uses a dedicated fixed slot rather than a flexible generic build plot.
- Clicking an unbuilt dedicated slot should open a `Build` screen with one intended building choice for that slot.

### 7.8 Institute

Observed screen title:

- `Institute`

Observed visible controls:

- `Glory Level`
- `Upgrade`
- `Development`
- `Economy`
- `Military`
- `Fortification`

Observed supporting content:

- research entries such as `Unit Tactics`, `Formations`, `Military II`, `Dragonia`, `Development II`, `Battle III`, and `War Fury`
- a visible `Research Queue` panel

Current implementation assumptions:

- Institute is fixed and upgradeable.
- Institute owns its own research-category controls and should not remain folded into the current generic `academy` concept.

### 7.9 Warehouse

Observed screen title:

- `Warehouse`

Observed visible controls:

- `Glory Level`
- `Upgrade`

Observed supporting content:

- protected resource rows such as `Prt. Food`, `Prt. Wood`, `Prt. Iron`, and `Prt. Gold`
- a `Soulstone Held/Soulstone Cap` row

Current implementation assumptions:

- Warehouse is fixed and upgradeable.
- The visible resource rows are screen content, not primary action selectors.
- No actionable controls beyond `Glory Level` and `Upgrade` are currently known.

### 7.10 Trap Workshop and the barracks production family

Observed trap-workshop screen title:

- `Trap Workshop`

Observed barracks-family screen titles:

- `Infantry Barracks`
- `Cavalry Barracks`
- `Ranged Barracks`
- `Siege Factory`

Observed shared production-surface controls:

- `Glory Level`
- `Upgrade`
- green `Unit Advantage` entry on the production screen
- tier selectors such as `T3`, `T4`, `T5`, `T6`, `T8`, and locked higher tiers
- quantity controls with minus/plus adjustments and a lock toggle
- a blue primary action button such as `Train` or `Craft` when idle
- a yellow primary action button labeled `Speedup` while training/crafting is in progress

Observed queue-state behavior:

- the same production surface changes state across idle, in-progress, and collect-ready phases
- idle state shows the normal blue production button such as `Train` or `Craft`
- in-progress state shows a yellow `Speedup` button
- finished output becomes collect-ready on the building itself and should be modeled as a third queue-state action on the same surface rather than a separate screen

Observed shared production-surface content:

- selected unit or trap art and stats
- training or crafting time display
- queue text such as `Train T6 Ace Champion x940`
- resource-cost rows under the quantity controls

Observed barracks-specific behavior:

- T1 is always available
- higher troop tiers unlock from barracks level increases
- the unlock table structure is shared across the barracks family, while the unit names differ by barracks type
- user confirmed trained units can become ready to collect from the building
- user confirmed Daily To-Do `Go` only focuses the correct building and does not complete the collect action
- user confirmed a yellow `zzz` marker above home-city barracks indicates that no troop batch is currently training
- user confirmed the yellow checkmark-style ready-unit indicator can appear above the home-city building when troops are ready to collect
- user confirmed the home-city building can remain idle both before collecting ready troops and after collecting them if no new batch has been started, so collect-ready and training-in-progress must be modeled as different states rather than one generic busy marker
- user confirmed the hammer icon is the building-upgrade indicator and is unrelated to whether a new troop batch is currently training

Observed trap-workshop-specific behavior:

- trap-type display such as `Burning Log`
- the effect table shows trap capacity, trap crafting cap, and unlocked trap tiers
- the trap unlock schedule differs from the barracks family unlock schedule
- user confirmed Trap Workshop uses the same home-city state categories as barracks for idle, ready-to-collect, and in-progress work
- user confirmed the Trap Workshop home-city markers use a different icon family than barracks even when the underlying state category is equivalent

Observed diamond-rush behavior:

- `Train Now` or `Craft Now` is the yellow diamond-cost rush action
- user explicitly does not want the automation to use the diamond-rush action

Current implementation assumptions:

- Trap Workshop and the barracks family should share one production-surface model in implementation.
- Trap Workshop and the barracks family should share the same underlying state model, even though their home-city state markers use different icon art.
- `train_units` and `craft_traps` should resolve tier selection, quantity selection, and starting the normal blue production button.
- Production automation should prefer the maximum trainable/craftable quantity by default.
- The quantity-lock toggle should be modeled as stateful production configuration rather than as a separate building type.
- `Train Now` and `Craft Now` should be treated as visible but intentionally unsupported diamond-rush actions.
- Ready-to-collect output should be modeled as the third primary queue-state action on the same production surface after idle `Train/Craft` and in-progress `Speedup`.
- `collect_trained_units` and `collect_crafted_traps` should be modeled as distinct post-production actions from starting production.
- `Siege Factory` should be the canonical building label for siege-unit production, even though the user earlier referred to it as Siege Barracks.

### 7.11 Large build slots, Blacksmith, Alliance Hall, and Market

Observed home-city large-slot evidence:

- large square plots below `Bulletin`

Observed large-slot build screen title:

- `Build`

Observed large-slot build options:

- `Alliance Hall`
- `Blacksmith`
- `Market`

Observed shared build messaging:

- `Owned: 0`
- `Requirements not met. Tap to view.`

Observed Blacksmith screen title and controls:

- `Blacksmith`
- `Glory Level`
- `Upgrade`
- fixed action rows such as `Gear`, `Gem`, `Saurgem`, `Hero Curio`, `Warsigil`, and `Ascend`

Observed Blacksmith state behavior:

- some rows are level-locked on the lower-level screenshot
- the higher-level screenshot shows more entries unlocked
- user confirmed Gear, Gem, and Saurgem are redundant with Lord Info tabs for current planning
- user confirmed Hero Curio is useful but deferred for later work

Observed Saurgem destination behavior:

- screen title `Saurgem`
- top progression/building markers such as `Lv.16`, `Lv.20`, `Lv.22`, and `Lv.30`
- current screenshot state shows `No saurgems`
- bottom `Get Saurgem` button
- `Cabinet` entry at the lower-right

Observed Ascend destination behavior:

- screen title `Ascend`
- central source/result item slots with an arrow between them
- supporting text `Select the item you'd like to ascend`
- bottom `Ascend` button
- separate bag screenshot text `Promote Gear to 10★ to unlock Ascension`

Observed Alliance Hall screen title and controls:

- `Alliance Hall`
- `Glory Level`
- `Upgrade`
- `Send Back`
- `Reinforce`

Observed Alliance Hall state behavior:

- current screenshot shows `No reinforcements from allies`
- `Reinforce` opens a context-specific `Alliance Member` list with per-row `Reinforce` buttons

Observed Market screen title and controls:

- `Market`
- `Glory Level`
- `Upgrade`
- `Resource Transport`

Observed Market state behavior:

- visible transport info such as `Transport Fee` and `Total Resources`
- `Resource Transport` opens a context-specific `Alliance Member` list with per-row `Transport` buttons
- user confirmed this transport flow is distinct from the reinforce flow and from the Alliance screen's member list

Current implementation assumptions:

- Blacksmith, Alliance Hall, and Market are constructed from the flexible large-slot build menu and then behave as normal built buildings.
- Blacksmith should expose a fixed, level-gated menu of destinations.
- Alliance Hall and Market should each own their own context-specific `Alliance Member` destination flow.
- Alliance Hall and Market should both be modeled as upgradeable Glory-capable buildings.

### 7.12 Hero Hall

Observed screen title:

- `Hero Hall`

Observed top tabs:

- `Recruit`
- `Exchange`

Observed Recruit-tab behavior:

- recruit pools such as `Basic Recruit`, `Adv. Recruit`, and `Rare Recruit`
- `Free`
- `Recruit 1x`
- `Recruit 10x`
- user confirmed token-based `Recruit 10x` for 9 tokens should always be favored over single-pull use when available

Observed Recruit-tab supporting content:

- fixed recruit banners/cards across the bottom
- token counts displayed near the recruit buttons

Observed Exchange-tab behavior:

- fixed fragment list with repeated `Exchange` buttons
- point resource labeled `Pts`

Observed related inventory evidence:

- recruit tokens are visible externally under `Bag -> Misc`
- shown examples include `Oath Rune I`, `Oath Rune II`, `Oath Rune III`, and `Timed Oath Rune`

Current implementation assumptions:

- Hero Hall should be modeled as a non-upgradeable building with fixed `Recruit` and `Exchange` tabs.
- Recruit pools should be treated as stable selectable banners rather than as an unbounded dynamic feed.
- The exchange list should be treated as a stable repeated list with per-row `Exchange` actions.
- Token inspection in `Bag -> Misc` is related evidence, but Bag should not be modeled as a Hero Hall-owned screen.
- Recruit-priority and token-spending policy should be owned by [PNC_HERO_HALL_POLICY_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_HERO_HALL_POLICY_SUBPLAN.md) instead of expanded further here.

### 7.13 Watchtower

Observed screen title:

- `Watch Tower`

Observed visible controls:

- `Glory Level`
- `Upgrade`

Observed visible tabs and content:

- `Attack Warning`
- `Recon Warning`
- `Reinforcement Warning`
- `Rally Warning`
- `No troops are approaching`

Current implementation assumptions:

- Watchtower is a fixed-position upgradeable building.
- Watchtower is Glory-capable.
- The warning tabs should currently be treated as passive information views rather than as primary actionable flows.

### 7.14 Sauroi Lair and Sauregg

Observed home-city building labels and states:

- `Sauroi Lair` in awakened form
- `Sauroi Lair` in egg form presentation before tutorial completion

Observed egg-form screen title:

- `Sauregg`

Observed egg-form controls and text:

- `Obtain`
- `Hatch 3 times to awaken Sauroi`
- `Next hatching requires Life Essence 0/1`

Observed awakened-form screen title:

- `Sauroi Lair`

Observed awakened-form controls and text:

- `Upgrade`
- current and next level benefit panels
- level-specific upgrade modifiers such as `Military Runestone` and `Economy Runestone`

Current implementation assumptions:

- Sauroi Lair is always at one fixed home-city position.
- Sauroi Lair is progression-stateful: the same building can appear in egg form before tutorial completion and in awakened form after unlock.
- The egg-form owned screen should currently be modeled as `sauregg`.
- The awakened form should use the normal owned Sauroi Lair detail screen with `Upgrade`.
- The user-confirmed tutorial-gated transition from `sauregg` to awakened `Sauroi Lair` should be owned by [PNC_TUTORIAL_ROUTINE_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TUTORIAL_ROUTINE_SUBPLAN.md) rather than remaining an open building-action question.

### 7.15 Campaign

Observed home-city building label:

- `Campaign`

Observed linked screen content:

- region nodes such as `Dawn Forest` and `Misty Bay`
- special destination `Neptune's Labyrinth`

Current implementation assumptions:

- Campaign is always present at one fixed home-city position.
- Campaign is non-upgradeable.
- The current screenshot should be modeled as a campaign map screen with tappable region or stage nodes.
- Detailed Campaign, Arena, and match-solver follow-up should be owned by [PNC_CAMPAIGN_ARENA_MATCH_SOLVER_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_CAMPAIGN_ARENA_MATCH_SOLVER_SUBPLAN.md).

### 7.16 Arena and Versus Center

Observed home-city building label:

- `Arena`

Observed owned screen title:

- `Versus Center`

Observed visible controls:

- `Arena`
- `Exchange Shop`

Observed visible entries:

- `Hero Showdown`
- `Hero Championship`

Current implementation assumptions:

- Arena is always present at one fixed home-city position.
- Arena is non-upgradeable.
- Arena opens the `Versus Center` screen.
- `Hero Showdown` and `Hero Championship` should be modeled as tappable entries on the `Arena` tab.
- Detailed Campaign, Arena, and match-solver follow-up should be owned by [PNC_CAMPAIGN_ARENA_MATCH_SOLVER_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_CAMPAIGN_ARENA_MATCH_SOLVER_SUBPLAN.md).

### 7.17 Wall and Defense Info

Observed home-city building label:

- `Wall`

Observed wall screen title:

- `Wall`

Observed visible controls:

- `Glory Level`
- `Upgrade`
- `Defense Info`
- `Repair Wall`

Observed stateful wall behavior:

- `Repair Wall` is clickable.
- `Repair Wall` turns red when the wall is damaged.
- `Repair Wall` remains present even when the wall is not damaged.

Observed Defense Info screen title:

- `Defense Info`

Observed Defense Info content:

- up to five hero slots across the top row
- existing assigned heroes when slots are occupied
- `+` buttons when fewer than five heroes are assigned

Current implementation assumptions:

- Wall is always present at one fixed home-city position.
- Wall is upgradeable.
- `Defense Info` and `Repair Wall` are both primary clickable actions on the Wall screen.
- `Defense Info` should be modeled as a Wall-owned linked screen.
- Empty Defense Info hero slots should be modeled as addable slots via the visible `+` button.
- `Repair Wall` should currently be treated as a trivial restore-to-max-HP action and intentionally skipped from active automation for now.

### 7.18 Unlockable territory below the wall and small build slots

Observed locked territory state:

- fog-covered terrain below the wall
- a visible lock icon that can be clicked
- quest text such as `Develop Territory (5/6)`

Observed unlocked territory state:

- the fogged region below the wall becomes visible and buildable
- small circular build spots appear in the unlocked areas
- built examples shown in the unlocked territory include `Moon Well`, `Infirmary`, `Farm`, `Lumber Camp`, `Recruiting Center`, and `Iron Mine`

Observed small-slot build menu title:

- `Build`

Observed small-slot build options:

- `Farm`
- `Lumber Camp`
- `Moon Well`
- `Recruiting Center`
- `Infirmary`
- `Iron Mine`
- `Gold Mine`

Current implementation assumptions:

- The territory below the wall is gated first by a territory unlock interaction and only then by normal building-slot interactions.
- The lock icon should be modeled as a territory-unlock control, not as a build slot.
- Once unlocked, the region exposes repeatable small build slots.
- Small build slots should use one shared multi-option `Build` menu.
- The small-slot building family should be modeled separately from both the dedicated fixed-slot buildings and the flexible large-slot buildings.

## 8. Initial action taxonomy

The seeded action vocabulary should start with these ids:

- `upgrade`
- `open`
- `train_units`
- `train_now`
- `open_unit_unlock_table`
- `speedup_training`
- `collect_trained_units`
- `unlock_territory_region`
- `open_small_build_menu`
- `construct_farm`
- `construct_lumber_camp`
- `construct_moon_well`
- `construct_recruiting_center`
- `construct_infirmary`
- `construct_iron_mine`
- `construct_gold_mine`
- `open_defense_info`
- `open_repair_wall`
- `add_wall_defender`
- `open_campaign`
- `open_campaign_region`
- `open_campaign_special_stage`
- `open_versus_center`
- `open_arena_tab`
- `open_exchange_shop_tab`
- `open_hero_showdown`
- `open_hero_championship`
- `obtain_life_essence`
- `open_fixed_build_menu`
- `construct_fixed_building`
- `open_large_build_menu`
- `construct_alliance_hall`
- `construct_blacksmith`
- `construct_market`
- `open_territory_overview`
- `open_glory_level`
- `open_development_research`
- `open_economy_research`
- `open_military_research`
- `open_fortification_research`
- `open_trap_effect_table`
- `set_prioritized_unit_type`
- `join_rally_attack`
- `reinforce_allies`
- `set_troop_formation`
- `open_hero_hall_recruit_tab`
- `select_hero_recruit_banner`
- `recruit_heroes_1x`
- `recruit_heroes_10x`
- `open_hero_hall_exchange_tab`
- `exchange_hero_fragments`
- `open_gear_screen`
- `open_gem_screen`
- `open_saurgem_screen`
- `get_saurgem`
- `open_hero_curio`
- `open_warsigil_screen`
- `open_ascend_screen`
- `ascend_item`
- `open_reinforcement_member_list`
- `reinforce_ally`
- `send_back_reinforcements`
- `open_transport_member_list`
- `transport_resources_to_ally`
- `open_artifact_collection`
- `browse_artifacts`
- `inspect_artifact`
- `open_relics`
- `browse_relic_sets`
- `open_event_relic_tab`
- `open_private_collection_tab`
- `inspect_relic_set`
- `open_trial_challenge`
- `open_trial_exchange`
- `open_trial_progress`
- `open_trial_total_rank`
- `open_trial_entry_rank`
- `open_trial_entry_stats`
- `start_trial_stage`
- `speedup_upgrade`
- `craft_now`
- `craft_traps`
- `speedup_crafting`
- `collect_crafted_traps`
- `open_blessing_record`
- `open_blessing_record_lord_tree`
- `bless_other_lord_tree`
- `harvest`
- `open_rare_earth_field`
- `exchange_rare_earth`
- `enter_field`
- `switch_mine`
- `attack_mine`
- `dispatch_attack`

This action list is intentionally explicit. We should prefer exact action ids over generic labels such as `special_action_1`.

## 9. UI action archetypes

The currently known building screens already show multiple distinct interaction shapes:

- static screen buttons such as `Upgrade`, `Glory Level`, `Territory Overview`, `Harvest`, `Exchange`, and `Enter Field`,
- stateful action tiles such as Wall `Defense Info` and `Repair Wall`,
- category-entry buttons such as Institute `Development`, `Economy`, `Military`, and `Fortification`,
- single-option build menus for dedicated fixed slots,
- multi-option build menus for flexible large slots,
- multi-option build menus for repeatable small slots,
- dropdown or selector-style controls such as `Prioritized Unit Type`,
- home-city overlay icons such as Sanctum `Artifact` and `Relic`,
- stateful owned screens for the same building such as Sauroi egg form versus awakened form,
- repeated row actions such as Hall of War `Go` rows,
- fixed row actions keyed to stable named entries such as Trial Challenge `Rank`, `Stats`, and `Trial`,
- repeated row actions with state-dependent button labels such as Rare Earth Field `Enter Field`, `Switch Mine`, and `Attack`,
- repeated collection/list entries such as Sanctum artifact cards and Relics set rows,
- modal list entries with per-row navigation such as Sacred Tree `Blessing Record`,
- fixed destination entries such as Versus Center `Hero Showdown` and `Hero Championship`,
- info-only linked screens such as Castle `Territory Overview`,
- fixed menu rows with level-gated destinations such as Blacksmith `Gear`, `Gem`, `Saurgem`, `Hero Curio`, and `Warsigil`,
- shared production surfaces with tier selection, quantity controls, and queue-state buttons such as the barracks family and Trap Workshop,
- context-specific alliance member lists such as Alliance Hall `Reinforce` and Market `Transport`,
- fixed recruit-banner carousels with repeated pull buttons such as Hero Hall,
- fixed hero assignment slots with add buttons such as Wall `Defense Info`,
- stateful enable/disable actions such as Sacred Tree `Harvest` and remote-tree `Bless`,
- quantity-adjustment controls and craft buttons such as Trap Workshop `Craft Now` and `Craft`,
- unlock controls for fogged territory regions,
- map-node entry points such as Campaign region nodes,
- reserved prebuild slots such as the circular Goddess Statue platform,
- linked-screen transitions such as `Pit -> Rare Earth Field`.

The implementation should support those archetypes directly rather than forcing every building into the current single "open details, then press Upgrade" path.

## 10. Initial implementation slices

### Slice 1: canonical building ids and metadata

- replace coarse building categories with exact building ids in home-city observation metadata,
- preserve optional higher-level grouping such as `barracks_family`,
- attach capability metadata so task logic can decide whether a building supports upgrade, train, or only open actions,
- allow reserved-slot metadata when the visible plot is semantically tied to one future building such as Goddess Statue,
- distinguish dedicated fixed build slots from flexible large build slots,
- distinguish unlocked repeatable small build slots from both dedicated fixed slots and large build slots,
- allow stateful fixed-position buildings such as Sauroi Lair to expose different owned screens under one canonical building id.

### Slice 2: building-owned screen modeling

- distinguish home-city building identity from linked destination screens,
- explicitly model dedicated fixed-slot build menus for Institute, Warehouse, and Trap Workshop,
- explicitly model flexible large-slot build menus for Blacksmith, Alliance Hall, and Market,
- explicitly model territory unlock controls and small-slot build menus for the below-wall region,
- explicitly model the shared barracks/trap-workshop production surface and its unlock-table destinations,
- explicitly model `wall -> defense_info`,
- explicitly model `castle -> territory_overview`,
- explicitly model `campaign -> campaign_map`,
- explicitly model `arena -> versus_center`,
- explicitly model `alliance_hall -> alliance_member_reinforce` and `market -> alliance_member_transport`,
- explicitly model the fixed Hero Hall tab set and recruit-banner flows,
- explicitly model `sauroi_lair -> sauregg` and `sauroi_lair -> awakened Sauroi Lair detail screen` according to progression state,
- explicitly model `pit -> rare_earth_field`,
- explicitly model Castle-owned screen actions such as `Territory Overview` and conditional `Glory Level`,
- explicitly model `sacred_tree -> sacred_tree_blessing_record -> other_lord_sacred_tree`,
- explicitly model `tower_of_trial -> trial_challenge`,
- explicitly model Castle, Hall of War, Sacred Tree, Goddess Statue, Institute, Warehouse, Trap Workshop, the barracks family, Blacksmith, Alliance Hall, Market, Wall, Watchtower, Hero Hall, and Sauroi Lair action screens as building-owned interaction surfaces.

### Slice 3: shared building action flow

- extract one shared path for selecting a building, opening its screen, and resolving available actions,
- keep `building_upgrade` as the first concrete consumer,
- add non-upgrade actions from the same registry once their screenshots are available.

### Selector updates required

Yes, the relevant selectors and screen evidence will need to be updated as part of implementation.

Required selector work for the current building set includes:

- home-city OCR and spatial-object recognition for Castle, fixed utility buildings, the barracks family, permanent non-upgradeable buildings, Sauroi Lair states, flexible large build slots, locked territory regions, and small build slots,
- screen recognition for `Castle`, `Territory Overview`, `Wall`, `Defense Info`, `Sacred Tree`, `Blessing Record`, `other_lord_sacred_tree`, `Trial Challenge`, `Goddess Statue`, `Institute`, `Warehouse`, `Trap Workshop`, `trap_workshop_effect_table`, `barracks_unlock_table`, `Hero Hall`, `Watch Tower`, `Blacksmith`, `Gear`, `Gem`, `Warsigil`, `Hero Curio`, `Alliance Hall`, `Alliance Member`, `Market`, `Sauregg`, `Versus Center`, `Build`, and the current Campaign map view,
- selector coverage for static buttons and tiles such as `Territory Overview`, `Exchange`, `Progress`, `Total Rank`, `Glory Level`, `Upgrade`, `Speedup`, `Craft Now`, `Craft`, `Train`, `Train Now`, `Defense Info`, `Repair Wall`, `Arena`, `Exchange Shop`, `Obtain`, `Harvest`, `Bless`, `Reinforce`, and `Resource Transport`,
- selector coverage for build-menu options such as `Institute`, `Trap Workshop`, `Alliance Hall`, `Blacksmith`, `Market`, `Farm`, `Lumber Camp`, `Moon Well`, `Recruiting Center`, `Infirmary`, `Iron Mine`, and `Gold Mine`,
- selector coverage for Campaign map nodes and Versus Center entries,
- selector coverage for barracks/trap tier selectors, quantity controls, quantity-lock state, queue-state buttons, and home-city production-state indicators,
- selector coverage for Blacksmith destination rows and Hero Hall recruit/exchange surfaces,
- selector coverage for context-specific Alliance Member rows and their context-specific primary buttons,
- selector coverage for Sacred Tree progress nodes, Blessing Record rows, visit-tree controls, and ready-state indicators such as the user-confirmed gift badge,
- selector coverage for Defense Info hero slots and empty-slot `+` buttons,
- selector coverage for territory lock controls and small-slot build spots,
- stable row/slot recognition for Trial Challenge entries, including their availability state instead of treating them as dynamic list content,
- preserving the distinction between fixed selectors, repeated list entries, and building-owned linked screens.

### Planned selectors from provided screenshots

These are proposed selector ids only. They are not implemented yet.

Home-city building names such as `castle`, `wall`, `institute`, `warehouse`, `trap_workshop`, `infantry_barracks`, `cavalry_barracks`, `ranged_barracks`, `siege_factory`, `watchtower`, `hall_of_war`, `hero_hall`, `sanctum`, `tower_of_trial`, `sauroi_lair`, `campaign`, `arena`, `goddess_statue`, `sacred_tree`, `pit`, `blacksmith`, `alliance_hall`, `market`, and the repeatable small-slot building family should still be recognized primarily as spatial objects with building metadata, not as fixed `UiElementId` selectors.

Planned fixed selectors and structured-entry selectors from the currently provided screenshots:

| Proposed selector id | Screen or surface | Planned kind | Basis from screenshots |
| --- | --- | --- | --- |
| `PNC_CASTLE_HEADER` | `castle` | fixed selector | Screen title `Castle`. |
| `PNC_CASTLE_TERRITORY_OVERVIEW_BUTTON` | `castle` | fixed selector | Round icon with three vertical bars in a circle beside the green `Territory Overview` label. |
| `PNC_CASTLE_GLORY_LEVEL_BUTTON` | `castle` | fixed selector | Button labeled `Glory Level` when the Castle Glory feature is visible. |
| `PNC_CASTLE_UPGRADE_BUTTON` | `castle` | fixed selector | Button labeled `Upgrade`. |
| `PNC_TERRITORY_OVERVIEW_HEADER` | `territory_overview` | fixed selector | Screen title `Territory Overview`. |
| `PNC_HALL_OF_WAR_HEADER` | `hall_of_war` | fixed selector | Screen title `Hall of War`. |
| `PNC_HALL_OF_WAR_PRIORITIZED_UNIT_TYPE_DROPDOWN` | `hall_of_war` | fixed selector | Button/dropdown labeled `Prioritized Unit Type`. |
| `PNC_HALL_OF_WAR_GLORY_LEVEL_BUTTON` | `hall_of_war` | fixed selector | Button labeled `Glory Level`. |
| `PNC_HALL_OF_WAR_UPGRADE_BUTTON` | `hall_of_war` | fixed selector | Button labeled `Upgrade`. |
| `PNC_HALL_OF_WAR_JOIN_RALLY_ATTACK_GO_BUTTON` | `hall_of_war` | fixed selector | `Go` button on the `Join Rally Attack` row. |
| `PNC_HALL_OF_WAR_REINFORCE_ALLIES_GO_BUTTON` | `hall_of_war` | fixed selector | `Go` button on the `Reinforce Allies` row. |
| `PNC_HALL_OF_WAR_TROOP_FORMATION_SET_GO_BUTTON` | `hall_of_war` | fixed selector | `Go` button on the `Troop Form. Set` row. |
| `PNC_INFANTRY_BARRACKS_HEADER` | `infantry_barracks` | fixed selector | Screen title `Infantry Barracks`. |
| `PNC_CAVALRY_BARRACKS_HEADER` | `cavalry_barracks` | fixed selector | Screen title `Cavalry Barracks`. |
| `PNC_RANGED_BARRACKS_HEADER` | `ranged_barracks` | fixed selector | Screen title `Ranged Barracks`. |
| `PNC_SIEGE_FACTORY_HEADER` | `siege_factory` | fixed selector | Screen title `Siege Factory`. |
| `PNC_BARRACKS_GLORY_LEVEL_BUTTON` | `infantry_barracks`, `cavalry_barracks`, `ranged_barracks`, `siege_factory` | fixed selector | Button labeled `Glory Level`. |
| `PNC_BARRACKS_UPGRADE_BUTTON` | `infantry_barracks`, `cavalry_barracks`, `ranged_barracks`, `siege_factory` | fixed selector | Button labeled `Upgrade`, or building-level `Speedup` while the upgrade is already in progress. |
| `PNC_BARRACKS_UNIT_ADVANTAGE_BUTTON` | `infantry_barracks`, `cavalry_barracks`, `ranged_barracks`, `siege_factory` | fixed selector | Green `Unit Advantage` entry that opens the level-effect unlock table. |
| `PNC_BARRACKS_UNIT_TIER_SLOT` | `infantry_barracks`, `cavalry_barracks`, `ranged_barracks`, `siege_factory` | structured entry selector | Tier icons such as `T1`, `T4`, `T5`, `T6`, and locked higher tiers. |
| `PNC_BARRACKS_QUANTITY_LOCK_BUTTON` | `infantry_barracks`, `cavalry_barracks`, `ranged_barracks`, `siege_factory` | fixed selector | Lock toggle that preserves a fixed training quantity when enabled. |
| `PNC_BARRACKS_QUANTITY_SLIDER` | `infantry_barracks`, `cavalry_barracks`, `ranged_barracks`, `siege_factory` | fixed selector | Quantity slider with minus/plus controls for troop count selection. |
| `PNC_BARRACKS_TRAIN_BUTTON` | `infantry_barracks`, `cavalry_barracks`, `ranged_barracks`, `siege_factory` | fixed selector | Blue `Train` button with estimated time display when idle and trainable. |
| `PNC_BARRACKS_TRAIN_NOW_BUTTON` | `infantry_barracks`, `cavalry_barracks`, `ranged_barracks`, `siege_factory` | fixed selector | Yellow diamond-cost `Train Now` button that should not be used by automation. |
| `PNC_BARRACKS_SPEEDUP_BUTTON` | `infantry_barracks`, `cavalry_barracks`, `ranged_barracks`, `siege_factory` | fixed selector | Yellow `Speedup` button shown while troop training is already in progress. |
| `PNC_BARRACKS_COLLECT_BUTTON` | `infantry_barracks`, `cavalry_barracks`, `ranged_barracks`, `siege_factory` | fixed selector | Primary queue-state button shown when finished troops are ready to collect. |
| `PNC_BARRACKS_EFFECT_TABLE_ROW` | `barracks_unlock_table` | structured entry selector | Level/effect rows in the barracks unlock table. |
| `PNC_WALL_HEADER` | `wall` | fixed selector | Screen title `Wall`. |
| `PNC_WALL_GLORY_LEVEL_BUTTON` | `wall` | fixed selector | Button labeled `Glory Level` when present. |
| `PNC_WALL_UPGRADE_BUTTON` | `wall` | fixed selector | Button labeled `Upgrade`. |
| `PNC_WALL_DEFENSE_INFO_TILE` | `wall` | fixed selector | Clickable tile labeled `Defense Info`. |
| `PNC_WALL_REPAIR_WALL_TILE` | `wall` | fixed selector | Clickable tile labeled `Repair Wall`; tile turns red when the wall is damaged. |
| `PNC_DEFENSE_INFO_HEADER` | `defense_info` | fixed selector | Screen title `Defense Info`. |
| `PNC_DEFENSE_INFO_HERO_SLOT` | `defense_info` | structured entry selector | Top-row defender hero slots. |
| `PNC_DEFENSE_INFO_ADD_HERO_BUTTON` | `defense_info` | structured child selector | `+` button shown in empty hero slots when fewer than five defenders are assigned. |
| `PNC_SACRED_TREE_HEADER` | `sacred_tree` | fixed selector | Screen title `Sacred Tree`. |
| `PNC_SACRED_TREE_BLESSING_RECORD_BUTTON` | `sacred_tree` | fixed selector | Button labeled `Blessing Record`. |
| `PNC_SACRED_TREE_GROWTH_REWARD_PANEL` | `sacred_tree` | fixed selector | Right-side `Growth Reward` reward preview panel; currently display-only. |
| `PNC_SACRED_TREE_PROGRESS_NODE` | `sacred_tree`, `other_lord_sacred_tree` | structured entry selector | Filled and unfilled blessing-progress nodes shown above `Harvest` or `Bless`. |
| `PNC_SACRED_TREE_HARVEST_BUTTON` | `sacred_tree` | fixed selector | Bottom button labeled `Harvest`. |
| `PNC_SACRED_TREE_BLESSING_RECORD_HEADER` | `sacred_tree_blessing_record` | fixed selector | Overlay title `Blessing Record`. |
| `PNC_SACRED_TREE_BLESSING_RECORD_ROW` | `sacred_tree_blessing_record` | structured entry selector | Repeated lord rows with portrait, player name, and time. |
| `PNC_SACRED_TREE_BLESSING_RECORD_ROW_VISIT_TREE_BUTTON` | `sacred_tree_blessing_record` | structured child selector | Tree/arrow visit control at the right side of each blessing-record row. |
| `PNC_OTHER_LORD_SACRED_TREE_OWNER_NAME_LABEL` | `other_lord_sacred_tree` | fixed selector | Owner name shown above the progress nodes. |
| `PNC_OTHER_LORD_SACRED_TREE_BLESS_BUTTON` | `other_lord_sacred_tree` | fixed selector | Bottom button labeled `Bless`; can be enabled or greyed. |
| `PNC_RARE_EARTH_FIELD_HEADER` | `rare_earth_field` | fixed selector | Screen title `Rare Earth Field`. |
| `PNC_RARE_EARTH_FIELD_EXCHANGE_BUTTON` | `rare_earth_field` | fixed selector | Button labeled `Exchange`. |
| `PNC_RARE_EARTH_FIELD_ENTER_FIELD_BUTTON` | `rare_earth_field` | fixed selector | Button labeled `Enter Field` for the currently selected mine. |
| `PNC_RARE_EARTH_FIELD_GOLD_PICKAXE_CONTROL` | `rare_earth_field` | fixed selector | Gold Pickaxe control shown on the Rare Earth Field surface; current evidence keeps it within this same screen. |
| `PNC_RARE_EARTH_FIELD_MINE_ROW` | `rare_earth_field` | structured entry selector | Fixed mine-level rows keyed by visible level numbers such as `1` through `9`. |
| `PNC_RARE_EARTH_FIELD_MINE_ROW_PRIMARY_ACTION_BUTTON` | `rare_earth_field` | structured child selector | Row action region that changes by progression state between `Switch Mine`, `Attack`, or no button when a prerequisite message is shown. |
| `PNC_DISPATCH_HEADER` | `dispatch` | fixed selector | Screen title `Dispatch`. |
| `PNC_DISPATCH_CLEAR_HERO_BUTTON` | `dispatch` | fixed selector | Button labeled `Clear Hero`. |
| `PNC_DISPATCH_TROOP_ROW` | `dispatch` | structured entry selector | Repeated troop rows such as `Dragon Warmaster` and `Whale Catapult`. |
| `PNC_DISPATCH_APPLICABLE_STATS_BUTTON` | `dispatch` | fixed selector | Entry labeled `Applicable Stats`. |
| `PNC_DISPATCH_SKIP_CHECKBOX` | `dispatch` | fixed selector | `Skip` checkbox near the bottom of the dispatch screen. |
| `PNC_DISPATCH_BUTTON` | `dispatch` | fixed selector | Bottom button labeled `Dispatch`. |
| `PNC_SANCTUM_ARTIFACT_BUTTON` | home-city Sanctum overlay | fixed selector | Overlay icon labeled `Artifact`. |
| `PNC_SANCTUM_RELIC_BUTTON` | home-city Sanctum overlay | fixed selector | Overlay icon labeled `Relic`. |
| `PNC_SANCTUM_HEADER` | Sanctum artifact screen | fixed selector | Screen title remains `Sanctum`. |
| `PNC_SANCTUM_ARTIFACT_CARD` | Sanctum artifact screen | structured entry selector | Repeated artifact cards in the lower grid. |
| `PNC_SANCTUM_ARTIFACT_CARD_INSPECT_BUTTON` | Sanctum artifact screen | structured child selector | Magnifier overlay on each artifact card. |
| `PNC_SANCTUM_ARTIFACT_DETAIL_TITLE_LABEL` | Sanctum artifact screen | fixed selector | Selected artifact title such as `Portal Scroll`. |
| `PNC_RELICS_HEADER` | `relics` | fixed selector | Screen title `Relics`. |
| `PNC_RELICS_TAB_SET_LIST` | `relics` | fixed selector | Top tab `Set List`. |
| `PNC_RELICS_TAB_EVENT_RELIC` | `relics` | fixed selector | Top tab `Event Relic`. |
| `PNC_RELICS_TAB_PRIVATE_COLLECTION` | `relics` | fixed selector | Top tab `Private Collection`. |
| `PNC_RELICS_SET_ROW` | `relics` | structured entry selector | Repeated relic-set rows such as `Lv.1 Gale Instrument (2/8)`. |
| `PNC_RELICS_SET_ROW_ACTION_BUTTON` | `relics` | structured child selector | Small row action button at the right of each relic-set row. Detailed row-destination ownership is deferred to [PNC_RELICS_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_RELICS_SUBPLAN.md). |
| `PNC_TRIAL_CHALLENGE_HEADER` | `trial_challenge` | fixed selector | Screen title `Trial Challenge`. |
| `PNC_TRIAL_CHALLENGE_EXCHANGE_BUTTON` | `trial_challenge` | fixed selector | Top button `Exchange`. |
| `PNC_TRIAL_CHALLENGE_PROGRESS_BUTTON` | `trial_challenge` | fixed selector | Top button `Progress`. |
| `PNC_TRIAL_CHALLENGE_TOTAL_RANK_BUTTON` | `trial_challenge` | fixed selector | Top button `Total Rank`. |
| `PNC_TRIAL_CHALLENGE_HERO_TRIAL_ROW` | `trial_challenge` | fixed slot selector | Stable row labeled `Hero Trial`. |
| `PNC_TRIAL_CHALLENGE_CURIO_TRIAL_ROW` | `trial_challenge` | fixed slot selector | Stable row labeled `Curio Trial`. |
| `PNC_TRIAL_CHALLENGE_TECH_TRIAL_ROW` | `trial_challenge` | fixed slot selector | Stable row labeled `Tech Trial`. |
| `PNC_TRIAL_CHALLENGE_GEAR_TRIAL_ROW` | `trial_challenge` | fixed slot selector | Stable row labeled `Gear Trial`. |
| `PNC_TRIAL_CHALLENGE_RUNE_TRIAL_ROW` | `trial_challenge` | fixed slot selector | Stable row labeled `Rune Trial`. |
| `PNC_TRIAL_CHALLENGE_SAUROI_TRIAL_ROW` | `trial_challenge` | fixed slot selector | Stable row labeled `Sauroi Trial`. |
| `PNC_TRIAL_CHALLENGE_ROW_RANK_BUTTON` | `trial_challenge` | relative child selector | `Rank` button resolved within one stable trial row. |
| `PNC_TRIAL_CHALLENGE_ROW_STATS_BUTTON` | `trial_challenge` | relative child selector | `Stats` button resolved within one stable trial row. |
| `PNC_TRIAL_CHALLENGE_ROW_TRIAL_BUTTON` | `trial_challenge` | relative child selector | `Trial` button resolved within one stable trial row when accessible. |
| `PNC_SAUREGG_HEADER` | `sauregg` | fixed selector | Screen title `Sauregg`. |
| `PNC_SAUREGG_OBTAIN_BUTTON` | `sauregg` | fixed selector | Button labeled `Obtain`. |
| `PNC_SAUROI_LAIR_HEADER` | `sauroi_lair` | fixed selector | Screen title `Sauroi Lair`. |
| `PNC_SAUROI_LAIR_UPGRADE_BUTTON` | `sauroi_lair` | fixed selector | Button labeled `Upgrade`. |
| `PNC_CAMPAIGN_MAP_REGION_NODE` | `campaign_map` | structured entry selector | Region nodes such as `Dawn Forest` and `Misty Bay`. |
| `PNC_CAMPAIGN_MAP_SPECIAL_STAGE_NODE` | `campaign_map` | structured entry selector | Special destination such as `Neptune's Labyrinth`. |
| `PNC_VERSUS_CENTER_HEADER` | `versus_center` | fixed selector | Screen title `Versus Center`. |
| `PNC_VERSUS_CENTER_TAB_ARENA` | `versus_center` | fixed selector | Top tab labeled `Arena`. |
| `PNC_VERSUS_CENTER_TAB_EXCHANGE_SHOP` | `versus_center` | fixed selector | Top tab labeled `Exchange Shop`. |
| `PNC_VERSUS_CENTER_HERO_SHOWDOWN_ENTRY` | `versus_center` | fixed selector | Entry labeled `Hero Showdown`. |
| `PNC_VERSUS_CENTER_HERO_CHAMPIONSHIP_ENTRY` | `versus_center` | fixed selector | Entry labeled `Hero Championship`. |
| `PNC_GODDESS_STATUE_HEADER` | `goddess_statue` | fixed selector | Screen title `Goddess Statue`. |
| `PNC_GODDESS_STATUE_GLORY_LEVEL_BUTTON` | `goddess_statue` | fixed selector | Button labeled `Glory Level`. |
| `PNC_GODDESS_STATUE_UPGRADE_BUTTON` | `goddess_statue` | fixed selector | Button labeled `Upgrade` when the building is idle. |
| `PNC_GODDESS_STATUE_SPEEDUP_BUTTON` | `goddess_statue` | fixed selector | Button labeled `Speedup` on the in-progress screen. |
| `PNC_GODDESS_STATUE_LEVEL_LABEL` | `goddess_statue` | fixed selector | Visible level text such as `Lv.13 Goddess Statue`. |
| `PNC_TERRITORY_UNLOCK_LOCK_ICON` | home-city locked territory region | fixed selector | Visible lock icon used to unlock the fogged territory below the wall. |
| `PNC_SMALL_TERRITORY_BUILD_SLOT` | home-city unlocked small-slot region | spatial slot selector | Small circular build spots that appear after unlocking the territory below the wall. |
| `PNC_BUILD_HEADER` | `build_menu_fixed_slot`, `build_menu_large_slot`, `build_menu_small_slot` | fixed selector | Screen title `Build`. |
| `PNC_BUILD_OPTION_ROW` | `build_menu_fixed_slot`, `build_menu_large_slot`, `build_menu_small_slot` | structured entry selector | Build-menu entry rows with building art, name, and requirement text. |
| `PNC_BUILD_INSTITUTE_OPTION` | `build_menu_fixed_slot` | fixed selector | Single-option build entry labeled `Institute`. |
| `PNC_BUILD_WAREHOUSE_OPTION` | `build_menu_fixed_slot` | fixed selector | Single-option build entry labeled `Warehouse`. |
| `PNC_BUILD_TRAP_WORKSHOP_OPTION` | `build_menu_fixed_slot` | fixed selector | Single-option build entry labeled `Trap Workshop`. |
| `PNC_BUILD_GODDESS_STATUE_OPTION` | `build_menu_fixed_slot` | fixed selector | Single-option build entry labeled `Goddess Statue`. |
| `PNC_BUILD_ALLIANCE_HALL_OPTION` | `build_menu_large_slot` | fixed selector | Build entry labeled `Alliance Hall`. |
| `PNC_BUILD_BLACKSMITH_OPTION` | `build_menu_large_slot` | fixed selector | Build entry labeled `Blacksmith`. |
| `PNC_BUILD_MARKET_OPTION` | `build_menu_large_slot` | fixed selector | Build entry labeled `Market`. |
| `PNC_BUILD_FARM_OPTION` | `build_menu_small_slot` | fixed selector | Build entry labeled `Farm`. |
| `PNC_BUILD_LUMBER_CAMP_OPTION` | `build_menu_small_slot` | fixed selector | Build entry labeled `Lumber Camp`. |
| `PNC_BUILD_MOON_WELL_OPTION` | `build_menu_small_slot` | fixed selector | Build entry labeled `Moon Well`. |
| `PNC_BUILD_RECRUITING_CENTER_OPTION` | `build_menu_small_slot` | fixed selector | Build entry labeled `Recruiting Center`. |
| `PNC_BUILD_INFIRMARY_OPTION` | `build_menu_small_slot` | fixed selector | Build entry labeled `Infirmary`. |
| `PNC_BUILD_IRON_MINE_OPTION` | `build_menu_small_slot` | fixed selector | Build entry labeled `Iron Mine`. |
| `PNC_BUILD_GOLD_MINE_OPTION` | `build_menu_small_slot` | fixed selector | Build entry labeled `Gold Mine`. |
| `PNC_INSTITUTE_HEADER` | `institute` | fixed selector | Screen title `Institute`. |
| `PNC_INSTITUTE_GLORY_LEVEL_BUTTON` | `institute` | fixed selector | Button labeled `Glory Level`. |
| `PNC_INSTITUTE_UPGRADE_BUTTON` | `institute` | fixed selector | Button labeled `Upgrade`. |
| `PNC_INSTITUTE_DEVELOPMENT_BUTTON` | `institute` | fixed selector | Category button labeled `Development`. |
| `PNC_INSTITUTE_ECONOMY_BUTTON` | `institute` | fixed selector | Category button labeled `Economy`. |
| `PNC_INSTITUTE_MILITARY_BUTTON` | `institute` | fixed selector | Category button labeled `Military`. |
| `PNC_INSTITUTE_FORTIFICATION_BUTTON` | `institute` | fixed selector | Category button labeled `Fortification`. |
| `PNC_INSTITUTE_RESEARCH_QUEUE_PANEL` | `institute` | fixed selector | Bottom `Research Queue` panel. |
| `PNC_WAREHOUSE_HEADER` | `warehouse` | fixed selector | Screen title `Warehouse`. |
| `PNC_WAREHOUSE_GLORY_LEVEL_BUTTON` | `warehouse` | fixed selector | Button labeled `Glory Level`. |
| `PNC_WAREHOUSE_UPGRADE_BUTTON` | `warehouse` | fixed selector | Button labeled `Upgrade`. |
| `PNC_TRAP_WORKSHOP_HEADER` | `trap_workshop` | fixed selector | Screen title `Trap Workshop`. |
| `PNC_TRAP_WORKSHOP_GLORY_LEVEL_BUTTON` | `trap_workshop` | fixed selector | Button labeled `Glory Level`. |
| `PNC_TRAP_WORKSHOP_UPGRADE_BUTTON` | `trap_workshop` | fixed selector | Button labeled `Upgrade`. |
| `PNC_TRAP_WORKSHOP_UNIT_ADVANTAGE_BUTTON` | `trap_workshop` | fixed selector | Green `Unit Advantage` entry that opens the trap effect table. |
| `PNC_TRAP_WORKSHOP_QUANTITY_LOCK_BUTTON` | `trap_workshop` | fixed selector | Lock toggle that preserves a fixed trap-crafting quantity when enabled. |
| `PNC_TRAP_WORKSHOP_QUANTITY_SLIDER` | `trap_workshop` | fixed selector | Quantity slider with minus/plus controls for trap count selection. |
| `PNC_TRAP_WORKSHOP_CRAFT_NOW_BUTTON` | `trap_workshop` | fixed selector | Button labeled `Craft Now`. |
| `PNC_TRAP_WORKSHOP_CRAFT_BUTTON` | `trap_workshop` | fixed selector | Button labeled `Craft`. |
| `PNC_TRAP_WORKSHOP_SPEEDUP_BUTTON` | `trap_workshop` | fixed selector | Yellow `Speedup` button shown while trap crafting is already in progress. |
| `PNC_TRAP_WORKSHOP_COLLECT_BUTTON` | `trap_workshop` | fixed selector | Primary queue-state button shown when finished traps are ready to collect. |
| `PNC_TRAP_WORKSHOP_TRAP_TIER_SLOT` | `trap_workshop` | structured entry selector | Trap-tier icons such as `T2`, `T3`, and locked higher tiers. |
| `PNC_TRAP_WORKSHOP_EFFECT_TABLE_ROW` | `trap_workshop_effect_table` | structured entry selector | Level/effect rows in the trap workshop effect table. |
| `PNC_HERO_HALL_HEADER` | `hero_hall` | fixed selector | Screen title `Hero Hall`. |
| `PNC_HERO_HALL_RECRUIT_TAB` | `hero_hall` | fixed selector | Top tab labeled `Recruit`. |
| `PNC_HERO_HALL_EXCHANGE_TAB` | `hero_hall` | fixed selector | Top tab labeled `Exchange`. |
| `PNC_HERO_HALL_RECRUIT_BANNER` | `hero_hall` | structured entry selector | Stable recruit banners such as `Basic Recruit`, `Adv. Recruit`, and `Rare Recruit`. |
| `PNC_HERO_HALL_RECRUIT_1X_BUTTON` | `hero_hall` | fixed selector | Button labeled `Recruit 1x`. |
| `PNC_HERO_HALL_RECRUIT_10X_BUTTON` | `hero_hall` | fixed selector | Button labeled `Recruit 10x`. |
| `PNC_HERO_HALL_EXCHANGE_ROW` | `hero_hall` | structured entry selector | Fixed fragment rows on the Exchange tab. |
| `PNC_HERO_HALL_EXCHANGE_ROW_BUTTON` | `hero_hall` | structured child selector | Row-local `Exchange` button on Hero Hall Exchange entries. |
| `PNC_WATCHTOWER_HEADER` | `watchtower` | fixed selector | Screen title `Watch Tower`. |
| `PNC_WATCHTOWER_GLORY_LEVEL_BUTTON` | `watchtower` | fixed selector | Button labeled `Glory Level`. |
| `PNC_WATCHTOWER_UPGRADE_BUTTON` | `watchtower` | fixed selector | Button labeled `Upgrade`. |
| `PNC_BLACKSMITH_HEADER` | `blacksmith` | fixed selector | Screen title `Blacksmith`. |
| `PNC_BLACKSMITH_GLORY_LEVEL_BUTTON` | `blacksmith` | fixed selector | Button labeled `Glory Level`. |
| `PNC_BLACKSMITH_UPGRADE_BUTTON` | `blacksmith` | fixed selector | Button labeled `Upgrade`. |
| `PNC_BLACKSMITH_MENU_ROW` | `blacksmith` | structured entry selector | Fixed destination rows such as `Gear`, `Gem`, `Saurgem`, `Hero Curio`, `Warsigil`, and `Ascend`. |
| `PNC_BLACKSMITH_GEAR_ROW` | `blacksmith` | fixed selector | Destination row labeled `Gear`. |
| `PNC_BLACKSMITH_GEM_ROW` | `blacksmith` | fixed selector | Destination row labeled `Gem`. |
| `PNC_BLACKSMITH_SAURGEM_ROW` | `blacksmith` | fixed selector | Destination row labeled `Saurgem`. |
| `PNC_BLACKSMITH_HERO_CURIO_ROW` | `blacksmith` | fixed selector | Destination row labeled `Hero Curio`. |
| `PNC_BLACKSMITH_WARSIGIL_ROW` | `blacksmith` | fixed selector | Destination row labeled `Warsigil`. |
| `PNC_BLACKSMITH_ASCEND_ROW` | `blacksmith` | fixed selector | Destination row labeled `Ascend`. |
| `PNC_GEAR_HEADER` | `gear` | fixed selector | Screen title `Gear`. |
| `PNC_GEM_HEADER` | `gem` | fixed selector | Screen title `Gem`. |
| `PNC_SAURGEM_HEADER` | `saurgem` | fixed selector | Screen title `Saurgem`. |
| `PNC_SAURGEM_GET_BUTTON` | `saurgem` | fixed selector | Bottom button labeled `Get Saurgem`. |
| `PNC_WARSIGIL_HEADER` | `warsigil` | fixed selector | Screen title `Warsigil`. |
| `PNC_HERO_CURIO_HEADER` | `hero_curio` | fixed selector | Screen title `Hero Curio`. |
| `PNC_ASCEND_HEADER` | `ascend` | fixed selector | Screen title `Ascend`. |
| `PNC_ASCEND_BUTTON` | `ascend` | fixed selector | Bottom button labeled `Ascend`. |
| `PNC_ALLIANCE_HALL_HEADER` | `alliance_hall` | fixed selector | Screen title `Alliance Hall`. |
| `PNC_ALLIANCE_HALL_GLORY_LEVEL_BUTTON` | `alliance_hall` | fixed selector | Button labeled `Glory Level`. |
| `PNC_ALLIANCE_HALL_UPGRADE_BUTTON` | `alliance_hall` | fixed selector | Button labeled `Upgrade`. |
| `PNC_ALLIANCE_HALL_SEND_BACK_BUTTON` | `alliance_hall` | fixed selector | Bottom button labeled `Send Back`. |
| `PNC_ALLIANCE_HALL_REINFORCE_BUTTON` | `alliance_hall` | fixed selector | Bottom button labeled `Reinforce`. |
| `PNC_MARKET_HEADER` | `market` | fixed selector | Screen title `Market`. |
| `PNC_MARKET_GLORY_LEVEL_BUTTON` | `market` | fixed selector | Button labeled `Glory Level`. |
| `PNC_MARKET_UPGRADE_BUTTON` | `market` | fixed selector | Button labeled `Upgrade`. |
| `PNC_MARKET_RESOURCE_TRANSPORT_BUTTON` | `market` | fixed selector | Bottom button labeled `Resource Transport`. |
| `PNC_ALLIANCE_MEMBER_HEADER` | `alliance_member_reinforce`, `alliance_member_transport` | fixed selector | Screen title `Alliance Member`. |
| `PNC_ALLIANCE_MEMBER_ROW` | `alliance_member_reinforce`, `alliance_member_transport` | structured entry selector | Repeated alliance-member rows with portrait, rank, and power stats. |
| `PNC_ALLIANCE_MEMBER_REINFORCE_BUTTON` | `alliance_member_reinforce` | structured child selector | Row-local `Reinforce` button. |
| `PNC_ALLIANCE_MEMBER_TRANSPORT_BUTTON` | `alliance_member_transport` | structured child selector | Row-local `Transport` button. |

Selectors intentionally not planned yet from the current screenshots:

- a fixed selector for the reserved Goddess Statue slot, because it should likely be modeled first as a home-city spatial object with reserved-slot metadata rather than a normal screen selector,
- a fixed selector for the Sacred Tree ready-gift indicator as a click target, because the gift should be treated as a readiness marker while actual building entry should still rely on stable spatial or label-based targeting rather than seasonal building art,
- fixed selectors for the home-city barracks/trap state markers as click targets, because the ready/idle/training markers are better modeled first as spatial state markers than as normal screen selectors,
- a fixed selector for the territory region itself, because the unlocked land and its small build spots should likely be modeled as spatial territory state rather than one normal UI element,

## 11. Open questions still pending screenshots

- March-specific open questions exposed by Alliance Hall reinforce and Market transport now live in [PNC_MARCH_MANAGEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_MARCH_MANAGEMENT_SUBPLAN.md).

## 12. Immediate next additions when more screenshots arrive

March-related screenshot follow-up exposed by Alliance Hall reinforce and Market transport now lives canonically in [PNC_MARCH_MANAGEMENT_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_MARCH_MANAGEMENT_SUBPLAN.md).
