# Remaining feature plans after V01–V43

Revised 2026-09-15 from the task **Retrieve remaining feature plans**. This is
the scope amendment for packages 03–06; implementation status is unchanged.
Use it with the [43-packet index](PNC_VISION_MODULAR_PLAN.md) and
[roadmap](PNC_VISION_ROADMAP.md). Planned V ownership is not proof that an output
is implemented or qualified.

## Remaining assignments

| Package | Consume from V01–V43; do not reimplement here | Work retained here |
|---|---|---|
| [03 — Gathering](../gameplay/PNC_CORE_REMAINING_03_GATHERING_PLAN.md) | V19 World object publication, current bounds/identity, reacquisition after movement, supported read-only object-detail entry/return; existing coordinate reading/movement | Resource policy, gathering-specific detail/eligibility facts, slots and active marches, army/formation, Gather/Dispatch, correlated receipts/reports, canonical action/journal, direct/Daily callers, missing World Search → coordinate-dialog edge |
| [04 — Campaign](../gameplay/PNC_CORE_REMAINING_04_CAMPAIGN_PLAN.md) | V02 Home acquisition; V13 map/chapter facts and selection; V14 stage/formation facts, stage-to-formation/return operations and existing Campaign consumer endpoint correction | Ordered mode/stage policy, typed workflow composition/result, public/API/authored bindings, lifecycle/cleanup parity, migrated legacy dispatch removal and production caller acceptance |
| [05 — Mail/Login](../mail/PNC_CORE_REMAINING_05_MAIL_LOGIN_PLAN.md) | V01 shared visual/observation extension contract; any V-owned surface traversed by a profile route | Mailbox/profile/Compose/send-receipt recognition and routes, exact recipient/payload and one-send behavior; specified Login/provider screens, account evidence, lifecycle/preparation callers |
| [06 — Castle switching](../account-runtime/PNC_CORE_REMAINING_06_CASTLE_NAVIGATION_PLAN.md) | V01 shared visual/observation extension contract; existing Home identity | More/Settings/Manage Characters, roster recognition, exact selected identity, bounded scan and switch/return, typed caller/alignment behavior |

**V41 is the Castle building/Territory menu, not account or castle selection.**
V02–V03 own Home camera localization, atlas targets, panning, seasonal appearances
and event slots. Those are not additions to package 06. Mail/Login and
More/Settings/roster recognition remain uncovered by the V packets and retain
their feature-local work in packages 05 and 06.

## Handoff rules

1. Reuse V01's existing extension contract: one feature parser and canonical typed
   additions serve both observation paths. Packages 03–06 do not create another
   OpenCV/OCR engine, observer, route graph or generic recovery system.
2. For a transferred surface, record the providing V packet, actual revision,
   typed fields/operations and qualification evidence. Missing coverage remains
   an explicit dependency on that owner. Do not implement a parallel parser or
   fabricate observations to close it.
3. V19 promises one qualified object class, not every resource or every safety
   fact needed for dispatch. Package 03 records which required classes/facts are
   delivered. Gathering-only detail, slot, formation and receipt fields stay in
   03, extending the same canonical producer. Missing World detector classes
   belong to V19/model qualification; do not relabel Stone or invent a target
   finder. Coordinate Search/dialog correction remains in 03 because V19 reuses
   existing coordinate navigation rather than delivering that missing edge.
4. V13–V14 own Campaign facts, measured navigation and the `campaign_task.py`
   endpoint adjustment. Package 04 owns migration to typed workflow/caller
   composition. Reuse delivered preparation results; do not create a competing
   observation schema or repeat an endpoint fix. Preserve source-stage context
   separately from the actual `PNC_HERO_FORMATION` frame. The 2026-09-21
   [match-3 component amendment](../gameplay/PNC_MATCH3_COMPONENT_PLAN.md)
   adds mode forwarding to V13 and one shared-API handoff adapter/minimal caller
   binding to V14. Package 04 consumes that adapter during migration. M0 plus
   offline caller tests completes this added scope; solver, Daily-exit and Auto
   implementations, battle authority and live combat stay outside these packages.
   Preserve existing preparation-only calls. V30 owns the equivalent Arena API
   adapter; neither V feature calls the pure solver directly.
5. Continue independent policy, caller, action and receipt work without waiting
   for all 43 packets. Typed consumer fixtures prove decisions, not perception
   qualification. End-to-end acceptance requires the specific outputs consumed.
   Reuse valid producer/route evidence, then run only the additional production
   caller proof needed by the remaining feature contract.

## Starting point and historical instructions

Inspect the actual current implementation and retain completed work. Preserve a
resumed task's branch, commits and task-owned changes; record its code base and
this plan revision separately. Use a suitable isolated checkout under the
[source-control workflow](../../../.agents/skills/manage-source-control/SKILL.md).
Do not reset to `6bc2758`/`a4ac5d2` merely to reuse a recovered prompt.

The updated kickoffs in the four plans replace overlapping ownership in sections
03–06 of the recovered ignored report
`.local-data/reports/feature_agent_launch_prompts_20260914.md`. That report and
the chat are historical retrieval evidence. Their “own all producers” and “no
peer dependency” clauses do not override this split. The six-package umbrella's
full-vertical clauses are likewise limited by this amendment; packages 01–02
are not otherwise reassigned by this change.

This revision is planning only. Future implementation uses the current
assignment's confirmed account/instance, action and budget plus configured live
roles. Historical target tables and screenshots are not a fresh allocation.
Preserve applicable explicit authorization from the execution session without
asking again; do not import unlimited budgets or account-switch/mail permissions
from old documents. No live action, model migration or plan retirement is needed
for these scope edits.
