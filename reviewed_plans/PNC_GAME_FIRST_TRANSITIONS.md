# Game-first navigation additions — September 10, 2026

Feature branch: `codex/pnc-replacement-core`.
Worktree: `C:/Users/lebel/pnc/artifacts/replacement_core/worktree`.

## Evidence method

The source of the additions was the running game. No historical screenshots, OCR logs, prior transition reports or saved tours were consulted to discover these routes. Fresh screenshots were acquired through the configured `testing` BlueStacks runtime. Controls were selected by visually inspecting each current screen, tapped through the existing device actuator, and the resulting game screen was inspected before proceeding. The active character was checked in Manage Character without selecting a row.

Only after that exploration were the observed routes compared with the replacement graph and encoded. Fresh captures were then cropped into recognition/control templates and regression fixtures. Those newly created files are evidence of this exploration, not historical evidence used to predict it.

Exploration command: `py C:/Users/lebel/pnc/artifacts/replacement_core/game_first_probe.py LABEL [--point X Y]`. Points refer to the just-inspected 540×960 preview and are projected through the existing spatial action abstraction. This manual exploration helper is not a coordinate fallback in the production core. Each step is recorded in `C:/Users/lebel/pnc/artifacts/replacement_core/game_first/exploration.jsonl`.

## Observed connections and content

| Entry | Destination / observed content | Observed return |
|---|---|---|
| Settings → Manage Char. | Character roster, selected-character checkmark, New Character entry | Settings |
| Settings → Rank | Rank hub, Personal Rank categories and View buttons; Alliance Rank section | Settings |
| City → More → Rank | Same Rank hub | City |
| World → More → Rank | Same Rank hub | World |
| Settings → Settings | Sound, frame rate, graphics and additional preferences | Settings hub |
| Settings → Notifications | Upgrade/training, personal military, alliance military and Dragonia notification preferences | Settings hub |
| World → More → Settings | Settings hub | World |
| City → More → Settings | Settings hub | City |
| World overview → globe | Kingdom List, code search, kingdom groups and rows | World overview |

No character/kingdom was selected, preference changed, message sent, rank reward claimed or in-game resource spent. Rank detail View buttons, lower preference sections, kingdom selection/search and other menus were not explored in this pass.

Two important findings were not simple missing edges:

- The preferences screen has the same **Settings** title as its parent hub. It is recognized independently using Sound Settings content as well as the header; the title alone is insufficient.
- **Back depends on the entry context.** Rank can return to Settings, City or World. The Settings hub can return to City or World. The former core graph incorrectly assumed Settings always returned to City. The core now accepts only the observed parent alternatives and replans using the destination actually captured.

## Implementation

- Added 12 graph edges and corrected the existing Settings return edge; the graph now has 37 edges. It does not claim complete game coverage.
- Added four visual profiles: preferences, notifications, rank hub and kingdom list. The catalog now has 22 profiles. Manage Character already had recognition but lacked core entry/return routing and a measured Back control.
- Added four selector identifiers and populated measured controls for the Settings entries, More → Rank, World → More, overview globe and Manage Character Back.
- Promoted the overview globe selector from an unreviewed action declaration to a reviewed Kingdom List navigation contract.
- Added 16 fresh PNG assets. Preferences, Notifications and Manage Character expose only Back to this core; their mutating controls are not automation targets.
- Added regression coverage for identical titles, measured controls at both supported resolutions, context-dependent return/replanning and rejection of an unobserved return parent. Roster/ranking/kingdom-row content is masked in reusable fixtures because it is not needed for identity.
- Extended the existing `tools/validate_visual_navigation.py` with `--replacement-core --game-first-routes`; capture, action and completion retain their existing owners.

Fixture and template provenance: `tests/data/game_first_navigation/provenance.json`. Each asset records its fresh source capture and crop. These are same-session development examples, not independent evidence of unattended reliability.

## Verification

- **Passed:** `py -m unittest tests.test_navigation_core tests.test_visual_screen_recognizer tests.test_selectors` — 41 tests, `C:/Users/lebel/pnc/artifacts/replacement_core/game_first/focused.log`.
- **Passed:** `py -m unittest tests.test_validate_visual_navigation` — 2 tests.
- **Passed:** `py -m unittest discover -s tests` — 1,038 tests, 18 skips, `C:/Users/lebel/pnc/artifacts/replacement_core/game_first/full_suite.log`.
- **Passed:** final `py -m unittest tests.test_selectors tests.test_validate_visual_navigation` — 11 tests after final selector geometry, `C:/Users/lebel/pnc/artifacts/replacement_core/game_first/final_selector_tests.log`.
- **Passed:** `git -c core.safecrlf=false diff --check`.
- **Passed:** live replay through the replacement core:

```powershell
py tools/validate_visual_navigation.py --replacement-core --game-first-routes --config C:/Users/lebel/pnc/config/accounts.yaml --account testing --output-dir C:/Users/lebel/pnc/artifacts/replacement_core/game_first/live
```

The replay checked all 20 context-specific route cases, rather than accepting any known screen. Including setup, identity verification navigation and final return, it recorded **32 confirmed transitions** and returned to City. These are executed-and-observed transitions, not the count of newly added graph edges. The existing roster parser only verified active identity; navigation used the replacement core.

Live evidence: `C:/Users/lebel/pnc/artifacts/replacement_core/game_first/live/20260910T232644Z_core_4bc19d51/summary.json` and `trace.jsonl`. The trace-derived inventory is `C:/Users/lebel/pnc/artifacts/replacement_core/game_first/replay_evidence.json`.

- **Failed due to test-tool coverage:** the existing `tools/validate_navigation_selectors.py` validator, invoked by `py C:/Users/lebel/pnc/artifacts/replacement_core/game_first/validate_selector_boundary.py` with the globe target, cannot prepare `PNC_WORLD_MAP_OVERVIEW` as a source. It stopped before the globe action. The exact failure is retained in `C:/Users/lebel/pnc/artifacts/replacement_core/game_first/selector_boundary.yaml`. This is a remaining legacy-validator capability gap; the replacement-core overview → Kingdom List → overview proof above passed. The helper now accepts `--selector PNC_WORLD_OVERVIEW_WORLD_ICON` to reproduce this check.
- **Passed:** `py C:/Users/lebel/pnc/artifacts/replacement_core/game_first/validate_selector_boundary.py` with its Manage Character default — one passed case, zero failures/skips, and a replacement-core return to City. This invokes the same existing validator on its supported Settings source. Evidence: `C:/Users/lebel/pnc/artifacts/replacement_core/game_first/selector_boundary_manage.yaml`, `selector_boundary_manage.log`, and `boundary_return_trace.jsonl`.

The resolved BlueStacks display name was `testing`. ADB connectivity was established through the configured runtime, and active identity was verified without changing the character. The final captured state was `PNC_HOME_CITY`. Protected account/castle config was not edited. All new navigation behavior was exercised live; no new core route is waiting on the legacy validator's overview preparation support.

The manual probe initially omitted the required empty `visible_elements` argument; it stopped before sending a tap and was corrected. The asset-authoring helper initially found two suffix-matching filenames; it stopped before writing the catalog and was corrected to require an exact capture label. These were helper errors, not game transitions or successful proofs. The first Preferences Back capture still showed the source during settling; a later passive capture established the Settings destination without another tap.

Changes remain uncommitted alongside preserved pre-existing work in the isolated feature worktree.

This is a bounded addition to the opt-in replacement core. Default daily workflows were not migrated by this pass, and the game has not been exhaustively mapped.
