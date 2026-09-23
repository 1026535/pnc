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
        self.assertIn("Read(pnc_automation/**)", allow)
        self.assertIn("Read(.local-data/**)", allow)
        self.assertIn("Exec(git log)", allow)
        self.assertIn("Exec(rg)", allow)
        self.assertIn("Exec(git push)", deny)
        self.assertIn("Exec(git commit)", deny)
        self.assertIn("Exec(rm)", deny)
        self.assertIn("Exec(adb)", deny)

    def test_no_blanket_read_or_wildcard_exec(self) -> None:
        """P1: unrestricted Read(**)/Exec(*) reopens local config and code exec."""
        allow = set(consult.consultant_config()["permissions"]["allow"])
        self.assertNotIn("Read(**)", allow)
        for rule in allow:
            self.assertNotIn(rule, ("Exec(*)", "Exec(**)", "Exec()"))

    def test_no_exec_capable_command_is_allowed(self) -> None:
        """P1: no interpreter, shell, or exec/write-capable tool is auto-approved."""
        # Commands that run arbitrary code or write files despite looking like
        # readers: interpreters/shells execute anything; find -exec/-delete and
        # sort -o mutate; echo's only use is shell redirection probes.
        exec_capable = {
            "python", "py", "python3", "pythonw", "pyw", "node", "deno",
            "bash", "sh", "zsh", "fish", "cmd", "powershell", "pwsh",
            "perl", "ruby", "lua", "find", "sort", "echo", "xargs",
        }
        allow = consult.consultant_config()["permissions"]["allow"]
        for rule in allow:
            if not rule.startswith("Exec("):
                continue
            command = rule[len("Exec("):-1].split(" ", 1)[0]
            self.assertNotIn(command, exec_capable, f"{rule} escapes the read-only boundary")

    def test_interpreters_and_exec_capable_tools_are_denied(self) -> None:
        deny = set(consult.consultant_config()["permissions"]["deny"])
        for rule in (
            "Exec(python)", "Exec(py)", "Exec(node)", "Exec(bash)", "Exec(sh)",
            "Exec(cmd)", "Exec(powershell)", "Exec(pwsh)", "Exec(find)",
            "Exec(sort)",
        ):
            self.assertIn(rule, deny)

    def test_sensitive_read_paths_are_denied(self) -> None:
        """P1: ignored local config, account data, and credentials stay unreadable."""
        deny = set(consult.consultant_config()["permissions"]["deny"])
        for rule in (
            "Read(config/**)",
            "Read(**/config/*.yaml)",
            "Read(**/config/*.yml)",
            "Read(**/accounts*.yaml)",
            "Read(**/accounts*.yml)",
            "Read(**/.env)",
            "Read(**/*.env)",
            "Read(**/*.key)",
            "Read(**/*.pem)",
            "Read(.git)",
            "Read(.git/**)",
        ):
            self.assertIn(rule, deny)

    def test_allowed_reads_stay_path_scoped(self) -> None:
        """Every allowed Read rule names a path scope, never an unrestricted glob."""
        allow = consult.consultant_config()["permissions"]["allow"]
        for rule in allow:
            if rule.startswith("Read("):
                self.assertNotEqual(rule, "Read(**)")
                self.assertTrue(
                    rule.endswith("/**)") or "*" in rule[len("Read("):-1],
                    f"{rule} is not path-scoped",
                )

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
