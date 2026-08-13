"""Tests for the Feature-Knowledge-Sweep gate (docs-first, per-task).

The gate closes the "one-memory-then-act" loophole: same-session follow-up
tasks re-enter WF_CLASSIFY but nothing asserted the Step 4d sweep actually
happened before the first edit. New surfaces under test:

  - core/stream: get_feature_sentinel_path, collect_values_since_task_start
  - post/swe_post_read_state: _extract_memory_names, _search_credit
    (search surfacing only already-read docs = credit; NEW docs = no credit)
  - mcp/wm_server: _parse_memories_loaded, _check_memory_sweep
    ("Memories loaded" list verified against actual docreads → sweep sentinel)
  - pre/swe_pre_edit_validate: _is_test_target, sweep-sentinel deny wiring
  - core/state_manager: transition into WF_CLASSIFY clears the sweep sentinel

Stdlib unittest only. Deterministic + offline; IO via tempfile, path
resolution via monkeypatching the exact symbol each module imported.
"""
import inspect
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_hook, import_core, reset_caches  # noqa: E402

stream = import_core("swe_hooks.core.stream")
read_mod = import_hook("post/swe_post_read_state")
edit_mod = import_hook("pre/swe_pre_edit_validate")
wm = import_core("swe_hooks.mcp.wm_server")
config = import_core("swe_hooks.core.config")


def _write_stream(path, events):
    with open(path, "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


# ──────────────────────────────────────────────────────────────────
# core/stream — sentinel path + per-task value collection
# ──────────────────────────────────────────────────────────────────

class TestStreamHelpers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stream_path = os.path.join(self.tmp.name, "s1.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_feature_sentinel_path_shape(self):
        p = stream.get_feature_sentinel_path("abc123", "sweep")
        self.assertTrue(p.endswith("/.sweep_feature_abc123"))

    def test_collect_names_since_session_start(self):
        _write_stream(self.stream_path, [
            {"type": "docread", "name": "wf/WF_INIT"},
            {"type": "session_start", "s": "s1"},
            {"type": "docread", "name": "feature/FEATURE_X"},
            {"type": "gated"},
            {"type": "docread", "name": "dom/DOM_X"},
        ])
        names = stream.collect_values_since_task_start(self.stream_path)
        self.assertEqual(names, {"feature/feature_x", "dom/dom_x"})

    def test_collect_resets_at_reentry_into_wf_classify(self):
        # Follow-up task: reads from the FIRST task must not satisfy the sweep
        # for the SECOND task.
        _write_stream(self.stream_path, [
            {"type": "session_start", "s": "s1"},
            {"type": "docread", "name": "feature/FEATURE_A"},
            {"type": "state", "from_s": "WF_DONE", "to_s": "WF_CLASSIFY"},
            {"type": "docread", "name": "feature/FEATURE_B"},
        ])
        names = stream.collect_values_since_task_start(self.stream_path)
        self.assertEqual(names, {"feature/feature_b"})

    def test_collect_ignores_state_events_to_other_states(self):
        _write_stream(self.stream_path, [
            {"type": "docread", "name": "feature/FEATURE_A"},
            {"type": "state", "from_s": "WF_CLASSIFY", "to_s": "WF_EXECUTE"},
            {"type": "docread", "name": "ref/REF_B"},
        ])
        names = stream.collect_values_since_task_start(self.stream_path)
        self.assertEqual(names, {"feature/feature_a", "ref/ref_b"})

    def test_collect_missing_file_and_nameless_events(self):
        self.assertEqual(
            stream.collect_values_since_task_start(self.stream_path), set())
        _write_stream(self.stream_path, [{"type": "docread"}])
        self.assertEqual(
            stream.collect_values_since_task_start(self.stream_path), set())


# ──────────────────────────────────────────────────────────────────
# post/swe_post_read_state — memory-name extraction + search credit
# ──────────────────────────────────────────────────────────────────

class TestExtractMemoryNames(unittest.TestCase):
    def test_extracts_from_by_name_result_shape(self):
        text = ('{"memories": ["feedback/FEEDBACK_DOCS_FIRST_ALWAYS", '
                '"ref/REF_SWE_MEMORY_SEARCH"], '
                '"read_only_memories": ["templates/feedback/FEEDBACK_X"]}')
        names = read_mod._extract_memory_names(text)
        self.assertIn("feedback/feedback_docs_first_always", names)
        self.assertIn("ref/ref_swe_memory_search", names)

    def test_no_names_in_empty_result(self):
        self.assertEqual(read_mod._extract_memory_names("{}"), set())
        self.assertEqual(read_mod._extract_memory_names(""), set())


class TestSearchCredit(unittest.TestCase):
    def test_same_docs_already_read_gives_credit(self):
        # Operator rule: a re-search returning the SAME docs as the
        # authoritative already-read set passes (refills the gate).
        credit, new = read_mod._search_credit(
            {"feature/feature_x", "dom/dom_x"},
            {"feature/feature_x", "dom/dom_x", "ref/ref_y"})
        self.assertTrue(credit)
        self.assertEqual(new, set())

    def test_new_docs_surfaced_blocks_credit_until_read(self):
        credit, new = read_mod._search_credit(
            {"feature/feature_x", "ref/ref_new"},
            {"feature/feature_x"})
        self.assertFalse(credit)
        self.assertEqual(new, {"ref/ref_new"})

    def test_zero_hits_gives_credit(self):
        # Searched, nothing documented → exploring source is legitimate.
        credit, new = read_mod._search_credit(set(), {"feature/feature_x"})
        self.assertTrue(credit)
        self.assertEqual(new, set())


# ──────────────────────────────────────────────────────────────────
# mcp/wm_server — "Memories loaded" parse + sweep validation
# ──────────────────────────────────────────────────────────────────

class TestParseMemoriesLoaded(unittest.TestCase):
    def test_parses_comma_separated_line(self):
        content = ("- **Primary**: X - reason\n"
                   "- **Memories loaded**: feature/FEATURE_X, dom/DOM_X, "
                   "ref/REF_Y\n")
        names = wm._parse_memories_loaded(content)
        self.assertEqual(
            names, {"feature/feature_x", "dom/dom_x", "ref/ref_y"})

    def test_returns_none_when_line_absent(self):
        self.assertIsNone(wm._parse_memories_loaded("- **Primary**: X\n"))


class TestCheckMemorySweep(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.session = "sweeptest"
        self.stream_path = os.path.join(self.tmp.name, f"{self.session}.jsonl")
        self._orig_stream_path = wm.get_stream_path
        self._orig_sentinel = wm.get_feature_sentinel_path
        wm.get_stream_path = lambda sid: os.path.join(self.tmp.name, f"{sid}.jsonl")
        wm.get_feature_sentinel_path = (
            lambda sid, gate: os.path.join(self.tmp.name, f".{gate}_feature_{sid}"))

    def tearDown(self):
        wm.get_stream_path = self._orig_stream_path
        wm.get_feature_sentinel_path = self._orig_sentinel
        self.tmp.cleanup()

    def _sentinel(self):
        return os.path.join(self.tmp.name, f".sweep_feature_{self.session}")

    def test_all_listed_names_read_creates_sentinel(self):
        _write_stream(self.stream_path, [
            {"type": "docread", "name": "feature/FEATURE_X"},
            {"type": "docread", "name": "dom/DOM_X"},
        ])
        content = "- **Memories loaded**: feature/FEATURE_X, dom/DOM_X\n"
        err = wm._check_memory_sweep(self.session, content)
        self.assertIsNone(err)
        self.assertTrue(os.path.exists(self._sentinel()))

    def test_listed_but_unread_names_rejected(self):
        _write_stream(self.stream_path, [
            {"type": "docread", "name": "feature/FEATURE_X"},
        ])
        content = "- **Memories loaded**: feature/FEATURE_X, dom/DOM_X\n"
        err = wm._check_memory_sweep(self.session, content)
        self.assertIsNotNone(err)
        self.assertIn("dom/dom_x", err.lower())
        self.assertFalse(os.path.exists(self._sentinel()))

    def test_follow_up_task_cannot_reuse_prior_task_reads(self):
        # Reads before re-entry into WF_CLASSIFY do not count for this task.
        _write_stream(self.stream_path, [
            {"type": "docread", "name": "feature/FEATURE_X"},
            {"type": "state", "from_s": "WF_DONE", "to_s": "WF_CLASSIFY"},
        ])
        content = "- **Memories loaded**: feature/FEATURE_X\n"
        err = wm._check_memory_sweep(self.session, content)
        self.assertIsNotNone(err)

    def test_requires_a_feature_memory_or_no_feature_token(self):
        _write_stream(self.stream_path, [
            {"type": "docread", "name": "ref/REF_Y"},
        ])
        err = wm._check_memory_sweep(
            self.session, "- **Memories loaded**: ref/REF_Y\n")
        self.assertIsNotNone(err)
        # Explicit no-feature declaration is the sanctioned exception.
        err2 = wm._check_memory_sweep(
            self.session, "- **Primary**: no-feature\n"
                          "- **Memories loaded**: ref/REF_Y\n")
        self.assertIsNone(err2)

    def test_empty_list_rejected(self):
        err = wm._check_memory_sweep(
            self.session, "- **Memories loaded**:\n")
        self.assertIsNotNone(err)


class TestUpdateSectionSweepWiring(unittest.TestCase):
    """tool_swe_wm_update_section validates Affected Features writes."""

    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        self.session = "wired001"
        os.makedirs(os.path.join(self.tmp.name, ".git"))
        os.makedirs(os.path.join(self.tmp.name, ".serena", "memories"))
        os.makedirs(os.path.join(self.tmp.name, ".serena", "streams"))
        wm_path = os.path.join(
            self.tmp.name, ".serena", "memories", f"WM_{self.session}.md")
        with open(wm_path, "w") as f:
            f.write(f"# Working Memory: Session {self.session}\n\n"
                    "## Current Task\n\n(x)\n\n## Affected Features\n\n(tbd)\n")
        # Pin project root the way test_wm_server does; daemon staleness off.
        config._PROJECT_ROOT = self.tmp.name
        self._saved_stale = config._is_stale_daemon
        config._is_stale_daemon = lambda: False
        # Route stream/sentinel paths into the tmp streams dir.
        self._orig_stream_path = wm.get_stream_path
        self._orig_sentinel = wm.get_feature_sentinel_path
        streams = os.path.join(self.tmp.name, ".serena", "streams")
        wm.get_stream_path = lambda sid: os.path.join(streams, f"{sid}.jsonl")
        wm.get_feature_sentinel_path = (
            lambda sid, gate: os.path.join(streams, f".{gate}_feature_{sid}"))
        self.stream_path = wm.get_stream_path(self.session)

    def tearDown(self):
        config._is_stale_daemon = self._saved_stale
        config._PROJECT_ROOT = None
        wm.get_stream_path = self._orig_stream_path
        wm.get_feature_sentinel_path = self._orig_sentinel
        self.tmp.cleanup()
        reset_caches()

    def test_affected_features_with_unread_names_errors(self):
        _write_stream(self.stream_path, [
            {"type": "docread", "name": "feature/FEATURE_X"},
        ])
        result = wm.tool_swe_wm_update_section(
            "Affected Features",
            "- **Memories loaded**: feature/FEATURE_X, dom/DOM_MISSING",
            session_id=self.session)
        self.assertIn("error", result)

    def test_affected_features_with_verified_sweep_succeeds(self):
        _write_stream(self.stream_path, [
            {"type": "docread", "name": "feature/FEATURE_X"},
            {"type": "docread", "name": "dom/DOM_X"},
        ])
        result = wm.tool_swe_wm_update_section(
            "Affected Features",
            "- **Primary**: X\n- **Memories loaded**: feature/FEATURE_X, dom/DOM_X",
            session_id=self.session)
        self.assertTrue(result.get("success"))
        self.assertTrue(os.path.exists(
            wm.get_feature_sentinel_path(self.session, "sweep")))

    def test_other_sections_not_gated(self):
        result = wm.tool_swe_wm_update_section(
            "Notes", "free-form", session_id=self.session)
        self.assertTrue(result.get("success"))


# ──────────────────────────────────────────────────────────────────
# pre/swe_pre_edit_validate — sweep deny + test-target detection
# ──────────────────────────────────────────────────────────────────

class TestIsTestTarget(unittest.TestCase):
    def test_test_paths_match(self):
        for p in ("tests/test_foo.py", "a/b/tests/x.php", "e2e/checkout.spec.ts",
                  "src/thing.test.tsx", "tests/specs/x.feature",
                  "plugin/tests/FooTest.php"):
            self.assertTrue(edit_mod._is_test_target(p), p)

    def test_non_test_paths_do_not_match(self):
        for p in ("src/index.ts", "hooks/pre/gate.py", "attest/readme.md",
                  "contest.php", "latest/notes.md"):
            self.assertFalse(edit_mod._is_test_target(p), p)


class TestSweepGateVerdict(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.session = "gate0001"
        self.streams = os.path.join(self.tmp.name, ".serena", "streams")
        os.makedirs(self.streams)
        self._orig_sentinel = edit_mod.get_feature_sentinel_path
        self._orig_stream = edit_mod.get_stream_path
        edit_mod.get_feature_sentinel_path = (
            lambda sid, gate: os.path.join(self.streams, f".{gate}_feature_{sid}"))
        edit_mod.get_stream_path = (
            lambda sid: os.path.join(self.streams, f"{sid}.jsonl"))
        self._orig_root = edit_mod.get_project_root
        edit_mod.get_project_root = lambda: self.tmp.name

    def tearDown(self):
        edit_mod.get_feature_sentinel_path = self._orig_sentinel
        edit_mod.get_stream_path = self._orig_stream
        edit_mod.get_project_root = self._orig_root
        self.tmp.cleanup()

    def _arm_managed_session(self):
        # Init sentinel + stream = managed session.
        open(os.path.join(self.streams, f".init_{self.session}"), "w").close()
        _write_stream(os.path.join(self.streams, f"{self.session}.jsonl"),
                      [{"type": "session_start", "s": self.session}])

    def _create_sweep(self):
        open(os.path.join(
            self.streams, f".sweep_feature_{self.session}"), "w").close()

    def test_denies_edit_without_sweep_sentinel(self):
        self._arm_managed_session()
        msg = edit_mod._sweep_gate_verdict(
            self.session, {"file_path": "src/foo.py"})
        self.assertIsNotNone(msg)
        self.assertIn("SWEEP", msg.upper())

    def test_allows_edit_with_sweep_sentinel(self):
        self._arm_managed_session()
        self._create_sweep()
        self.assertIsNone(edit_mod._sweep_gate_verdict(
            self.session, {"file_path": "src/foo.py"}))

    def test_unmanaged_session_never_gated(self):
        # No init sentinel = spawned agent / unmanaged — fail open.
        self.assertIsNone(edit_mod._sweep_gate_verdict(
            self.session, {"file_path": "src/foo.py"}))

    def test_wm_file_writes_exempt(self):
        self._arm_managed_session()
        self.assertIsNone(edit_mod._sweep_gate_verdict(
            self.session,
            {"file_path": ".serena/memories/WM_gate0001.md"}))

    def test_test_target_requires_test_docs_when_they_exist(self):
        self._arm_managed_session()
        self._create_sweep()
        # Project documents its test harness → writing a test without having
        # read the harness docs THIS TASK is denied.
        dev_dir = os.path.join(self.tmp.name, ".serena", "memory", "dev")
        os.makedirs(dev_dir)
        with open(os.path.join(dev_dir, "DEV_TESTS.md"), "w") as f:
            f.write("x")
        msg = edit_mod._sweep_gate_verdict(
            self.session, {"file_path": "tests/test_new.py"})
        self.assertIsNotNone(msg)
        self.assertIn("dev/DEV_TESTS", msg)

    def test_test_target_passes_once_test_docs_read(self):
        self._arm_managed_session()
        self._create_sweep()
        dev_dir = os.path.join(self.tmp.name, ".serena", "memory", "dev")
        os.makedirs(dev_dir)
        with open(os.path.join(dev_dir, "DEV_TESTS.md"), "w") as f:
            f.write("x")
        _write_stream(os.path.join(self.streams, f"{self.session}.jsonl"), [
            {"type": "session_start", "s": self.session},
            {"type": "docread", "name": "dev/DEV_TESTS"},
        ])
        self.assertIsNone(edit_mod._sweep_gate_verdict(
            self.session, {"file_path": "tests/test_new.py"}))

    def test_test_target_ungated_when_project_has_no_test_docs(self):
        self._arm_managed_session()
        self._create_sweep()
        self.assertIsNone(edit_mod._sweep_gate_verdict(
            self.session, {"file_path": "tests/test_new.py"}))


# ──────────────────────────────────────────────────────────────────
# Task-boundary correctness — docreads survive continuation prompts
# and mid-task slash commands; only a REAL new task resets the sweep
# ──────────────────────────────────────────────────────────────────

class TestTaskBoundaryStamping(unittest.TestCase):
    """Regression guards for the sweep task-boundary bug: the boundary in
    events_since_task_start() advances on 'session_start' and
    to_s=WF_CLASSIFY 'state' events, so those events must be emitted ONLY
    at genuine task starts.

    Observed live (session 94aee7ae): a mid-task slash-command invocation
    re-ran the prompt hook's FAST TRACK, which re-stamped 'session_start'
    and silently dropped every docread before it — sweep verification then
    rejected memories the agent HAD read this task, and each /swe-wm-update
    invocation re-stamped again (unwinnable loop). Inverse defect: genuine
    new-task transitions via the prompt hook appended NO boundary event, so
    follow-up tasks could reuse a prior task's reads.
    """

    prompt_mod = import_hook("prompt/swe_user_prompt_workflow")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.session = "bnd00001"
        self.stream_path = os.path.join(self.tmp.name, f"{self.session}.jsonl")
        self._orig_stream_path = wm.get_stream_path
        self._orig_sentinel = wm.get_feature_sentinel_path
        wm.get_stream_path = lambda sid: os.path.join(self.tmp.name, f"{sid}.jsonl")
        wm.get_feature_sentinel_path = (
            lambda sid, gate: os.path.join(self.tmp.name, f".{gate}_feature_{sid}"))

    def tearDown(self):
        wm.get_stream_path = self._orig_stream_path
        wm.get_feature_sentinel_path = self._orig_sentinel
        self.tmp.cleanup()

    def test_append_task_boundary_resets_sweep(self):
        # A REAL new task stamps a boundary; prior reads stop counting.
        _write_stream(self.stream_path, [
            {"type": "session_start", "s": self.session},
            {"type": "docread", "name": "feature/FEATURE_X"},
        ])
        stream.append_task_boundary(self.stream_path, "WF_DONE", self.session)
        err = wm._check_memory_sweep(
            self.session, "- **Memories loaded**: feature/FEATURE_X\n")
        self.assertIsNotNone(err)
        self.assertIn("feature/feature_x", err.lower())

    def test_boundary_event_shape_matches_collector(self):
        # The stamped event must be exactly what events_since_task_start keys
        # on: type=state, to_s=WF_CLASSIFY.
        stream.append_task_boundary(self.stream_path, "WF_EXECUTE", self.session)
        with open(self.stream_path) as f:
            event = json.loads(f.readline())
        self.assertEqual(event["type"], "state")
        self.assertEqual(event["to_s"], "WF_CLASSIFY")
        self.assertEqual(event["from_s"], "WF_EXECUTE")

    def test_wm_recreate_without_stamp_preserves_task_reads(self):
        # Mid-task slash command (FAST TRACK re-invocation): WM is recreated
        # but the task boundary must NOT advance — docreads from earlier in
        # the task still satisfy the sweep afterward.
        _write_stream(self.stream_path, [
            {"type": "session_start", "s": self.session},
            {"type": "docread", "name": "feature/FEATURE_X"},
            {"type": "docread", "name": "dom/DOM_X"},
        ])
        os.environ["CLAUDE_PROJECT_DIR"] = self.tmp.name
        try:
            self.prompt_mod.create_wm_and_sentinel(
                self.tmp.name, self.session,
                initial_state="WF_EXECUTE", prev_state="WF_FASTTRACK",
                task="Direct command: /swe-wm-update",
                stamp_session_start=False)
        finally:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        names = stream.collect_values_since_task_start(self.stream_path)
        self.assertEqual(names, {"feature/feature_x", "dom/dom_x"})
        err = wm._check_memory_sweep(
            self.session,
            "- **Memories loaded**: feature/FEATURE_X, dom/DOM_X\n")
        self.assertIsNone(err)

    def test_fast_track_reinvocation_does_not_restamp(self):
        # Source guard (main() reads stdin): the FAST TRACK block must skip
        # the session_start stamp when the session already has a state file.
        src = inspect.getsource(self.prompt_mod.main)
        self.assertIn("stamp_session_start", src)

    def test_new_task_branch_stamps_boundary(self):
        # Source guard: genuine new-task transitions into WF_CLASSIFY stamp
        # the task boundary; the unknown-intent branch must NOT (an unclear
        # or continuation prompt never invalidates the task's reads).
        src = inspect.getsource(self.prompt_mod.main)
        self.assertIn("append_task_boundary", src)


# ──────────────────────────────────────────────────────────────────
# core/state_manager — sweep sentinel cleared on WF_CLASSIFY entry
# ──────────────────────────────────────────────────────────────────

class TestSweepSentinelClearedOnClassify(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["CLAUDE_PROJECT_DIR"] = self.tmp.name
        self.sm_mod = import_core("swe_hooks.core.state_manager")

    def tearDown(self):
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.tmp.cleanup()
        reset_caches()

    def test_transition_into_classify_removes_sweep_sentinel(self):
        session = "clr00001"
        sentinel = stream.get_feature_sentinel_path(session, "sweep")
        os.makedirs(os.path.dirname(sentinel), exist_ok=True)
        open(sentinel, "w").close()
        self.assertTrue(os.path.exists(sentinel))
        self.sm_mod.clear_sweep_sentinel(session)
        self.assertFalse(os.path.exists(sentinel))


if __name__ == "__main__":
    unittest.main()
