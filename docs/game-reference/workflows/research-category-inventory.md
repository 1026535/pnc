# Research category inventory — 2026-09-16

The lead captured Economy, Military and Fortification on the configured
mega_old_acc active castle using canonical runtime leases and the Institute's
current template category controls. No node, research, upgrade, unlock or item
action was performed. Build unknown. These are reference captures, not an
independent holdout or proof that every technology tier is supported.

The original native screenshots are
`tests/data/screen_recognition/research_tree_{economy,military,fortification}_20260916.png`.
Their manifest groups identify source runtimes e369463f,71d988ee,3e26f8ff.
Ignored source observations and traces reside under
`.local-data/research-inventory/` in the V05–V07 qualification checkout.

Each category title was visually reviewed and qualified with the shared
Master Researcher tree chrome. Title score1.0, chrome>=.98166, Back1.0;
foreign-menu title negatives<=.58972. Thresholds remain .95 for the new
titles and .93 for chrome/Back. Both production publishers proved the proper
category layout, CLEAR guard and template Back. The shared V05–V07 implementation and the acceptance evidence below now
qualify node content and the inspected detail transitions.

Economy shows Food Output I3/4, Wood Output I1/5, Food Harvest I2/5, Wood
Harvest I1/5, Iron Output I1/5 and Iron Harvest I0/5. The last label reaches
the bottom edge; its row must not gain a tap without complete geometry.
Output and Harvest share resource artwork. Wood Harvest wraps its suffix,
so category plus the entire displayed title distinguishes the node.

Military shows March Speed I, Infantry HP I, Infantry ATK I, Infantry DEF I,
Hunt March I, Cavalry ATK I and March Queue I with literal MAX labels.
Siege ATK I shows2/3 and Ranged ATK I shows1/3. MAX proves a displayed maximum
state; it does not reveal a numeric current or maximum level. These facts do
not authorize research and do not make an incomplete edge row actionable.

Fortification shows Wall DEF I2/10 and Trap ATK I0/3 without visible padlocks.
Trap DEF I, Trap HP I, Defender ATK I, Defender DEF I and Defender HP I each
show0/3 and a visible padlock. Several names wrap onto two lines, and the
bottom labels reach the viewport edge. The padlock is independent evidence
of the observed lock; a zero level alone is not lock evidence. Inspection
eligibility and research eligibility remain separate contracts.

Confidence is high for these visible labels, counters, artwork reuse and
lock glyphs. Scroll layouts, matching detail transitions and additional
nodes remain unqualified by this capture-only pass.


## Accepted shared category implementation — 2026-09-16

One category catalog owns four category titles, entry selectors, qualified
layouts and 31 supported node IDs. The existing ResearchContentProducer reads
measured node labels, paired levels, literal MAX and padlocks; a category must
be independently proved and foreign labels never become local nodes. MAX
without a numeric pair keeps both numbers unknown. Shared node/detail/scroll/
close operations refresh content and verify the requested identity and return
category. WorkflowContext only primes the existing Development Start boundary;
Economy, Military and Fortification support is inspection authority only.

Native Economy, Military and Fortification tree/detail fixtures pass real
bounded OCR through both publishers. Economy's original clipped Iron Harvest
row has no action. The later independent native Economy holdout (a02dbcf6,
frame0033, SHA256 67c55fc963167b81e10051820e69009cedc5bb7bc1636fca307ad1a88eb04b46)
places that row completely inside the viewport. A bounded 2x RGB fallback
resolves Wood/Iron Output labels whose blue border caused rotated OCR; it uses
the existing canonical label variants and does not alter the OCR backend or
confidence floors. Detail headers share that preprocessing owner and exclude
the chart icon before their bounded retry. Unreadable fields stay unknown.

Validation: unit.app.pnc.vision passed223 tests before the final bounded-header
correction; focused navigation/mutation/task checks passed45. The full affected
fallback ec652f65660c4b18aedd740e7b6fd312 passed2423 with7 skipped (2430 total,
2026-09-16T17:04:45Z, base10decf7). The final captured Research module plus
category-fact and mutation contracts passed26 tests in157.898s after the label
fallback correction. Camera unit/publication and distribution checks are
recorded in home-camera-navigation.md; independent passing contracts are reused.

Live runtimea02dbcf6 (17:10–17:16Z), canonical mega_old_acc lease, active
K157/NPC2/22: Economy -> Food Output I3/4 -> Economy -> Home; Military ->
Siege ATK I2/3 -> Military -> Home; Fortification -> Wall DEF I2/10 ->
Fortification -> Home. The lead visually inspected all matching detail frames.
Food/Siege premium costs were read66/346; the tiny displayed Fortification
premium1 remained unreadable in its typed output and is not claimed as proved.
The final corrected label run45be2a99 opened Wood Output I1/5 (frame0034,
17:39:58Z) and returned Home0045 at17:40:27Z; both images were visually checked.
No research, premium, unlock, upgrade or item action was sent. Each lease was
released and the pre-existing instance preserved. Artifacts and traces are in
.local-data/devin-v05-v07/live_candidate_corrected and live_wood_output_corrected.

Coverage is the evidenced six Economy, nine Military and seven Fortification
nodes and qualified shared details. No exhaustive technology or scroll catalog,
unseen tiers, empty states or new spending flow is claimed. The build remains
unknown. Source-only captures and the independent live holdout are distinguished
in the manifest and provenance records.

Final integration check against accepted V12: 59 tests passed in23.846s,
including all six identities on the independent Economy tree, Home pan bounds,
visual profile metadata and Bag identity contracts. No production behavior was
changed by the V12 merge; the shared profile entries were combined by key.
