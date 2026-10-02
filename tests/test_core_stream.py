"""Tests for swe_hooks.core.stream — append-only JSONL event tracking.

All counting functions take an EXPLICIT stream_path, so they are tested against
real temp files with no monkeypatching. get_stream_path / get_sentinel_path
resolve their directory through swe_hooks.core.config.get_project_root, which is
monkeypatched to a tmpdir.
"""
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_core, reset_caches  # noqa: E402

stream = import_core("swe_hooks.core.stream")
config = import_core("swe_hooks.core.config")


class BaseStreamTest(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = self.tmp.name
        self.stream_path = os.path.join(self.tmpdir, "session.jsonl")

    def tearDown(self):
        self.tmp.cleanup()
        reset_caches()

    def _write_jsonl(self, events):
        """Write a list of event dicts as JSONL to self.stream_path."""
        with open(self.stream_path, "w") as f:
            for ev in events:
                f.write(json.dumps(ev, separators=(",", ":")) + "\n")

    def _read_lines(self):
        with open(self.stream_path, "r") as f:
            return [ln for ln in f.read().splitlines() if ln.strip()]


class TestAppendEvent(BaseStreamTest):
    def test_writes_one_valid_json_line(self):
        stream.append_event(self.stream_path, "tool")
        lines = self._read_lines()
        self.assertEqual(len(lines), 1)
        event = json.loads(lines[0])
        self.assertEqual(event["type"], "tool")
        self.assertIn("t", event)
        self.assertIsInstance(event["t"], int)

    def test_timestamp_is_plausible_epoch_int(self):
        before = int(time.time())
        stream.append_event(self.stream_path, "state")
        after = int(time.time())
        event = json.loads(self._read_lines()[0])
        # Assert structure/range, not exact value.
        self.assertGreaterEqual(event["t"], before)
        self.assertLessEqual(event["t"], after)

    def test_extra_data_is_merged_into_event(self):
        stream.append_event(self.stream_path, "edit", path="foo.py", n=3)
        event = json.loads(self._read_lines()[0])
        self.assertEqual(event["type"], "edit")
        self.assertEqual(event["path"], "foo.py")
        self.assertEqual(event["n"], 3)

    def test_file_grows_by_one_line_each_call(self):
        for i in range(1, 6):
            stream.append_event(self.stream_path, "tool", i=i)
            self.assertEqual(len(self._read_lines()), i)
        # Every line is valid JSON with a type field.
        for ln in self._read_lines():
            ev = json.loads(ln)
            self.assertEqual(ev["type"], "tool")

    def test_creates_missing_parent_directories(self):
        nested = os.path.join(self.tmpdir, "a", "b", "c", "session.jsonl")
        self.assertFalse(os.path.exists(os.path.dirname(nested)))
        stream.append_event(nested, "tool")
        self.assertTrue(os.path.exists(nested))
        with open(nested) as f:
            event = json.loads(f.read().splitlines()[0])
        self.assertEqual(event["type"], "tool")

    def test_data_can_override_type_key(self):
        # event.update(data) runs after type is set, so an explicit type in data wins.
        stream.append_event(self.stream_path, "tool", type="override")
        event = json.loads(self._read_lines()[0])
        self.assertEqual(event["type"], "override")

    def test_appends_do_not_truncate(self):
        stream.append_event(self.stream_path, "state")
        stream.append_event(self.stream_path, "edit")
        types = [json.loads(ln)["type"] for ln in self._read_lines()]
        self.assertEqual(types, ["state", "edit"])


class TestGetEventCount(BaseStreamTest):
    def test_missing_file_returns_zero(self):
        self.assertEqual(stream.get_event_count(self.stream_path), 0)

    def test_empty_file_returns_zero(self):
        open(self.stream_path, "w").close()
        self.assertEqual(stream.get_event_count(self.stream_path), 0)

    def test_counts_n_appends(self):
        for _ in range(7):
            stream.append_event(self.stream_path, "tool")
        self.assertEqual(stream.get_event_count(self.stream_path), 7)

    def test_counts_lines_including_non_json(self):
        # get_event_count is a raw line count (sum over binary handle).
        with open(self.stream_path, "w") as f:
            f.write('{"t":1,"type":"a"}\n')
            f.write("garbage not json\n")
            f.write('{"t":2,"type":"b"}\n')
        self.assertEqual(stream.get_event_count(self.stream_path), 3)

    def test_returns_int(self):
        stream.append_event(self.stream_path, "tool")
        self.assertIsInstance(stream.get_event_count(self.stream_path), int)


class TestCountEventsSinceLast(BaseStreamTest):
    def test_missing_file_returns_zero(self):
        self.assertEqual(stream.count_events_since_last(self.stream_path), 0)

    def test_no_marker_counts_all_matching(self):
        self._write_jsonl([
            {"t": 1, "type": "edit"},
            {"t": 2, "type": "tool"},
            {"t": 3, "type": "edit"},
            {"t": 4, "type": "edit"},
        ])
        self.assertEqual(
            stream.count_events_since_last(self.stream_path,
                                           marker_types=("state", "checkpoint"),
                                           count_type="edit"),
            3,
        )

    def test_marker_resets_count(self):
        self._write_jsonl([
            {"t": 1, "type": "edit"},
            {"t": 2, "type": "edit"},
            {"t": 3, "type": "state"},   # marker resets
            {"t": 4, "type": "edit"},
            {"t": 5, "type": "edit"},
        ])
        self.assertEqual(
            stream.count_events_since_last(self.stream_path,
                                           marker_types=("state", "checkpoint"),
                                           count_type="edit"),
            2,
        )

    def test_only_counts_since_LAST_marker(self):
        self._write_jsonl([
            {"t": 1, "type": "checkpoint"},
            {"t": 2, "type": "edit"},
            {"t": 3, "type": "state"},   # this is the last marker
            {"t": 4, "type": "edit"},
        ])
        self.assertEqual(
            stream.count_events_since_last(self.stream_path,
                                           marker_types=("state", "checkpoint"),
                                           count_type="edit"),
            1,
        )

    def test_marker_at_end_yields_zero(self):
        self._write_jsonl([
            {"t": 1, "type": "edit"},
            {"t": 2, "type": "state"},
        ])
        self.assertEqual(
            stream.count_events_since_last(self.stream_path,
                                           marker_types=("state", "checkpoint"),
                                           count_type="edit"),
            0,
        )

    def test_ignores_non_count_non_marker_types(self):
        self._write_jsonl([
            {"t": 1, "type": "edit"},
            {"t": 2, "type": "tool"},
            {"t": 3, "type": "search"},
            {"t": 4, "type": "edit"},
        ])
        self.assertEqual(
            stream.count_events_since_last(self.stream_path,
                                           marker_types=("state", "checkpoint"),
                                           count_type="edit"),
            2,
        )

    def test_malformed_lines_are_skipped(self):
        with open(self.stream_path, "w") as f:
            f.write('{"t":1,"type":"edit"}\n')
            f.write("this is not json\n")
            f.write("\n")  # blank line
            f.write('{"t":2,"type":"edit"}\n')
        self.assertEqual(
            stream.count_events_since_last(self.stream_path,
                                           marker_types=("state", "checkpoint"),
                                           count_type="edit"),
            2,
        )

    def test_custom_marker_and_count_types(self):
        self._write_jsonl([
            {"t": 1, "type": "search"},
            {"t": 2, "type": "docread"},   # custom marker
            {"t": 3, "type": "search"},
            {"t": 4, "type": "search"},
        ])
        self.assertEqual(
            stream.count_events_since_last(self.stream_path,
                                           marker_types=("docread",),
                                           count_type="search"),
            2,
        )

    def test_large_file_seek_boundary_counts_since_last_marker(self):
        # Build a file well over 10KB so the seek-to-last-10KB branch runs.
        # Layout: lots of edits, then a marker, then a known number of edits.
        # The marker must fall within the last 10KB window so it is seen.
        events = []
        for i in range(2000):  # padding, each line ~30+ bytes => >>10KB
            events.append({"t": i, "type": "edit", "pad": "x" * 20})
        events.append({"t": 9000, "type": "state"})  # last marker
        for i in range(5):
            events.append({"t": 9001 + i, "type": "edit"})
        self._write_jsonl(events)
        self.assertGreater(os.path.getsize(self.stream_path), 10240)
        self.assertEqual(
            stream.count_events_since_last(self.stream_path,
                                           marker_types=("state", "checkpoint"),
                                           count_type="edit"),
            5,
        )

    def test_large_file_no_marker_in_window_counts_window_edits(self):
        # Over 10KB with NO marker anywhere; only edits inside the last-10KB
        # window are counted (the partial first line is skipped). We assert the
        # count is positive and bounded by total edits — the seek path is
        # exercised without depending on the exact window size.
        events = [{"t": i, "type": "edit", "pad": "y" * 40} for i in range(1000)]
        self._write_jsonl(events)
        self.assertGreater(os.path.getsize(self.stream_path), 10240)
        count = stream.count_events_since_last(self.stream_path,
                                               marker_types=("state", "checkpoint"),
                                               count_type="edit")
        self.assertGreater(count, 0)
        self.assertLess(count, 1000)  # only the tail window, not the whole file


class TestCountEditsSinceCheckpoint(BaseStreamTest):
    def test_default_markers_state_and_checkpoint(self):
        # No marker -> counts all edits.
        self._write_jsonl([
            {"t": 1, "type": "edit"},
            {"t": 2, "type": "edit"},
            {"t": 3, "type": "edit"},
        ])
        self.assertEqual(stream.count_edits_since_checkpoint(self.stream_path), 3)

    def test_checkpoint_marker_resets(self):
        self._write_jsonl([
            {"t": 1, "type": "edit"},
            {"t": 2, "type": "checkpoint"},  # reset
            {"t": 3, "type": "edit"},
        ])
        self.assertEqual(stream.count_edits_since_checkpoint(self.stream_path), 1)

    def test_state_marker_resets(self):
        self._write_jsonl([
            {"t": 1, "type": "edit"},
            {"t": 2, "type": "edit"},
            {"t": 3, "type": "state"},  # reset
            {"t": 4, "type": "edit"},
        ])
        self.assertEqual(stream.count_edits_since_checkpoint(self.stream_path), 1)

    def test_searches_do_not_count_as_edits(self):
        self._write_jsonl([
            {"t": 1, "type": "search"},
            {"t": 2, "type": "edit"},
        ])
        self.assertEqual(stream.count_edits_since_checkpoint(self.stream_path), 1)

    def test_missing_file_zero(self):
        self.assertEqual(stream.count_edits_since_checkpoint(self.stream_path), 0)


class TestCountSearchesSinceDocread(BaseStreamTest):
    def test_counts_searches_with_no_marker(self):
        self._write_jsonl([
            {"t": 1, "type": "search"},
            {"t": 2, "type": "search"},
        ])
        self.assertEqual(stream.count_searches_since_docread(self.stream_path), 2)

    def test_docread_marker_resets(self):
        self._write_jsonl([
            {"t": 1, "type": "search"},
            {"t": 2, "type": "search"},
            {"t": 3, "type": "docread"},  # reset
            {"t": 4, "type": "search"},
        ])
        self.assertEqual(stream.count_searches_since_docread(self.stream_path), 1)

    def test_state_marker_resets_searches(self):
        self._write_jsonl([
            {"t": 1, "type": "search"},
            {"t": 2, "type": "state"},  # reset
            {"t": 3, "type": "search"},
            {"t": 4, "type": "search"},
        ])
        self.assertEqual(stream.count_searches_since_docread(self.stream_path), 2)

    def test_checkpoint_marker_resets_searches(self):
        self._write_jsonl([
            {"t": 1, "type": "search"},
            {"t": 2, "type": "checkpoint"},  # reset
            {"t": 3, "type": "search"},
        ])
        self.assertEqual(stream.count_searches_since_docread(self.stream_path), 1)

    def test_edits_do_not_count_as_searches(self):
        self._write_jsonl([
            {"t": 1, "type": "edit"},
            {"t": 2, "type": "search"},
            {"t": 3, "type": "edit"},
        ])
        self.assertEqual(stream.count_searches_since_docread(self.stream_path), 1)

    def test_missing_file_zero(self):
        self.assertEqual(stream.count_searches_since_docread(self.stream_path), 0)


class TestPathHelpers(unittest.TestCase):
    """get_stream_path / get_sentinel_path resolve via config.get_project_root."""

    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = self.tmp.name
        self._orig_get_root = config.get_project_root
        config.get_project_root = lambda: self.tmpdir

    def tearDown(self):
        config.get_project_root = self._orig_get_root
        self.tmp.cleanup()
        reset_caches()

    def test_get_stream_dir_creates_serena_streams(self):
        d = stream.get_stream_dir()
        self.assertEqual(d, os.path.join(self.tmpdir, ".serena", "streams"))
        self.assertTrue(os.path.isdir(d))

    def test_get_stream_path_suffix_and_basename(self):
        p = stream.get_stream_path("abc123")
        self.assertTrue(p.endswith(".jsonl"))
        self.assertEqual(os.path.basename(p), "abc123.jsonl")
        self.assertEqual(
            p, os.path.join(self.tmpdir, ".serena", "streams", "abc123.jsonl")
        )

    def test_get_sentinel_path_prefix_and_basename(self):
        p = stream.get_sentinel_path("abc123")
        self.assertEqual(os.path.basename(p), ".init_abc123")
        self.assertEqual(
            p, os.path.join(self.tmpdir, ".serena", "streams", ".init_abc123")
        )

    def test_stream_and_sentinel_share_directory(self):
        sp = stream.get_stream_path("sid")
        sen = stream.get_sentinel_path("sid")
        self.assertEqual(os.path.dirname(sp), os.path.dirname(sen))

    def test_get_edit_mode_path_prefix_and_basename(self):
        p = stream.get_edit_mode_path("abc123")
        self.assertEqual(os.path.basename(p), ".edit_mode_abc123")
        self.assertEqual(
            p, os.path.join(self.tmpdir, ".serena", "streams", ".edit_mode_abc123")
        )

    def test_edit_mode_and_sentinel_share_directory(self):
        em = stream.get_edit_mode_path("sid")
        sen = stream.get_sentinel_path("sid")
        self.assertEqual(os.path.dirname(em), os.path.dirname(sen))


class TestEditModeFlag(unittest.TestCase):
    """is_edit_mode / set_edit_mode — sentinel-file flag, same family as the
    init/test/sweep sentinels. Existence of the file IS the signal."""

    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = self.tmp.name
        self._orig_get_root = config.get_project_root
        config.get_project_root = lambda: self.tmpdir

    def tearDown(self):
        config.get_project_root = self._orig_get_root
        self.tmp.cleanup()
        reset_caches()

    def test_off_by_default(self):
        self.assertFalse(stream.is_edit_mode("sid"))

    def test_set_on_then_is_edit_mode_true(self):
        self.assertTrue(stream.set_edit_mode("sid", True))
        self.assertTrue(stream.is_edit_mode("sid"))
        self.assertTrue(os.path.exists(stream.get_edit_mode_path("sid")))

    def test_set_off_removes_sentinel(self):
        stream.set_edit_mode("sid", True)
        self.assertTrue(stream.set_edit_mode("sid", False))
        self.assertFalse(stream.is_edit_mode("sid"))
        self.assertFalse(os.path.exists(stream.get_edit_mode_path("sid")))

    def test_set_off_when_already_off_is_noop_success(self):
        self.assertTrue(stream.set_edit_mode("sid", False))
        self.assertFalse(stream.is_edit_mode("sid"))

    def test_empty_session_id_is_false_and_set_fails(self):
        self.assertFalse(stream.is_edit_mode(""))
        self.assertFalse(stream.set_edit_mode("", True))

    def test_flag_is_per_session(self):
        stream.set_edit_mode("sid-a", True)
        self.assertTrue(stream.is_edit_mode("sid-a"))
        self.assertFalse(stream.is_edit_mode("sid-b"))


# ---------------------------------------------------------------------------
# Init-gate degraded mode: count_init_denies_since_docread / is_degraded /
# degraded_tool_allowed / degraded_bash_is_readonly / is_manual_reset_cli
# ---------------------------------------------------------------------------
class TestCountInitDeniesSinceDocread(BaseStreamTest):
    def test_counts_denies_since_last_docread(self):
        self._write_jsonl([
            {"type": "docread", "name": "wf/WF_INIT"},
            {"type": "init_deny"},
            {"type": "init_deny"},
        ])
        self.assertEqual(stream.count_init_denies_since_docread(self.stream_path), 2)

    def test_docread_resets_the_streak(self):
        self._write_jsonl([
            {"type": "init_deny"},
            {"type": "init_deny"},
            {"type": "init_deny"},
            {"type": "docread", "name": "wf/WF_INIT"},
            {"type": "init_deny"},
        ])
        self.assertEqual(stream.count_init_denies_since_docread(self.stream_path), 1)

    def test_no_stream_file_returns_zero(self):
        missing = os.path.join(self.tmpdir, "missing.jsonl")
        self.assertEqual(stream.count_init_denies_since_docread(missing), 0)


class TestIsDegraded(BaseStreamTest):
    def test_below_threshold_not_degraded(self):
        self._write_jsonl([{"type": "init_deny"}, {"type": "init_deny"}])
        self.assertFalse(stream.is_degraded(self.stream_path))

    def test_at_threshold_is_degraded(self):
        self._write_jsonl([{"type": "init_deny"}] * stream.DEGRADED_DENY_THRESHOLD)
        self.assertTrue(stream.is_degraded(self.stream_path))

    def test_past_threshold_is_degraded(self):
        self._write_jsonl([{"type": "init_deny"}] * (stream.DEGRADED_DENY_THRESHOLD + 4))
        self.assertTrue(stream.is_degraded(self.stream_path))

    def test_docread_clears_degraded_state(self):
        self._write_jsonl(
            [{"type": "init_deny"}] * stream.DEGRADED_DENY_THRESHOLD
            + [{"type": "docread", "name": "wf/WF_INIT"}]
        )
        self.assertFalse(stream.is_degraded(self.stream_path))

    def test_mcp_unavailable_event_triggers_degraded_immediately(self):
        self._write_jsonl([{"type": "mcp_unavailable", "name": "mcp__plugin_swe_serena__read_memory"}])
        self.assertTrue(stream.is_degraded(self.stream_path))

    def test_explicit_degraded_event_is_sticky_until_docread(self):
        self._write_jsonl([{"type": "degraded", "trigger": "mcp_unavailable"}])
        self.assertTrue(stream.is_degraded(self.stream_path))

    def test_no_stream_file_not_degraded(self):
        missing = os.path.join(self.tmpdir, "missing.jsonl")
        self.assertFalse(stream.is_degraded(missing))


class TestDegradedBashIsReadonly(unittest.TestCase):
    def test_cat_is_readonly(self):
        self.assertTrue(stream.degraded_bash_is_readonly("cat foo.txt"))

    def test_git_status_is_readonly(self):
        self.assertTrue(stream.degraded_bash_is_readonly("git status"))

    def test_unittest_runner_is_not_readonly(self):
        # Test runners EXECUTE code — removed from the degraded allowlist.
        self.assertFalse(stream.degraded_bash_is_readonly(
            "python3 -m unittest discover -s tests -p 'test_*.py'"))

    def test_pytest_is_not_readonly(self):
        self.assertFalse(stream.degraded_bash_is_readonly("pytest tests/"))

    def test_claude_mcp_list_is_not_degraded_readonly(self):
        # `claude mcp list` is a Tier-1 RECOVERY command, not general Tier-2
        # degraded read-only Bash (it isn't codebase inspection).
        self.assertFalse(stream.degraded_bash_is_readonly("claude mcp list"))

    def test_chained_readonly_groups_all_readonly(self):
        self.assertTrue(stream.degraded_bash_is_readonly("ls -la && git log -5"))

    def test_mutating_command_not_readonly(self):
        self.assertFalse(stream.degraded_bash_is_readonly("rm -rf /tmp/x"))

    def test_chained_with_one_mutation_not_readonly(self):
        self.assertFalse(stream.degraded_bash_is_readonly("git status && echo x > f"))

    def test_empty_command_not_readonly(self):
        self.assertFalse(stream.degraded_bash_is_readonly(""))


class TestIsManualResetCli(unittest.TestCase):
    def test_reset_sentinel_invocation_detected(self):
        cmd = "python3 hooks/pre/swe_pre_tool_init_gate.py --reset-sentinel abc12345"
        self.assertTrue(stream.is_manual_reset_cli(cmd))

    def test_plain_init_gate_invocation_not_detected(self):
        self.assertFalse(stream.is_manual_reset_cli(
            "python3 hooks/pre/swe_pre_tool_init_gate.py"))

    def test_unrelated_command_not_detected(self):
        self.assertFalse(stream.is_manual_reset_cli("rm -rf /tmp/x"))

    def test_empty_command_not_detected(self):
        self.assertFalse(stream.is_manual_reset_cli(""))


class TestDegradedToolAllowed(unittest.TestCase):
    def test_read_tool_allowed(self):
        self.assertTrue(stream.degraded_tool_allowed("Read"))

    def test_grep_glob_ls_toolsearch_allowed(self):
        for name in ("Grep", "Glob", "LS", "ToolSearch"):
            self.assertTrue(stream.degraded_tool_allowed(name), name)

    def test_readonly_bash_allowed(self):
        self.assertTrue(stream.degraded_tool_allowed("Bash", "git status"))

    def test_manual_reset_cli_bash_allowed(self):
        cmd = "python3 hooks/pre/swe_pre_tool_init_gate.py --reset-sentinel"
        self.assertTrue(stream.degraded_tool_allowed("Bash", cmd))

    def test_mutating_bash_denied(self):
        self.assertFalse(stream.degraded_tool_allowed("Bash", "rm -rf /tmp/x"))

    def test_edit_denied(self):
        self.assertFalse(stream.degraded_tool_allowed("Edit"))

    def test_write_denied(self):
        self.assertFalse(stream.degraded_tool_allowed("Write"))

    def test_unrelated_mcp_tool_denied(self):
        self.assertFalse(stream.degraded_tool_allowed("mcp__plugin_swe_serena__write_memory"))


class TestCollectValuesSinceTaskStartAgentFilter(BaseStreamTest):
    """agent_id partitions docread accounting by WHO produced the event
    (core.session.get_agent_id). Default (agent_id=None) must keep counting
    ONLY events with no 'agent' field at all — pre-existing events never had
    one, so main-agent callers see identical behavior to before this param
    existed."""

    def _write(self, events):
        self._write_jsonl([{"type": "session_start"}] + events)

    def test_default_counts_only_events_without_agent_field(self):
        self._write([
            {"type": "docread", "name": "feature/FEATURE_X"},
            {"type": "docread", "name": "feature/FEATURE_Y", "agent": "a1"},
        ])
        result = stream.collect_values_since_task_start(self.stream_path)
        self.assertEqual(result, {"feature/feature_x"})

    def test_agent_id_counts_only_matching_agent(self):
        self._write([
            {"type": "docread", "name": "feature/FEATURE_X"},
            {"type": "docread", "name": "feature/FEATURE_Y", "agent": "a1"},
            {"type": "docread", "name": "feature/FEATURE_Z", "agent": "a2"},
        ])
        result = stream.collect_values_since_task_start(
            self.stream_path, agent_id="a1")
        self.assertEqual(result, {"feature/feature_y"})

    def test_unknown_agent_id_yields_empty(self):
        self._write([
            {"type": "docread", "name": "feature/FEATURE_X", "agent": "a1"},
        ])
        result = stream.collect_values_since_task_start(
            self.stream_path, agent_id="does-not-exist")
        self.assertEqual(result, set())

    def test_preexisting_events_with_no_agent_field_unaffected(self):
        # Simulates pre-upgrade stream data: no event ever carries 'agent'.
        self._write([
            {"type": "docread", "name": "feature/FEATURE_A"},
            {"type": "docread", "name": "dom/DOM_B"},
        ])
        result = stream.collect_values_since_task_start(self.stream_path)
        self.assertEqual(result, {"feature/feature_a", "dom/dom_b"})


if __name__ == "__main__":
    unittest.main()
