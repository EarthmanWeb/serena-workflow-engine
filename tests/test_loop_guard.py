"""Tests for swe_hooks.core.loop_guard (pure functions) and its integration
into StateManager.transition_to (cap refusal, force bypass, oscillation
warning, subflow reason, CLARIFY return rules, mtime cache invalidation,
ranks-from-json).

Deterministic + offline: no network, no real Serena, no real git. IO goes
through tempfile.TemporaryDirectory. get_project_root is monkeypatched on the
config module (which state_manager and stream both delegate to) so all path
resolution lands inside the tmpdir.
"""
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import import_core, reset_caches  # noqa: E402

loop_guard = import_core("swe_hooks.core.loop_guard")
sm = import_core("swe_hooks.core.state_manager")
config = import_core("swe_hooks.core.config")
stream = import_core("swe_hooks.core.stream")


def _state_event(from_s, to_s):
    return {"type": "state", "from_s": from_s, "to_s": to_s}


class EdgeKeyTest(unittest.TestCase):
    def test_edge_key_directed(self):
        self.assertEqual(loop_guard.edge_key("A", "B"), "A->B")
        self.assertEqual(loop_guard.edge_key("B", "A"), "B->A")

    def test_bidirectional_key_order_independent(self):
        self.assertEqual(loop_guard.bidirectional_key("A", "B"), loop_guard.bidirectional_key("B", "A"))
        self.assertEqual(loop_guard.bidirectional_key("WF_EXECUTE", "WF_CHECKPOINT"), "WF_CHECKPOINT<->WF_EXECUTE")


class CountEdgeTraversalsTest(unittest.TestCase):
    def test_counts_directed_only(self):
        events = [_state_event("A", "B"), _state_event("B", "A"), _state_event("A", "B")]
        self.assertEqual(loop_guard.count_edge_traversals(events, "A", "B"), 2)
        self.assertEqual(loop_guard.count_edge_traversals(events, "B", "A"), 1)

    def test_counts_bidirectional(self):
        events = [_state_event("A", "B"), _state_event("B", "A"), _state_event("A", "B")]
        self.assertEqual(loop_guard.count_edge_traversals(events, "A", "B", bidirectional=True), 3)

    def test_ignores_non_state_events(self):
        events = [{"type": "edit"}, _state_event("A", "B"), {"type": "checkpoint"}]
        self.assertEqual(loop_guard.count_edge_traversals(events, "A", "B"), 1)

    def test_empty_events(self):
        self.assertEqual(loop_guard.count_edge_traversals([], "A", "B"), 0)


class CheckLoopCapTest(unittest.TestCase):
    def test_uncapped_edge_always_ok(self):
        ok, count, cap, msg = loop_guard.check_loop_cap([], "A", "B", {})
        self.assertTrue(ok)
        self.assertIsNone(cap)
        self.assertEqual(msg, "")

    def test_within_directed_cap(self):
        events = [_state_event("A", "B")]
        ok, count, cap, msg = loop_guard.check_loop_cap(events, "A", "B", {"A->B": 3})
        self.assertTrue(ok)
        self.assertEqual(count, 1)
        self.assertEqual(cap, 3)

    def test_exceeds_directed_cap(self):
        events = [_state_event("A", "B"), _state_event("A", "B"), _state_event("A", "B")]
        ok, count, cap, msg = loop_guard.check_loop_cap(events, "A", "B", {"A->B": 3})
        self.assertFalse(ok)
        self.assertEqual(count, 3)
        self.assertIn("Loop cap exceeded", msg)
        self.assertIn("--force", msg)

    def test_exceeds_bidirectional_cap_counts_both_directions(self):
        events = [_state_event("A", "B"), _state_event("B", "A")]
        ok, count, cap, msg = loop_guard.check_loop_cap(events, "A", "B", {"A<->B": 2})
        self.assertFalse(ok)
        self.assertEqual(count, 2)

    def test_at_exactly_cap_boundary_next_traversal_blocked(self):
        # cap=2, 2 prior traversals -> the 3rd (prospective) would exceed.
        events = [_state_event("A", "B"), _state_event("A", "B")]
        ok, count, cap, msg = loop_guard.check_loop_cap(events, "A", "B", {"A->B": 2})
        self.assertFalse(ok)

    def test_one_below_cap_boundary_allowed(self):
        events = [_state_event("A", "B")]
        ok, count, cap, msg = loop_guard.check_loop_cap(events, "A", "B", {"A->B": 2})
        self.assertTrue(ok)


class DetectOscillationTest(unittest.TestCase):
    def test_no_oscillation_on_straight_path(self):
        events = [_state_event("A", "B"), _state_event("B", "C"), _state_event("C", "D")]
        self.assertIsNone(loop_guard.detect_oscillation(events))

    def test_detects_ab_ab_oscillation(self):
        events = [_state_event("A", "B"), _state_event("B", "A"), _state_event("A", "B"), _state_event("B", "A")]
        result = loop_guard.detect_oscillation(events)
        self.assertIsNotNone(result)
        self.assertIn("Oscillation", result)

    def test_short_history_no_oscillation(self):
        events = [_state_event("A", "B")]
        self.assertIsNone(loop_guard.detect_oscillation(events))

    def test_empty_history_no_oscillation(self):
        self.assertIsNone(loop_guard.detect_oscillation([]))


class ForwardRankFromJsonTest(unittest.TestCase):
    def setUp(self):
        reset_caches()

    def tearDown(self):
        reset_caches()

    def test_load_forward_rank_matches_real_states_json(self):
        ranks = sm.load_forward_rank()
        self.assertEqual(ranks["WF_CLASSIFY"], 1)
        self.assertEqual(ranks["WF_EXECUTE"], 4)
        self.assertEqual(ranks["WF_DONE"], 6)

    def test_load_forward_rank_excludes_subflows(self):
        ranks = sm.load_forward_rank()
        # WF_INIT is a subflow (documented procedure), not a states.json
        # node, and carries no "rank" field there. There is no hardcoded
        # fallback table anymore — subflows are simply absent from the rank
        # map, and is_forward_read_transition disables read-advance rather
        # than guessing when a rank is missing.
        self.assertNotIn("WF_INIT", ranks)

    def test_load_forward_rank_empty_when_states_json_unreadable(self):
        orig = sm.get_states_file_path
        sm.get_states_file_path = lambda: "/nonexistent/states.json"
        try:
            reset_caches()
            self.assertEqual(sm.load_forward_rank(), {})
        finally:
            sm.get_states_file_path = orig
            reset_caches()

    def test_is_forward_read_transition_disabled_when_ranks_missing(self):
        orig = sm.get_states_file_path
        sm.get_states_file_path = lambda: "/nonexistent/states.json"
        sm._transition_matrix_cache = {"WF_CLASSIFY": ["WF_EXECUTE"]}
        try:
            ok, reason = sm.is_forward_read_transition("WF_CLASSIFY", "WF_EXECUTE")
            self.assertFalse(ok)
            self.assertIn("read-advance disabled", reason)
        finally:
            sm.get_states_file_path = orig
            reset_caches()

    def test_module_level_forward_rank_populated_at_import(self):
        self.assertEqual(sm._FORWARD_RANK["WF_CLASSIFY"], 1)


class LoadSubflowsAndCapsTest(unittest.TestCase):
    def setUp(self):
        reset_caches()

    def tearDown(self):
        reset_caches()

    def test_load_subflows_includes_wf_init(self):
        self.assertIn("WF_INIT", sm.load_subflows())

    def test_load_loop_caps_excludes_description_key(self):
        caps = sm.load_loop_caps()
        self.assertNotIn("description", caps)
        self.assertTrue(all(isinstance(v, int) for v in caps.values()))

    def test_load_loop_caps_has_execute_checkpoint_entry(self):
        caps = sm.load_loop_caps()
        self.assertIn("WF_EXECUTE<->WF_CHECKPOINT", caps)

    def test_is_read_advance_enabled_true_on_real_doc(self):
        self.assertTrue(sm.is_read_advance_enabled())


class SubflowRejectionTest(unittest.TestCase):
    def setUp(self):
        reset_caches()

    def tearDown(self):
        reset_caches()

    def test_is_valid_transition_rejects_subflow_target_with_distinct_reason(self):
        ok, msg = sm.is_valid_transition("WF_CLASSIFY", "WF_INIT")
        self.assertFalse(ok)
        self.assertIn("subflow", msg)
        self.assertNotIn("Unknown state", msg)

    def test_is_valid_transition_rejects_other_subflow_targets(self):
        for subflow in ("WF_CLEANUP", "WF_RESEARCH_LITE", "WF_UPDATE_MEMORY"):
            ok, msg = sm.is_valid_transition("WF_CLASSIFY", subflow)
            self.assertFalse(ok, subflow)
            self.assertIn("subflow", msg, subflow)


class MtimeCacheInvalidationTest(unittest.TestCase):
    def setUp(self):
        reset_caches()
        self.tmp = tempfile.TemporaryDirectory()
        self.states_path = os.path.join(self.tmp.name, "states.json")
        self._orig_get_states_file_path = sm.get_states_file_path
        sm.get_states_file_path = lambda: self.states_path

    def tearDown(self):
        sm.get_states_file_path = self._orig_get_states_file_path
        self.tmp.cleanup()
        reset_caches()

    def _write(self, doc, mtime_bump=0.0):
        with open(self.states_path, "w") as f:
            json.dump(doc, f)
        if mtime_bump:
            t = time.time() + mtime_bump
            os.utime(self.states_path, (t, t))

    def test_cache_reflects_initial_content(self):
        self._write({"transitionMatrix": {"A": ["B"]}})
        doc = sm.load_states_document()
        self.assertEqual(doc["transitionMatrix"], {"A": ["B"]})

    def test_cache_invalidates_on_mtime_change(self):
        self._write({"transitionMatrix": {"A": ["B"]}})
        first = sm.load_states_document()
        self.assertEqual(first["transitionMatrix"], {"A": ["B"]})

        # Rewrite with different content and a bumped mtime.
        self._write({"transitionMatrix": {"A": ["C"]}}, mtime_bump=5.0)
        second = sm.load_states_document()
        self.assertEqual(second["transitionMatrix"], {"A": ["C"]})

    def test_cache_reused_when_mtime_unchanged(self):
        self._write({"transitionMatrix": {"A": ["B"]}})
        first = sm.load_states_document()
        second = sm.load_states_document()
        self.assertIs(first, second)


class _StateManagerLoopGuardBase(unittest.TestCase):
    """tmpdir project root + one WM file, with a real .serena/streams dir so
    transition_to's best-effort stream read has somewhere real to look."""

    def setUp(self):
        reset_caches()
        self._orig_get_project_root = config.get_project_root
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, ".git"), exist_ok=True)
        self.memories_dir = os.path.join(self.root, ".serena", "memories")
        os.makedirs(self.memories_dir, exist_ok=True)
        config.get_project_root = lambda: self.root

    def tearDown(self):
        config.get_project_root = self._orig_get_project_root
        self.tmp.cleanup()
        reset_caches()

    def _write_wm(self, name, current_state, session_id):
        path = os.path.join(self.memories_dir, f"{name}.md")
        with open(path, "w") as f:
            f.write(
                "\n".join([
                    "# WORKING MEMORY",
                    "",
                    "## Session Context",
                    "**Status**: In progress",
                    "",
                    "## Workflow Context",
                    f"**Current State**: {current_state}",
                    f"**Session ID**: {session_id}",
                    "",
                    "## Progress",
                    "- started",
                    "",
                ])
            )
        return path

    def _seed_stream(self, session_id, transitions):
        """Write raw 'state' events directly to this session's stream file."""
        path = stream.get_stream_path(session_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            for frm, to in transitions:
                f.write(json.dumps({"t": int(time.time()), "type": "state", "from_s": frm, "to_s": to, "s": session_id}) + "\n")


class LoopCapIntegrationTest(_StateManagerLoopGuardBase):
    def test_cap_refuses_transition_when_exceeded(self):
        sid = "loopsess1"
        self._write_wm(f"WM_{sid}", "WF_EXECUTE", sid)
        # Seed the EXECUTE<->CHECKPOINT cap (20) already exhausted: 20 prior
        # traversals of the edge about to be taken again.
        self._seed_stream(sid, [("WF_EXECUTE", "WF_CHECKPOINT")] * 20)
        manager = sm.StateManager(self.root, session_id=sid)
        self.assertEqual(manager.get_current_state(), "WF_EXECUTE")
        ok, msg = manager.transition_to("WF_CHECKPOINT")
        self.assertFalse(ok)
        self.assertIn("Loop cap exceeded", msg)

    def test_cap_allows_transition_below_threshold(self):
        sid = "loopsess2"
        self._write_wm(f"WM_{sid}", "WF_EXECUTE", sid)
        self._seed_stream(sid, [("WF_EXECUTE", "WF_CHECKPOINT")] * 5)
        manager = sm.StateManager(self.root, session_id=sid)
        ok, msg = manager.transition_to("WF_CHECKPOINT")
        self.assertTrue(ok, msg)

    def test_force_bypasses_cap(self):
        sid = "loopsess3"
        self._write_wm(f"WM_{sid}", "WF_EXECUTE", sid)
        self._seed_stream(sid, [("WF_EXECUTE", "WF_CHECKPOINT")] * 25)
        manager = sm.StateManager(self.root, session_id=sid)
        ok, msg = manager.transition_to("WF_CHECKPOINT", force=True)
        self.assertTrue(ok, msg)

    def test_no_stream_file_is_a_noop_not_a_block(self):
        sid = "loopsess4"
        self._write_wm(f"WM_{sid}", "WF_EXECUTE", sid)
        # No stream seeded at all.
        manager = sm.StateManager(self.root, session_id=sid)
        ok, msg = manager.transition_to("WF_CHECKPOINT")
        self.assertTrue(ok, msg)


class OscillationIntegrationTest(_StateManagerLoopGuardBase):
    def test_oscillation_warns_but_does_not_block(self):
        sid = "oscsess1"
        self._write_wm(f"WM_{sid}", "WF_EXECUTE", sid)
        # A->B->A->B already in history; the prospective move continues it.
        self._seed_stream(sid, [
            ("WF_EXECUTE", "WF_CHECKPOINT"),
            ("WF_CHECKPOINT", "WF_EXECUTE"),
            ("WF_EXECUTE", "WF_CHECKPOINT"),
        ])
        manager = sm.StateManager(self.root, session_id=sid)
        ok, msg = manager.transition_to("WF_CHECKPOINT")
        # This edge is within cap (well below 20) so it succeeds...
        # oscillation only warns, appended to the success message.
        self.assertTrue(ok, msg)


class ClarifyReturnRulesIntegrationTest(_StateManagerLoopGuardBase):
    def test_clarify_returns_to_previous_state(self):
        sid = "clarsess1"
        self._write_wm(f"WM_{sid}", "WF_ARCH_REVIEW", sid)
        manager = sm.StateManager(self.root, session_id=sid)
        ok, _ = manager.transition_to("WF_CLARIFY")
        self.assertTrue(ok)
        ok, msg = manager.transition_to("WF_ARCH_REVIEW")
        self.assertTrue(ok, msg)

    def test_clarify_can_fall_back_to_classify(self):
        sid = "clarsess2"
        self._write_wm(f"WM_{sid}", "WF_EXECUTE", sid)
        manager = sm.StateManager(self.root, session_id=sid)
        manager.transition_to("WF_CLARIFY", force=True)  # arbitrary entry, simulate
        ok, msg = manager.transition_to("WF_CLASSIFY")
        self.assertTrue(ok, msg)

    def test_clarify_rejects_unrelated_target_without_force(self):
        sid = "clarsess3"
        # WF_CLASSIFY -> WF_CLARIFY is a real matrix edge (unlike EXECUTE).
        self._write_wm(f"WM_{sid}", "WF_CLASSIFY", sid)
        manager = sm.StateManager(self.root, session_id=sid)
        ok, _ = manager.transition_to("WF_CLARIFY")
        self.assertTrue(ok)
        # WF_VERIFY is neither the entered-from state (WF_CLASSIFY) nor one
        # of the fallbacks (WF_CLASSIFY/WF_ARCH_REVIEW) — should be refused.
        ok, msg = manager.transition_to("WF_VERIFY")
        self.assertFalse(ok)
        self.assertIn("BLOCKED", msg)

    def test_clarify_reject_bypassable_with_force(self):
        sid = "clarsess4"
        self._write_wm(f"WM_{sid}", "WF_CLASSIFY", sid)
        manager = sm.StateManager(self.root, session_id=sid)
        manager.transition_to("WF_CLARIFY")
        ok, msg = manager.transition_to("WF_VERIFY", force=True)
        self.assertTrue(ok, msg)

    def test_clarify_allowed_targets_pure_function(self):
        self.assertEqual(sm.clarify_allowed_targets("WF_EXECUTE"), ["WF_EXECUTE", "WF_CLASSIFY", "WF_ARCH_REVIEW"])
        self.assertEqual(sm.clarify_allowed_targets(None), ["WF_CLASSIFY", "WF_ARCH_REVIEW"])
        self.assertEqual(sm.clarify_allowed_targets("WF_CLASSIFY"), ["WF_CLASSIFY", "WF_ARCH_REVIEW"])

    def test_clarify_entered_from_persists_across_processes_debug_tdd(self):
        # Reviewer-confirmed bug: clarify_entered_from was only ever set in
        # memory, so a SEPARATE process (every hook rebuilds StateManager from
        # disk) rebuilding StateManager after CLARIFY entry always saw None,
        # which only permits returning to WF_CLASSIFY/WF_ARCH_REVIEW —
        # stranding sessions that entered CLARIFY from WF_DEBUG_TDD.
        sid = "clarsess_debugtdd"
        self._write_wm(f"WM_{sid}", "WF_DEBUG_TDD", sid)

        # Process 1: enter CLARIFY from WF_DEBUG_TDD.
        manager1 = sm.StateManager(self.root, session_id=sid)
        ok, msg = manager1.transition_to("WF_CLARIFY")
        self.assertTrue(ok, msg)

        # Process 2: brand-new StateManager instance, rebuilt purely from
        # disk (state file + WM) — simulates the next hook invocation.
        manager2 = sm.StateManager(self.root, session_id=sid)
        self.assertEqual(manager2.get_current_state(), "WF_CLARIFY")
        self.assertEqual(manager2.state.get("clarify_entered_from"), "WF_DEBUG_TDD")

        # Returning to the caller (WF_DEBUG_TDD) succeeds WITHOUT --force.
        ok, msg = manager2.transition_to("WF_DEBUG_TDD")
        self.assertTrue(ok, msg)

        # clarify_entered_from is cleared on exit — a THIRD process should
        # not see a stale caller state once CLARIFY has been left.
        manager3 = sm.StateManager(self.root, session_id=sid)
        self.assertIsNone(manager3.state.get("clarify_entered_from"))

    def test_clarify_entered_from_cross_process_refuses_unrelated_target(self):
        sid = "clarsess_debugtdd2"
        self._write_wm(f"WM_{sid}", "WF_DEBUG_TDD", sid)

        manager1 = sm.StateManager(self.root, session_id=sid)
        ok, msg = manager1.transition_to("WF_CLARIFY")
        self.assertTrue(ok, msg)

        # New process, same as above.
        manager2 = sm.StateManager(self.root, session_id=sid)
        # WF_VERIFY is neither the entered-from state (WF_DEBUG_TDD) nor one
        # of the fallbacks (WF_CLASSIFY/WF_ARCH_REVIEW) — refused without force.
        ok, msg = manager2.transition_to("WF_VERIFY")
        self.assertFalse(ok)
        self.assertIn("BLOCKED", msg)

        ok, msg = manager2.transition_to("WF_VERIFY", force=True)
        self.assertTrue(ok, msg)

    def test_clarify_entered_from_cross_process_continue_and_initial_setup(self):
        # Backward compat + coverage for the other strandable callers named
        # in the bug report: WF_CONTINUE and WF_INITIAL_SETUP.
        for caller in ("WF_CONTINUE", "WF_INITIAL_SETUP"):
            sid = f"clarsess_{caller.lower()}"
            self._write_wm(f"WM_{sid}", caller, sid)
            manager1 = sm.StateManager(self.root, session_id=sid)
            ok, msg = manager1.transition_to("WF_CLARIFY", force=True)
            self.assertTrue(ok, msg)

            manager2 = sm.StateManager(self.root, session_id=sid)
            self.assertEqual(manager2.state.get("clarify_entered_from"), caller)
            ok, msg = manager2.transition_to(caller)
            self.assertTrue(ok, msg)

    def test_state_file_without_clarify_entered_from_field_still_works(self):
        # Backward compat: a state file written before this fix existed (no
        # clarify_entered_from key at all) must not crash StateManager init,
        # and CLARIFY exit falls back to the None -> CLASSIFY/ARCH_REVIEW
        # behavior, exactly as before this fix.
        sid = "clarsess_legacy"
        self._write_wm(f"WM_{sid}", "WF_CLASSIFY", sid)
        config.write_state_file(sid, "WF_CLARIFY", prev_state="WF_CLASSIFY")
        # Simulate a legacy file: strip the field if somehow present.
        path = config.get_state_file_path(sid)
        with open(path) as f:
            data = json.load(f)
        data.pop("clarify_entered_from", None)
        with open(path, "w") as f:
            json.dump(data, f)

        manager = sm.StateManager(self.root, session_id=sid)
        self.assertIsNone(manager.state.get("clarify_entered_from"))
        ok, msg = manager.transition_to("WF_CLASSIFY")
        self.assertTrue(ok, msg)


if __name__ == "__main__":
    unittest.main()
