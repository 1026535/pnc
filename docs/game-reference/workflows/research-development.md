# Development research tree, node detail and queue

## Evidence and limits

The inspected client source is PNC **5.0.203 / version code 233** from the
recovered gameplay Lua cache; see [provenance](../PROVENANCE.md). The September
13 live session displayed Settings footer `5.2.77 5.0.204.235`. The qualified
Development evidence is the September 15 `vision_live_tour_20260915` captures on
the configured `testing` instance at 900x1600 (upper tree, Construction detail,
post-close tree and one bounded scroll) plus tracked 540x960 fixtures from the
September 12 session. No direct game-service request was made, and nothing here
authorizes a mutation.

## Measured layout, September 15–16

**Offline checked (V04, both production observation paths, real RapidOCR):**

- The Development tree publishes its node rows from measured blue label
  components (~179x55 px at 900x1600, ~107x33 at 540x960). Each row's icon
  square is derived above its label (0.82 width, 0.80 height, 0.15 gap of the
  label width) and must show its blue frame; the action point is the icon
  center. Nine tier-I node identities resolve only from their own bounded label
  reads; live OCR variants (`Constructionl`, `Storagel`, `Speed!`) map inside
  the same bounded family.
- The fixed header occupies the top ~6.5% of the frame; tiles that cross it or
  the frame edge publish `clipped` with no action geometry and no level/lock
  reads. A full tile inside the scroll viewport whose icon frame cannot be
  proved publishes `unreadable`, also without actions. On the scrolled capture
  the two header-covered top rows are clipped while the five fully visible
  lower nodes (Infirmary Cap I through Food Output I) publish complete rows
  with level/max-level and padlock-glyph lock evidence.
- The shared node-detail layout publishes the title's `(n/m)` levels, Might and
  effect lines, the `Institute:Lv.N` prerequisite, food/wood cost rows resolved
  by their measured resource icons, Original/Actual times, and the distinct
  gold `Research Now` button with its gem count as read-only geometry. An
  active detail publishes its `No idle queue` countdown; the artifact-prefixed
  or unsupported titles on cross-category captures leave `node_id` unknown
  rather than guessing an identity. The detail panel does not display its own
  category, so `category` stays unset there.
- The Research Queue surface publishes its measured row (`1stResearchQueue`)
  with explicit `idle`/`active`/`unknown` state. Queue-text evidence without
  the proved queue profile still classifies as a blocking popup.
- `ResearchDetail` and `ResearchQueueRow` carry `frame_ref`, `source_screen`
  and `source_layout_id` bound by the shared provenance owner on both
  publication paths; contradictory pre-bound evidence is rejected and nothing
  carries onto the next frame.

## Navigation and mutation boundary

`NavigationCore.open_research_node` requires one unique `complete` typed row on
the proved Development grid, taps it once, and confirms two consecutive fresh
detail frames whose typed `node_id` matches the requested node (a displayed
conflicting category fails; an absent category relies on the proved source).
`scroll_research_tree` sends the single reviewed swipe; `close_research_detail`
sends one Android Back; failed confirmation never repeats a gesture.
`WorkflowContext.open_research_node` primes mutation readiness only when the
returned matching detail exposes the measured template `PNC_RESEARCH_START_BUTTON`;
active, max-level or locked details stay read-only. Research Start authorization, budget
and receipts remain with the feature01 `CoreMutationBoundary` owners.

## Automation implications

- Never tap a research node from tree position, row index or an unreadable
  label; require the typed `complete` row.
- A detail panel proves node identity only through its typed `node_id`; a
  Start control alone does not prove which node is open.
- Premium `Research Now` geometry is observation evidence only; it is never a
  navigation or spending entry point.
- Queue rows and detail queue state describe observed timers; an absent timer
  is `unknown`, not idle.

## Live qualification, September 16

**Live-observed, high confidence:** canonical core runtime
`20260916T084241Z_a52974fe` on the configured `mega_old_acc` active castle completed
Home → Institute → Development → one bounded scroll → Infirmary Cap I 5/5 detail
→ Back → Home → Research Queue → Home without spending. Evidence is
`.local-data/devin-v04/live_max_detail/` in the V04 worktree; destination frame
`0046` at `08:45:01Z`, queue `0061` at `08:45:36Z`, final Home `0066` at
`08:45:44Z`. The lead inspected actual frames and typed facts. The current build
was not independently re-read in this run. Lease released; pre-existing emulator
preserved; no account or castle switch.

The initial live route stopped safely on Troop Load I 5/5's previously unseen
max-level panel (runtime `20260916T082308Z_2b28b9b6`, frame `0044`). This panel is
lower than idle/active details, with fixed Research header glyph and Max banner.
It contains title `(n/m)`, Might and effect lines, but no Research button, premium
button, costs, time or queue facts. The separate
`research_tree_node_detail_max` profile owns bounded OCR and no controls.
`research_node_detail_max_20260916.png` is the reference;
`research_node_detail_max_infirmary_holdout_20260916.png` is the later independent
native-size holdout, never used to create its anchors. Both production publishers
and safe matching-detail/Back navigation are qualified.

The current Research Queue first row explicitly says Idle. The second says
Inactive; the current typed idle/active model reports that unsupported state as
unknown and exposes no Activate action. Do not infer free queue capacity from a
missing timer. A current active queue layout and non-Development trees still
need their own evidence. This packet did not press Research or Research Now;
spending behavior remains with feature01's separately authorized proof.
