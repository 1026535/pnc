# NPC 2 Hero Arena Seven-Entry Audit

## Objective

Across seven consecutive local-calendar daily Hero Arena entries on `mega_old_acc / [NGF] NPC 2`, record whether:

1. the Elemental Fluctuation Intro appears; and
2. the expected unset-Formation gate appears, while preserving the known Monday 00:00 UTC weekly-reset rule as background rather than a test result.

The audit stops before all battle attempts. It never starts a paid attempt, opens the paid-attempt path, changes a hero selection, or presses `Save Form.` without separate explicit authorization.

## Formation-state interpretation

The game-week Formation reset is known: it occurs at Monday 00:00 UTC. Separately, the game asks for Formation on every visit while no Formation has been saved. This audit intentionally never saves Formation, so a Formation gate on each entry is expected and is not evidence of a weekly reset. The seven-entry sample therefore measures daily Intro variability and proves that the automation safely handles an unset Formation state across repeated entries; it does not rediscover the known weekly reset rule.

## Qualifying streak

The current qualifying streak begins 2026-09-01 America/Toronto. The 2026-08-28 planning entry remains useful historical evidence but cannot count toward a consecutive-day streak because 2026-08-29 through 2026-08-31 were not observed on NPC 2.

| Entry | Local date | Elemental Intro | Hero Formation gate | Battle/paid attempt | Formation changed/saved | Result |
|---:|---|---|---|---|---|---|
| 1 | 2026-09-01 | Appeared | Appeared | No | No | Qualifies |
| 2 | 2026-09-02 | Pending | Expected while unset; pending live confirmation | Pending | Pending | Due next |
| 3 | 2026-09-03 | Pending | Expected while unset; pending live confirmation | Pending | Pending | Pending |
| 4 | 2026-09-04 | Pending | Expected while unset; pending live confirmation | Pending | Pending | Pending |
| 5 | 2026-09-05 | Pending | Expected while unset; pending live confirmation | Pending | Pending | Pending |
| 6 | 2026-09-06 | Pending | Expected while unset; pending live confirmation | Pending | Pending | Pending |
| 7 | 2026-09-07 | Pending | Expected while unset; pending live confirmation | Pending | Pending | Pending |

Current progress: **1/7 consecutive entries**. Six daily entries remain.

## Entry 1 evidence — 2026-09-01

- BlueStacks display name: `mega_old_acc`; the instance was already running and ADB resolved through the configured runtime.
- Fresh Manage Char evidence showed `K157 / NPC 2 / Castle Level 22` as the selected target row: `artifacts/2026-09-01/mega_old_acc/20260901T133805Z_arena_audit_20260901_baseline.png`.
- The current configured roster is stale. The canonical selector loaded NPC 2 successfully, but post-selection verification exceeded its replan budget because the stale roster could not recognize NPC 2. The observed NPC 2 Home screen is preserved at `artifacts/2026-09-01/mega_old_acc/20260901T133925Z_popup_recovery_post_action_1.png`.
- Arena opened through the canonical `open_building` task. The typed Versus Center baseline is `artifacts/2026-09-01/mega_old_acc/20260901T134135Z_arena_audit_20260901_versus_before.png`.
- The fresh Hero Showdown entry displayed Elemental Fluctuation Intro and the concurrent message `Please set defense formation first`: `artifacts/2026-09-01/mega_old_acc/20260901T134219Z_post_action_1.png`.
- Confirming only the informational intro exposed the Hero Formation screen, proving the gate recurred: `artifacts/2026-09-01/mega_old_acc/20260901T134301Z_post_action_1.png`.
- No hero card and no `Save Form.` control was touched. The gold top-left back control returned directly to typed Versus Center: `artifacts/2026-09-01/mega_old_acc/20260901T134341Z_post_action_1.png`.
- No ranking Challenge, opponent, free attempt, paid attempt, refresh, or purchase control was entered.

Disposition: `live_observed`; qualifies as entry 1.

Structured summary: `artifacts/2026-09-01/mega_old_acc/20260901T134341Z_hero_arena_audit_entry_2026-09-01.json`. This is explicitly marked as a manual backfill from the reviewed live artifacts, allowing the exact-target duplicate-date guard to protect the already-completed September 1 entry.

## Historical baseline — not part of the streak

On 2026-08-28, NPC 2 displayed both the Elemental Fluctuation Intro and Hero Formation gate. Formation was saved during that separately authorized planning session. Relevant evidence:

- `artifacts/2026-08-28/mega_old_acc/20260828T232119Z_daily_plan_npc2_hero_showdown_post_action_1.png`
- `artifacts/2026-08-28/mega_old_acc/20260828T232242Z_daily_plan_npc2_arena_intro_close_post_action_1.png`
- `artifacts/2026-08-28/mega_old_acc/20260828T233410Z_daily_plan_npc2_arena_after_manual_formation_save.png`

The Formation gate appeared on 2026-09-01 while no formation was saved. It is therefore consistent with the known “ask until set” behavior, not evidence about the weekly reset. Entries 2–7 will measure whether the Elemental Intro appears on every daily entry and confirm that the repeated unset-Formation path remains safe.

## Guarded audit helper

Entries 2–7 use `py tools/run_hero_arena_audit_entry.py`. The helper:

- prepares exact `mega_old_acc / K157 / NPC 2 / level 22` identity through the canonical runtime;
- opens Arena through the canonical `open_building` task;
- requires typed Versus Center and normalized-geometry Hero Showdown/Confirm/Back selectors;
- records Intro, Formation, or Ranking and fails closed on any other screen;
- contains no action for hero selection, `Save Form.`, `Challenge`, refresh, purchases, or attempts;
- rejects a second summary on the same America/Toronto calendar date; and
- persists a JSON summary plus screenshot artifact paths before reporting success.

The duplicate check loads candidate JSON and matches local date, account, kingdom, castle name, and level, so another castle's same-date audit does not suppress NPC 2. Malformed same-date summaries fail closed before account preparation. Because Windows does not normally provide the IANA timezone database required by `ZoneInfo("America/Toronto")`, `tzdata` is an explicit project dependency.

Implementation regression coverage is in `tests/test_hero_arena_audit.py`, with classifier, selector, OCR-enrichment, and castle-switch loading coverage in the shared vision tests. On 2026-09-01, 192 focused offline tests passed and the full suite passed 842 tests with 17 expected skips. A read-only live observation also proved typed Versus Center and a geometry-backed Hero Showdown action point at `(450, 336)`: `artifacts/2026-09-01/mega_old_acc/20260901T140549Z_arena_audit_read_only_selector_check.png`.

The current pipeline was also replayed against the actual saved NPC 2 screens rather than only synthetic OCR fixtures:

- `20260901T134219Z_post_action_1.png` classified as Elemental Intro with geometry-backed Confirm at `(450, 1067)`;
- `20260901T134301Z_post_action_1.png` classified as Hero Formation with geometry-backed Save and Back controls; and
- `20260828T233410Z_daily_plan_npc2_arena_after_manual_formation_save.png` classified as Hero Showdown Ranking with geometry-backed Back. Challenge remained OCR semantic evidence with no audit action.

This replay was read-only and did not create another September 1 Arena entry.

The production command was then invoked on September 1 as a negative safety test. It found the structured entry-1 summary and aborted before ADB resolution or emulator interaction. Six focused guard tests and the full 844-test offline suite passed; 17 live/local-fixture tests skipped as expected.

## Per-entry procedure

1. Confirm the local date matches the next due row and run the focused offline selector/classifier tests after relevant code changes.
2. Run `py tools/run_hero_arena_audit_entry.py` once. Its exact-target preparation, typed navigation, geometry provenance checks, and duplicate-date guard are mandatory.
3. Inspect the JSON summary and referenced screenshots. Require `final_screen: pnc_versus_center` and all three safety fields to remain false.
4. Record Intro and Formation results in exactly one date row and link the generated summary and screenshots. Mark Formation as an expected unset-state gate when it appears; do not interpret it as reset evidence.
5. If the helper stops on an unknown or unreviewed screen, do not retry entry navigation that day. Preserve the evidence and request user classification.

Any genuinely different or ambiguous screen stops the interactive entry for user classification. A second entry on the same local date does not count.

## Final report

Pending entries 2–7. Completion requires seven qualifying rows with no date gap and evidence for the Intro plus the expected unset-Formation handling on every row. It does not claim to validate the weekly reset timing.
