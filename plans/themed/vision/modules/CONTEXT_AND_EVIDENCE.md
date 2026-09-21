# Vision planning context and evidence

[Plan index](../PNC_VISION_MODULAR_PLAN.md). Extracted 2026-09-15. These are evidence summaries, not inherited task instructions.

## Precise OCR incident

The Development Research task failed to acquire Institute from a Home image whose label was read as **“Insitute”**. The recorded word bounds were x411, y843, width78, height19. Legacy RapidOCR confidence was 0.8464. A later RapidOCR/PP-OCR experiment still returned “Insitute”, with 0.9990 confidence at 2x scaling. Higher OCR confidence did not establish correct spelling.

Source: [incident report](C:/Users/lebel/pnc/.local-data/reports/home_city_navigation_research_20260915/report.md). The original image and experiment parameters are indexed there. This is an observed acquisition failure, not evidence that all research parsing fails.

Decision: Home identity comes from a known atlas location and current visual evidence. Names remain supporting content. Do not solve the architecture with one alias per typo, or fuzzily repair costs, quantities or castle identity.

## User-confirmed Home constraints

Confirmed in this task on 2026-09-15; variant builds not supplied:

- Building locations and dimensions mostly stay fixed; the map pans.
- Christmas skins change appearances while preserving building locations.
- Dragondom and Lost City Headquarters occupy fixed event slots that may be empty.
- Sauroi Lair stays in one location and changes appearance with tutorial progression.

Implication: localize the camera against stable reviewed landmarks, project canonical atlas positions, then verify current visibility, occupancy and click geometry. Unknown appearance is not evidence of an empty slot. Seasonal reference qualification is still needed.

## Tour and later correction

[Six-surface report](C:/Users/lebel/pnc/.local-data/reports/vision_live_tour_20260915/report.md), [gallery](C:/Users/lebel/pnc/.local-data/reports/vision_live_tour_20260915/gallery.html) and [artifact index](C:/Users/lebel/pnc/.local-data/reports/vision_live_tour_20260915/artifact_index.json).

The tour used the configured testing instance's active level-10 castle in K287, game 5.2.80, 900x1600. No resources, account switches or castle switches were used. These are historical capture facts, not a hardcoded future target.

| Evidence group / result prefix | What it establishes | Remaining gap |
|---|---|---|
| 02_home, 07_pan, 08_institute | Home pans; Institute was omitted before pan; visually chosen building body opened Institute | Production camera localization and acquisition |
| 09_development, 10_research_detail, 12_research_scroll | Upper nodes, detail costs/buttons and lower scrolled nodes are visible | Lower nodes omitted; Miraculous Survival I incorrectly clipped; full typed details |
| 15_campaign_building | Chapter 6 map; return portal at bottom right | Wider map/chapter content and stage/formation route |
| 19_bag, 22_bag_speedup, 23_bag_treasure, 24_chest_preview | Resource rows, non-resource tab layouts, chest preview | Non-resource rows/details and shared card state |
| 28_tower_pan, 29_tower_open | Tower body opens Trial Challenge with six trial cards | Card semantics and deeper read-only route |
| 01_world | Standard World screen identified; this observation published no objects | Diagnose publication/model scope; no global claim about all World modes |
| Alliance research | Not captured by this tour | Category, node, detail and return evidence |

### Navigation findings retained in these plans

The original failures were corrected and validated on
[source commit `4d317db`](https://github.com/1026535/pnc/commit/4d317dbad066afca989dfa3b09d76bd1f7b82a02).
The [fix report](C:/Users/lebel/pnc/.local-data/reports/vision_navigation_fix_20260915/report.md)
and its ignored traces retain the observations. These findings remain useful as
versioned evidence; they do not establish that a different checkout contains the fix.

The source revision's `tests/data/screen_recognition/manifest.json` records capture
group `2026-09-15/vision_live_tour_20260915`, decoded-image hashes and reference/
validation roles. Reuse those authored fixtures and profile changes where they
fit the current owner; do not rerun the tour merely to recreate evidence.

| Finding and exact source evidence | Plan obligation |
|---|---|
| Campaign Chapter 6 exits Home through the bottom-right portal. The selected-node ring pulses, so the stable title-only anchor excludes it. `campaign_map_chapter_6.png` and `campaign_map_chapter_6_pulse.png` cover the reference and settled-frame regression. The first loading frame was not qualified. | V13 owns the identity/portal and pulse regression before extending chapter content. It supplies neither stage selection proof nor generic loading/UNKNOWN recovery. |
| A Tower body tap opened Trial Challenge directly; its measured top-left control returned Home. `trial_challenge.png` covers the category-list appearance. | V15 owns the canonical Tower → `PNC_TRIAL_CHALLENGE` destination and return, then card semantics. V02 owns Home acquisition. This does not prove trial entry or battle behavior. |
| Arena Surprise Chest's magnifier opened contents without using the item. `bag_arena_chest_preview.png` covers the preview and gold-X close to Bag. Ordinary observation retained the preview. | V11 owns preview identity, measured close, task-owned inspection and content. Missing close/unknown interruptions retain the existing guards; no automatic dismissal or Use/Open action. |

**Baseline port after `ff38127` (2026-09-15):** the initial main plan landing
omitted the runtime correction. At the user's request, the bounded fix is now
included alongside these plans: all 22 runtime/test/fixture paths are ported
exactly from `4d317db`. Before the port, main's runtime/tests/tools matched that
fix's parent; after it, they match the live-tested source revision. Tower now
maps to `PNC_TRIAL_CHALLENGE`; the Chapter 6 and owned-preview profiles, measured
returns and four fixtures are present. The retired standalone findings note
remains removed. Preserve this baseline in V11/V13/V15; their content parsing and
broader feature acceptance remain planned. V01 still starts from the existing
Bag layout.

The source fix recorded **427 focused passes**: 249 navigation, 122 vision and
56 engine. The affected and vision-integration runs were stopped at the user's
request; neither is a passing broader gate. Recorded live returns were Trial →
Home, corrected Chapter 6 → Home, and preview → Bag → Home on the same active
testing castle, game 5.2.80 in English at 900 × 1600. The Campaign pulse failure
preceded its successful corrected retry. No trial, battle, item use, research,
account/castle switch or spending occurred. These results qualify those captured
surfaces and revision only. The exact port reuses that saved live evidence;
it adds no claim about all chapters/chests or Home variants.

**Port validation (2026-09-15):** the navigation group passed all 249 tests.
`py tools/run_tests.py affected --base origin/main --explain` selected all 306
portable modules against `ff38127` because of the shared screen contracts; the
full fallback passed with 2,182 passes and 7 skips (2,189 total). Skips were six
unavailable optional captures and one Windows symlink privilege case. This
completes the broader offline gate that was stopped in the original source run.
The runtime/test tree still exactly matches `4d317db`. No new live tour was run;
the saved route evidence above was reused. Plan links and `git diff --check`
also passed.

## OpenCV evidence and its limits

The tour's `template_probe.json` records an Institute body patch moving by (-468,-931) pixels, correlation 0.9796, about32ms for that local probe. The patch excludes the label. An older castle appearance matched only0.6497; it is not qualified.

The same session's `camera_probe.json` / `camera_probe_rectangular_mask.json` compare ORB landmark matching. After excluding HUD protrusions, 65/82 feature matches agreed on (-468,-931), median residual0.76px. A World negative had only1/30 agreement. A simpler rectangular mask had falsely retained28 stationary HUD matches.

Implications: actual camera motion must be observed; finger displacement is not a measured camera update. Mask advertisements and other HUD protrusions. Use translation at the supported scale first. These two Home frames do not establish seasonal, cross-castle or long-session reliability, and local timings are not a benchmark.

Official references supporting the available techniques:
[OpenCV template matching](https://docs.opencv.org/4.13.0/de/da9/tutorial_template_matching.html),
[ORB](https://docs.opencv.org/4.13.0/d1/d89/tutorial_py_orb.html),
[feature matching](https://docs.opencv.org/4.13.0/d1/de0/tutorial_py_feature_homography.html).
No homography or new detector is required merely because OpenCV offers one.

The earlier [GPT-6 Pro consultation](https://chatgpt.com/g/g-p-6aa2bcd61ce08191a499c5b6f2b67eb5-pnc-bot/c/6aa96a63-2784-83e9-a0b4-b8eb99bef19f) recommended a trained detector for Home/World, while allowing templates to win on measured evidence. It preceded the fixed-location clarification and was not reconsulted on it. This plan uses the later user facts for Home and leaves World model choice to its current qualified work.

## Retrieved task lessons and stale goals

### Continue non-YOLO recognition

Task ID `01a09c8c-4fb4-7fe1-a992-e50aac39b959`.

Useful lesson: Savannah parsing once depended on text outside production's bounded OCR crop. Tests that supplied OCR words directly passed despite a broken production input path. Qualification must exercise the real OCR planner and both observation publishers. Static offer artwork and measured owned close controls often remove unnecessary text dependencies.

Historical Savannah/VIP/Lucifer missing-profile conclusions are not current work items by default: the [archived checklist](../../../dropped/PNC_NON_YOLO_RECOGNITION_REMAINING_CHECKLIST.md) records later corrections, and current code determines what remains. Preserve current session/epoch popup gating, bounded guard OCR and visual close ownership. Do not copy the earlier branch's dirty-file state or its “wait for B” instructions.

### Review improve screen recognition

Task ID `01a08bea-8e6e-7062-9181-6a7716f5b506`.

Useful lesson: visual claims need screenshot evidence, feature implementation should stay coherent, and tiny delegated chores caused unnecessary coordination. Its crash handoff is local historical context:
`C:/Users/lebel/pnc/.local-data/worktrees/non-yolo-recognition-continuation/.local-data/reports/PNC_NON_YOLO_IMPLEMENTATION_HANDOFF_20260913_2020Z.md`.

Do not import its unfinished branch state, older source baseline, broad test-removal goal or spending permissions. Keep deterministic semantic tests when meaningful; distinguish them from visual qualification.

### Current repository precedence

Read the current [core workflow plan](../../core/PNC_CORE_WORKFLOW_PORTING_PLAN.md) and [modular vision plan](../PNC_VISION_MODULAR_PLAN.md) for ownership. The [archived recognition follow-up](../../../dropped/PNC_B_FOLLOWUP_RECOGNITION_HANDOFF.md) supplies gap provenance only; its queued B handoff is retired. The [retirement map](../../../reviewed/vision/modules/PLAN_RETIREMENT.md) traces each requirement to its current owner.

The existing [screen implementation report](../../../completed/vision/PNC_SCREEN_RECOGNITION_IMPLEMENTATION.md) proves OpenCV integration and historical design decisions. Older OCR fallback descriptions and profile counts are not the current contract.

## Evidence handling

Generated reports/screenshots remain under ignored `.local-data/`. Promote only the exact authored fixtures/crops and manifest entries needed for a changed feature into tracked test/package data. Do not modify machine-local fixture configuration as a shortcut. Record source date/build, whether a capture is a reference or independent validation, and supported variants.

Missing local evidence is a capture gap, not authority to switch castles, trigger events or spend resources. Verify newer feature commits before treating any historical gap as still open.
