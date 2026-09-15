# Building-menu coverage

[Plan index](../PNC_VISION_MODULAR_PLAN.md) · [Execution roadmap](../PNC_VISION_ROADMAP.md). Updated 2026-09-15.

Every current `HomeCityObjectId` has a planning owner below; Lost City Headquarters is an additional user-confirmed slot awaiting catalog qualification. **Assigned does not mean implemented or visually qualified.** V02 supplies current Home acquisition; each feature owns the opened menu, content, popups and actual return. V16 owns shared upgrade/requirement/queue surfaces; V17 owns construction menus.

The catalog and [building-endpoint note](../../docs/game-reference/workflows/building-endpoints.md) are the repository baseline. A declared screen or old client route is a lead, not proof of the current interface. For capture gaps, use the packet's bounded route and report unsupported states.

| Home object / exact catalog ID | Menu owner | Boundary |
|---|---|---|
| Castle — `castle` | [V41](V41_CASTLE_TERRITORY.md) | Castle and Territory Overview; upgrade V16 |
| Wall — `wall` | [V34](V34_WALL_DEFENSE.md) | Defense Info and read-only Wall details |
| Institute — `institute` | [V04](V04_INSTITUTE_DEVELOPMENT.md), [V05](V05_RESEARCH_ECONOMY.md), [V06](V06_RESEARCH_MILITARY.md), [V07](V07_RESEARCH_FORTIFICATION.md) | Research; building upgrades V16 |
| Warehouse — `warehouse` | [V42](V42_UTILITY_BUILDING_DETAILS.md) | Capacity/protection and ordinary details |
| Trap Workshop — `trap_workshop` | [V36](V36_TRAP_WORKSHOP.md) | Trap information, Effect Table and queue facts |
| Watchtower — `watchtower` | [V35](V35_WATCHTOWER.md) | Warning/report information |
| Farm — `farm` | [V42](V42_UTILITY_BUILDING_DETAILS.md) | Shared production/detail family |
| Lumber Camp — `lumber_camp` | V42 | Shared production/detail family |
| Moon Well — `moon_well` | V42 | Shared production/detail family |
| Recruiting Center — `recruiting_center` | V42 | Current support/details; split if a distinct endpoint is observed |
| Infirmary — `infirmary` | [V21](V21_INFIRMARY_HEALING.md) | Wounded/healing menu and queue presentation |
| Iron Mine — `iron_mine` | V42 | Shared production/detail family |
| Gold Mine — `gold_mine` | V42 | Shared production/detail family |
| Blacksmith — `blacksmith` | [V22](V22_BLACKSMITH_AND_GEAR.md) | Hub and Gear; remaining branches below |
| Alliance Hall — `alliance_hall` | [V37](V37_ALLIANCE_HALL_REINFORCEMENT.md) | Reinforcement/member information; research V08 |
| Market — `market` | [V27](V27_MARKET_TRANSPORT.md) | Recipient list and transport form |
| Infantry Barracks — `infantry_barracks` | [V20](V20_BARRACKS_TRAINING.md) | Exact troop family and shared training information |
| Cavalry Barracks — `cavalry_barracks` | V20 | Exact troop family and shared training information |
| Ranged Barracks — `ranged_barracks` | V20 | Exact troop family and shared training information |
| Siege Factory — `siege_factory` | V20 | Exact troop family and shared training information |
| Hall of War — `hall_of_war` | [V38](V38_HALL_OF_WAR.md) | Rally and Glory Level information |
| Hero Hall — `hero_hall` | [V18](V18_HERO_HALL_AND_RESULTS.md) | Menu and saved recruitment result surfaces |
| Sanctum — `sanctum` | [V28](V28_SANCTUM_RELICS.md) | Relics tabs, sets and information |
| Tower of Trial — `tower_of_trial` | [V15](V15_TRIAL_CHALLENGE.md) | Trial cards and evidenced read-only detail family |
| Sauroi Lair — `sauroi_lair` | [V29](V29_SAUROI_AND_SAUREGG.md) | Lair/Sauregg; Home appearance variants V03 |
| Campaign — `campaign` | [V13](V13_CAMPAIGN_MAP_AND_CHAPTERS.md), [V14](V14_CAMPAIGN_STAGE_AND_FORMATION.md) | Map/chapter/stage/formation inspection and return |
| Arena — `arena` | [V30](V30_ARENA_VERSUS_CENTER.md) | Versus Center/Arena information and previews |
| Goddess Statue — `goddess_statue` | [V43](V43_GODDESS_STATUE.md) | Current attributes and information details |
| Sacred Tree — `sacred_tree` | [V31](V31_SACRED_TREE.md) | Own tree and Blessing Record |
| Pit — `pit` | [V39](V39_PIT_RARE_EARTH.md) | Rare Earth information; not an upgradeable building |
| Bank — `bank` | [V40](V40_BANK_TREASURE_CAVE.md) | Current endpoint must be qualified |
| Dragondom — `dragondom_conquest` | [V32](V32_DRAGONDOM_EVENT.md) | Current occupied event hub; V03 occupancy |
| Lost City Headquarters — ID pending | [V33](V33_LOST_CITY_HEADQUARTERS.md) | User-confirmed slot; canonical ID/menu qualification with V03 |
| `reserved_institute_slot`, `reserved_warehouse_slot`, `reserved_trap_workshop_slot`, `reserved_goddess_statue_slot` | [V17](V17_CONSTRUCTION_AND_SLOTS.md) | Fixed-slot construction menus |
| `large_support_build_slot`, `small_territory_build_slot` | V17 | Large/small construction menus |
| `locked_territory_region_below_wall`, `territory_unlock_lock_icon` | V41 + V17 | Read-only requirements and slot visibility; no unlock action |

## Blacksmith branches

| Branch | Owner |
|---|---|
| Gear and the hub | [V22](V22_BLACKSMITH_AND_GEAR.md) |
| Gem and Saurgem | [V23](V23_GEM_AND_SAURGEM.md) |
| Warsigil | [V24](V24_WARSIGIL.md) |
| Hero Curio | [V25](V25_HERO_CURIO.md) |
| Ascend | [V26](V26_ASCEND.md) |

## How to use this map

An agent implements one packet's observed feature family, including its ordinary detail/close/popups. It does not need to implement every possible future event or locked progression variant to finish an evidenced subset, but must state those limits. A newly discovered, materially distinct subtree becomes a named follow-on packet before expansion; it must not disappear behind an “all buildings supported” claim.

Fresh capture evidence can supersede old route names. One shared menu family may cover several building IDs only when identity and geometry are actually proved. Existing working profiles remain intact, and generic upgrades/construction are reused rather than reimplemented per building.
