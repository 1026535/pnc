"""Reviewed Home-city camera catalog and view calibration loading."""

from __future__ import annotations

import json
import math
from dataclasses import replace
from functools import lru_cache

from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_slots import HomeCitySlotSelector
from pnc_automation.app.pnc.domain.observation import Bounds
from pnc_automation.app.pnc.vision.selector_catalog import default_selector_asset_root
from pnc_automation.core.errors import SelectorResolutionError

from pnc_automation.app.pnc.domain.home_city_camera_catalog import (
    HOME_CITY_CAMERA_ATLAS_TO_REFERENCE_OFFSET,
    HOME_CITY_CAMERA_REFERENCE_SIZE,
    HomeCityCameraCatalog,
    HomeCityCameraLandmark,
    HomeCityCameraTarget,
    HomeCityViewNormalization,
    HomeCityZoomAnchorSpec,
    HomeCityZoomEndpointCalibration,
)

_NORMALIZATION_FILE_NAME = "normalization.json"
_CAMERA_DATA_DIR = default_selector_asset_root() / "home_city_camera"

@lru_cache(maxsize=1)
def load_home_city_camera_catalog() -> HomeCityCameraCatalog:
    """Loads the reviewed landmark catalog once and validates every packaged crop."""

    institute_body_bounds = Bounds(700, 1240, 80, 75)
    tower_body_bounds = Bounds(240, 1620, 130, 140)
    campaign_body_bounds = Bounds(1480, 1306, 150, 70)
    manor_body_bounds = Bounds(441, 2210, 132, 112)
    catalog = HomeCityCameraCatalog(
        landmarks=(
            HomeCityCameraLandmark(
                id="p2_institute_facade",
                group_id="institute_structure",
                file_name="p2_institute_facade.png",
                reference_bounds=Bounds(615, 1185, 120, 100),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="p3_institute_base_left",
                group_id="institute_structure",
                file_name="p3_institute_base_left.png",
                reference_bounds=Bounds(585, 1250, 105, 70),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="p4_garden_terrace",
                group_id="garden_terrace",
                file_name="p4_garden_terrace.png",
                reference_bounds=Bounds(583, 1071, 90, 110),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="p5_plaza_low",
                group_id="plaza_low",
                file_name="p5_plaza_low.png",
                reference_bounds=Bounds(610, 1345, 120, 45),
                min_score=0.80,
            ),
            HomeCityCameraLandmark(
                id="t6_plaza_south",
                group_id="plaza_low",
                file_name="t6_plaza_south.png",
                reference_bounds=Bounds(540, 1340, 130, 50),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="p6_path_right",
                group_id="institute_structure",
                file_name="p6_path_right.png",
                reference_bounds=institute_body_bounds,
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="t5_barracks_roofs",
                group_id="barracks_roofs",
                file_name="t5_barracks_roofs.png",
                reference_bounds=Bounds(121, 990, 140, 110),
                min_score=0.80,
            ),
            HomeCityCameraLandmark(
                id="tower_of_trial_body",
                group_id="tower_structure",
                file_name="tower_of_trial_body.png",
                reference_bounds=tower_body_bounds,
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="blacksmith_structure",
                group_id="blacksmith_structure",
                file_name="blacksmith_structure.png",
                reference_bounds=Bounds(640, 1845, 120, 130),
                min_score=0.90,
                # Blacksmith is a player-chosen occupant of large slots 11-13;
                # its scene position legitimately varies between accounts.
                movable=True,
            ),
            HomeCityCameraLandmark(
                id="southern_courtyard",
                group_id="southern_courtyard",
                file_name="southern_courtyard.png",
                reference_bounds=Bounds(640, 1530, 100, 100),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="castle_fountain",
                group_id="castle_structure",
                file_name="castle_fountain.png",
                reference_bounds=Bounds(417, 875, 85, 70),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="castle_tower",
                group_id="castle_structure",
                file_name="castle_tower.png",
                reference_bounds=Bounds(543, 667, 62, 157),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="statue_wings",
                # The monument and its circular base are correlated parts of
                # the same plaza, not two independent camera landmarks.
                group_id="plaza_low",
                file_name="statue_wings.png",
                reference_bounds=Bounds(390, 1030, 120, 100),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="garden_west",
                group_id="courtyard_garden",
                file_name="garden_west.png",
                reference_bounds=Bounds(300, 1060, 90, 110),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="plaza_ring",
                group_id="plaza_low",
                file_name="plaza_ring.png",
                reference_bounds=Bounds(340, 1290, 60, 60),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="east_aqueduct",
                group_id="east_fortification",
                file_name="east_aqueduct.png",
                reference_bounds=Bounds(1451, 1505, 120, 140),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="east_parapet",
                group_id="east_fortification",
                file_name="east_parapet.png",
                reference_bounds=Bounds(1651, 1715, 80, 60),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="east_cliff_rock",
                group_id="east_cliff",
                file_name="east_cliff_rock.png",
                reference_bounds=Bounds(1681, 1825, 80, 140),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="east_rock_trees",
                group_id="east_cliff",
                file_name="east_rock_trees.png",
                reference_bounds=Bounds(1521, 1965, 120, 100),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="campaign_portal_body",
                group_id="campaign_portal",
                file_name="campaign_portal_body.png",
                reference_bounds=campaign_body_bounds,
                # The Campaign portal is a fixed scene structure, not a
                # player-chosen slot occupant; the independently measured
                # post-pan pedestal score (.92164) is documented in the
                # fixture manifest and home-camera-navigation.md.
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="campaign_left_pedestal",
                group_id="campaign_portal",
                file_name="campaign_left_pedestal.png",
                reference_bounds=Bounds(1371, 1222, 85, 135),
                # A second fixed region of the same Campaign structure: it
                # shares campaign_portal with the body, so the two crops are
                # one structure's correspondences and never independent
                # votes. Localization evidence only -- no target or tap.
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="ridge_wall",
                group_id="east_fortification",
                file_name="ridge_wall.png",
                reference_bounds=Bounds(1117, 1365, 100, 130),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="alliance_hall_structure",
                group_id="alliance_hall_structure",
                file_name="alliance_hall_structure.png",
                reference_bounds=Bounds(1197, 1675, 140, 80),
                min_score=0.90,
                # Alliance Hall is a player-chosen occupant of large slots
                # 11-13; its scene position legitimately varies between
                # accounts.
                movable=True,
            ),
            HomeCityCameraLandmark(
                id="west_trial_wall",
                group_id="tower_structure",
                file_name="west_trial_wall.png",
                reference_bounds=Bounds(110, 1875, 120, 140),
                min_score=0.95,
            ),
            HomeCityCameraLandmark(
                id="west_sanctum_column",
                group_id="sanctum_structure",
                file_name="west_sanctum_column.png",
                reference_bounds=Bounds(50, 2005, 80, 105),
                min_score=0.95,
            ),
            # Two non-overlapping fixed parts of the Illusory Beast Manor share
            # one group: they are one structure's identity correspondences and
            # cannot supply an independent consensus vote by themselves.
            HomeCityCameraLandmark(
                id="illusory_beast_manor_owl_head",
                group_id="illusory_beast_manor_structure",
                file_name="illusory_beast_manor_owl_head.png",
                reference_bounds=Bounds(441, 2210, 72, 53),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="illusory_beast_manor_right_tower",
                group_id="illusory_beast_manor_structure",
                file_name="illusory_beast_manor_right_tower.png",
                reference_bounds=Bounds(527, 2237, 46, 75),
                min_score=0.90,
            ),
            # Northeast coverage measured on 2026-09-23 157_farm frames: the
            # Sauroi Lair pier is one fixed structure group, and the two moat
            # fortification parts join east_fortification rather than voting
            # independently. All three exclude HUD, nameplates and badges.
            HomeCityCameraLandmark(
                id="northeast_sauroi_pier",
                group_id="sauroi_lair_structure",
                file_name="northeast_sauroi_pier.png",
                reference_bounds=Bounds(1361, 957, 90, 125),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="northeast_moat_cap",
                group_id="east_fortification",
                file_name="northeast_moat_cap.png",
                reference_bounds=Bounds(1246, 1112, 95, 115),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="northeast_moat_shaft",
                group_id="east_fortification",
                file_name="northeast_moat_shaft.png",
                reference_bounds=Bounds(1291, 1227, 70, 95),
                min_score=0.90,
            ),
        ),
        targets=(
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.INSTITUTE,
                landmark_id="p6_path_right",
                file_name="p6_path_right.png",
                reference_bounds=institute_body_bounds,
                reference_action_bounds=Bounds(712, 1244, 30, 18),
                reference_action_point=(724, 1253),
                min_score=0.90,
                max_projection_error=8,
                # Authored at the static single-type slot 9: the binding tags
                # the observed slot without changing candidate behavior.
                reference_slot=HomeCitySlotSelector(9),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.TOWER_OF_TRIAL,
                landmark_id="tower_of_trial_body",
                file_name="tower_of_trial_body.png",
                reference_bounds=tower_body_bounds,
                reference_action_bounds=Bounds(272, 1680, 56, 50),
                reference_action_point=(299, 1714),
                min_score=0.90,
                max_projection_error=8,
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.CAMPAIGN,
                landmark_id="campaign_portal_body",
                file_name="campaign_portal_body.png",
                reference_bounds=campaign_body_bounds,
                reference_action_bounds=Bounds(1540, 1332, 22, 22),
                reference_action_point=(1551, 1343),
                # The independent post-pan live body scores .922; retained
                # non-Home negatives stay below .40. Projection agreement and
                # independent camera consensus remain mandatory.
                min_score=0.90,
                max_projection_error=8,
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.BLACKSMITH,
                landmark_id="blacksmith_structure",
                file_name="blacksmith_structure.png",
                reference_bounds=Bounds(640, 1845, 120, 130),
                # Candidate action geometry measured inside the front
                # wall/door on the saved 157_farm f2 view (native 712,829);
                # it awaits live destination qualification and is not a
                # previously proved click.
                reference_action_bounds=Bounds(700, 1915, 20, 20),
                reference_action_point=(710, 1925),
                min_score=0.90,
                # 12 reference px covers the 6 px scene-calibration
                # uncertainty plus matching noise; failures are retained
                # rather than loosened without new evidence.
                max_projection_error=12,
                # The crop was authored while Blacksmith occupied slot 12 on
                # the reviewed 157_farm views; live candidates are all
                # eligible large slots (11-13) and the binding is evidence,
                # not a universal layout claim.
                reference_slot=HomeCitySlotSelector(12),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.ALLIANCE_HALL,
                landmark_id="alliance_hall_body",
                file_name="alliance_hall_body.png",
                # Native slot-13 body on 157_farm f5 (2026-09-22), with a
                # separate f6 capture as holdout. At zoom 1 and translation
                # (-1632,-718), this crops frame (106,610,162,180), below
                # the spire tips and above the nameplate. The floating
                # upgrade arrow/level badge lies outside the crop.
                reference_bounds=Bounds(1206, 1550, 162, 180),
                # Clear front-wall pixels at native (172,736), away from
                # flags, help/upgrade controls and nameplate. This is a
                # measured body candidate, not live collider qualification.
                reference_action_bounds=Bounds(1262, 1666, 20, 20),
                reference_action_point=(1272, 1676),
                min_score=0.90,
                max_projection_error=12,
                # Reference geometry only: eligibility is 11/12/13 and
                # matching must establish the current same-type occupant.
                # The movable landmark cannot vote for camera pose.
                reference_slot=HomeCitySlotSelector(13),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.MARKET,
                landmark_id="market_body",
                file_name="market_body.png",
                # Native wall-corridor capture (2026-09-23): slot 11,
                # zoom 1, translation (-1298,-645), frame crop
                # (130,875,155,110). The market stalls and central plinth
                # exclude the nameplate, level badge and floating controls.
                reference_bounds=Bounds(896, 1742, 155, 110),
                # Native (213,949) is inside the central market plinth.
                # This is visual body geometry; live entry/return remains
                # unqualified and the public route continues to refuse.
                reference_action_bounds=Bounds(969, 1806, 20, 20),
                reference_action_point=(979, 1816),
                min_score=0.90,
                max_projection_error=12,
                # Current matching, not this source placement, determines
                # the occupant among configurable slots 11/12/13.
                reference_slot=HomeCitySlotSelector(11),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.ILLUSORY_BEAST_MANOR,
                landmark_id="illusory_beast_manor_body",
                file_name="illusory_beast_manor_body.png",
                reference_bounds=manor_body_bounds,
                reference_action_bounds=Bounds(490, 2280, 20, 20),
                reference_action_point=(500, 2290),
                # The 2026-09-21 verified tap (511,722) relative to the matched
                # body scores .918-.931 on three independent PW captures;
                # non-overlapping rivals stay below .65 and the generic Manor
                # is never selected. The body is one identity correspondence,
                # not an additional independent landmark vote.
                min_score=0.90,
                max_projection_error=8,
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.WALL,
                landmark_id="wall_gatehouse",
                file_name="wall_gatehouse.png",
                reference_bounds=Bounds(1180, 1845, 95, 125),
                reference_action_bounds=Bounds(1205, 1907, 32, 32),
                reference_action_point=(1221, 1923),
                min_score=0.90,
                max_projection_error=12,
                reference_slot=HomeCitySlotSelector(2),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.GODDESS_STATUE,
                landmark_id="goddess_statue_body",
                file_name="goddess_statue_body.png",
                # The body is the static gold statue column/plinth measured on
                # the 2026-09-23 live005 frame 0066 (native 368,145,60,78 under
                # camera (-595,-847)); the earlier circular platform trim was
                # never a proved clickable body. The crop excludes the upper
                # HUD, the mutable level badge at the statue's right edge, the
                # floating nameplate, and the platform ring below.
                reference_bounds=Bounds(431, 1214, 60, 78),
                # Keep the candidate tap on the interior gold column body.
                reference_action_bounds=Bounds(451, 1259, 20, 20),
                reference_action_point=(461, 1269),
                min_score=0.90,
                max_projection_error=12,
                reference_slot=HomeCitySlotSelector(15),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.CASTLE,
                landmark_id="castle_tower",
                file_name="castle_tower.png",
                reference_bounds=Bounds(543, 667, 62, 157),
                # Interior stonework on the two native Castle views from
                # 2026-09-21; destination qualification remains a live gate.
                reference_action_bounds=Bounds(560, 742, 28, 24),
                reference_action_point=(574, 754),
                min_score=0.90,
                max_projection_error=8,
                reference_slot=HomeCitySlotSelector(1),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.WAREHOUSE,
                landmark_id="warehouse_body",
                file_name="warehouse_body.png",
                reference_bounds=Bounds(902, 1050, 112, 138),
                # The L-shaped keep plus courtyard measured on the 2026-09-29
                # turn006 post-pan frame 0047 (native 282,667,83,102 under
                # camera (-777,55) at zoom ~0.739); the independent 0084
                # survey view scores .957. The crop excludes the nameplate,
                # level badge and the sidebar-occluded edge.
                reference_action_bounds=Bounds(956, 1108, 22, 22),
                reference_action_point=(967, 1119),
                min_score=0.90,
                # 12 reference px covers scene-calibration uncertainty plus
                # matching noise; the same skin republishes at slot 3 on
                # other castles, which is correct slot-3-only evidence.
                max_projection_error=12,
                # Warehouse is the single occupant type slot 3 allows; the
                # binding tags the authored slot without narrowing
                # candidate behavior beyond its reviewed eligibility.
                reference_slot=HomeCitySlotSelector(3),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.BANK,
                landmark_id="bank_body",
                file_name="bank_body.png",
                reference_bounds=Bounds(-212, 1543, 160, 129),
                # Golden facade and blue dome under the fixed sys_1/5001
                # marker, measured on the 2026-09-29 attempt1 baseline frame
                # 0022 (native 216,1036,120,97 under camera (-24,45) at zoom
                # 0.75); the independent 0092 survey view scores .972. The
                # crop starts below the floating '!' badge pointer and
                # excludes the nameplate. The node projects outside the
                # canonical reference window but matching is frame-space.
                reference_action_bounds=Bounds(-144, 1578, 22, 22),
                reference_action_point=(-133, 1589),
                min_score=0.90,
                max_projection_error=8,
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.INFANTRY_BARRACKS,
                landmark_id="infantry_barracks_body",
                file_name="infantry_barracks_body.png",
                # White facade between the red columns under the front
                # watchtower, measured on the 2026-09-29 attempt1 baseline
                # frame 0022 (native 415,625,83,78 under camera (-24,45) at
                # zoom 0.75) with a readable 'Infantry Barracks' nameplate;
                # the independent 0092 survey view measures the same body at
                # (287,559,83,78) and the zoom-1.0 f0 baseline at
                # (53,995,111,104). The crop excludes the floating coin
                # bubble and pennant above, the gold 'Z' marker and level
                # badge at the right, and the nameplate below.
                reference_bounds=Bounds(53, 995, 111, 104),
                # Interior parapet point clear of all floating controls on
                # both saved views; destination qualification remains a live
                # gate since collider routing is not proven by a body match.
                reference_action_bounds=Bounds(89, 1038, 22, 22),
                reference_action_point=(100, 1049),
                min_score=0.90,
                # 12 reference px covers the scene-calibration uncertainty
                # plus matching noise, matching the slot-bound convention.
                max_projection_error=12,
                # Slot 5 is the single-type infantry slot (client 1020); the
                # binding tags the authored slot's reviewed eligibility.
                reference_slot=HomeCitySlotSelector(5),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.CAVALRY_BARRACKS,
                landmark_id="cavalry_barracks_body",
                file_name="cavalry_barracks_body.png",
                # Blue awning and tower under the radar dome, measured on the
                # 2026-09-29 attempt1 baseline frame 0022 (native
                # 252,690,100,42 under camera (-24,45) at zoom 0.75); the
                # independent 0092 survey view measures the same body at
                # (124,624,100,42) and carries the readable 'Cavalry
                # Barracks' nameplate that corroborates the slot-6 body.
                # The crop excludes the floating 'Z' marker grazing its
                # upper-right and the statue/nameplate below the awning.
                reference_bounds=Bounds(-164, 1082, 133, 56),
                # Interior awning point clear of floating controls on both
                # saved views; destination qualification remains a live gate.
                reference_action_bounds=Bounds(-101, 1114, 22, 22),
                reference_action_point=(-90, 1125),
                min_score=0.90,
                max_projection_error=12,
                # Slot 6 is the single-type cavalry slot (client 1021).
                reference_slot=HomeCitySlotSelector(6),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.RANGED_BARRACKS,
                landmark_id="ranged_barracks_body",
                file_name="ranged_barracks_body.png",
                # Gong, towers and platform band, measured on the 2026-09-29
                # attempt1 baseline frame 0022 (native 390,800,120,34 under
                # camera (-24,45) at zoom 0.75) with a readable 'Ranged
                # Barracks' nameplate; the independent 0092 survey view
                # measures the same body at (262,734,120,34). The crop
                # excludes the '6' badge above, the red '0' badges and 'Z'
                # marker at the right, and the nameplate below.
                reference_bounds=Bounds(20, 1229, 160, 45),
                # Interior platform point clear of floating controls on both
                # saved views; destination qualification remains a live gate.
                reference_action_bounds=Bounds(82, 1242, 22, 22),
                reference_action_point=(93, 1253),
                min_score=0.90,
                max_projection_error=12,
                # Slot 7 is the single-type ranged slot (client 1022).
                reference_slot=HomeCitySlotSelector(7),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.SIEGE_FACTORY,
                landmark_id="siege_factory_body",
                file_name="siege_factory_body.png",
                # Factory front wall between the blue-topped towers, measured
                # on the 2026-09-29 attempt1 baseline frame 0022 (native
                # 212,806,72,84 under camera (-24,45) at zoom 0.75) with a
                # readable 'Siege Factory' nameplate; the independent 0092
                # survey view measures the same body at (84,740,72,84), where
                # the action point projects inside the declared left-HUD
                # exclusion band. The crop excludes the floating 'Z' marker
                # at its upper-right and the cavalry nameplate above.
                reference_bounds=Bounds(-217, 1237, 96, 112),
                # Interior wall point clear of floating controls on the
                # saved views; destination qualification remains a live gate.
                reference_action_bounds=Bounds(-184, 1291, 22, 22),
                reference_action_point=(-173, 1302),
                min_score=0.90,
                max_projection_error=12,
                # Slot 8 is the single-type siege slot (client 1023).
                reference_slot=HomeCitySlotSelector(8),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.MOON_WELL,
                landmark_id="moon_well_body",
                file_name="moon_well_body.png",
                # Rocky mound, green crystals and blue-roofed hut measured
                # on the 2026-09-30 ef03789c turn020 frame 0029 (native
                # 625,1110,122,60 under camera (-637,-421) at zoom 0.75)
                # with a readable 'Moon Well' nameplate; the translated
                # holdout frame 0030 measures the same body window under
                # camera (-882,-413) at zoom ~0.742. The crop excludes the
                # floating gem-collect bubble above, the level badge and
                # yellow flag at the right, and the nameplate below.
                reference_bounds=Bounds(1151, 2263, 162, 80),
                # Interior mound point clear of floating controls on both
                # saved views; destination qualification remains a live
                # gate and this detection point sits below the
                # conservative tap band on the measured views.
                reference_action_bounds=Bounds(1227, 2293, 20, 20),
                reference_action_point=(1237, 2303),
                min_score=0.90,
                # 12 reference px covers the scene-calibration uncertainty
                # plus matching noise, matching the slot-bound convention.
                max_projection_error=12,
                # Slot 17 is one of the multi-type ordinary slots (17-51)
                # eligible for moon-well bodies (client 1027); the binding
                # tags the authored slot's reviewed eligibility.
                reference_slot=HomeCitySlotSelector(17),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.WATCHTOWER,
                landmark_id="watchtower_body",
                file_name="watchtower_body.png",
                # Clean stone shaft of the level-12 'Watch Tower', cropped
                # as rows 80:200 by columns 15:100 of the original
                # full-body template authored on the 2026-09-29 turn006
                # frame 0047 (shaft measured at native (387,311) under
                # camera (-777,55) at zoom ~0.739). The translated turn030
                # holdout frame 0050 measures the same shaft at (142,314)
                # under camera (-1044,42) at zoom 0.75 — a body-specific
                # ~+4/+12 frame-px displacement corroborated against two
                # independent same-frame bodies. The unshifted shaft
                # reference is (1044,569); the prior below is the
                # evidenced midpoint and splits the residual to ~6px on
                # each saved view. The crop drops the '/120'
                # ribbon-covered sky corner that depressed the packaged
                # full-body score to .806 on 0050, plus the nameplate,
                # level badge and left HUD rail.
                reference_bounds=Bounds(1047, 577, 85, 120),
                # Interior shaft point re-expressed against this crop,
                # preserving the measured 0047 source point near (423,373)
                # and the holdout point near (179,377); both sit inside
                # the HUD-safe band. Destination qualification remains a
                # live gate since a body match does not prove collider
                # routing.
                reference_action_bounds=Bounds(1084, 645, 22, 22),
                reference_action_point=(1096, 661),
                min_score=0.90,
                # 12 reference px covers the scene-calibration uncertainty
                # plus matching noise, matching the slot-bound convention.
                max_projection_error=12,
                # Slot 4 is the single-type watchtower slot (client 1006).
                reference_slot=HomeCitySlotSelector(4),
            ),
        ),
        reference_size=HOME_CITY_CAMERA_REFERENCE_SIZE,
        atlas_to_reference_offset=HOME_CITY_CAMERA_ATLAS_TO_REFERENCE_OFFSET,
        anchor_object_ids=(
            HomeCityObjectId.CASTLE,
            HomeCityObjectId.INFANTRY_BARRACKS,
        ),
        reference_source=(
            "20260915T160615Z_core_20260915T160413Z_018f500d_0025_06_fresh_fresh_home_for_pan.png"
        ),
        data_dir=_CAMERA_DATA_DIR,
    )
    for item in (*catalog.landmarks, *catalog.targets):
        path = catalog.template_path(item.file_name)
        if not path.is_file():
            raise SelectorResolutionError(
                "Home-camera catalog template is missing from package data.",
                template=str(path),
            )
        with Image.open(path) as template:
            if template.size != (item.reference_bounds.width, item.reference_bounds.height):
                raise SelectorResolutionError(
                    "Home-camera catalog template size does not match its reference bounds.",
                    template=str(path),
                    expected=(item.reference_bounds.width, item.reference_bounds.height),
                    actual=template.size,
                )
    for target in catalog.targets:
        if not target.reference_bounds.contains_bounds(target.reference_action_bounds):
            raise SelectorResolutionError(
                "Camera target action bounds must stay inside the authored body crop.",
                landmark_id=target.landmark_id,
            )
        if not target.reference_action_bounds.contains_point(target.reference_action_point):
            raise SelectorResolutionError(
                "Camera target action bounds must contain the verified action point.",
                landmark_id=target.landmark_id,
            )
    return replace(catalog, normalization=_load_view_normalization(catalog))


def _load_view_normalization(
    catalog: HomeCityCameraCatalog,
) -> HomeCityViewNormalization:
    """Loads and validates the packaged endpoint/anchor view calibration."""

    path = catalog.data_dir / _NORMALIZATION_FILE_NAME
    if not path.is_file():
        raise SelectorResolutionError(
            "Home-camera view normalization calibration is missing from package data.",
            template=str(path),
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SelectorResolutionError(
            "Home-camera view normalization calibration is not valid JSON.",
            template=str(path),
        ) from error
    if not isinstance(document, dict):
        raise SelectorResolutionError(
            "Home-camera view normalization calibration must be a JSON object.",
            template=str(path),
        )
    if document.get("version") != 1:
        raise SelectorResolutionError(
            "Home-camera view normalization calibration must declare version 1.",
            template=str(path),
            version=document.get("version"),
        )
    endpoint = _normalization_endpoint(document.get("endpoint"), catalog)
    native_frame_size = document.get("native_frame_size")
    if (
        not isinstance(native_frame_size, list | tuple)
        or len(native_frame_size) != 2
        or any(
            type(value) is not int or value <= 0 for value in native_frame_size
        )
    ):
        raise SelectorResolutionError(
            "Home-camera view normalization must declare a positive native frame size.",
            entry=native_frame_size,
        )
    return HomeCityViewNormalization(
        hud_exclusion_bounds=tuple(
            _normalization_bounds(item, field="hud_exclusion_bounds")
            for item in document.get("hud_exclusion_bounds", ())
        ),
        native_frame_size=(native_frame_size[0], native_frame_size[1]),
        endpoint=endpoint,
        zoom_anchors=tuple(
            _normalization_anchor(item, catalog)
            for item in document.get("zoom_anchors", ())
        ),
    )


def _normalization_bounds(entry: object, *, field: str) -> Bounds:
    """Coerces one ``[x, y, w, h]`` authored rectangle into typed bounds."""

    if (
        not isinstance(entry, list | tuple)
        or len(entry) != 4
        or any(type(value) is not int for value in entry)
    ):
        raise SelectorResolutionError(
            "Home-camera view normalization bounds must be four integers.",
            field=field,
            entry=entry,
        )
    bounds = Bounds(*entry)
    if bounds.width <= 0 or bounds.height <= 0:
        raise SelectorResolutionError(
            "Home-camera view normalization bounds must have positive size.",
            field=field,
            entry=entry,
        )
    return bounds


def _normalization_endpoint(
    entry: object,
    catalog: HomeCityCameraCatalog,
) -> HomeCityZoomEndpointCalibration | None:
    """Parses the authored endpoint calibration against the catalog layout."""

    if entry is None:
        return None
    if not isinstance(entry, dict):
        raise SelectorResolutionError(
            "The Home-camera endpoint calibration must be a JSON object.",
            entry=entry,
        )
    endpoint_id = entry.get("id")
    reference_size = entry.get("reference_size")
    zoom_interval = entry.get("zoom_interval")
    non_endpoint_floor = entry.get("non_endpoint_floor")
    min_fixed_groups = entry.get("min_fixed_groups")
    max_mean_residual = entry.get("max_mean_residual_px")
    if not isinstance(endpoint_id, str) or endpoint_id == "":
        raise SelectorResolutionError(
            "The Home-camera endpoint calibration must name a stable calibration id.",
            entry=entry,
        )
    if (
        not isinstance(reference_size, list | tuple)
        or len(reference_size) != 2
        or any(type(value) is not int or value <= 0 for value in reference_size)
    ):
        raise SelectorResolutionError(
            "The Home-camera endpoint calibration must declare a supported reference size.",
            entry=entry,
        )
    if tuple(reference_size) != tuple(catalog.reference_size):
        raise SelectorResolutionError(
            "The Home-camera endpoint calibration's reference size must match the catalog layout.",
            entry=entry,
            reference_size=catalog.reference_size,
        )
    if (
        not isinstance(zoom_interval, list | tuple)
        or len(zoom_interval) != 2
        or any(
            not isinstance(value, int | float) or not math.isfinite(value)
            for value in zoom_interval
        )
        or not 0.0 < zoom_interval[0] < zoom_interval[1]
    ):
        raise SelectorResolutionError(
            "The Home-camera endpoint calibration must declare an increasing positive zoom interval.",
            entry=entry,
        )
    if (
        not isinstance(non_endpoint_floor, int | float)
        or not math.isfinite(non_endpoint_floor)
        or non_endpoint_floor <= zoom_interval[1]
    ):
        raise SelectorResolutionError(
            "The Home-camera endpoint calibration's non-endpoint floor must exceed its interval.",
            entry=entry,
        )
    if type(min_fixed_groups) is not int or min_fixed_groups < 1:
        raise SelectorResolutionError(
            "The Home-camera endpoint calibration must require at least one independent group.",
            entry=entry,
        )
    if (
        not isinstance(max_mean_residual, int | float)
        or not math.isfinite(max_mean_residual)
        or max_mean_residual <= 0.0
    ):
        raise SelectorResolutionError(
            "The Home-camera endpoint calibration must declare a positive residual bound.",
            entry=entry,
        )
    return HomeCityZoomEndpointCalibration(
        id=endpoint_id,
        reference_size=(reference_size[0], reference_size[1]),
        zoom_interval=(float(zoom_interval[0]), float(zoom_interval[1])),
        non_endpoint_floor=float(non_endpoint_floor),
        min_fixed_groups=min_fixed_groups,
        max_mean_residual_px=float(max_mean_residual),
        native_sources=_normalization_sources(entry.get("native_sources")),
        holdout_sources=_normalization_sources(entry.get("holdout_sources")),
    )


def _normalization_sources(entry: object) -> tuple[str, ...]:
    """Coerces one authored source-capture list into provenance strings."""

    if not isinstance(entry, list | tuple):
        return ()
    if any(not isinstance(item, str) or item == "" for item in entry):
        raise SelectorResolutionError(
            "Home-camera view normalization sources must be non-empty names.",
            entry=entry,
        )
    return tuple(entry)


def _normalization_anchor(
    entry: object,
    catalog: HomeCityCameraCatalog,
) -> HomeCityZoomAnchorSpec:
    """Parses one authored native scenery patch plus its contained point."""

    if not isinstance(entry, dict):
        raise SelectorResolutionError(
            "A Home-camera zoom-anchor spec must be a JSON object.",
            entry=entry,
        )
    anchor_id = entry.get("id")
    file_name = entry.get("file_name")
    point_offset = entry.get("point_offset")
    scales = entry.get("scales")
    min_score = entry.get("min_score")
    if not isinstance(anchor_id, str) or anchor_id == "":
        raise SelectorResolutionError(
            "A Home-camera zoom anchor must name a stable qualification id.",
            entry=entry,
        )
    if not isinstance(file_name, str) or not catalog.template_path(file_name).is_file():
        raise SelectorResolutionError(
            "A Home-camera zoom anchor must name a packaged template crop.",
            entry=entry,
            template=file_name,
        )
    if (
        not isinstance(point_offset, list | tuple)
        or len(point_offset) != 2
        or any(type(value) is not int or value < 0 for value in point_offset)
    ):
        raise SelectorResolutionError(
            "A Home-camera zoom anchor's point must be a non-negative integer offset inside its crop.",
            entry=entry,
        )
    with Image.open(catalog.template_path(file_name)) as template:
        template_size = template.size
    if not (
        point_offset[0] < template_size[0]
        and point_offset[1] < template_size[1]
    ):
        raise SelectorResolutionError(
            "A Home-camera zoom anchor's point must lie inside its packaged crop.",
            entry=entry,
            template_size=template_size,
        )
    if (
        not isinstance(scales, list | tuple)
        or not scales
        or any(
            not isinstance(value, int | float)
            or not math.isfinite(value)
            or value <= 0.0
            for value in scales
        )
    ):
        raise SelectorResolutionError(
            "A Home-camera zoom anchor must declare non-empty positive template scales.",
            entry=entry,
        )
    if (
        not isinstance(min_score, int | float)
        or not math.isfinite(min_score)
        or not 0.0 < min_score <= 1.0
    ):
        raise SelectorResolutionError(
            "A Home-camera zoom anchor must declare a match floor in (0, 1].",
            entry=entry,
        )
    return HomeCityZoomAnchorSpec(
        id=anchor_id,
        file_name=file_name,
        point_offset=(point_offset[0], point_offset[1]),
        scales=tuple(float(value) for value in scales),
        min_score=float(min_score),
        native_sources=_normalization_sources(entry.get("native_sources")),
    )


def home_city_camera_target(object_id: HomeCityObjectId) -> HomeCityCameraTarget | None:
    """Returns the camera-qualified target spec for one canonical object id."""

    return load_home_city_camera_catalog().target_for(object_id)
