# Ranged Barracks primary panel

Observed in the September 22, 2026 saved frame
`20260922T003355Z_core_20260922T003339Z_a5948a9b_0007_c4_final.png` from the V08
live run on `serious_stuff`; the run stopped on this then-unknown screen after
canonical popup recovery, so no live route used it. The tracked reference is
`tests/data/screen_recognition/building_routes/ranged_barracks_reference_20260922.png`
(540x960). The foreign-family negative
`infantry_barracks_20260917.png` proves the shared barracks prefab alone cannot
claim Ranged identity.

**Artifact-observed, high confidence:** the primary `CAMP_PANEL` layout shows
the `Ranged Barracks` title, the family-specific line "Where Ranged units are
trained. Upgrade to unlock more advanced units.", and a top-left Back arrow.

**Repository-proven:** the `building_ranged_barracks` visual profile requires
both the title and the family description anchors; neither alone nor the shared
prefab graphics establish identity. Through both production observation
publishers the screen publishes only the measured `PNC_BACK_BUTTON_TOP_LEFT`
control. The reviewed edge list adds the candidate
`PNC_RANGED_BARRACKS -> PNC_HOME_CITY` Back return.

**Not yet proven:** the Back return edge is a candidate awaiting a live capture
that observes the transition to Home. Unit tiers, glory level, training
quantities/costs, queue facts, speedup/collect controls, and the Infantry,
Cavalry, and Siege family panels remain unqualified. This note grants no
training, upgrade, spending, or live-route acceptance; the static reference is
not live acceptance evidence.
