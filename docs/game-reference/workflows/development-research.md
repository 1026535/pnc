# Development Research

Inspected 2026-09-14 against the packaged PNC **5.0.203 / version code 233**
source described in [provenance](../PROVENANCE.md), then compared with authorized
live `mega_old_acc` / K157 / NPC 2 / level 22 captures from the later running
client. The packaged source is structural evidence, not proof that a later
downloaded client or the server uses identical data.

## Tree node rendering

**Client source verified:** `uis/college/collegeresearchsubicon.lua`,
`CollegeResearchSubIcon:SetData`, renders the current level and configured
`maxLevel` as `i/n`. `CollegeResearchSubIcon:InitLine` then calls
`CollegeData:IsMax(techId)` and replaces that text with `MAX` when complete.
`datas/collegedata.lua`, `CollegeData:IsMax`, compares the stored current level
with the node's configured maximum. This supports the following observation
contract:

- `MAX`, or a valid numeric `i/n` with `i == n`, is complete;
- a valid `i/n` with `0 <= i < n` is incomplete;
- missing, conflicting, or out-of-range text is unknown and cannot authorize a
  research-node tap.

**Client source verified:** `uis/college/collegeresearchsubitem.lua`,
`CollegeResearchSubItem:RefreshThree` and `RefreshFour`, place each tree row in
three- or four-column layouts using a fixed 148-unit horizontal interval.
`CollegeResearchSubIcon:InitLine` uses a 226-unit vertical interval for
prerequisite connectors. This explains the repeated node grid and supports
bounded viewport scrolling, but runtime action geometry remains measured from
the live blue node tiles rather than projected from source constants.

## Selection and eligibility

**Client source verified:** `CollegeResearchSubIcon.OnClick` opens the research
detail for the selected `techId` without first proving its prerequisites.
`CollegeResearchSubIcon:InitLine` exposes `ImgResearchLock` or `ImgSecondLock`
when the prerequisite predicate is false, depending on whether the node is
still level zero or already progressed.
Prerequisite checks occur in the detail/start path, including
`uis/college/collegeresearchuppan.lua`, `CollegeResearchUpPan:CheckCondition`.
Therefore an incomplete tree counter is a scan candidate, not proof that normal
Start is eligible. Automation must still require the reviewed normal Start
control on the resulting detail and must not promote an immediate/premium path.

**Client source verified:** `CollegeResearchUpPan.OnBtnResearch` separately
calls `CollegeData:GetIdelCoolStatusType()` before checking the displayed
resource costs. Status `2` opens `BUILD_AND_TEACH_QUEUE_WIN` and returns instead
of sending `RequireStudyTech`; the captured “No idle queue” detail is therefore
not a safe normal-Start source. When a resource is short the same handler calls
`ItemData:ResFaseUse(...)` and returns without sending
`CollegetechSend.RequireStudyTech`. A blue normal Research control therefore is
not sufficient by itself. The pre-mutation observation must positively prove an
idle queue, parse at least two complete `current/required` resource rows, and
prove every current amount is at least its requirement; missing or malformed
facts remain non-authoritative.

**Client source verified:** the insufficient-resource branch passes
`WinType.COLLEGE_CONDITION` to `ItemData:ResFaseUse` in
`uis/college/collegeresearchuppan.lua`. `datas/itemdata.lua`,
`ItemData:ResFaseUse`, builds the proposed pack list, while
`uis/bag/resfaseusewin.lua`, `ResFaseUseWin.OnUseHandler`, closes the “Auto Use”
popup and sends `ItemSend.UseBoxItems`. The response refreshes the college
condition; it does not call `RequireStudyTech`. Consequently the opt-in runtime
path must confirm the exact positive “Sufficient after use” popup, re-observe a
funded idle detail, and press normal Research a second time. The Bag confirmation
and second Research tap belong to the same durable `research-001` intent.

## Live comparison

**Live observed:** the 2026-09-14 non-spending inspection under
`.local-data/artifacts/development_research/development_grid_inspection_20260914T230808Z/`
showed the first Development viewport at `MAX`. After bounded upward scrolling,
the tree showed tier-II examples including Research Speed `4/10`, Storage
`1/10`, and Food Output `1/5`. Both production observation paths replayed the
same saved frames with strict cropped OCR and identical typed rows. The run sent
no Start and spent zero diamonds.

The 2026-09-15 production attempt under
`.local-data/artifacts/development_research/research_caller_20260915T001732Z/`
opened `Troop Load II (1/10)` and exposed the normal blue Research control in a
detail panel shifted upward from the older Construction reference. The visual
profile now covers both settled panel positions while retaining the separate
normal-control template. Real bounded OCR in both observers read
`119,429/163,000`, `394,084/320,000`, and `45,778/12,000`; the first row proves
that this live candidate cannot start without separate resource setup. No
Research intent or Start was dispatched.

A later bounded scan under
`.local-data/artifacts/development_research/research_caller_20260915T012717Z/`
proved the exact NPC 2 target, inspected multiple Development details, and
reached `Food Output II (1/5)`. Its panel moved between two vertical positions;
the profile's header, time-label, and blue Research searches now cover that
bounded motion. Both production observers replay the settled position as a
clear Research detail with an idle queue and insufficient resources. The four
visible requirements all exceed inventory, so the run created no durable
Research intent and sent no Start.

RapidOCR split some stacked labels and confused roman `II` with `Il` or `ll`.
The automation accepts only reviewed two-glyph tier-II variants, joins
vertically aligned fragments within one column, and leaves ambiguous
numeral-loss cases non-authoritative. Progress text is bound only when its
center lies inside the measured node icon, with one strict node-local OCR
fallback when the shared crop misses it. A node-local red-pixel probe over the
lock-sprite corner matched all three locked live nodes and excluded the
available tier-II nodes plus independent MAX and 540px negative controls.

The 2026-09-15 authorized non-confirming capture under
`.local-data/artifacts/development_research/resource_popup_capture_20260915T050023Z/`
opened the live `Construction II` shortfall popup on NPC 2. Bounded OCR measured
the centered `Auto Use` title, positive `Sufficient after use` status, paired
Cancel/Confirm row, and the proposed Food packs. No pack was confirmed, no
Research started, and zero diamonds were spent. The saved final frame is the
tracked two-observer regression for the task-owned Confirm selector.

The later authorized production run under
`.local-data/artifacts/development_research/research_caller_20260915T054612Z/`
selected `Research Speed II (4/10)`, revealed and confirmed one exact Auto Use
popup, re-proved the funded idle detail, and pressed normal Research once. Its
correlated post-Start frame shows the countdown and only Speedup controls. The
active Development panel is vertically higher than the earlier Construction
reference, so the bounded active-detail anchor regions cover both observed
positions. A no-replay reconciliation under
`.local-data/artifacts/development_research/research_reconciliation_20260915T062039Z/`
combined that correlated receipt with a fresh exact NPC 2 preflight and final
Home, then committed the one durable `research-001` intent. Diamonds spent were
zero.

## Remaining uncertainty

The extracted APK does not establish the active later client's complete
Development catalog, server eligibility, or research duration. The scoped
selector excludes a visible prerequisite-lock badge. A current normal Start,
positive idle-queue and resource-sufficiency facts, and a fresh correlated
active-detail observation are all required around dispatch.
