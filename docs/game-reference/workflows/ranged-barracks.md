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
control. The reviewed edge list includes
`PNC_RANGED_BARRACKS -> PNC_HOME_CITY` Back return.

**2026-09-29 native appearance, artifact-observed:** turn010 reached typed
Ranged Barracks on native frame0070 and completed its reviewed Back return.
Turn012 then tapped a freshly measured slot-7 body at `(182,818)` and showed
the same Ranged panel on frames0070/0072, but classified it `UNKNOWN`. On
turn012 frame0072 the old title score is `.96669 >= .95` and Back is
`.98917 >= .94`; the old description scores `.92838 < .94`. The separate
turn010 frame scores `.99267` on that description. A guarded native variant
uses the current frame0072 description crop in canonical 540x960 LANCZOS
space, retaining the old profile. The turn012 frame0070 is a correlated
same-session validation; turn010 frame0070 is an independent session check
of preserved older recognition, not an independent holdout for the new
variant. Fixture paths, file/decoded hashes and capture groups are recorded
in `tests/data/screen_recognition/manifest.json`. The installed client build
was not recorded in those manifests.

**Not yet proven:** a live return after recognition by the new native variant
still needs observation. Unit tiers, glory level, training quantities/costs,
queue facts, and speedup/collect controls remain unqualified.
Infantry has a separate candidate identity/return prerequisite in
`infantry-barracks.md`; Cavalry and Siege primary panels remain unqualified. This note grants no
training, upgrade or spending authority. The current variant's offline proof
does not replace live route acceptance.
