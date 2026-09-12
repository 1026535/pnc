"""Git snapshot tests exercise real, isolated repositories without user config."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.test_selection.git_changes import (
    base_revision,
    changed_paths,
    python_snapshot,
    resolve,
    working_paths,
)


class GitChangesTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="selection-git-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.git("init", "--quiet", "-b", "fixture")
        for key, value in (
            ("user.name", "Offline Fixture"), ("user.email", "fixture@example.invalid"),
            ("commit.gpgSign", "false"), ("core.autocrlf", "false"),
            ("core.hooksPath", str(self.root / ".git" / "disabled-hooks")),
            ("core.excludesFile", str(self.root / ".git" / "empty-excludes")),
        ):
            self.git("config", "--local", key, value)
        self.write("pkg/alpha.py", "VALUE = 'base alpha'\n")
        self.write("pkg/beta.py", "VALUE = 'base beta'\n")
        self.write("docs/notes.md", "base docs\n")
        self.write(".gitignore", "ignored/\n")
        self.commit("baseline")
        self.base = resolve(self.root, "HEAD")

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.root), *args], capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=20, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def write(self, path: str, source: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8", newline="\n")

    def commit(self, message: str) -> None:
        self.git("add", "--all")
        self.git("commit", "--quiet", "-m", message)

    def test_clean_repository_has_no_changes(self) -> None:
        self.assertEqual(changed_paths(self.root, self.base), [])

    def test_staged_modification(self) -> None:
        self.write("pkg/alpha.py", "VALUE = 'staged'\n")
        self.git("add", "pkg/alpha.py")
        self.assertEqual(changed_paths(self.root, self.base), ["pkg/alpha.py"])

    def test_unstaged_modification(self) -> None:
        self.write("pkg/alpha.py", "VALUE = 'unstaged'\n")
        self.assertEqual(changed_paths(self.root, self.base), ["pkg/alpha.py"])

    def test_untracked_files_are_included_but_ignored_files_are_not(self) -> None:
        self.write("pkg/new.py", "VALUE = 1\n")
        self.write("assets/new.json", "{}")
        self.write("ignored/private.py", "raise RuntimeError('must stay excluded')")
        self.assertEqual(changed_paths(self.root, self.base), ["assets/new.json", "pkg/new.py"])
        self.assertNotIn("ignored/private.py", working_paths(self.root))

    def test_mixed_index_worktree_and_untracked_paths_are_sorted_unique(self) -> None:
        self.write("pkg/alpha.py", "VALUE = 'index'\n")
        self.git("add", "pkg/alpha.py")
        self.write("pkg/alpha.py", "VALUE = 'worktree'\n")
        self.write("pkg/beta.py", "VALUE = 'unstaged'\n")
        self.write("pkg/new.py", "VALUE = 'new'\n")
        self.assertEqual(changed_paths(self.root, self.base), ["pkg/alpha.py", "pkg/beta.py", "pkg/new.py"])

    def test_staged_addition(self) -> None:
        self.write("pkg/new.py", "VALUE = 'new'\n")
        self.git("add", "pkg/new.py")
        self.assertEqual(changed_paths(self.root, self.base), ["pkg/new.py"])

    def test_staged_rename_includes_both_endpoints(self) -> None:
        self.git("mv", "pkg/alpha.py", "pkg/renamed.py")
        self.assertEqual(changed_paths(self.root, self.base), ["pkg/alpha.py", "pkg/renamed.py"])

    def test_unstaged_rename_includes_deleted_and_untracked_endpoints(self) -> None:
        (self.root / "pkg/alpha.py").rename(self.root / "pkg/renamed.py")
        self.assertEqual(changed_paths(self.root, self.base), ["pkg/alpha.py", "pkg/renamed.py"])

    def test_staged_delete_is_in_diff_but_absent_from_working_inventory(self) -> None:
        self.git("rm", "pkg/alpha.py")
        self.assertEqual(changed_paths(self.root, self.base), ["pkg/alpha.py"])
        self.assertNotIn("pkg/alpha.py", working_paths(self.root))

    def test_unstaged_delete_is_in_diff_but_absent_from_working_inventory(self) -> None:
        (self.root / "pkg/alpha.py").unlink()
        self.assertEqual(changed_paths(self.root, self.base), ["pkg/alpha.py"])
        self.assertNotIn("pkg/alpha.py", working_paths(self.root))

    def test_spaces_unicode_and_leading_dash_paths_survive_git_parsing(self) -> None:
        for path in ("pkg/space name.py", "pkg/café.py", "-option.py"):
            self.write(path, "VALUE = 1\n")
        self.commit("unusual paths")
        unusual_base = resolve(self.root, "HEAD")
        self.git("mv", "pkg/space name.py", "pkg/renamed space.py")
        self.write("pkg/café.py", "VALUE = 2\n")
        self.write("-option.py", "VALUE = 3\n")
        self.assertEqual(changed_paths(self.root, unusual_base), ["-option.py", "pkg/café.py", "pkg/renamed space.py", "pkg/space name.py"])
        snapshot = python_snapshot(self.root, unusual_base)
        self.assertEqual(snapshot["pkg/space name.py"], "VALUE = 1\n")
        self.assertEqual(snapshot["pkg/café.py"], "VALUE = 1\n")

    def test_committed_changes_since_explicit_base_are_included(self) -> None:
        self.write("pkg/alpha.py", "VALUE = 'committed'\n")
        self.commit("candidate")
        self.assertEqual(changed_paths(self.root, self.base), ["pkg/alpha.py"])

    def test_snapshots_retain_deleted_base_and_current_worktree_over_index(self) -> None:
        self.write("pkg/alpha.py", "VALUE = 'index'\n")
        self.git("add", "pkg/alpha.py")
        self.write("pkg/alpha.py", "VALUE = 'worktree'\n")
        (self.root / "pkg/beta.py").unlink()
        self.write("pkg/new.py", "raise RuntimeError('snapshot must not execute')\n")
        self.assertEqual(python_snapshot(self.root, self.base), {
            "pkg/alpha.py": "VALUE = 'base alpha'\n", "pkg/beta.py": "VALUE = 'base beta'\n",
        })
        self.assertEqual(python_snapshot(self.root, None), {
            "pkg/alpha.py": "VALUE = 'worktree'\n",
            "pkg/new.py": "raise RuntimeError('snapshot must not execute')\n",
        })

    def test_bom_sources_decode_in_both_snapshots(self) -> None:
        self.write("pkg/bom.py", "\ufeffVALUE = 'café'\n")
        self.commit("BOM")
        for revision in (resolve(self.root, "HEAD"), None):
            with self.subTest(revision=revision):
                self.assertEqual(python_snapshot(self.root, revision)["pkg/bom.py"], "VALUE = 'café'\n")

    def test_empty_python_snapshot(self) -> None:
        self.git("rm", "pkg/alpha.py", "pkg/beta.py")
        self.commit("only documentation remains")
        self.assertEqual(python_snapshot(self.root, "HEAD"), {})
        self.assertEqual(python_snapshot(self.root, None), {})

    def test_committed_crlf_and_worktree_source_normalize_identically(self) -> None:
        (self.root / "pkg/alpha.py").write_bytes(b"VALUE = 'windows'\r\n# next line\r\n")
        self.commit("literal CRLF blob")
        expected = "VALUE = 'windows'\n# next line\n"
        self.assertEqual(python_snapshot(self.root, "HEAD")["pkg/alpha.py"], expected)
        self.assertEqual(python_snapshot(self.root, None)["pkg/alpha.py"], expected)

    def test_analysis_does_not_change_head_index_or_worktree(self) -> None:
        self.write("pkg/alpha.py", "VALUE = 'index'\n")
        self.git("add", "pkg/alpha.py")
        self.write("pkg/alpha.py", "VALUE = 'working'\n")
        self.write("new.txt", "new\n")
        before = (self.git("status", "--porcelain=v1"), self.git("diff"), self.git("diff", "--cached"))
        changed_paths(self.root, self.base)
        working_paths(self.root)
        python_snapshot(self.root, self.base)
        python_snapshot(self.root, None)
        self.assertEqual(resolve(self.root, "HEAD"), self.base)
        self.assertEqual(before, (self.git("status", "--porcelain=v1"), self.git("diff"), self.git("diff", "--cached")))

    def test_explicit_base_needs_no_upstream(self) -> None:
        self.assertEqual(base_revision(self.root, "HEAD"), self.base)
        self.assertEqual(base_revision(self.root, self.base), self.base)

    def test_missing_upstream_and_invalid_refs_fail_actionably(self) -> None:
        with self.assertRaisesRegex(ValueError, "Git command failed"):
            base_revision(self.root, None)
        for ref in ("not-a-revision", "--help", "HEAD:pkg/alpha.py"):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                resolve(self.root, ref)

    def test_default_base_uses_merge_base_not_diverged_upstream_tip(self) -> None:
        self.git("branch", "upstream-fixture")
        self.write("candidate.txt", "candidate\n")
        self.commit("candidate branch")
        self.git("checkout", "--quiet", "upstream-fixture")
        self.write("upstream.txt", "upstream\n")
        self.commit("upstream branch")
        self.git("checkout", "--quiet", "fixture")
        self.git("config", "branch.fixture.remote", ".")
        self.git("config", "branch.fixture.merge", "refs/heads/upstream-fixture")
        self.assertNotEqual(resolve(self.root, "upstream-fixture"), self.base)
        self.assertEqual(base_revision(self.root, None), self.base)

    def test_historical_control_character_paths_cannot_inject_batch_requests(self) -> None:
        # Construct a tree without checking it out, so Windows also exercises
        # historical paths containing characters its filesystem cannot create.
        original_a = b"VALUE = 'original alpha'\n"
        original_b = b"VALUE = 'original beta'\n"
        unusual = b"VALUE = 'unusual path'\n"
        entries = {
            "a.py": original_a,
            "a.py\nHEAD:b.py": unusual,
            "b.py": original_b,
            "tab\tand\rcaf\u00e9.py": b"# utf-8\nVALUE = 'caf\xc3\xa9'\n",
        }
        tree_input = bytearray()
        for path, contents in entries.items():
            blob = subprocess.run(
                ["git", "-C", str(self.root), "hash-object", "-w", "--stdin"],
                input=contents, capture_output=True, check=True, timeout=20,
            ).stdout.strip()
            tree_input.extend(b"100644 blob " + blob + b"\t" + path.encode() + b"\0")
        tree = subprocess.run(
            ["git", "-C", str(self.root), "mktree", "-z"],
            input=bytes(tree_input), capture_output=True, check=True, timeout=20,
        ).stdout.decode().strip()
        self.write("b.py", "VALUE = 'candidate beta'\n")
        self.commit("candidate differs from historical tree")
        self.assertEqual(
            python_snapshot(self.root, tree),
            {path: contents.decode() for path, contents in entries.items()},
        )


class GitSnapshotFramingTests(unittest.TestCase):
    """Malformed batch responses must never become partial source snapshots."""

    OID = b"a" * 40
    OTHER_OID = b"b" * 40

    def snapshot(self, tree: bytes, response: bytes, returncode: int = 0) -> dict[str, str]:
        completed = subprocess.CompletedProcess([], returncode, response, b"")
        with patch("tools.test_selection.git_changes.git", return_value=tree), patch(
            "tools.test_selection.git_changes.subprocess.run", return_value=completed
        ):
            return python_snapshot(Path("unused-offline-repository"), "base")

    def tree(self, oid: bytes | None = None) -> bytes:
        return b"100644 blob " + (oid or self.OID) + b"\tsource.py\0"

    def block(self, source: bytes, oid: bytes | None = None) -> bytes:
        return (oid or self.OID) + b" blob " + str(len(source)).encode() + b"\n" + source + b"\n"

    def test_batch_contains_only_full_object_ids_for_both_hash_formats(self) -> None:
        for size in (40, 64):
            with self.subTest(oid_size=size):
                oid = b"a" * size
                tree = b"100644 blob " + oid + b"\ta.py\nHEAD:b.py\0"
                completed = subprocess.CompletedProcess([], 0, self.block(b"pass\n", oid), b"")
                with patch("tools.test_selection.git_changes.git", return_value=tree), patch(
                    "tools.test_selection.git_changes.subprocess.run", return_value=completed
                ) as run:
                    result = python_snapshot(Path("unused"), "base")
                self.assertEqual(result, {"a.py\nHEAD:b.py": "pass\n"})
                self.assertEqual(run.call_args.kwargs["input"], oid + b"\n")

    def test_rejects_wrong_missing_or_malformed_blob_headers(self) -> None:
        responses = (
            b"", self.OID + b" blob 1", self.OID + b" missing\n",
            self.block(b"x", self.OTHER_OID), self.OID + b" tree 1\nx\n",
            self.OID + b" blob -1\n\n", self.OID + b" blob +1\nx\n",
            self.OID + b" blob one\nx\n", self.OID + b" blob 1 extra\nx\n",
        )
        for response in responses:
            with self.subTest(response=response), self.assertRaises(ValueError):
                self.snapshot(self.tree(), response)

    def test_rejects_truncated_or_misframed_body_and_trailing_data(self) -> None:
        valid = self.block(b"pass\n")
        responses = (
            valid[:-1], valid[:-2], valid[:-1] + b"x",
            self.OID + b" blob 100\nx\n", valid + b"\n", valid + valid,
        )
        for response in responses:
            with self.subTest(response=response), self.assertRaises(ValueError):
                self.snapshot(self.tree(), response)

    def test_each_response_must_match_its_requested_oid(self) -> None:
        tree = self.tree() + b"100644 blob " + self.OTHER_OID + b"\tsecond.py\0"
        for response in (
            self.block(b"first\n"),
            self.block(b"second\n", self.OTHER_OID) + self.block(b"first\n"),
        ):
            with self.subTest(response=response), self.assertRaises(ValueError):
                self.snapshot(tree, response)
        self.assertEqual(
            self.snapshot(tree, self.block(b"first\n") + self.block(b"second\n", self.OTHER_OID)),
            {"source.py": "first\n", "second.py": "second\n"},
        )

    def test_body_uses_byte_size_and_normalizes_source_newlines(self) -> None:
        source = "\ufeff# caf\u00e9\r\nvalue = 1\rvalue = 2\n".encode()
        self.assertEqual(
            self.snapshot(self.tree(), self.block(source)),
            {"source.py": "# caf\u00e9\nvalue = 1\nvalue = 2\n"},
        )
        self.assertEqual(self.snapshot(self.tree(), self.block(b"")), {"source.py": ""})

    def test_nonzero_batch_exit_is_a_selection_analysis_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "batch failed"):
            self.snapshot(self.tree(), self.block(b"pass\n"), returncode=1)

    def test_rejects_malformed_tree_before_starting_batch(self) -> None:
        trees = (
            self.tree()[:-1], self.tree() + self.tree(),
            b"100644 blob a\tsource.py\0",
            b"100644 blob " + b"g" * 40 + b"\tsource.py\0",
            b"100644 blob " + self.OID + b"\nHEAD:b.py\tsource.py\0",
            b"100644 blob " + self.OID + b"\0",
            b"100644 blob " + self.OID + b"\t\0",
            b"040000 tree " + self.OID + b"\tsource.py\0",
        )
        for tree in trees:
            with self.subTest(tree=tree), patch(
                "tools.test_selection.git_changes.git", return_value=tree
            ), patch("tools.test_selection.git_changes.subprocess.run") as run:
                with self.assertRaises(ValueError):
                    python_snapshot(Path("unused"), "base")
                run.assert_not_called()
