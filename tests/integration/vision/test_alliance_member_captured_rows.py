"""Captured Alliance member rows prove mode and frame-local row ownership."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import unittest

from PIL import Image, ImageDraw

from pnc_automation.app.pnc.domain.observation import RowRecognitionStatus, ListEntryKind
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from tests.integration.vision.test_alliance_remaining_visual_contracts import _builder, _capture, _perception
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.alliance_member_rows import (
    detect_alliance_member_row_bounds,
    parse_alliance_member_rows,
)
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import (
    ObservationOcrContext,
    OcrLine,
    OcrResult,
    RapidOcrService,
)


TEST_ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = TEST_ROOT / "data" / "screen_recognition" / "alliance_variants" / "member_rows"
RAW_ROOT = TEST_ROOT.parent / ".local-data" / "artifacts" / "capture_gap_exploration" / "20260913T030954Z"
MANAGE_LAYOUT = "alliance_remaining_member_list"
REINFORCE_LAYOUT = "alliance_remaining_member_reinforce"


@dataclass(slots=True)
class _BoundedOcrBackend:
    """Serve controlled lines only when the requested semantic crop contains them."""

    lines: tuple[OcrLine, ...]
    calls: list[Bounds | None] = field(default_factory=list)

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        """Reject unbounded reads and preserve global line coordinates."""

        del image
        self.calls.append(region)
        if region is None:
            raise AssertionError("Alliance member parser must never read the whole frame.")
        lines = tuple(line for line in self.lines if region.contains_bounds(line.bounds))
        return OcrResult(lines=lines, words=tuple(word for line in lines for word in line.words))

    def read_lines(self, image: Image.Image, region: Bounds | None = None) -> tuple[OcrLine, ...]:
        """Expose the OCR protocol's line helper."""

        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Bounds) -> str:
        """Expose the OCR protocol's text helper."""

        return "\n".join(line.text for line in self.read_result(image, region).lines)


def _load_fixture(name: str) -> Image.Image:
    """Load one sanitized captured row fixture."""

    with Image.open(FIXTURE_ROOT / name) as image:
        return image.convert("RGB")


def _frame_ref(label: str) -> FrameRef:
    """Return deterministic-enough frame provenance for a parser context."""

    return FrameRef(
        session_id=label,
        session_epoch=1,
        capture_sequence=1,
        input_sequence=0,
        captured_at=datetime.now(UTC),
    )


def _make_context(
    image: Image.Image,
    *,
    action: str,
    names: tuple[str, ...],
    missing_action_rows: frozenset[int] = frozenset(),
    wrong_action: str | None = None,
) -> tuple[ObservationOcrContext, _BoundedOcrBackend]:
    """Build a frame-bound backend with lines in only the reviewed fields."""

    screen = (
        ScreenType.PNC_ALLIANCE_MEMBER_LIST
        if action == "manage"
        else ScreenType.PNC_ALLIANCE_MEMBER_REINFORCE
    )
    layout = MANAGE_LAYOUT if action == "manage" else REINFORCE_LAYOUT
    rows = detect_alliance_member_row_bounds(image=image, screen_type=screen, layout_id=layout)
    lines: list[OcrLine] = []
    for index, row in enumerate(rows):
        lines.append(OcrLine(names[index], Bounds(row.x + 240, row.y + 30, 100, 30), 0.99))
        if index not in missing_action_rows:
            text = wrong_action or action.title()
            lines.append(OcrLine(text, Bounds(row.x + 665, row.y + 78, 120, 30), 0.99))
    backend = _BoundedOcrBackend(tuple(lines))
    context = ObservationOcrContext(image, backend, _frame_ref(f"alliance-{action}"), "captured-row-test")
    context.require_bounded_regions()
    return context, backend


class AllianceMemberCapturedRowsTests(unittest.TestCase):
    """Keep captured Manage and Hall Reinforce rows semantically separate."""

    def test_full_captured_layouts_publish_rows_through_both_production_paths(self) -> None:
        """Independent profile identity owns each named row and its measured action."""

        cases = (
            ("alliance_member_manage_rows.png", ScreenType.PNC_ALLIANCE_MEMBER_LIST,
             MANAGE_LAYOUT, "manage", (560, 861, 1079, 1297)),
            ("alliance_member_reinforce_rows.png", ScreenType.PNC_ALLIANCE_MEMBER_REINFORCE,
             REINFORCE_LAYOUT, "reinforce", (185, 488, 706, 924, 1142, 1360)),
        )
        for fixture, screen, layout, action, tops in cases:
            with Image.open(FIXTURE_ROOT / fixture) as source:
                original = source.convert("RGB")
            for size in ((540, 960), (900, 1600)):
                image = original.resize(size, Image.Resampling.LANCZOS)
                factor = size[0] / 900
                def bounds(x, y, w, h):
                    return Bounds(*(round(v * factor) for v in (x, y, w, h)))
                names = tuple(f"Member {i + 1}" for i in range(len(tops)))
                lines = tuple(line for i, top in enumerate(tops) for line in (
                    OcrLine(names[i], bounds(265, top + 30, 120, 30), 1.),
                    OcrLine(action.title(), bounds(682, top + 78, 120, 30), 1.),
                ))
                for path in ("builder", "navigation"):
                    with self.subTest(fixture=fixture, size=size, path=path):
                        backend = _BoundedOcrBackend(lines)
                        builder = _builder(backend)
                        capture = _capture(image, session_id=f"rows:{fixture}:{path}:{size}")
                        observation = (builder.build(capture, request=ObservationRequest.source_screen_retry(screen))
                                       if path == "builder" else _perception(builder).build(capture, include_content=True))
                        self.assertEqual(observation.screen_type, screen)
                        self.assertEqual(observation.decision.layout_id, layout)
                        entries = observation.entries(ListEntryKind.ALLIANCE_MEMBER)
                        self.assertEqual(tuple(row.title_text for row in entries), names)
                        for row, top in zip(entries, tops):
                            self.assertEqual(row.metadata["action"], action)
                            self.assertTrue(bounds(640, top + 62, 220, 78).contains_point(row.action_point))
                            self.assertEqual(row.frame_ref, capture.frame_ref)
                            self.assertEqual(row.source_layout_id, layout)
                        self.assertTrue(backend.calls)
                        self.assertNotIn(Bounds(0, 0, *size), backend.calls)

    def test_manage_rows_associate_exact_names_with_manage_buttons(self) -> None:
        """Manage cards start below the officer banner and exclude the clipped card."""

        image = _load_fixture("alliance_member_manage_rows.png")
        names = ("Member One", "Member Two", "Member Three", "Member Four")
        context, backend = _make_context(image, action="manage", names=names)
        entries = parse_alliance_member_rows(
            image=image,
            screen_type=ScreenType.PNC_ALLIANCE_MEMBER_LIST,
            layout_id=MANAGE_LAYOUT,
            ocr_context=context,
        )

        self.assertEqual(len(entries), 4)
        self.assertEqual(tuple(entry.title_text for entry in entries), names)
        self.assertTrue(all(entry.row_status == RowRecognitionStatus.COMPLETE for entry in entries))
        self.assertTrue(all(entry.metadata["action"] == "manage" for entry in entries))
        self.assertTrue(all(entry.bounds.y >= 560 for entry in entries))
        self.assertTrue(all(entry.action_point is not None for entry in entries))
        self.assertTrue(all(entry.bounds.contains_bounds(entry.action_bounds) for entry in entries))
        self.assertTrue(all(entry.frame_ref == context.frame_ref for entry in entries))
        self.assertTrue(all(entry.source_screen == ScreenType.PNC_ALLIANCE_MEMBER_LIST for entry in entries))
        self.assertTrue(all(entry.source_layout_id == MANAGE_LAYOUT for entry in entries))
        self.assertTrue(all(region is not None for region in backend.calls))
        self.assertTrue(all(region != Bounds(0, 0, image.width, image.height) for region in backend.calls))

    def test_reinforce_rows_use_reinforce_and_never_manage_actions(self) -> None:
        """Hall rows begin at the captured 185px body position and have their own action."""

        image = _load_fixture("alliance_member_reinforce_rows.png")
        names = tuple(f"Member {index}" for index in range(1, 7))
        context, _backend = _make_context(image, action="reinforce", names=names)
        entries = parse_alliance_member_rows(
            image=image,
            screen_type=ScreenType.PNC_ALLIANCE_MEMBER_REINFORCE,
            layout_id=REINFORCE_LAYOUT,
            ocr_context=context,
        )

        self.assertEqual(len(entries), 6)
        self.assertEqual(tuple(entry.title_text for entry in entries), names)
        self.assertTrue(all(entry.metadata["action"] == "reinforce" for entry in entries))
        self.assertTrue(all(entry.bounds.y >= 185 for entry in entries))
        self.assertTrue(all(entry.action_point is not None for entry in entries))
        self.assertTrue(all(entry.action_bounds is not None for entry in entries))

    def test_missing_button_has_no_synthetic_action_point(self) -> None:
        """A visible card remains observable while a missing blue button abstains."""

        image = _load_fixture("alliance_member_manage_rows.png")
        rows = detect_alliance_member_row_bounds(
            image=image,
            screen_type=ScreenType.PNC_ALLIANCE_MEMBER_LIST,
            layout_id=MANAGE_LAYOUT,
        )
        removed = image.copy()
        draw = ImageDraw.Draw(removed)
        row = rows[1]
        draw.rectangle((row.x + 620, row.y + 50, row.x + row.width - 1, row.y + 150), fill=(28, 42, 72))
        names = ("Member One", "Member Two", "Member Three", "Member Four")
        context, _backend = _make_context(removed, action="manage", names=names)
        entries = parse_alliance_member_rows(
            image=removed,
            screen_type=ScreenType.PNC_ALLIANCE_MEMBER_LIST,
            layout_id=MANAGE_LAYOUT,
            ocr_context=context,
        )

        self.assertEqual(len(entries), 4)
        self.assertIsNone(entries[1].action_point)
        self.assertIsNone(entries[1].action_bounds)
        self.assertEqual(entries[1].row_status, RowRecognitionStatus.NO_ACTION)
        self.assertEqual(entries[1].metadata["unresolved_reason"], "missing_button")
        self.assertTrue(all(entry.action_point is not None for entry in (entries[0], entries[2], entries[3])))

    def test_displaced_card_is_rejected_when_nominal_slot_keeps_generic_blue_surface(self) -> None:
        """A shifted card cannot borrow the old slot's surface or row geometry."""

        image = _load_fixture("alliance_member_manage_rows.png")
        original_rows = detect_alliance_member_row_bounds(
            image=image,
            screen_type=ScreenType.PNC_ALLIANCE_MEMBER_LIST,
            layout_id=MANAGE_LAYOUT,
        )
        first = original_rows[0]
        card = image.crop((first.x, first.y, first.x + first.width, first.y + first.height))
        moved = image.copy()
        draw = ImageDraw.Draw(moved)
        # Keep a generic blue surface through the old slot, but erase its
        # measured separators before moving the captured card by 20 pixels.
        draw.rectangle(
            (first.x, first.y - 3, first.x + first.width - 1, first.y + first.height + 3),
            fill=(25, 38, 65),
        )
        moved.paste(card, (first.x, first.y + 20))

        rows = detect_alliance_member_row_bounds(
            image=moved,
            screen_type=ScreenType.PNC_ALLIANCE_MEMBER_LIST,
            layout_id=MANAGE_LAYOUT,
        )

        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row.y != first.y for row in rows))
        self.assertNotIn(first.y, {row.y for row in rows})

    def test_partially_clipped_displaced_card_is_rejected(self) -> None:
        """A card moved below the viewport cannot become a complete row."""

        image = _load_fixture("alliance_member_manage_rows.png")
        original_rows = detect_alliance_member_row_bounds(
            image=image,
            screen_type=ScreenType.PNC_ALLIANCE_MEMBER_LIST,
            layout_id=MANAGE_LAYOUT,
        )
        first = original_rows[0]
        card = image.crop((first.x, first.y, first.x + first.width, first.y + first.height))
        moved = image.copy()
        draw = ImageDraw.Draw(moved)
        draw.rectangle(
            (first.x, first.y - 10, first.x + first.width - 1, first.y + first.height + 10),
            fill=(25, 38, 65),
        )
        moved.paste(card, (first.x, image.height - first.height // 2))

        rows = detect_alliance_member_row_bounds(
            image=moved,
            screen_type=ScreenType.PNC_ALLIANCE_MEMBER_LIST,
            layout_id=MANAGE_LAYOUT,
        )

        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row.y != first.y for row in rows))

    def test_missing_or_wrong_action_label_keeps_point_unknown(self) -> None:
        """A blue box alone cannot authorize a mode-incompatible action."""

        image = _load_fixture("alliance_member_reinforce_rows.png")
        names = tuple(f"Member {index}" for index in range(1, 7))
        context, _backend = _make_context(
            image,
            action="reinforce",
            names=names,
            missing_action_rows=frozenset({2}),
            wrong_action="Manage",
        )
        entries = parse_alliance_member_rows(
            image=image,
            screen_type=ScreenType.PNC_ALLIANCE_MEMBER_REINFORCE,
            layout_id=REINFORCE_LAYOUT,
            ocr_context=context,
        )

        self.assertEqual(len(entries), 6)
        self.assertTrue(all(entry.action_point is None for entry in entries))
        self.assertTrue(all(entry.row_status == RowRecognitionStatus.NO_ACTION for entry in entries))
        self.assertEqual(entries[2].metadata["unresolved_reason"], "missing_or_ambiguous_action")
        self.assertEqual(entries[0].metadata["unresolved_reason"], "wrong_action")

    def test_unproved_screen_layout_pair_abstains_without_ocr(self) -> None:
        """The parser never borrows actions from another Alliance list mode."""

        image = _load_fixture("alliance_member_manage_rows.png")
        context, backend = _make_context(
            image,
            action="manage",
            names=("Member One", "Member Two", "Member Three", "Member Four"),
        )
        entries = parse_alliance_member_rows(
            image=image,
            screen_type=ScreenType.PNC_ALLIANCE_MEMBER_REINFORCE,
            layout_id=MANAGE_LAYOUT,
            ocr_context=context,
        )

        self.assertEqual(entries, ())
        self.assertEqual(backend.calls, [])

    def test_real_rapidocr_replay_associates_current_rows(self) -> None:
        """Replay the saved raw captures when RapidOCR and ignored artifacts exist."""

        cases = (
            (
                "0156_alliance_member_list.png",
                ScreenType.PNC_ALLIANCE_MEMBER_LIST,
                MANAGE_LAYOUT,
                4,
            ),
            (
                "0182_alliance_hall_reinforce_members.png",
                ScreenType.PNC_ALLIANCE_MEMBER_REINFORCE,
                REINFORCE_LAYOUT,
                6,
            ),
        )
        try:
            ocr = RapidOcrService()
        except Exception as exc:  # pragma: no cover - environment-dependent optional evidence
            raise unittest.SkipTest(f"RapidOCR replay unavailable: {exc}") from exc
        for file_name, screen, layout, expected_count in cases:
            raw_path = RAW_ROOT / file_name
            if not raw_path.exists():
                raise unittest.SkipTest(f"saved raw Alliance capture unavailable: {raw_path}")
            with self.subTest(capture=file_name):
                with Image.open(raw_path) as source:
                    image = source.convert("RGB")
                context = ObservationOcrContext(image, ocr, _frame_ref(f"rapid:{file_name}"), "rapidocr-captured")
                context.require_bounded_regions()
                entries = parse_alliance_member_rows(
                    image=image,
                    screen_type=screen,
                    layout_id=layout,
                    ocr_context=context,
                )
                self.assertEqual(len(entries), expected_count)
                self.assertTrue(all(entry.title_text for entry in entries))
                self.assertTrue(all(entry.action_point is not None for entry in entries))
                self.assertTrue(all(entry.action_bounds is not None for entry in entries))
                self.assertTrue(all(entry.bounds.contains_bounds(entry.action_bounds) for entry in entries))
                expected_action = (
                    "manage"
                    if screen == ScreenType.PNC_ALLIANCE_MEMBER_LIST
                    else "reinforce"
                )
                self.assertTrue(
                    all(entry.metadata["action"] == expected_action for entry in entries)
                )
                self.assertTrue(all(entry.frame_ref == context.frame_ref for entry in entries))
                for entry in entries:
                    source_regions = entry.metadata["source_region_bounds"]
                    self.assertTrue(entry.bounds.contains_bounds(source_regions["name"]))
                    self.assertTrue(entry.bounds.contains_bounds(source_regions["action"]))


if __name__ == "__main__":
    unittest.main()
