"""Tests for swe_hooks.core.state_manager.

Covers the pure transition logic (is_valid_transition, is_forward_read_transition),
the transition-matrix loader + fail-closed behavior, module-level constants
(_FORWARD_RANK, STATE_ICONS, PLAN_MODE_STATES, EXIT_PLAN_MODE_STATES), and the
pure StateManager methods (get_current_state, get_icon, increment/reset edits,
should_checkpoint, get_working_memory, is_plan_mode).

StateManager instances are constructed against a real temp WM markdown file in a
tmpdir .serena/memories/ directory. get_project_root is monkeypatched (on the
config module the state_manager delegates to) so all path resolution lands inside
the tmpdir. No network, no real Serena, no real git.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_core, reset_caches  # noqa: E402

mod = import_core("swe_hooks.core.state_manager")
config = import_core("swe_hooks.core.config")


# A minimal but valid WM markdown with a Workflow Context section.
def _wm_markdown(current_state="WF_CLASSIFY", feature_keys=None, session_id=None):
    lines = [
        "# WORKING MEMORY",
        "",
        "## Session Context",
        "**Status**: In progress",
        "",
        "## Workflow Context",
        f"**Current State**: {current_state}",
    ]
    if feature_keys:
        lines.append(f"**Feature Key(s)**: {', '.join(feature_keys)}")
    if session_id:
        lines.append(f"**Session ID**: {session_id}")
    lines += [
        "",
        "## Progress",
        "- started",
        "",
    ]
    return "\n".join(lines)


class TransitionMatrixLoaderTest(unittest.TestCase):
    def setUp(self):
        reset_caches()

    def tearDown(self):
        reset_caches()

    def test_loads_real_matrix_from_states_json(self):
        matrix = mod.load_transition_matrix()
        # Real states.json ships a non-empty transitionMatrix.
        self.assertIsInstance(matrix, dict)
        self.assertIn("WF_CLASSIFY", matrix)
        self.assertIn("WF_EXECUTE", matrix["WF_CLASSIFY"])
        self.assertEqual(matrix["WF_DONE"], ["WF_CLASSIFY"])

    def test_result_is_cached(self):
        first = mod.load_transition_matrix()
        # Cache is populated after the first call.
        self.assertIsNotNone(mod._transition_matrix_cache)
        second = mod.load_transition_matrix()
        self.assertIs(first, second)


class IsValidTransitionTest(unittest.TestCase):
    def setUp(self):
        reset_caches()
        # Seed a known matrix so tests are independent of states.json edits.
        mod._transition_matrix_cache = {
            "WF_CLASSIFY": ["WF_ARCH_REVIEW", "WF_EXECUTE", "WF_RESEARCH", "WF_DEBUG_TDD", "WF_CLARIFY"],
            "WF_EXECUTE": ["WF_CHECKPOINT", "WF_VERIFY"],
            "WF_RESEARCH": ["WF_CLASSIFY", "WF_DONE"],
            "WF_DONE": ["WF_CLASSIFY"],
            "WF_CLARIFY": ["(return_to_caller)"],
            "WF_TERMINAL_NONE": [None],
        }

    def tearDown(self):
        reset_caches()

    def test_valid_transition(self):
        ok, msg = mod.is_valid_transition("WF_CLASSIFY", "WF_EXECUTE")
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_invalid_transition_blocks(self):
        ok, msg = mod.is_valid_transition("WF_EXECUTE", "WF_RESEARCH")
        self.assertFalse(ok)
        self.assertIn("BLOCKED", msg)
        self.assertIn("Invalid transition", msg)
        self.assertIn("WF_EXECUTE", msg)

    def test_wf_init_can_go_anywhere(self):
        for src in ("WF_INIT", "UNINITIALIZED", "SessionStart"):
            ok, msg = mod.is_valid_transition(src, "WF_ANYTHING_AT_ALL")
            self.assertTrue(ok, src)
            self.assertEqual(msg, "")

    def test_wf_clarify_returns_to_any_caller(self):
        ok, msg = mod.is_valid_transition("WF_CLARIFY", "WF_EXECUTE")
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_unknown_from_state_blocks(self):
        ok, msg = mod.is_valid_transition("WF_BOGUS", "WF_EXECUTE")
        self.assertFalse(ok)
        self.assertIn("Unknown state WF_BOGUS", msg)

    def test_terminal_state_with_only_none_targets_allows_anything(self):
        # valid_targets filters out None -> empty -> terminal -> allowed.
        ok, msg = mod.is_valid_transition("WF_TERMINAL_NONE", "WF_WHATEVER")
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_fail_closed_empty_matrix_allows_only_init(self):
        mod._transition_matrix_cache = {}
        ok, msg = mod.is_valid_transition("WF_INIT", "WF_CLASSIFY")
        self.assertTrue(ok)
        ok2, msg2 = mod.is_valid_transition("UNINITIALIZED", "WF_EXECUTE")
        self.assertTrue(ok2)

    def test_fail_closed_empty_matrix_blocks_non_init(self):
        mod._transition_matrix_cache = {}
        ok, msg = mod.is_valid_transition("WF_EXECUTE", "WF_VERIFY")
        self.assertFalse(ok)
        self.assertIn("State machine unavailable", msg)


class IsForwardReadTransitionTest(unittest.TestCase):
    def setUp(self):
        reset_caches()
        mod._transition_matrix_cache = {
            "WF_CLASSIFY": ["WF_ARCH_REVIEW", "WF_EXECUTE", "WF_RESEARCH", "WF_DEBUG_TDD", "WF_CLARIFY"],
            "WF_EXECUTE": ["WF_CHECKPOINT", "WF_VERIFY"],
            "WF_RESEARCH": ["WF_CLASSIFY", "WF_DONE"],
            "WF_VERIFY": ["WF_DONE", "WF_EXECUTE", "WF_CLASSIFY"],
            "WF_ARCH_REVIEW": ["WF_EXECUTE", "WF_ARCH_REVIEW", "WF_CLARIFY"],
            "WF_DONE": ["WF_CLASSIFY"],
        }

    def tearDown(self):
        reset_caches()

    def test_init_bootstrap_never_forwards(self):
        for src in ("WF_INIT", "UNINITIALIZED", "SessionStart"):
            ok, reason = mod.is_forward_read_transition(src, "WF_CLASSIFY")
            self.assertFalse(ok, src)
            self.assertIn("init bootstrap", reason)

    def test_reading_into_clarify_never_forwards(self):
        ok, reason = mod.is_forward_read_transition("WF_CLASSIFY", "WF_CLARIFY")
        self.assertFalse(ok)
        self.assertIn("WF_CLARIFY", reason)

    def test_forward_valid_transition_advances(self):
        # WF_CLASSIFY (rank 1) -> WF_EXECUTE (rank 4): forward + valid.
        ok, reason = mod.is_forward_read_transition("WF_CLASSIFY", "WF_EXECUTE")
        self.assertTrue(ok)
        self.assertIn("forward read transition", reason)

    def test_forward_equal_rank_advances(self):
        # WF_EXECUTE (4) -> WF_CHECKPOINT (4): equal rank counts as forward.
        ok, reason = mod.is_forward_read_transition("WF_EXECUTE", "WF_CHECKPOINT")
        self.assertTrue(ok)

    def test_backward_read_does_not_advance(self):
        # WF_VERIFY (rank 5) -> WF_EXECUTE (rank 4): valid matrix move but backward.
        ok, reason = mod.is_forward_read_transition("WF_VERIFY", "WF_EXECUTE")
        self.assertFalse(ok)
        self.assertIn("read-ahead/back", reason)

    def test_invalid_matrix_transition_does_not_advance(self):
        # WF_EXECUTE -> WF_RESEARCH is not in the matrix targets.
        ok, reason = mod.is_forward_read_transition("WF_EXECUTE", "WF_RESEARCH")
        self.assertFalse(ok)
        self.assertIn("BLOCKED", reason)

    def test_research_backward_to_classify_not_advanced(self):
        # WF_RESEARCH (rank 2) -> WF_CLASSIFY (rank 1): valid but backward.
        ok, reason = mod.is_forward_read_transition("WF_RESEARCH", "WF_CLASSIFY")
        self.assertFalse(ok)
        self.assertIn("read-ahead/back", reason)


class ForwardRankConstantTest(unittest.TestCase):
    def test_clarify_rank_is_negative_one(self):
        self.assertEqual(mod._FORWARD_RANK["WF_CLARIFY"], -1)

    def test_rank_ordering_is_monotonic_forward(self):
        rank = mod._FORWARD_RANK
        self.assertEqual(rank["WF_INIT"], 0)
        self.assertEqual(rank["WF_CLASSIFY"], 1)
        self.assertEqual(rank["WF_RESEARCH"], 2)
        self.assertEqual(rank["WF_ARCH_REVIEW"], 3)
        self.assertEqual(rank["WF_EXECUTE"], 4)
        self.assertEqual(rank["WF_VERIFY"], 5)
        self.assertEqual(rank["WF_DONE"], 6)
        # Strict ordering along the happy path.
        self.assertLess(rank["WF_CLASSIFY"], rank["WF_EXECUTE"])
        self.assertLess(rank["WF_EXECUTE"], rank["WF_DONE"])

    def test_execute_family_shares_rank(self):
        rank = mod._FORWARD_RANK
        self.assertEqual(rank["WF_EXECUTE"], rank["WF_CHECKPOINT"])
        self.assertEqual(rank["WF_EXECUTE"], rank["WF_DEBUG_TDD"])


class ModuleConstantsTest(unittest.TestCase):
    def test_state_icons_spot_check(self):
        self.assertEqual(mod.STATE_ICONS["WF_INIT"], "🎬")
        self.assertEqual(mod.STATE_ICONS["WF_EXECUTE"], "⚡")
        self.assertEqual(mod.STATE_ICONS["WF_DONE"], "🎉")

    def test_plan_mode_states(self):
        self.assertEqual(mod.PLAN_MODE_STATES, {"WF_ARCH_REVIEW"})

    def test_exit_plan_mode_states(self):
        self.assertEqual(
            mod.EXIT_PLAN_MODE_STATES,
            {"WF_EXECUTE", "WF_CHECKPOINT", "WF_VERIFY", "WF_DEBUG_TDD"},
        )
        # Disjoint from PLAN_MODE_STATES.
        self.assertEqual(mod.PLAN_MODE_STATES & mod.EXIT_PLAN_MODE_STATES, set())


class _StateManagerBase(unittest.TestCase):
    """Sets up a tmpdir project root with one WM file and points
    config.get_project_root at it, so StateManager.__init__ finds the WM."""

    def setUp(self):
        reset_caches()
        self._orig_get_project_root = config.get_project_root
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        # Real git dir (harness rule: only a tmpdir .git).
        os.makedirs(os.path.join(self.root, ".git"), exist_ok=True)
        self.memories_dir = os.path.join(self.root, ".serena", "memories")
        os.makedirs(self.memories_dir, exist_ok=True)
        config.get_project_root = lambda: self.root

    def tearDown(self):
        config.get_project_root = self._orig_get_project_root
        self.tmp.cleanup()
        reset_caches()

    def _write_wm(self, name="WM_20260101_120000", **kw):
        path = os.path.join(self.memories_dir, f"{name}.md")
        with open(path, "w") as f:
            f.write(_wm_markdown(**kw))
        return path


class StateManagerConstructionTest(_StateManagerBase):
    def test_loads_current_state_from_wm(self):
        self._write_wm(current_state="WF_CLASSIFY")
        sm = mod.StateManager(self.root)
        self.assertEqual(sm.get_current_state(), "WF_CLASSIFY")

    def test_loads_feature_keys_from_wm(self):
        self._write_wm(current_state="WF_EXECUTE", feature_keys=["SWE", "STATE"])
        sm = mod.StateManager(self.root)
        self.assertEqual(sm.state["feature_keys"], ["SWE", "STATE"])

    def test_no_wm_file_defaults_to_wf_init(self):
        # No WM written -> fallback branch.
        sm = mod.StateManager(self.root)
        self.assertEqual(sm.get_current_state(), "WF_INIT")
        self.assertIsNone(sm.state["working_memory_file"])
        self.assertFalse(sm.is_plan_mode())

    def test_working_memory_filename_derived_from_path(self):
        self._write_wm(name="WM_20260101_120000", current_state="WF_CLASSIFY")
        sm = mod.StateManager(self.root)
        self.assertEqual(sm.get_working_memory(), "WM_20260101_120000")

    def test_plan_mode_true_when_state_is_arch_review(self):
        self._write_wm(current_state="WF_ARCH_REVIEW")
        sm = mod.StateManager(self.root)
        self.assertTrue(sm.is_plan_mode())

    def test_plan_mode_false_for_non_plan_state(self):
        self._write_wm(current_state="WF_EXECUTE")
        sm = mod.StateManager(self.root)
        self.assertFalse(sm.is_plan_mode())

    def test_most_recent_wm_wins(self):
        # Two WMs; newest filename (reverse sort) is authoritative.
        self._write_wm(name="WM_20250101_000000", current_state="WF_RESEARCH")
        self._write_wm(name="WM_20260101_120000", current_state="WF_VERIFY")
        sm = mod.StateManager(self.root)
        self.assertEqual(sm.get_current_state(), "WF_VERIFY")


class StateManagerPureMethodsTest(_StateManagerBase):
    def _sm(self, current_state="WF_EXECUTE"):
        self._write_wm(current_state=current_state)
        return mod.StateManager(self.root)

    def test_get_current_state_default_when_missing_key(self):
        sm = self._sm()
        # Simulate a state dict missing the key entirely.
        sm.state.pop("current_state", None)
        self.assertEqual(sm.get_current_state(), "UNINITIALIZED")

    def test_get_icon_uses_current_state_by_default(self):
        sm = self._sm(current_state="WF_EXECUTE")
        self.assertEqual(sm.get_icon(), "⚡")

    def test_get_icon_explicit_state(self):
        sm = self._sm()
        self.assertEqual(sm.get_icon("WF_DONE"), "🎉")

    def test_get_icon_unknown_state_default_pin(self):
        sm = self._sm()
        self.assertEqual(sm.get_icon("WF_NOT_A_STATE"), "📍")

    def test_increment_edits_counts_up(self):
        sm = self._sm()
        self.assertEqual(sm.increment_edits(), 1)
        self.assertEqual(sm.increment_edits("some/file.py"), 2)
        self.assertEqual(sm.state["edits_since_checkpoint"], 2)

    def test_reset_edit_counter(self):
        sm = self._sm()
        sm.increment_edits()
        sm.increment_edits()
        sm.reset_edit_counter()
        self.assertEqual(sm.state["edits_since_checkpoint"], 0)

    def test_should_checkpoint_default_threshold_is_three(self):
        sm = self._sm()
        self.assertFalse(sm.should_checkpoint())  # 0 edits
        sm.increment_edits()
        sm.increment_edits()
        self.assertFalse(sm.should_checkpoint())  # 2 < 3
        sm.increment_edits()
        self.assertTrue(sm.should_checkpoint())    # 3 >= 3

    def test_should_checkpoint_custom_threshold(self):
        sm = self._sm()
        sm.increment_edits()
        self.assertTrue(sm.should_checkpoint(threshold=1))
        self.assertFalse(sm.should_checkpoint(threshold=5))

    def test_should_checkpoint_missing_counter_key(self):
        sm = self._sm()
        sm.state.pop("edits_since_checkpoint", None)
        self.assertFalse(sm.should_checkpoint())

    def test_get_working_memory_falls_back_to_state_dict(self):
        sm = self._sm()
        sm.wm_filename = None
        sm.state["working_memory_file"] = "WM_fallback"
        self.assertEqual(sm.get_working_memory(), "WM_fallback")

    def test_get_working_memory_none_when_nothing_set(self):
        sm = self._sm()
        sm.wm_filename = None
        sm.state["working_memory_file"] = None
        self.assertIsNone(sm.get_working_memory())

    def test_is_plan_mode_reflects_state_flag(self):
        sm = self._sm()
        self.assertFalse(sm.is_plan_mode())
        sm.state["plan_mode"] = True
        self.assertTrue(sm.is_plan_mode())

    def test_is_plan_mode_missing_key_defaults_false(self):
        sm = self._sm()
        sm.state.pop("plan_mode", None)
        self.assertFalse(sm.is_plan_mode())


if __name__ == "__main__":
    unittest.main()
