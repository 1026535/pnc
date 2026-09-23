"""Exercise the consultation launcher's offline boundaries; no Devin process runs."""

import unittest

import consult_game_knowledge as consult


REJECTION = consult.TOOL_REJECTION_MARKER
MEMO = "Answer\nFindings\nAutomation implications\nNext smallest observation\nHandback: READY_FOR_REVIEW\n"


class ConsultationStatusTests(unittest.TestCase):
    """A clean exit alone is not a completed consultation."""

    def test_completed_requires_the_handback_memo(self) -> None:
        status, handback, rejected = consult.consultation_status(0, True, MEMO, "")
        self.assertEqual(status, "completed")
        self.assertEqual(handback, "READY_FOR_REVIEW")
        self.assertFalse(rejected)

    def test_headless_rejection_without_memo_is_incomplete(self) -> None:
        """The observed failure: exit 0, unchanged worktree, no memo."""
        status, handback, rejected = consult.consultation_status(
            0, True, "I'll trace the building upgrade path.\n", f"warning: {REJECTION}.\n"
        )
        self.assertEqual(status, "incomplete")
        self.assertIsNone(handback)
        self.assertTrue(rejected)

    def test_empty_response_is_incomplete(self) -> None:
        status, handback, _ = consult.consultation_status(0, True, "", "")
        self.assertEqual(status, "incomplete")
        self.assertIsNone(handback)

    def test_memo_after_a_recovered_rejection_stays_completed_but_flagged(self) -> None:
        status, _, rejected = consult.consultation_status(
            0, True, MEMO, f"warning: {REJECTION}.\n"
        )
        self.assertEqual(status, "completed")
        self.assertTrue(rejected)

    def test_needs_lead_is_a_completed_consultation(self) -> None:
        memo = MEMO.replace("READY_FOR_REVIEW", "NEEDS_LEAD")
        status, handback, _ = consult.consultation_status(0, True, memo, "")
        self.assertEqual(status, "completed")
        self.assertEqual(handback, "NEEDS_LEAD")

    def test_markdown_bold_handback_on_the_next_line_matches(self) -> None:
        """Observed memo shape: ``**Handback**`` header, token on a later line."""
        memo = "**Next smallest observation**\n\nNone.\n\n**Handback**\n\nREADY_FOR_REVIEW — clean.\n"
        status, handback, _ = consult.consultation_status(0, True, memo, "")
        self.assertEqual(status, "completed")
        self.assertEqual(handback, "READY_FOR_REVIEW")

    def test_nonzero_exit_and_worktree_changes_keep_their_status(self) -> None:
        self.assertEqual(consult.consultation_status(2, True, MEMO, "")[0], "failed")
        self.assertEqual(consult.consultation_status(0, False, MEMO, "")[0], "worktree-changed")


class ConsultantConfigTests(unittest.TestCase):
    """The run config grants read-only inspection and denies mutation verbs."""

    def test_permissions_shape(self) -> None:
        permissions = consult.consultant_config()["permissions"]
        allow = set(permissions["allow"])
        deny = set(permissions["deny"])
        self.assertIn("Read(**)", allow)
        self.assertIn("Exec(git log)", allow)
        self.assertIn("Exec(rg)", allow)
        self.assertIn("Exec(git push)", deny)
        self.assertIn("Exec(git commit)", deny)
        self.assertIn("Exec(rm)", deny)
        self.assertIn("Exec(adb)", deny)

    def test_no_mutation_verb_is_allowed(self) -> None:
        """Every allowed Exec rule names a read-only command form."""
        allow = consult.consultant_config()["permissions"]["allow"]
        for rule in allow:
            if rule.startswith("Exec(git "):
                verb = rule.removeprefix("Exec(git ")
                self.assertIn(
                    verb,
                    (
                        "status)", "log)", "show)", "diff)", "grep)", "blame)",
                        "ls-files)", "ls-tree)", "cat-file)", "rev-parse)",
                        "shortlog)", "describe)", "count-objects)",
                    ),
                )


if __name__ == "__main__":
    unittest.main()
