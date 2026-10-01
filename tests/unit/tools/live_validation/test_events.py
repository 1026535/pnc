"""Dispatch-attribution collector tests."""

from __future__ import annotations

import unittest

from pnc_automation.core.infra.emulator.input_dispatch import (
    InputDispatchFailure,
    InputDispatchRecord,
    TapDispatch,
)

from tools.live_validation.events import AttributionPhase, DispatchCollector

from tests.unit.tools.live_validation.helpers import frame_ref, home_observation, tap_receipt


class DispatchCollectorTests(unittest.TestCase):
    def test_case_phase_attributes_events_to_the_case(self):
        collector = DispatchCollector()
        source = home_observation()
        receipt = tap_receipt(source)
        with collector.phase(AttributionPhase.CASE, case_id="v44_bank_body_menu"):
            collector.append(receipt)
            mark = collector.mark()
            collector.append(
                InputDispatchFailure(
                    source_frame=source.frame_ref,
                    input_kind="tap",
                    failure_phase="send",
                    exception_type="RuntimeError",
                )
            )
        events = collector.events
        self.assertEqual("in-0001", events[0].event_id)
        self.assertEqual("in-0002", events[1].event_id)
        self.assertEqual("v44_bank_body_menu", events[0].case_id)
        self.assertIs(events[0].event, receipt)
        self.assertEqual(("in-0002",), tuple(e.event_id for e in collector.events_since(mark)))

    def test_non_case_events_carry_no_case_id(self):
        collector = DispatchCollector()
        receipt = InputDispatchRecord(
            source_frame=frame_ref(), dispatch=TapDispatch(point=(1, 1), input_sequence=0)
        )
        with collector.phase(AttributionPhase.SETUP):
            collector.append(receipt)
        self.assertIsNone(collector.events[0].case_id)
        self.assertIs(AttributionPhase.SETUP, collector.events[0].phase)

    def test_case_phase_requires_a_case_id(self):
        collector = DispatchCollector()
        with self.assertRaises(ValueError):
            with collector.phase(AttributionPhase.CASE):
                pass

    def test_receipt_event_id_matches_identity_within_the_case(self):
        collector = DispatchCollector()
        receipt = tap_receipt(home_observation())
        other = tap_receipt(home_observation())
        with collector.phase(AttributionPhase.CASE, case_id="v44_bank_body_menu"):
            collector.append(other)
            collector.append(receipt)
        self.assertEqual(
            "in-0002",
            collector.receipt_event_id(receipt, case_id="v44_bank_body_menu"),
        )
        self.assertIsNone(
            collector.receipt_event_id(receipt, case_id="v44_watchtower_body_menu")
        )


if __name__ == "__main__":
    unittest.main()
