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
  post/swe_post_read_state     — _get_continuation, _discovery_no_credit_message
  post/swe_post_tool_failure   — unresolved_serena_correction, FLAIL_THRESHOLD, _BARE_SERENA_NAMES
  post/swe_post_todo_wm_sync   — sync_todos_to_wm, TODO_FENCE_START/END
  post/swe_post_memory_index   — find_memory_md, size/entry thresholds
  swe_hooks.core.output        — emit_once (E2 byte-identical suppression)

Stdlib unittest only. Deterministic + offline: no network, no real Serena, no
real git. IO uses tempfile.TemporaryDirectory; get_project_root is monkeypatched.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_hook, import_core, reset_caches  # noqa: E402

output_mod = import_core("swe_hooks.core.output")
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
# swe_post_read_state._continuation_directive — dedup wrapper
# ---------------------------------------------------------------------------
class TestContinuationDirective(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, ".git"), exist_ok=True)
        self._orig_env = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = self.tmp.name

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = self._orig_env
        self.tmp.cleanup()
        reset_caches()

    def test_first_emission_for_a_state_returns_directive(self):
        directive = read_state_mod._continuation_directive("WF_EXECUTE", "sess0001")
        self.assertIn("WF_EXECUTE", directive)

    def test_repeated_call_same_state_returns_empty(self):
        sid = "sess0002"
        first = read_state_mod._continuation_directive("WF_EXECUTE", sid)
        second = read_state_mod._continuation_directive("WF_EXECUTE", sid)
        self.assertTrue(first)
        self.assertEqual(second, "")

    def test_state_change_re_emits(self):
        sid = "sess0003"
        read_state_mod._continuation_directive("WF_EXECUTE", sid)
        directive = read_state_mod._continuation_directive("WF_VERIFY", sid)
        self.assertIn("WF_VERIFY", directive)

    def test_no_session_id_always_returns_directive_uncached(self):
        # No session id -> no stream to dedupe against; falls back to the raw
        # (non-deduped) directive every time.
        d1 = read_state_mod._continuation_directive("WF_EXECUTE", None)
        d2 = read_state_mod._continuation_directive("WF_EXECUTE", None)
        self.assertTrue(d1)
        self.assertTrue(d2)

    def test_unknown_state_returns_empty_and_records_nothing(self):
        sid = "sess0004"
        self.assertEqual(read_state_mod._continuation_directive("WF_NOPE", sid), "")

    def test_same_state_re_emits_after_event_threshold(self):
        # E1: a same-state directive suppressed as a repeat is re-emitted
        # once >= CONTINUATION_REEMIT_EVENTS stream events accumulate since
        # it was last shown.
        from swe_hooks.core.stream import get_stream_path, append_event
        sid = "sess0005"
        first = read_state_mod._continuation_directive("WF_EXECUTE", sid)
        self.assertTrue(first)
        stream_path = get_stream_path(sid)
        threshold = read_state_mod.CONTINUATION_REEMIT_EVENTS
        for _ in range(threshold - 1):
            append_event(stream_path, 'tool', s=sid)
        self.assertEqual(
            read_state_mod._continuation_directive("WF_EXECUTE", sid), "")
        append_event(stream_path, 'tool', s=sid)
        re_emitted = read_state_mod._continuation_directive("WF_EXECUTE", sid)
        self.assertIn("WF_EXECUTE", re_emitted)
        # The re-emission stamps a fresh continuation marker: suppressed again.
        self.assertEqual(
            read_state_mod._continuation_directive("WF_EXECUTE", sid), "")


# ---------------------------------------------------------------------------
# swe_hooks.core.stream.get_last_continuation
# ---------------------------------------------------------------------------
class TestGetLastContinuation(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        import importlib
        self.stream = importlib.import_module("swe_hooks.core.stream")

    def tearDown(self):
        self.tmp.cleanup()
        reset_caches()

    def test_missing_stream_returns_empty(self):
        path = os.path.join(self.tmp.name, "nope.jsonl")
        self.assertEqual(self.stream.get_last_continuation(path), "")

    def test_returns_latest_continuation_state(self):
        path = os.path.join(self.tmp.name, "s.jsonl")
        self.stream.append_event(path, "continuation", state="WF_EXECUTE")
        self.stream.append_event(path, "tool", name="Read")
        self.stream.append_event(path, "continuation", state="WF_VERIFY")
        self.assertEqual(self.stream.get_last_continuation(path), "WF_VERIFY")

    def test_no_continuation_event_returns_empty(self):
        path = os.path.join(self.tmp.name, "s2.jsonl")
        self.stream.append_event(path, "tool", name="Read")
        self.assertEqual(self.stream.get_last_continuation(path), "")


# ---------------------------------------------------------------------------
# swe_post_read_state._discovery_no_credit_message — tiered wording (4d)
# ---------------------------------------------------------------------------
class TestDiscoveryNoCreditMessage(unittest.TestCase):
    def test_lists_the_surfaced_names(self):
        msg = read_state_mod._discovery_no_credit_message(
            {"dom/dom_x", "ref/ref_y"})
        self.assertIn("dom/dom_x", msg)
        self.assertIn("ref/ref_y", msg)

    def test_tiered_defer_language_present(self):
        msg = read_state_mod._discovery_no_credit_message({"dom/dom_x"})
        self.assertIn("defer", msg.lower())
        self.assertIn("Memories deferred", msg)
        self.assertIn("RELEVANT", msg)

    def test_read_every_surfaced_doc_demand_absent(self):
        # The message must not demand ALL surfaced names be read — cold
        # sibling-tree hits are deferrable per WF_CLASSIFY 4d.
        msg = read_state_mod._discovery_no_credit_message({"em/feature/x"})
        self.assertNotIn("read_memory each before proceeding", msg)


# ---------------------------------------------------------------------------
# swe_hooks.core.output.emit_once — E2 byte-identical suppression
# ---------------------------------------------------------------------------
class TestEmitOnce(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.streams = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_emission_returns_true_and_records(self):
        self.assertTrue(output_mod.emit_once("sess0001", "hello",
                                             streams_dir=self.streams))
        ledger = os.path.join(self.streams, ".emitted_sess0001")
        self.assertTrue(os.path.exists(ledger))
        with open(ledger) as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(len(lines[0]), 64)  # one sha256 hex digest per line

    def test_identical_text_suppressed_on_repeat(self):
        self.assertTrue(output_mod.emit_once("sess0002", "same text",
                                             streams_dir=self.streams))
        self.assertFalse(output_mod.emit_once("sess0002", "same text",
                                              streams_dir=self.streams))
        self.assertFalse(output_mod.emit_once("sess0002", "same text",
                                              streams_dir=self.streams))

    def test_different_text_not_suppressed(self):
        self.assertTrue(output_mod.emit_once("sess0003", "text A",
                                             streams_dir=self.streams))
        self.assertTrue(output_mod.emit_once("sess0003", "text B",
                                             streams_dir=self.streams))
        self.assertFalse(output_mod.emit_once("sess0003", "text A",
                                              streams_dir=self.streams))

    def test_per_session_isolation(self):
        self.assertTrue(output_mod.emit_once("sessAAAA", "shared text",
                                             streams_dir=self.streams))
        # Same bytes, different session → its own ledger, so it emits.
        self.assertTrue(output_mod.emit_once("sessBBBB", "shared text",
                                             streams_dir=self.streams))
        self.assertFalse(output_mod.emit_once("sessAAAA", "shared text",
                                              streams_dir=self.streams))

    def test_io_error_passes_message_through(self):
        # streams_dir is a FILE, so every ledger open raises OSError —
        # emit_once must fail open (True) and never lose the message.
        bogus_dir = os.path.join(self.streams, "not_a_dir")
        with open(bogus_dir, "w") as f:
            f.write("x")
        self.assertTrue(output_mod.emit_once("sess0004", "msg",
                                             streams_dir=bogus_dir))
        self.assertTrue(output_mod.emit_once("sess0004", "msg",
                                             streams_dir=bogus_dir))

    def test_missing_session_id_passes_through(self):
        self.assertTrue(output_mod.emit_once("", "msg",
                                             streams_dir=self.streams))
        self.assertTrue(output_mod.emit_once(None, "msg",
                                             streams_dir=self.streams))

    def test_empty_text_passes_through(self):
        self.assertTrue(output_mod.emit_once("sess0005", "",
                                             streams_dir=self.streams))


# ---------------------------------------------------------------------------
# swe_post_read_state — memory-name extraction/link parsing (alias-aware)
# ---------------------------------------------------------------------------
class TestMemoryNameRegexAliasAware(unittest.TestCase):
    def test_two_segment_name_matched(self):
        self.assertEqual(
            read_state_mod.MEMORY_NAME_RE.findall("see feature/FEATURE_X here"),
            ["feature/FEATURE_X"],
        )

    def test_three_segment_aliased_name_not_truncated(self):
        # A 3-segment aliased name (alias/dir/NAME) matches in full.
        self.assertEqual(
            read_state_mod.MEMORY_NAME_RE.findall("see em/feature/FEATURE_X here"),
            ["em/feature/FEATURE_X"],
        )

    def test_multiple_names_including_aliased(self):
        text = "em/feature/FEATURE_X, dom/DOM_Y"
        self.assertEqual(
            read_state_mod.MEMORY_NAME_RE.findall(text),
            ["em/feature/FEATURE_X", "dom/DOM_Y"],
        )


class TestExtractMemoryNamesAliasAware(unittest.TestCase):
    def test_aliased_name_extracted_whole(self):
        names = read_state_mod._extract_memory_names(
            "Found: em/feature/FEATURE_X (score 0.9)")
        self.assertIn("em/feature/feature_x", names)
        self.assertNotIn("em/feature", names)


class TestRelatedLinksFiltersInvalidTokens(unittest.TestCase):
    def test_placeholder_feature_key_link_is_dropped(self):
        # A literal "FEATURE_[KEY]" placeholder in memory prose must never
        # surface as the truncated garbage link "feature/feature_".
        text = "See mem:feature/FEATURE_[KEY] for the primary feature memory."
        self.assertEqual(read_state_mod._related_links(text), set())

    def test_valid_mem_link_is_kept(self):
        text = "Related: mem:feature/FEATURE_SWE and more prose."
        self.assertEqual(
            read_state_mod._related_links(text), {"feature/feature_swe"})

    def test_valid_bracket_link_is_kept(self):
        text = "See [[dom/DOM_X]] for details."
        self.assertEqual(read_state_mod._related_links(text), {"dom/dom_x"})

    def test_aliased_link_is_kept(self):
        text = "See mem:em/feature/FEATURE_TESTS for the em-serena feature doc."
        self.assertEqual(
            read_state_mod._related_links(text), {"em/feature/feature_tests"})

    def test_excluded_prefix_link_is_dropped(self):
        text = "See mem:wf/WF_INIT for the entry point."
        self.assertEqual(read_state_mod._related_links(text), set())

    def test_placeholder_mixed_with_valid_link_only_valid_kept(self):
        text = ("Primary: mem:feature/FEATURE_[KEY]. Related: "
                "mem:dom/DOM_BUILDER_BLOCKS and more prose")
        self.assertEqual(
            read_state_mod._related_links(text), {"dom/dom_builder_blocks"})


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
# swe_post_tool_failure.is_mcp_unavailable_error — degraded-mode trigger
# ---------------------------------------------------------------------------
class TestIsMcpUnavailableError(unittest.TestCase):
    def test_fully_qualified_serena_tool_connection_closed(self):
        self.assertTrue(failure_mod.is_mcp_unavailable_error(
            "mcp__plugin_swe_serena__read_memory", "Connection closed"))

    def test_bare_serena_name_server_disconnected(self):
        self.assertTrue(failure_mod.is_mcp_unavailable_error(
            "read_memory", "MCP server disconnected unexpectedly"))

    def test_econnrefused_detected(self):
        self.assertTrue(failure_mod.is_mcp_unavailable_error(
            "mcp__plugin_swe_serena__write_memory", "connect ECONNREFUSED 127.0.0.1:1234"))

    def test_case_insensitive(self):
        self.assertTrue(failure_mod.is_mcp_unavailable_error(
            "mcp__plugin_swe_serena__list_memories", "FAILED TO CONNECT to MCP Server"))

    def test_unresolved_name_error_is_not_connection_error(self):
        # "No such tool available" is a deferred-schema issue, not a
        # connection failure — must NOT trigger degraded mode.
        self.assertFalse(failure_mod.is_mcp_unavailable_error(
            "read_memory", "No such tool available: read_memory"))

    def test_schema_validation_error_is_not_connection_error(self):
        self.assertFalse(failure_mod.is_mcp_unavailable_error(
            "mcp__plugin_swe_serena__replace_content", "field required: needle"))

    def test_non_serena_tool_is_never_mcp_unavailable(self):
        self.assertFalse(failure_mod.is_mcp_unavailable_error(
            "Bash", "connection closed"))

    def test_empty_inputs_false(self):
        self.assertFalse(failure_mod.is_mcp_unavailable_error("", ""))
        self.assertFalse(failure_mod.is_mcp_unavailable_error(None, None))


class TestMainAppendsMcpUnavailableAndDegraded(unittest.TestCase):
    """main() must append 'mcp_unavailable' (and, on the FIRST occurrence,
    'degraded') to the stream when a Serena MCP connection failure is
    reported — the init gate's circuit breaker reads these events."""

    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, ".git"), exist_ok=True)
        self._orig_env = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = self.tmp.name
        import importlib
        self.stream = importlib.import_module("swe_hooks.core.stream")

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = self._orig_env
        self.tmp.cleanup()
        reset_caches()

    def _run_main(self, tool_name, tool_error, session_id="abcd1234"):
        import io
        from unittest import mock
        transcript = f"/x/{session_id}-0000-0000-0000-000000000000.jsonl"
        payload = {
            "tool_name": tool_name,
            "tool_error": tool_error,
            "transcript_path": transcript,
            "tool_input": {},
        }
        buf = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
             mock.patch("select.select", return_value=([sys.stdin], [], [])), \
             mock.patch("sys.stdout", buf):
            try:
                failure_mod.main()
            except SystemExit:
                pass
        return buf.getvalue()

    def test_connection_failure_appends_both_events_first_time(self):
        self._run_main("mcp__plugin_swe_serena__read_memory", "Connection closed")
        stream_path = self.stream.get_stream_path("abcd1234")
        with open(stream_path) as f:
            types = [json.loads(line)["type"] for line in f if line.strip()]
        self.assertIn("mcp_unavailable", types)
        self.assertIn("degraded", types)

    def test_second_connection_failure_does_not_re_append_degraded(self):
        self._run_main("mcp__plugin_swe_serena__read_memory", "Connection closed",
                        session_id="eeff5678")
        self._run_main("mcp__plugin_swe_serena__read_memory", "Connection closed",
                        session_id="eeff5678")
        stream_path = self.stream.get_stream_path("eeff5678")
        with open(stream_path) as f:
            types = [json.loads(line)["type"] for line in f if line.strip()]
        self.assertEqual(types.count("degraded"), 1)
        self.assertEqual(types.count("mcp_unavailable"), 2)

    def test_non_connection_failure_does_not_append_degraded(self):
        self._run_main("read_memory", "No such tool available: read_memory",
                        session_id="facade02")
        stream_path = self.stream.get_stream_path("facade02")
        with open(stream_path) as f:
            types = [json.loads(line)["type"] for line in f if line.strip()]
        self.assertNotIn("degraded", types)
        self.assertNotIn("mcp_unavailable", types)


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
