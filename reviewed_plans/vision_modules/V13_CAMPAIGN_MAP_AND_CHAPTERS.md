# V13 — Campaign map and chapter navigation

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V01; V02 for automatic Home entry. Align with [feature04](../PNC_CORE_REMAINING_04_CAMPAIGN_PLAN.md). Deliverable: current visible chapter/stage-map facts and verified map/chapter/return routes.

## Current state and owners

The [source fix](CONTEXT_AND_EVIDENCE.md#navigation-findings-retained-in-these-plans)
recognizes Chapter6 and its bottom-right Home portal on `4d317db`; it is absent
from main at `762cf84`. Reconcile the current base and reuse the reviewed
Campaign-specific changes and fixtures here if missing. In `pnc_observation_enricher.py`, `_build_campaign_additions` still publishes only the reviewed Chapter10/Grandia Ruins and stage3 cases. `campaign_ocr_regions.py` contains those bounded regions. `navigation_core.py` and `tasks/campaign_task.py` own navigation and consumption.

Use tour15, the Chapter6 pulse validation fixture, and the saved Chapter10/path/stage evidence in the [Campaign note](../../docs/game-reference/workflows/campaign-navigation.md). Old source-build conclusions do not prove today's visible control semantics.

## Implementation

1. Establish or preserve the reviewed title-only Chapter6 anchor and bottom-right
   Home portal on this candidate. Reuse `campaign_map_chapter_6.png` and
   `campaign_map_chapter_6_pulse.png` with source-manifest provenance. Exclude the
   animated ring; the source's first loading frame does not justify UNKNOWN retry. Expand content within observed map/chapter layouts, without hardcoding the only readable chapter to10.
2. Discover visible chapter/path markers using stable artwork and measured geometry; obtain number/name from bounded OCR. Publish observed lock/selection/completion only when pixels prove them.
3. Bind each target to its visible chapter/stage identity and current viewport. A fixed known chapter order can guide search but cannot create unseen actionable nodes.
4. Extend the existing Campaign content producer and region planner for the evidenced layouts. Use one shared representation consumed by the current campaign task; remove touched one-off duplicate parsing.
5. Add measured map → chapter path and explicit return edges. Verify destination chapter identity and refresh nodes after camera/viewport movement. Preserve transition context separately from newly observed facts.

## Acceptance and proof

Extend `test_campaign_visual_profiles.py` and Campaign task/navigation tests with Chapter6 and10 source/validation frames. Both publishers must emit the correct current identities and geometry. Preserve the pulsing-ring regression and absence of unsupported mode/eligibility facts.

Start `py tools/run_tests.py group unit.app.pnc.vision` and `group unit.app.pnc.navigation`, then affected checks. One core-runtime route: Home → Campaign map → one proved unlocked chapter path → map → Home via the bottom-right portal. Save source/destination frames, typed targets and trace. Stop if no independently measured chapter entry is available. Stage Challenge, formation and battles are outside this packet; V14 owns the next boundary.
