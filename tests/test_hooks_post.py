"""Tests for hooks/post/* pure functions and module constants.

Covers five PostToolUse hook modules (their pure, side-effect-free helpers and
the module-level constants they key off). Functions listed as ALREADY-TESTED
elsewhere are intentionally NOT re-tested here:
  - swe_post_tool_failure.schema_correction / count_consecutive_failures
  - swe_post_todo_wm_sync.format_todos
  - swe_post_memory_index.check_memory_md_health / memory_name_in_index
    (+ SKIP_PREFIXES / NON_INDEXED_CATEGORIES) — covered by
    test_swe_post_memory_index.py.

Modules under test:
  post/swe_post_memory_style   — strip_examples, scan_style, SUGGESTION/VAGUE patterns
  post/swe_post_read_state     — _get_continuation
  post/swe_post_tool_failure   — unresolved_serena_correction, FLAIL_THRESHOLD, _BARE_SERENA_NAMES
  post/swe_post_todo_wm_sync   — sync_todos_to_wm, TODO_FENCE_START/END
  post/swe_post_memory_index   — find_memory_md, size/entry thresholds

Stdlib unittest only. Deterministic + offline: no network, no real Serena, no
real git. IO uses tempfile.TemporaryDirectory; get_project_root is monkeypatched.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_hook, reset_caches  # noqa: E402

style_mod = import_hook("post/swe_post_memory_style")
read_state_mod = import_hook("post/swe_post_read_state")
failure_mod = import_hook("post/swe_post_tool_failure")
todo_mod = import_hook("post/swe_post_todo_wm_sync")
index_mod = import_hook("post/swe_post_memory_index")


# A valid front-matter header that satisfies FRONT_MATTER_RE (name / description /
# metadata.type). Prepend to a body to build a scan_style fixture whose ONLY
# possible violations come from the body prose.
VALID_FRONT_MATTER = (
    "---\n"
    "name: DOM_TEST\n"
    "description: test memory\n"
    "metadata:\n"
    "  type: dom\n"
    "---\n\n"
)


# ---------------------------------------------------------------------------
# swe_post_memory_style.strip_examples
# ---------------------------------------------------------------------------
class TestStripExamples(unittest.TestCase):
    def test_fenced_code_block_removed_prose_kept(self):
        text = (
            "prose line one\n"
            "```\n"
            "you should not flag this\n"
            "```\n"
            "prose line two\n"
        )
        out = style_mod.strip_examples(text)
        self.assertIn("prose line one", out)
        self.assertIn("prose line two", out)
        self.assertNotIn("you should not flag this", out)

    def test_tilde_fenced_block_removed(self):
        text = "keep me\n~~~\nyou should hide\n~~~\nkeep me too\n"
        out = style_mod.strip_examples(text)
        self.assertIn("keep me", out)
        self.assertIn("keep me too", out)
        self.assertNotIn("you should hide", out)

    def test_blockquote_line_removed(self):
        text = "real prose\n> you should quoted directive\n"
        out = style_mod.strip_examples(text)
        self.assertIn("real prose", out)
        self.assertNotIn("quoted directive", out)

    def test_table_row_removed(self):
        text = "real prose\n| you should | not flag table |\n"
        out = style_mod.strip_examples(text)
        self.assertIn("real prose", out)
        self.assertNotIn("not flag table", out)

    def test_inline_code_span_stripped(self):
        text = "use `you should` inline here\n"
        out = style_mod.strip_examples(text)
        # The word "here" (outside the span) survives; the span content is gone.
        self.assertIn("here", out)
        self.assertNotIn("you should", out)

    def test_double_quoted_span_stripped(self):
        text = 'the phrase \"you should\" is an example\n'
        out = style_mod.strip_examples(text)
        self.assertIn("example", out)
        self.assertNotIn("you should", out)

    def test_single_quoted_span_stripped(self):
        text = "the phrase 'you should' is an example\n"
        out = style_mod.strip_examples(text)
        self.assertIn("example", out)
        self.assertNotIn("you should", out)

    def test_plain_prose_survives_unchanged_words(self):
        text = "Run the tests and fix the failures.\n"
        out = style_mod.strip_examples(text)
        self.assertIn("Run the tests", out)
        self.assertIn("fix the failures", out)

    def test_empty_input(self):
        self.assertEqual(style_mod.strip_examples(""), "")


# ---------------------------------------------------------------------------
# swe_post_memory_style.scan_style + pattern constants
# ---------------------------------------------------------------------------
class TestScanStyle(unittest.TestCase):
    def test_clean_terse_memory_yields_no_violations(self):
        content = VALID_FRONT_MATTER + "Run the tests. Fix failures. Commit.\n"
        self.assertEqual(style_mod.scan_style(content), [])

    def test_suggestion_mood_flagged(self):
        content = VALID_FRONT_MATTER + "You should run the tests whenever convenient.\n"
        violations = style_mod.scan_style(content)
        self.assertTrue(any("suggestion-mood" in v for v in violations))
        self.assertTrue(any("you should" in v for v in violations))

    def test_conversational_opener_flagged(self):
        content = VALID_FRONT_MATTER + "Let me explain the setup here.\n"
        violations = style_mod.scan_style(content)
        self.assertTrue(any("conversational opener" in v for v in violations))

    def test_vague_quantifier_flagged(self):
        content = VALID_FRONT_MATTER + "Retry a few times before giving up.\n"
        violations = style_mod.scan_style(content)
        self.assertTrue(any("vague quantifier" in v for v in violations))

    def test_missing_front_matter_flagged(self):
        # No front-matter at all -> the front-matter violation must appear.
        violations = style_mod.scan_style("Just some prose without metadata.\n")
        self.assertTrue(any("front-matter" in v for v in violations))

    def test_suggestion_phrase_inside_code_span_not_flagged(self):
        # strip_examples removes inline code spans, so an example phrase there is
        # NOT a violation.
        content = VALID_FRONT_MATTER + "Reject `you should` phrasing in memories.\n"
        violations = style_mod.scan_style(content)
        self.assertFalse(any("suggestion-mood" in v for v in violations))

    def test_empty_content_reports_missing_front_matter(self):
        violations = style_mod.scan_style("")
        self.assertTrue(any("front-matter" in v for v in violations))

    def test_suggestion_patterns_constant_contains_you_should(self):
        self.assertIn(r"\byou should\b", style_mod.SUGGESTION_PATTERNS)
        self.assertIn(r"\bfeel free to\b", style_mod.SUGGESTION_PATTERNS)

    def test_vague_patterns_constant_contains_a_few(self):
        self.assertIn(r"\ba few\b", style_mod.VAGUE_PATTERNS)
        self.assertIn(r"\bas appropriate\b", style_mod.VAGUE_PATTERNS)


# ---------------------------------------------------------------------------
# swe_post_read_state._get_continuation
# ---------------------------------------------------------------------------
class TestGetContinuation(unittest.TestCase):
    def test_known_states_map_to_nonempty_directives(self):
        for state in ("WF_CLASSIFY", "WF_EXECUTE", "WF_VERIFY", "WF_DONE",
                      "WF_ARCH_REVIEW", "WF_RESEARCH"):
            directive = read_state_mod._get_continuation(state)
            self.assertTrue(directive, f"{state} should have a directive")
            self.assertIn(state, directive)
            self.assertIn("CONTINUE", directive)

    def test_execute_directive_content(self):
        directive = read_state_mod._get_continuation("WF_EXECUTE")
        self.assertIn("WF_VERIFY", directive)

    def test_unknown_state_returns_empty_string(self):
        self.assertEqual(read_state_mod._get_continuation("WF_NOPE"), "")

    def test_empty_state_returns_empty_string(self):
        self.assertEqual(read_state_mod._get_continuation(""), "")

    def test_none_state_returns_empty_string(self):
        # dict.get(None) -> None -> falsy -> "" (no exception).
        self.assertEqual(read_state_mod._get_continuation(None), "")


# ---------------------------------------------------------------------------
# swe_post_tool_failure.unresolved_serena_correction + constants
# ---------------------------------------------------------------------------
class TestUnresolvedSerenaCorrection(unittest.TestCase):
    def test_bare_name_with_unresolved_error_returns_correction(self):
        out = failure_mod.unresolved_serena_correction(
            "read_memory", "No such tool available: read_memory"
        )
        self.assertTrue(out)
        self.assertIn("read_memory", out)
        # Correction names the fully-qualified form and the ToolSearch step.
        self.assertIn("mcp__plugin_swe_serena__read_memory", out)
        self.assertIn("ToolSearch", out)

    def test_marker_matching_is_case_insensitive(self):
        out = failure_mod.unresolved_serena_correction(
            "find_symbol", "ERROR: No Such Tool Available here"
        )
        self.assertTrue(out)

    def test_bare_name_with_schema_error_returns_empty(self):
        # A schema/param error is NOT an unresolved-name error.
        out = failure_mod.unresolved_serena_correction(
            "read_memory", "field required: memory_name"
        )
        self.assertEqual(out, "")

    def test_fully_qualified_name_returns_empty(self):
        # Already-qualified names are not in _BARE_SERENA_NAMES.
        out = failure_mod.unresolved_serena_correction(
            "mcp__plugin_swe_serena__read_memory", "no such tool available"
        )
        self.assertEqual(out, "")

    def test_non_serena_tool_returns_empty(self):
        out = failure_mod.unresolved_serena_correction(
            "Bash", "no such tool available: Bash"
        )
        self.assertEqual(out, "")

    def test_empty_inputs_return_empty(self):
        self.assertEqual(failure_mod.unresolved_serena_correction("", ""), "")

    def test_none_inputs_do_not_raise(self):
        # str() coercion inside the function means None is handled gracefully.
        self.assertEqual(failure_mod.unresolved_serena_correction(None, None), "")

    def test_flail_threshold_is_two(self):
        self.assertEqual(failure_mod.FLAIL_THRESHOLD, 2)

    def test_bare_serena_names_membership(self):
        self.assertIn("read_memory", failure_mod._BARE_SERENA_NAMES)
        self.assertIn("write_memory", failure_mod._BARE_SERENA_NAMES)
        self.assertIn("find_symbol", failure_mod._BARE_SERENA_NAMES)
        # A fully-qualified name is NOT in the bare set.
        self.assertNotIn(
            "mcp__plugin_swe_serena__read_memory", failure_mod._BARE_SERENA_NAMES
        )


# ---------------------------------------------------------------------------
# swe_post_todo_wm_sync.sync_todos_to_wm + fence constants
# ---------------------------------------------------------------------------
class TestSyncTodosToWm(unittest.TestCase):
    WM_TEMPLATE = (
        "# Working Memory\n\n"
        "## Progress\n\n"
        "manual notes preserved\n\n"
        "## Implementation Notes\n(none)\n"
    )

    def _write_wm(self, tmpdir, content=None):
        wm = os.path.join(tmpdir, "WM_test.md")
        with open(wm, "w", encoding="utf-8") as f:
            f.write(self.WM_TEMPLATE if content is None else content)
        return wm

    @staticmethod
    def _read(path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_fenced_block_injected_with_formatted_todos(self):
        with tempfile.TemporaryDirectory() as td:
            wm = self._write_wm(td)
            todos = [
                {"content": "task A", "status": "completed"},
                {"content": "task B", "status": "in_progress"},
                {"content": "task C", "status": "pending"},
            ]
            todo_mod.sync_todos_to_wm(wm, todos)
            content = self._read(wm)
            self.assertIn(todo_mod.TODO_FENCE_START, content)
            self.assertIn(todo_mod.TODO_FENCE_END, content)
            self.assertIn("- [x] task A", content)
            self.assertIn("- [~] task B", content)
            self.assertIn("- [ ] task C", content)
            # Manual notes are preserved (fenced block does not clobber them).
            self.assertIn("manual notes preserved", content)
            # Exactly one fenced block.
            self.assertEqual(content.count(todo_mod.TODO_FENCE_START), 1)
            self.assertEqual(content.count(todo_mod.TODO_FENCE_END), 1)

    def test_second_call_replaces_not_duplicates(self):
        with tempfile.TemporaryDirectory() as td:
            wm = self._write_wm(td)
            todo_mod.sync_todos_to_wm(wm, [{"content": "first", "status": "pending"}])
            todo_mod.sync_todos_to_wm(wm, [{"content": "second", "status": "pending"}])
            content = self._read(wm)
            # Still exactly one fenced block; the old todo is gone, the new present.
            self.assertEqual(content.count(todo_mod.TODO_FENCE_START), 1)
            self.assertEqual(content.count(todo_mod.TODO_FENCE_END), 1)
            self.assertNotIn("first", content)
            self.assertIn("- [ ] second", content)

    def test_progress_section_created_when_absent(self):
        # No "## Progress" heading, but "## Implementation Notes" present ->
        # a Progress section is inserted before it.
        wm_body = "# Working Memory\n\n## Implementation Notes\n(none)\n"
        with tempfile.TemporaryDirectory() as td:
            wm = self._write_wm(td, content=wm_body)
            todo_mod.sync_todos_to_wm(wm, [{"content": "x", "status": "pending"}])
            content = self._read(wm)
            self.assertIn("## Progress", content)
            self.assertIn(todo_mod.TODO_FENCE_START, content)
            self.assertIn("- [ ] x", content)

    def test_no_progress_and_no_notes_appends_at_end(self):
        wm_body = "# Working Memory\n\nSome header content only.\n"
        with tempfile.TemporaryDirectory() as td:
            wm = self._write_wm(td, content=wm_body)
            todo_mod.sync_todos_to_wm(wm, [{"content": "y", "status": "completed"}])
            content = self._read(wm)
            self.assertIn("## Progress", content)
            self.assertIn("- [x] y", content)

    def test_missing_file_is_a_noop(self):
        # A non-existent WM path returns silently (open raises IOError -> caught).
        missing = os.path.join(tempfile.gettempdir(), "definitely_absent_wm_xyz.md")
        if os.path.exists(missing):
            os.remove(missing)
        try:
            todo_mod.sync_todos_to_wm(missing, [{"content": "z", "status": "pending"}])
        except Exception as e:  # pragma: no cover
            self.fail(f"sync_todos_to_wm raised on missing file: {e}")
        self.assertFalse(os.path.exists(missing))

    def test_empty_todos_writes_empty_fenced_block(self):
        with tempfile.TemporaryDirectory() as td:
            wm = self._write_wm(td)
            todo_mod.sync_todos_to_wm(wm, [])
            content = self._read(wm)
            # Fence markers are still written (format_todos returns '' for []).
            self.assertIn(todo_mod.TODO_FENCE_START, content)
            self.assertIn(todo_mod.TODO_FENCE_END, content)

    def test_fence_constants(self):
        self.assertEqual(todo_mod.TODO_FENCE_START, "<!-- todo-sync-start -->")
        self.assertEqual(todo_mod.TODO_FENCE_END, "<!-- todo-sync-end -->")


# ---------------------------------------------------------------------------
# swe_post_memory_index.find_memory_md + thresholds
# ---------------------------------------------------------------------------
class TestFindMemoryMd(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self._orig_get_project_root = index_mod.get_project_root

    def tearDown(self):
        index_mod.get_project_root = self._orig_get_project_root
        reset_caches()

    def test_locates_memory_md_via_project_root(self):
        with tempfile.TemporaryDirectory() as td:
            memdir = os.path.join(td, ".serena", "memory")
            os.makedirs(memdir)
            memfile = os.path.join(memdir, "MEMORY.md")
            with open(memfile, "w", encoding="utf-8") as f:
                f.write("## Index\n- [X](ref/REF_X.md) — hook\n")
            index_mod.get_project_root = lambda: td
            # cwd is irrelevant here — project_root path wins first.
            found = index_mod.find_memory_md(cwd="/nonexistent/path")
            self.assertEqual(found, memfile)

    def test_falls_back_to_cwd_when_project_root_lacks_it(self):
        with tempfile.TemporaryDirectory() as root_td, \
             tempfile.TemporaryDirectory() as cwd_td:
            # project_root has NO MEMORY.md; cwd does.
            index_mod.get_project_root = lambda: root_td
            memdir = os.path.join(cwd_td, ".serena", "memory")
            os.makedirs(memdir)
            memfile = os.path.join(memdir, "MEMORY.md")
            with open(memfile, "w", encoding="utf-8") as f:
                f.write("## Index\n")
            found = index_mod.find_memory_md(cwd=cwd_td)
            self.assertEqual(found, memfile)

    def test_returns_none_when_absent_everywhere(self):
        with tempfile.TemporaryDirectory() as root_td, \
             tempfile.TemporaryDirectory() as cwd_td:
            index_mod.get_project_root = lambda: root_td
            self.assertIsNone(index_mod.find_memory_md(cwd=cwd_td))

    def test_thresholds(self):
        self.assertEqual(index_mod.MEMORY_MD_MAX_LINES, 200)
        self.assertEqual(index_mod.MEMORY_MD_MAX_BYTES, 24000)
        self.assertEqual(index_mod.INDEX_ENTRY_MAX_CHARS, 200)


if __name__ == "__main__":
    unittest.main()
