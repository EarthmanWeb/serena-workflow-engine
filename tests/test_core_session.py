"""Tests for swe_hooks.core.session.

Covers session ID extraction, project-root walking, working-memory session
matching, and the get_session_context aggregator.

Pure functions are exercised directly. IO functions receive tmpdir paths or
have session.get_project_root monkeypatched to a tmpdir. All tests are
deterministic and offline (no network, no real Serena, no real git server —
only a tmpdir .git directory we create ourselves).
"""
import os
import sys
import time
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_core, reset_caches  # noqa: E402

session = import_core("swe_hooks.core.session")


class ExtractSessionIdTests(unittest.TestCase):
    def test_valid_uuid_path_returns_first_8_chars(self):
        path = "/Users/x/.claude/projects/foo/00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl"
        self.assertEqual(session.extract_session_id(path), "00893aaf")

    def test_uuid_anywhere_in_string(self):
        # regex searches, so the UUID need not be the basename
        path = "prefix-11112222-3333-4444-5555-666677778888-suffix"
        self.assertEqual(session.extract_session_id(path), "11112222")

    def test_no_uuid_returns_none(self):
        self.assertIsNone(session.extract_session_id("/no/uuid/here.jsonl"))

    def test_uppercase_hex_not_matched(self):
        # regex is lowercase hex only ([a-f0-9]); uppercase must NOT match
        path = "/x/ABCDEF12-19FA-41D2-8238-13269B9B3CA0.jsonl"
        self.assertIsNone(session.extract_session_id(path))

    def test_empty_string_returns_none(self):
        self.assertIsNone(session.extract_session_id(""))

    def test_none_returns_none(self):
        self.assertIsNone(session.extract_session_id(None))

    def test_returns_exactly_8_chars(self):
        path = "abcdef01-2345-6789-abcd-ef0123456789.jsonl"
        result = session.extract_session_id(path)
        self.assertEqual(len(result), 8)
        self.assertEqual(result, "abcdef01")


class FindProjectRootTests(unittest.TestCase):
    def test_finds_git_at_start_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.realpath(tmp)
            os.mkdir(os.path.join(root, ".git"))
            self.assertEqual(session.find_project_root(root), root)

    def test_finds_git_walking_up_from_nested_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.realpath(tmp)
            os.mkdir(os.path.join(root, ".git"))
            nested = os.path.join(root, "a", "b", "c")
            os.makedirs(nested)
            self.assertEqual(session.find_project_root(nested), root)

    def test_no_git_returns_start_dir(self):
        # When no .git is found while walking to filesystem root, the
        # function returns the ORIGINAL start_dir argument (not abspath).
        with tempfile.TemporaryDirectory() as tmp:
            nested = os.path.join(tmp, "x", "y")
            os.makedirs(nested)
            self.assertEqual(session.find_project_root(nested), nested)

    def test_git_must_be_a_directory_not_a_file(self):
        # A .git FILE (as in git worktrees) is not an isdir match; walk continues.
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.realpath(tmp)
            # real .git dir at root
            os.mkdir(os.path.join(root, ".git"))
            child = os.path.join(root, "child")
            os.makedirs(child)
            # a .git FILE inside child should be ignored -> resolves to root
            with open(os.path.join(child, ".git"), "w") as f:
                f.write("gitdir: ../.git")
            self.assertEqual(session.find_project_root(child), root)


class ValidateWorkingMemorySessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, content=""):
        path = os.path.join(self.dir, name)
        with open(path, "w") as f:
            f.write(content)
        return path

    def test_session_id_in_filename_matches(self):
        path = self._write("WM_abcd1234.md", "no session field here")
        self.assertTrue(session.validate_working_memory_session(path, "abcd1234"))

    def test_session_id_in_content_matches(self):
        path = self._write("WM_other.md", "header\n**Session ID**: abcd1234\nbody")
        self.assertTrue(session.validate_working_memory_session(path, "abcd1234"))

    def test_content_session_must_match_exactly(self):
        # content has a DIFFERENT session id -> no match, and it is not in name
        path = self._write("WM_other.md", "**Session ID**: zzzz9999")
        self.assertFalse(session.validate_working_memory_session(path, "abcd1234"))

    def test_neither_name_nor_content_returns_false(self):
        path = self._write("WM_nomatch.md", "just some notes, no session marker")
        self.assertFalse(session.validate_working_memory_session(path, "abcd1234"))

    def test_no_session_id_returns_true(self):
        # session_id falsy -> nothing to validate -> True
        path = self._write("WM_anything.md", "content")
        self.assertTrue(session.validate_working_memory_session(path, None))
        self.assertTrue(session.validate_working_memory_session(path, ""))

    def test_nonexistent_file_returns_false(self):
        missing = os.path.join(self.dir, "does_not_exist.md")
        self.assertFalse(session.validate_working_memory_session(missing, "abcd1234"))

    def test_empty_filepath_returns_false(self):
        self.assertFalse(session.validate_working_memory_session("", "abcd1234"))
        self.assertFalse(session.validate_working_memory_session(None, "abcd1234"))

    def test_only_first_2000_bytes_of_content_checked(self):
        # Session marker placed AFTER 2000 bytes must NOT be found via content,
        # and since it's not in the filename either, result is False.
        padding = "x" * 2100
        path = self._write("WM_pad.md", padding + "\n**Session ID**: abcd1234")
        self.assertFalse(session.validate_working_memory_session(path, "abcd1234"))


class GetSerenaMemoriesDirTests(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self._orig_root = session.get_project_root

    def tearDown(self):
        session.get_project_root = self._orig_root
        reset_caches()

    def test_builds_path_from_project_root(self):
        session.get_project_root = lambda: "/fake/root"
        self.assertEqual(
            session.get_serena_memories_dir(),
            os.path.join("/fake/root", ".serena", "memories"),
        )

    def test_cwd_argument_is_ignored(self):
        session.get_project_root = lambda: "/fake/root"
        # cwd arg is documented as ignored; result identical regardless of value
        a = session.get_serena_memories_dir("/some/cwd")
        b = session.get_serena_memories_dir(None)
        self.assertEqual(a, b)
        self.assertEqual(a, os.path.join("/fake/root", ".serena", "memories"))


class FindWorkingMemoryForSessionTests(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self._orig_root = session.get_project_root
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.mem_dir = os.path.join(self.root, ".serena", "memories")
        os.makedirs(self.mem_dir)
        session.get_project_root = lambda: self.root

    def tearDown(self):
        session.get_project_root = self._orig_root
        self.tmp.cleanup()
        reset_caches()

    def _write_wm(self, name, content="wm"):
        path = os.path.join(self.mem_dir, name)
        with open(path, "w") as f:
            f.write(content)
        return path

    def test_finds_wm_file_for_session(self):
        path = self._write_wm("WM_abcd1234.md")
        result = session.find_working_memory_for_session(self.root, "abcd1234")
        self.assertEqual(result, path)

    def test_returns_none_when_no_matching_file(self):
        self._write_wm("WM_other999.md")
        result = session.find_working_memory_for_session(self.root, "abcd1234")
        self.assertIsNone(result)

    def test_returns_none_when_session_id_falsy(self):
        self._write_wm("WM_abcd1234.md")
        self.assertIsNone(session.find_working_memory_for_session(self.root, None))
        self.assertIsNone(session.find_working_memory_for_session(self.root, ""))

    def test_returns_none_when_memories_dir_missing(self):
        # Point project root at a dir with no .serena/memories
        empty = tempfile.TemporaryDirectory()
        try:
            session.get_project_root = lambda: empty.name
            self.assertIsNone(
                session.find_working_memory_for_session(empty.name, "abcd1234")
            )
        finally:
            empty.cleanup()

    def test_glob_pattern_is_exact_wm_name(self):
        # A file merely CONTAINING the session id but not matching WM_<id>.md
        # must not be returned (glob pattern is exact).
        self._write_wm("NOTE_abcd1234.md")
        self.assertIsNone(
            session.find_working_memory_for_session(self.root, "abcd1234")
        )

    def test_returns_newest_when_pattern_matches_single_file(self):
        # The glob pattern WM_<id>.md matches at most one filename, but the
        # code uses max(...by mtime). Verify the returned path is that file
        # with a controlled, most-recent mtime.
        path = self._write_wm("WM_abcd1234.md")
        newer = time.time() + 100
        os.utime(path, (newer, newer))
        result = session.find_working_memory_for_session(self.root, "abcd1234")
        self.assertEqual(result, path)


class GetSessionContextTests(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self._orig_root = session.get_project_root
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.mem_dir = os.path.join(self.root, ".serena", "memories")
        os.makedirs(self.mem_dir)
        session.get_project_root = lambda: self.root

    def tearDown(self):
        session.get_project_root = self._orig_root
        self.tmp.cleanup()
        reset_caches()

    def _write_wm(self, name, content="wm"):
        path = os.path.join(self.mem_dir, name)
        with open(path, "w") as f:
            f.write(content)
        return path

    def test_returns_session_id_and_wm_path(self):
        wm_path = self._write_wm("WM_00893aaf.md")
        input_data = {
            "transcript_path": "/x/00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl"
        }
        sid, wm = session.get_session_context(input_data, self.root)
        self.assertEqual(sid, "00893aaf")
        self.assertEqual(wm, wm_path)

    def test_session_id_without_wm_file(self):
        # Valid transcript -> session id extracted, but no WM file present
        input_data = {
            "transcript_path": "/x/00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl"
        }
        sid, wm = session.get_session_context(input_data, self.root)
        self.assertEqual(sid, "00893aaf")
        self.assertIsNone(wm)

    def test_missing_transcript_path_yields_none_none(self):
        sid, wm = session.get_session_context({}, self.root)
        self.assertIsNone(sid)
        self.assertIsNone(wm)

    def test_transcript_without_uuid_yields_none_none(self):
        input_data = {"transcript_path": "/no/uuid/here.jsonl"}
        sid, wm = session.get_session_context(input_data, self.root)
        self.assertIsNone(sid)
        self.assertIsNone(wm)

    def test_returns_tuple_of_length_two(self):
        result = session.get_session_context({}, self.root)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
