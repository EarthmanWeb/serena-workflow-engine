"""Tests for pre/swe_pre_read_guard.py — large-code-file Read windowing gate.

Covers:
  is_code_file     — extension classification (.py .php .ts .tsx .js .jsx
                      .scss .css .go .rb .java vs everything else)
  count_lines      — line counting, -1 on unreadable path
  should_deny      — the DENY predicate: no offset/limit + code file +
                      > LARGE_FILE_LINES lines
  build_deny_message
  main()           — end-to-end stdin -> stdout JSON

Stdlib unittest only. Deterministic + offline; IO via tempfile.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_hook  # noqa: E402

guard_mod = import_hook("pre/swe_pre_read_guard")


def _write_lines(path, n):
    with open(path, "w") as f:
        for i in range(n):
            f.write(f"line {i}\n")


class TestIsCodeFile(unittest.TestCase):
    def test_recognized_extensions(self):
        for ext in ('.py', '.php', '.ts', '.tsx', '.js', '.jsx', '.scss',
                    '.css', '.go', '.rb', '.java'):
            self.assertTrue(guard_mod.is_code_file(f"/x/foo{ext}"), ext)

    def test_case_insensitive(self):
        self.assertTrue(guard_mod.is_code_file("/x/Foo.PY"))

    def test_unrecognized_extension(self):
        for ext in ('.md', '.json', '.txt', '.yaml', '.html'):
            self.assertFalse(guard_mod.is_code_file(f"/x/foo{ext}"), ext)

    def test_no_extension(self):
        self.assertFalse(guard_mod.is_code_file("/x/Makefile"))

    def test_empty_path(self):
        self.assertFalse(guard_mod.is_code_file(""))
        self.assertFalse(guard_mod.is_code_file(None))


class TestCountLines(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_counts_lines(self):
        path = os.path.join(self.tmp.name, "f.py")
        _write_lines(path, 42)
        self.assertEqual(guard_mod.count_lines(path), 42)

    def test_missing_file_returns_negative_one(self):
        self.assertEqual(
            guard_mod.count_lines(os.path.join(self.tmp.name, "nope.py")), -1)

    def test_empty_file_is_zero(self):
        path = os.path.join(self.tmp.name, "empty.py")
        open(path, "w").close()
        self.assertEqual(guard_mod.count_lines(path), 0)


class TestShouldDeny(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _big_code_file(self, ext='.py', lines=301):
        path = os.path.join(self.tmp.name, f"big{ext}")
        _write_lines(path, lines)
        return path

    def test_denies_full_read_of_large_code_file(self):
        path = self._big_code_file()
        self.assertTrue(guard_mod.should_deny({'file_path': path}))

    def test_allows_when_offset_given(self):
        path = self._big_code_file()
        self.assertFalse(
            guard_mod.should_deny({'file_path': path, 'offset': 100}))

    def test_allows_when_limit_given(self):
        path = self._big_code_file()
        self.assertFalse(
            guard_mod.should_deny({'file_path': path, 'limit': 80}))

    def test_allows_when_both_offset_and_limit_given(self):
        path = self._big_code_file()
        self.assertFalse(guard_mod.should_deny(
            {'file_path': path, 'offset': 10, 'limit': 80}))

    def test_allows_small_code_file(self):
        path = self._big_code_file(lines=300)
        self.assertFalse(guard_mod.should_deny({'file_path': path}))

    def test_allows_at_exactly_threshold(self):
        # LARGE_FILE_LINES is an exclusive threshold (> not >=).
        path = os.path.join(self.tmp.name, "exact.py")
        _write_lines(path, guard_mod.LARGE_FILE_LINES)
        self.assertFalse(guard_mod.should_deny({'file_path': path}))

    def test_denies_one_over_threshold(self):
        path = os.path.join(self.tmp.name, "over.py")
        _write_lines(path, guard_mod.LARGE_FILE_LINES + 1)
        self.assertTrue(guard_mod.should_deny({'file_path': path}))

    def test_allows_non_code_large_file(self):
        path = os.path.join(self.tmp.name, "big.md")
        _write_lines(path, 1000)
        self.assertFalse(guard_mod.should_deny({'file_path': path}))

    def test_allows_missing_file(self):
        # count_lines returns -1 for an unreadable/missing path -> never > threshold.
        self.assertFalse(guard_mod.should_deny(
            {'file_path': os.path.join(self.tmp.name, 'ghost.py')}))

    def test_allows_no_file_path(self):
        self.assertFalse(guard_mod.should_deny({}))

    def test_allows_non_dict_input(self):
        self.assertFalse(guard_mod.should_deny(None))
        self.assertFalse(guard_mod.should_deny("not a dict"))

    def test_offset_zero_still_counts_as_given(self):
        # offset=0 is a legitimate explicit value, not "absent".
        path = self._big_code_file()
        self.assertFalse(
            guard_mod.should_deny({'file_path': path, 'offset': 0}))


class TestBuildDenyMessage(unittest.TestCase):
    def test_includes_path_and_line_count_and_guidance(self):
        msg = guard_mod.build_deny_message("/x/big.py", 500)
        self.assertIn("/x/big.py", msg)
        self.assertIn("500", msg)
        self.assertIn("Grep", msg)
        self.assertIn("offset", msg)
        self.assertIn("limit", msg)


class TestMainEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _run_main(self, payload):
        orig = guard_mod.read_stdin_safe
        guard_mod.read_stdin_safe = lambda **kw: payload
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                with self.assertRaises(SystemExit):
                    guard_mod.main()
        finally:
            guard_mod.read_stdin_safe = orig
        return json.loads(buf.getvalue())

    def test_denies_large_code_file_without_window(self):
        path = os.path.join(self.tmp.name, "big.py")
        _write_lines(path, 500)
        result = self._run_main(
            {'tool_name': 'Read', 'tool_input': {'file_path': path}})
        self.assertEqual(
            result['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_allows_windowed_read_of_large_code_file(self):
        path = os.path.join(self.tmp.name, "big.py")
        _write_lines(path, 500)
        result = self._run_main({
            'tool_name': 'Read',
            'tool_input': {'file_path': path, 'offset': 100, 'limit': 80},
        })
        self.assertEqual(result, {})

    def test_allows_small_file(self):
        path = os.path.join(self.tmp.name, "small.py")
        _write_lines(path, 10)
        result = self._run_main(
            {'tool_name': 'Read', 'tool_input': {'file_path': path}})
        self.assertEqual(result, {})

    def test_allows_non_code_file(self):
        path = os.path.join(self.tmp.name, "notes.md")
        _write_lines(path, 1000)
        result = self._run_main(
            {'tool_name': 'Read', 'tool_input': {'file_path': path}})
        self.assertEqual(result, {})

    def test_fails_open_on_malformed_input(self):
        # tool_input missing entirely -> get_input_field default {} -> allow.
        result = self._run_main({'tool_name': 'Read'})
        self.assertEqual(result, {})

    def test_main_agent_and_subagent_both_gated(self):
        # No spawned-agent exemption: agent_id present still denies.
        path = os.path.join(self.tmp.name, "big.py")
        _write_lines(path, 500)
        result = self._run_main({
            'tool_name': 'Read',
            'tool_input': {'file_path': path},
            'agent_id': 'agent-xyz',
        })
        self.assertEqual(
            result['hookSpecificOutput']['permissionDecision'], 'deny')


if __name__ == "__main__":
    unittest.main()
