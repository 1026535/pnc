# Infantry Barracks primary panel

Artifact-observed on September 17, 2026; reviewed September 29 for V44 acquisition.
Source: `tests/data/screen_recognition/building_routes/infantry_barracks_20260917.png`,
manifest group `2026-09-17/3xx_spies/v20_infantry_menu`. The preserved native frame
is RGB 900x1600, file SHA-256
`9a1d544fbcd319b2caadecfaec4f482b915ddff331c99f9e63c26cfb814775c9`.
Installed build was not recorded. English is visible in the saved frame.

The primary panel has the explicit Infantry Barracks title, a separate
Infantry-specific training description and a top-left Back arrow. Those are
high-confidence facts about this saved frame. Troop tiers, quantities and costs
are mutable content and do not establish family identity.

The candidate `building_infantry_barracks` profile requires both static identity
anchors. Templates are cropped after the canonical 540x960 LANCZOS normalization;
the original 900x1600 source remains preserved. This reference is not an independent
holdout. Its previous role as a Ranged foreign-family negative is retained by
cross-family tests; the manifest now correctly marks it as an Infantry reference.
Only the independently measured Back is added. The candidate Home-return edge
remains gated by current identity, control and destination observations.

Pending: captured-observer regression execution on the final matcher, an
independent appearance holdout where available, and live Home -> slot 5 Infantry -> Home
proof on the final reviewed candidate. This source does not qualify training,
upgrades, collection, resource spending or the Cavalry/Siege panels. Missing
live evidence is pending, not accepted behavior.
