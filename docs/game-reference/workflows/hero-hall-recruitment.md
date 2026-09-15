# Hero Hall free-single result flow

## Evidence and limits

Client source below is from PNC **5.0.203 / version code 233**; see
[provenance](../PROVENANCE.md). The September 13 live session had downloaded an
update; Settings later displayed footer text `5.2.77 5.0.204.235`. No new APK
extraction was performed. Source behavior and that live observation are
separate evidence, not a server contract.

## Result screens and controls

**Client source verified:** paths are relative to the recovered gameplay Lua root.

- `uis/pub/pubdrawrewardview.lua`, `PubDrawRewardView:OpenWins` and
  `OnStartEffectEnd`, run the summon animation before exposing rewards. For a
  free draw whose configured cost is empty, the result view selects another
  draw configuration and displays its cost for the next draw.
- `uis/pub/pubgetnewheroview.lua`, `PubGetNewHeroView:StartWindow` and
  `OnDrawHandler`, bind the hero presentation's `BtnOk` and return to the
  preceding window. This handler does not issue another draw request.
- `uis/pub/pubdrawrewardview.lua`, `StartWindow`, `OnCancelHandler` and
  `OnDrawHandler`, bind distinct Close and Draw controls. Close returns to the
  preceding window; Draw can call `PubSend.RequireDraw` after inventory checks.
- `uis/pub/pubrecruitpanel.lua`, `PubRecruitPanel:SetFreeLabel` and
  `OnTimeHandler`, switch the Recruit panel's label between remaining free
  attempts and a countdown based on `nextFreeTime`. A cooldown frame need not
  display the remaining attempts count simultaneously.

**Live observed, September 13, 21:52 UTC:** on the exactly verified K157 / NPC 2
castle, one distinct Free Recruit 1x tap led through a summon animation, an
Albertus presentation with Confirm, then an Albertus fragments result with a
blue Close and a separate paid Recruit 1x. The user performed the Confirm step.
The result retained eight recruit items, as shown before the free action; the
paid button was not used. Canonical recognition published these animation and
result frames as UNKNOWN, so the automatic workflow stopped after its one tap.

Saved evidence is under the integration candidate's ignored
`.local-data/artifacts/core_resume/manual_update_20260913T214455Z/2026-09-13/mega_old_acc_manual_update/`:
`..._0078_hero_hall_dispatch.png`, `..._0079_hero_hall_recruit_post.png`,
`..._0080_hero_result_diagnostic.png`, and `..._0081_hero_after_manual_confirm.png`.
The durable state and later disposition belong to the
[port validation ledger](../../../reviewed_plans/PNC_CORE_PORTING_VALIDATION.md).

After manual Confirm and Close, fresh Hero Hall evidence showed four Daily
attempts and eight recruit items. Following another exact NPC 2 preflight, the
canonical reconciliation primitive committed the existing single and the core
returned Home. No second recruit was sent. This is an operator-assisted receipt,
not acceptance of automatic summon/result navigation.

## Automation implications

Do not expect the first post-tap frame to be the Recruit panel, treat a result
screen's Recruit 1x as another free action, or infer completion from a missing
Free control. Recognition must qualify the result states and their separate
Confirm/Close controls before the core can own their bounded navigation. Keep
UNKNOWN fail-closed. Reconcile the existing durable intent using freshly guarded
attempt-decrement or cooldown evidence; do not replay the recruit. One observed
single does not prove the full five-single Daily requirement.
