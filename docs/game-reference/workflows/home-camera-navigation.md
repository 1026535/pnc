# Measured Home camera and building entry

Observed on 2026-09-16 UTC through the replacement core on the user-authorized
`mega_old_acc` active castle. Its configured live role is `daily_canary`.
The game build was not recorded by these runs. No account/castle switch,
research, Trial challenge, reward claim or resource spending was performed.

## Camera evidence

The camera uses the existing 900x1600 atlas basis. Castle and Infantry Barracks
anchor the reference translation at (-532,+222); a screenshot point is
`(atlas_point + translation) * frame_size / reference_size`.
Current structural matches establish translation; finger movement never does.
At least three agreeing patches from two independent scene groups are needed.
Insufficient or conflicting evidence cannot authorize a building tap.

Live Home initially had only garden and barracks matches because the right
offer rail and quest HUD covered the other catalog patches. The existing
south-plaza crop at reference (540,1340,130,50) matched at 0.993; saved Tower
and mega views scored 0.916 and 0.984, while World negatives scored about 0.52.
It shares the plaza group with the nearby plaza crop. The qualified Tower body
also supplies the independent Tower group as northern landmarks leave view.
Camera landmarks and target bodies share their canonical reference bounds.

## Observed routes and failures

- Institute: Home localized at (-532,+222), one measured upward pan, fresh
  body reacquisition, one tap, Institute menu, then Home at (-532,-395).
  The Research Queue Go focus route was not used.
- Tower: the first pan reached the lower Home view but left only two old
  landmarks. The core stopped before tapping. The already-qualified Tower
  body matched at 0.989 and agreed with the other patches at image offset
  (0,-1065), atlas translation (-532,-843).
- After that camera correction, one tap reached Trial Challenge. Its former
  Hero-card identity anchor failed on the completed/darkened card (0.796).
  The title and fixed Progress/Total Rank toolbar matched 1.0. The existing
  profile now uses that toolbar, preserving the measured Back control.
- The corrected Tower route confirmed Trial Challenge and returned Home at
  (-532,-843). The pre-existing instance remained running and every lease
  was released.

Evidence is under `.local-data/devin-v02/` in the implementation checkout:
`live_initial`, `live_plaza`, `live_tower`, `live_tower_extended`, and
`live_tower_toolbar`, each with result, trace and screenshot artifacts.
The successful Institute run is `20260916T063003Z_2059c3cc`; the successful
Tower run is `20260916T064201Z_a7999ab2` (destination0029, returned Home0034).
Tracked regressions and decoded hashes are in the Home-camera and
screen-recognition fixture manifests.

Confidence is high for these current routes and captured states. Campaign
portal calibration remains pending V02 work. Other Home appearances and
Trial-card content/eligibility require their owning packets; these runs prove
neither a general appearance catalog nor Trial eligibility.
