"""Tests for the WF_RESEARCH -> WF_CLASSIFY needs_implementation exit routing
and the read-hook inspect loop guard.

Targets:
  - prompt/swe_user_prompt_workflow: main()-level routing decision for
    WF_RESEARCH + an implement-intent prompt vs. a plain question, and the
    WF_EXECUTE possible_pivot path staying unchanged.
  - post/swe_post_read_state: count_inspect_loop() / inspect_loop_guard_message()
    pure helpers.

Stdlib unittest only; deterministic and offline. Follows the tempfile +
CLAUDE_PROJECT_DIR pattern used in test_hooks_prompt_stop_session.py.
"""
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_hook, reset_caches  # noqa: E402

prompt_mod = import_hook("prompt/swe_user_prompt_workflow")
read_state_mod = import_hook("post/swe_post_read_state")


# ---------------------------------------------------------------------------
# main()-level routing: WF_RESEARCH + implement-intent -> research_exit_directive
# ---------------------------------------------------------------------------
class TestResearchExitMainRouting(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = self.tmp.name
        os.makedirs(os.path.join(self.cwd, '.git'), exist_ok=True)
        os.makedirs(os.path.join(self.cwd, '.serena'), exist_ok=True)
        with open(os.path.join(self.cwd, '.serena', 'swe-setup-complete.json'), 'w') as f:
            json.dump({'complete': True}, f)
        self._orig_env = os.environ.get('CLAUDE_PROJECT_DIR')
        os.environ['CLAUDE_PROJECT_DIR'] = self.cwd

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop('CLAUDE_PROJECT_DIR', None)
        else:
            os.environ['CLAUDE_PROJECT_DIR'] = self._orig_env
        self.tmp.cleanup()
        reset_caches()

    def _write_state_file(self, session_id, state='WF_RESEARCH'):
        d = os.path.join(self.cwd, '.serena', 'swe-state')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f'{session_id}.state'), 'w') as f:
            json.dump({'current_state': state, 'session_id': session_id}, f)

    def _run_main(self, prompt, session_id):
        transcript = f'/x/{session_id}-0000-0000-0000-000000000000.jsonl'
        payload = {"prompt": prompt, "cwd": self.cwd, "transcript_path": transcript}
        buf = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
             mock.patch.object(os, 'getcwd', return_value=self.cwd), \
             mock.patch("sys.stdout", buf):
            try:
                prompt_mod.main()
            except SystemExit:
                pass
        return buf.getvalue()

    def _context(self, raw):
        result = json.loads(raw)
        return result.get("hookSpecificOutput", {}).get("additionalContext", "")

    def test_do_everything_in_research_emits_directive(self):
        sid = "aaaaaaaa"
        self._write_state_file(sid, 'WF_RESEARCH')
        out = self._context(self._run_main("do everything", sid))
        self.assertIn("wf/WF_CLASSIFY", out)
        self.assertIn("swe_wm_transition", out)
        self.assertIn("needs_implementation", out)

    def test_implement_it_in_research_emits_directive(self):
        sid = "bbbbbbbb"
        self._write_state_file(sid, 'WF_RESEARCH')
        out = self._context(self._run_main("implement it", sid))
        self.assertIn("needs_implementation", out)

    def test_fix_it_in_research_emits_directive(self):
        sid = "cccccccc"
        self._write_state_file(sid, 'WF_RESEARCH')
        out = self._context(self._run_main("fix it", sid))
        self.assertIn("needs_implementation", out)

    def test_okay_do_it_in_research_emits_directive(self):
        sid = "dddddddd"
        self._write_state_file(sid, 'WF_RESEARCH')
        out = self._context(self._run_main("okay, do it", sid))
        self.assertIn("needs_implementation", out)

    def test_plain_question_in_research_is_not_directive(self):
        sid = "eeeeeeee"
        self._write_state_file(sid, 'WF_RESEARCH')
        out = self._context(self._run_main("what does this function do?", sid))
        self.assertNotIn("needs_implementation", out)
        # Falls through to the ordinary ambiguous-intent note instead.
        self.assertIn("Ambiguous intent", out)

    def test_wf_execute_fix_spacing_unchanged_pivot_behavior(self):
        # Regression guard: the WF_EXECUTE possible_pivot path (a bare verb
        # mid-task) must still produce the ordinary pivot_analysis_note, not
        # the research-exit directive — RESEARCH_IMPLEMENT_RE only applies
        # inside WF_RESEARCH.
        sid = "facade00"
        self._write_state_file(sid, 'WF_EXECUTE')
        out = self._context(self._run_main("fix the spacing", sid))
        self.assertNotIn("needs_implementation", out)
        self.assertIn("Ambiguous intent", out)
        self.assertIn("swe_wm_transition", out)  # updated pivot advice


# ---------------------------------------------------------------------------
# post/swe_post_read_state — inspect loop-guard counting helper
# ---------------------------------------------------------------------------
class TestCountInspectLoop(unittest.TestCase):
    def test_single_inspect_below_threshold(self):
        events = [
            {"type": "inspect", "m": "WF_CLASSIFY", "from_s": "WF_RESEARCH"},
        ]
        count = read_state_mod.count_inspect_loop(events, "WF_CLASSIFY", "WF_RESEARCH")
        self.assertEqual(count, 1)
        self.assertEqual(
            read_state_mod.inspect_loop_guard_message(
                "WF_CLASSIFY", "WF_RESEARCH", "sess1", count),
            "")

    def test_second_same_name_same_from_state_triggers_message(self):
        events = [
            {"type": "inspect", "m": "WF_CLASSIFY", "from_s": "WF_RESEARCH"},
            {"type": "inspect", "m": "WF_CLASSIFY", "from_s": "WF_RESEARCH"},
        ]
        count = read_state_mod.count_inspect_loop(events, "WF_CLASSIFY", "WF_RESEARCH")
        self.assertEqual(count, 2)
        msg = read_state_mod.inspect_loop_guard_message(
            "WF_CLASSIFY", "WF_RESEARCH", "sess1", count)
        self.assertIn("LOOP GUARD", msg)
        self.assertIn("WF_CLASSIFY", msg)
        self.assertIn("WF_RESEARCH", msg)
        self.assertIn("swe_wm_transition", msg)
        self.assertIn("set_state.py", msg)
        self.assertIn("sess1", msg)

    def test_intervening_state_event_resets_count(self):
        events = [
            {"type": "inspect", "m": "WF_CLASSIFY", "from_s": "WF_RESEARCH"},
            {"type": "state", "from_s": "WF_RESEARCH", "to_s": "WF_CLASSIFY"},
            {"type": "inspect", "m": "WF_CLASSIFY", "from_s": "WF_RESEARCH"},
        ]
        count = read_state_mod.count_inspect_loop(events, "WF_CLASSIFY", "WF_RESEARCH")
        self.assertEqual(count, 1)

    def test_different_memory_names_counted_separately(self):
        events = [
            {"type": "inspect", "m": "WF_CLASSIFY", "from_s": "WF_RESEARCH"},
            {"type": "inspect", "m": "WF_EXECUTE", "from_s": "WF_RESEARCH"},
        ]
        self.assertEqual(
            read_state_mod.count_inspect_loop(events, "WF_CLASSIFY", "WF_RESEARCH"), 1)
        self.assertEqual(
            read_state_mod.count_inspect_loop(events, "WF_EXECUTE", "WF_RESEARCH"), 1)

    def test_different_from_state_counted_separately(self):
        events = [
            {"type": "inspect", "m": "WF_CLASSIFY", "from_s": "WF_RESEARCH"},
            {"type": "inspect", "m": "WF_CLASSIFY", "from_s": "WF_EXECUTE"},
        ]
        self.assertEqual(
            read_state_mod.count_inspect_loop(events, "WF_CLASSIFY", "WF_RESEARCH"), 1)
        self.assertEqual(
            read_state_mod.count_inspect_loop(events, "WF_CLASSIFY", "WF_EXECUTE"), 1)

    def test_empty_events_returns_zero(self):
        self.assertEqual(
            read_state_mod.count_inspect_loop([], "WF_CLASSIFY", "WF_RESEARCH"), 0)

    def test_threshold_constant_is_two(self):
        self.assertEqual(read_state_mod.INSPECT_LOOP_THRESHOLD, 2)


if __name__ == "__main__":
    unittest.main()
