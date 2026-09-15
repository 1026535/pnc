# V03 — Home appearances, seasonal references and event slots

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V02. Deliverable: supported Home appearance variants and honest fixed-slot availability.

## Scope and owner

Extend V02's canonical localization/catalog producer, `building_catalog.py` and its tests. User-confirmed fixed positions apply to seasonal skins, Dragondom/Lost City Headquarters event slots and Sauroi Lair progression. This tour did not capture those variants. Dragondom and Sauroi IDs exist; the inspected catalog has no Lost City Headquarters ID.

## Implementation

1. Inventory existing saved captures for one seasonal appearance, occupied/empty event slots, and Sauroi progression. Attach each reference to the existing atlas coordinates. If Lost City Headquarters needs an ID, verify its name and location from evidence and add it once.
2. Separate permanent slot identity from current appearance and availability. Publish present, empty or unknown using a typed state owned with the Home observation; only positive empty-slot evidence means empty.
3. Check which V02 landmarks survive each supported skin. Add the smallest qualified seasonal reference set where they change. A season must be selected by current evidence, not the calendar or a manual runtime toggle.
4. Keep Sauroi's identity fixed and expose only visually proved progression/availability facts. A different skin does not imply a moved building.
5. Gate event opening on current occupied, visible and unoccluded evidence. Preserve unknown results for unsupported skins or obscured slots; no speculative event-menu routes.

## Acceptance and proof

Extend V02's Home fixture tests. For each **actually available** variant, assert stable atlas identity, current camera proof, correct occupancy and no event click on empty/unknown. Cross-check visually different occupied slots against empty samples; reference crops alone are not validation frames.

This packet may deliver a subset with named unsupported variants; do not claim seasonal support from ordinary-day captures. Missing Christmas/tutorial captures are a qualification blocker for that variant, not a reason to change dates, accounts or progression.

Start `py tools/run_tests.py group unit.app.pnc.vision` and affected checks. If a newly available event/appearance changes the deployed open boundary, one testing-Home observation and bounded pan to its slot is the live proof. Open only a known non-spending menu with a reviewed return; otherwise stop at occupancy observation. Save camera/slot facts and source frames. No waiting for an event or creating tutorial progress is required.
