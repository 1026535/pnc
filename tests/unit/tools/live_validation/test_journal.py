"""Logical attempt journal persistence tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.live_validation.evidence import frame_ref_dict
from tools.live_validation.journal import (
    AttemptStatus,
    LogicalAttemptJournal,
    pending_attempts,
    read_journal,
)

from tests.unit.tools.live_validation.helpers import frame_ref


class LogicalAttemptJournalTests(unittest.TestCase):
    def test_begin_finish_rows_persist_and_close_the_attempt(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "attempts.jsonl"
            journal = LogicalAttemptJournal(path)
            attempt_id, consumed = journal.begin(
                case_id="v44_bank_return_home",
                control_name="return_home",
                operation_id="enter_building_body_for_discovery",
                number=1,
                limit=2,
                source_frame=frame_ref_dict(frame_ref()),
            )
            journal.finish(
                attempt_id,
                status=AttemptStatus.DISPATCHED,
                dispatch_event_id="in-0007",
            )
            journal.close()

            entries = read_journal(path)
            self.assertEqual(("attempt_begin", "attempt_finish"), tuple(e.record_type for e in entries))
            begin = entries[0]
            self.assertEqual("attempt-0001", begin.attempt_id)
            self.assertEqual("v44_bank_return_home", begin.payload["case_id"])
            self.assertEqual(1, begin.payload["number"])
            self.assertEqual(2, begin.payload["limit"])
            self.assertEqual("sess-test", begin.payload["source_frame"]["session_id"])
            self.assertEqual("attempts.jsonl#1", consumed.journal_ref)
            finish = entries[1]
            self.assertEqual("dispatched", finish.payload["status"])
            self.assertEqual("in-0007", finish.payload["dispatch_event_id"])
            self.assertEqual((), pending_attempts(path))

    def test_pending_attempts_lists_begun_unfinished_rows(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "attempts.jsonl"
            journal = LogicalAttemptJournal(path)
            first, _ = journal.begin(
                case_id="c1", control_name="x", operation_id="op",
                number=1, limit=1, source_frame={},
            )
            second, _ = journal.begin(
                case_id="c1", control_name="x", operation_id="op",
                number=2, limit=2, source_frame={},
            )
            journal.finish(first, status=AttemptStatus.REFUSED, detail="no")
            journal.close()

            pending = pending_attempts(path)
            self.assertEqual(1, len(pending))
            self.assertEqual(second, pending[0].attempt_id)
            self.assertEqual(2, pending[0].number)

    def test_reopening_continues_the_sequence(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "attempts.jsonl"
            journal = LogicalAttemptJournal(path)
            first, _ = journal.begin(
                case_id="c1", control_name="x", operation_id="op",
                number=1, limit=1, source_frame={},
            )
            journal.close()
            journal = LogicalAttemptJournal(path)
            second, _ = journal.begin(
                case_id="c1", control_name="x", operation_id="op",
                number=1, limit=1, source_frame={},
            )
            journal.close()
            self.assertNotEqual(first, second)
            self.assertEqual(2, len(read_journal(path)))


if __name__ == "__main__":
    unittest.main()
