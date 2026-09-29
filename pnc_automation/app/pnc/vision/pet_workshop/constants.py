"""Measured Pet Workshop recognition constants and packaged asset paths.

The values in this module are unchanged from the reviewed PW02 producer.
"""

from __future__ import annotations

import re

from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopItemStatus,
    WorkshopOrderRewardCategory,
)
from pnc_automation.app.pnc.vision.selector_catalog import default_selector_asset_root
from pnc_automation.core.vision.image.models import Bounds

_REFERENCE_SIZE = (540, 960)

# Measured board grid (540 x 960 reference): 7 columns x 9 rows, cell ids run
# bottom-up so board row 1 is the lowest display row.
_CELL_X0 = 22.2
_CELL_Y0 = 240.6
_CELL_W = 70.98
_CELL_H = 70.8

# Header OCR regions: "Lv.N" label, "N/M" EXP bar and "N/M" energy pill.
_LEVEL_REGION = Bounds(x=140, y=4, width=60, height=38)
_EXP_REGION = Bounds(x=208, y=4, width=175, height=38)
_ENERGY_REGION = Bounds(x=388, y=4, width=150, height=38)
_LEVEL_SEARCH = re.compile(r"LV\.?\s*(\d+)", re.IGNORECASE)
_GAUGE_SEARCH = re.compile(r"(\d+)\s*/\s*(\d+)")

# Order strip: card panels are detected from their non-background columns in
# the union band (reward row + requirement tile row), then the timer-column
# run is rejected by reward-row panel fraction. Card art starts ~y88; the
# panel body ends ~y225 where the wood chrome begins (~y227).
_CARD_UNION_BAND = (144, 228)
_CARD_PANEL_BAND = (147, 187)
_CARD_PANEL_TAIL_SCAN = (150, 228)
_CARD_TOP_SCAN = (60, 146)
_CARD_MIN_WIDTH = 30
# Full panels measure 168/169 px on both qualified Workshop levels. A
# narrower visible fragment cannot prove full requirements, even when it
# touches the timer viewport rather than the physical screenshot edge.
_CARD_FULL_MIN_WIDTH = 160
# A card run ending within three columns of the frame's right edge may
# continue past the viewport: edge vignette can hide a card's last border
# columns, so termination is only proven by a larger visible margin. A
# full-width panel ending further inside (e.g. the scrolled-left strip's
# third card ending at x1=534) is complete.
_CARD_CLIP_RIGHT_X = 537
_CARD_CLIP_LEFT_X = 92
# Requirement tiles sit as a centered group inside the card, each ~48-52 px
# wide with colored inlay interiors that read as non-panel columns.
_CARD_TILE_BAND = (190, 38)
_CARD_REQ_ICON_BAND = (180, 52)
_CARD_TILE_SLOT_PITCH = 52
_TILE_RUN_MIN_WIDTH = 16
# Reward icons sit on the reward row; each count hugs its icon's right edge.
_CARD_REWARD_BAND = (138, 36)
# The uninterrupted cream baseline below the reward glyphs identifies the
# reward panel, including cards whose panel occupies only their right half.
_REWARD_PANEL_BASELINE = 167
_REWARD_INK_BAND = (148, 164)
_REWARD_GROUP_GAP = 8
_CARD_COMPLETE_OFFSET = Bounds(x=80, y=90, width=96, height=54)
# Strip surface: the wood chrome runs along y227-238 across the whole widget;
# the measured top is the first row where the strip span is mostly content.
_STRIP_CHROME_BAND = (227, 242)
_STRIP_TOP_SCAN = (40, 145)
_STRIP_BOTTOM = 240

# Selection brackets and the selection-bar controls (bottom bar).
_BOARD_REGION = Bounds(x=15, y=235, width=512, height=615)
_INSPECT_SEARCH = Bounds(x=50, y=865, width=160, height=85)
_RECYCLE_SEARCH = Bounds(x=330, y=858, width=195, height=95)
_BACK_SEARCH = Bounds(x=2, y=2, width=74, height=62)
# The unselected bottom bar is a flat texture; a populated bar carries the
# portrait card and action controls, which is measurable edge evidence.
_SELECTION_BAR_REGION = Bounds(x=60, y=860, width=420, height=80)
_BAR_EMPTY_EDGE_MAX = 0.08
# Interior cells carry four corner brackets; cells on the board's bottom edge
# lose the lower pair to the selection bar, so two confident corners suffice.
_SELECTION_MIN_CORNERS = 2

# Modal close controls sit at each overlay's top-right corner.
_ITEM_DETAIL_CLOSE_SEARCH = Bounds(x=430, y=215, width=95, height=80)
_ORDER_DETAIL_CLOSE_SEARCH = Bounds(x=430, y=185, width=95, height=90)
_HELP_CLOSE_SEARCH = Bounds(x=430, y=100, width=95, height=80)

# Order-detail modal: requirement and reward icons stand on blue pedestals
# whose lip rows are measurable coverage (an unmatched pedestal preserves an
# unknown requirement/reward rather than vanishing). Reward counts float at
# each icon's top edge. Requirement icons form a centered group whose extent
# is measured on the modal (a three-icon group starts left of x150), so the
# band spans the modal with margin rather than assuming a fixed left edge.
_OD_REQUIREMENT_BAND = Bounds(x=120, y=285, width=410, height=95)
_OD_REQ_PEDESTAL_BAND = (366, 384)
_OD_REWARD_BAND = Bounds(x=180, y=440, width=360, height=60)
_OD_REW_PEDESTAL_BAND = (508, 522)
_OD_REWARD_TOKEN_BAND = Bounds(x=140, y=424, width=400, height=76)
_OD_PEDESTAL_MIN_WIDTH = 30
# One reward box's bottom lip can be interrupted where its icon art pokes
# through a small gap (the Item Chest does exactly that); runs separated by
# a much smaller gap than the spacing between distinct reward boxes are one
# pedestal, not two. Distinct boxes measured on the modal sit ~20+ px apart.
_OD_PEDESTAL_MERGE_GAP = 8
_OD_PEDESTAL_PAD_X = 20
# Detail count badges overlap the icon's top edge and can extend several
# pixels into the icon (Item Chest "1", feed "4,380" on the 2026-09-22 and
# lasso detail frames); a zone clipped at the badge's bottom edge loses or
# fragments the OCR read, so the lower bound keeps a few pixels of margin.
_OD_COUNT_ZONE_Y = (-20, 21)
# Wide count badges (feed "4,380") overhang the icon's right edge by ~22 px;
# a short pad clips the trailing digits. The next icon's left edge still
# bounds the zone, so the pad only widens into the same pedestal group.
_OD_COUNT_ZONE_RIGHT_PAD = 26

_CELL_OVERLAY_THRESHOLD = 0.90
_CELL_ITEM_THRESHOLD = 0.90
_CELL_EMPTY_THRESHOLD = 0.90
_SELECTION_THRESHOLD = 0.85
_CONTROL_THRESHOLD = 0.85
_STRIP_ICON_THRESHOLD = 0.90
_DETAIL_ICON_THRESHOLD = 0.90
_BOLT_THRESHOLD = 0.70
_CELL_STATE_THRESHOLD = 0.97

# The packaged assets remain owned by ``vision/data`` after this module became
# a package. Resolve through the feature package's parent so every existing
# selector path remains stable.
_DATA_DIR = default_selector_asset_root() / "screen_anchors"

# Board pieces recognized at cell scale. Templates carry identity only. Unmodeled
# pieces such as bread, bags and bolt-producers stay occupied-with-unknown-id.
_ITEM_TEMPLATES = (
    ("pet_workshop_item_tree_4.png", 20004),
    ("pet_workshop_item_fruit_1.png", 20101),
    ("pet_workshop_item_fruit_2.png", 20102),
    ("pet_workshop_item_fruit_3.png", 20103),
    ("pet_workshop_item_fruit_5.png", 20105),
    ("pet_workshop_item_wood_4.png", 20204),
    ("pet_workshop_item_wood_5.png", 20205),
    ("pet_workshop_item_wood_7.png", 20207),
    ("pet_workshop_item_wood_8.png", 20208),
    ("pet_workshop_item_bowl_5.png", 30105),
    ("pet_workshop_item_treasure_1.png", 10101),
    ("pet_workshop_item_treasure_6.png", 10106),
    ("pet_workshop_item_statue_4.png", 10204),
    ("pet_workshop_item_clay_2.png", 30002),
    ("pet_workshop_item_bowl_1_inactive.png", 30101),
)
# Independently reviewed full-cell appearances, cropped two pixels inside
# each cell using _cell_region on the normalized tracked board fixtures.
# These include the overlay area omitted by the tight identity glyph crops.
# Unsupported bubble/feed-lock/transition appearances must stay UNKNOWN.
_CELL_STATE_TEMPLATES = (
    (WorkshopItemStatus.NORMAL, "lv8", (1, 2, 4, 5, 7, 8, 12, 15, 17, 20, 24, 36, 46)),
    (WorkshopItemStatus.NORMAL, "lv6", (4, 8, 9)),
    (WorkshopItemStatus.INACTIVE, "lv8", (3, 52, 56)),
    (WorkshopItemStatus.INACTIVE, "lv6", (1,)),
)
_BADGE_TEMPLATES = tuple(
    _DATA_DIR / f"pet_workshop_ov_badge_{level}.png" for level in (7, 8, 9, 10, 11)
)
_GRASS_TEMPLATE = _DATA_DIR / "pet_workshop_ov_grass.png"
_EMPTY_CELL_TEMPLATE = _DATA_DIR / "pet_workshop_cell_empty.png"
# Producer "tap to generate" bolt badge; measured evidence of the ordinary
# per-produce production mode on this frame.
_BOLT_TEMPLATE = _DATA_DIR / "pet_workshop_ov_bolt.png"

# Order-strip requirement icons at slot scale (36 x 42 crops). The tile
# inlay carries a card-level state tint: fulfilled recipes sit on green,
# unfulfilled on blue, so an icon observed on both tints keeps one crop per
# reviewed appearance.
_STRIP_REQUIREMENT_TEMPLATES = (
    ("pet_workshop_req_food_9.png", 31109),
    ("pet_workshop_req_fruit_4.png", 20104),
    ("pet_workshop_req_fruit_4_blue.png", 20104),
    ("pet_workshop_req_fruit_5.png", 20105),
    ("pet_workshop_req_fruit_5_blue.png", 20105),
    ("pet_workshop_req_statue_4.png", 10204),
    ("pet_workshop_req_treasure_6.png", 10106),
    ("pet_workshop_req_treasure_6_green.png", 10106),
    ("pet_workshop_req_treasure_7.png", 10107),
    ("pet_workshop_req_wood_10.png", 20210),
    ("pet_workshop_req_wood_9.png", 20209),
)
_STRIP_REWARD_TEMPLATES = (
    ("pet_workshop_rew_chest.png", WorkshopOrderRewardCategory.CHEST),
    ("pet_workshop_rew_exp.png", WorkshopOrderRewardCategory.WORKSHOP_EXP),
    ("pet_workshop_rew_feed.png", WorkshopOrderRewardCategory.FEED),
    ("pet_workshop_rew_lasso.png", WorkshopOrderRewardCategory.BEAST_LASSO),
)

# Order-detail icons at modal scale (~70 px requirement, ~44 px reward crops).
_DETAIL_REQUIREMENT_TEMPLATES = (
    ("pet_workshop_od_req_fruit_4.png", 20104),
    ("pet_workshop_od_req_fruit_5.png", 20105),
    ("pet_workshop_od_req_treasure_6.png", 10106),
    ("pet_workshop_od_req_wood_10.png", 20210),
)
_DETAIL_REWARD_TEMPLATES = (
    ("pet_workshop_od_rew_chest.png", WorkshopOrderRewardCategory.CHEST),
    ("pet_workshop_od_rew_feed.png", WorkshopOrderRewardCategory.FEED),
    ("pet_workshop_od_rew_exp.png", WorkshopOrderRewardCategory.WORKSHOP_EXP),
    ("pet_workshop_od_rew_lasso.png", WorkshopOrderRewardCategory.BEAST_LASSO),
)

# The selection bracket's four orientations: the authored corner rotated.
_SEL_CORNER_TEMPLATES = tuple(
    _DATA_DIR / f"pet_workshop_sel_corner{suffix}.png"
    for suffix in ("", "_tr", "_br", "_bl")
)
_INSPECT_TEMPLATE = _DATA_DIR / "pet_workshop_sel_inspect.png"
_RECYCLE_TEMPLATE = _DATA_DIR / "pet_workshop_sel_recycle.png"
# The green Complete button differs across the reviewed 2026-09-22 captures
# and between cards in one frame. Retain those measured appearances under
# the unchanged control threshold; the captures do not establish the full
# animation cycle. Frames without the control stay below the threshold.
_COMPLETE_TEMPLATES = (
    _DATA_DIR / "pet_workshop_ctl_complete.png",
    _DATA_DIR / "pet_workshop_ctl_complete_2.png",
    _DATA_DIR / "pet_workshop_ctl_complete_3.png",
    _DATA_DIR / "pet_workshop_ctl_complete_4.png",
    _DATA_DIR / "pet_workshop_ctl_complete_5.png",
    _DATA_DIR / "pet_workshop_ctl_complete_6.png",
    _DATA_DIR / "pet_workshop_ctl_complete_large.png",
)
_COMPLETE_TEMPLATE_SIZE = (72, 32)
_BACK_TEMPLATE = _DATA_DIR / "pet_workshop_ctl_back.png"
_CLOSE_X_TEMPLATE = _DATA_DIR / "pet_workshop_ctl_close_x.png"

# The private names are internal feature data, but readers import them from
# this canonical owner rather than reaching through the producer.
__all__ = tuple(
    name for name in globals()
    if name.startswith("_") and not name.startswith("__")
)
