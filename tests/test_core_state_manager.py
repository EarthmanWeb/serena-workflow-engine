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
    """Seeds BOTH the transition-matrix cache AND a synthetic states.json
    document (ranks + readBackward), so this test class never depends on the
    real state-machine/states.json's rank/readBackward content leaking in via
    load_states_document()/load_forward_rank()/load_read_backward()."""

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
        # Synthetic states doc: ranks matching the matrix above, plus a
        # readBackward declaration on WF_RESEARCH only — mirrors the real
        # states.json shape (rank + readBackward per state) without reading
        # the real file. load_states_document() compares the cached mtime
        # against os.path.getmtime(real states.json) — match it exactly so
        # the synthetic doc is NOT invalidated/replaced by a real-file re-read.
        _real_mtime = os.path.getmtime(mod.get_states_file_path())
        mod._states_doc_cache = (_real_mtime, {
            "states": {
                "WF_CLASSIFY": {"rank": 1},
                "WF_EXECUTE": {"rank": 4},
                "WF_CHECKPOINT": {"rank": 4},
                "WF_RESEARCH": {"rank": 2, "readBackward": ["WF_CLASSIFY"]},
                "WF_VERIFY": {"rank": 5},
                "WF_ARCH_REVIEW": {"rank": 3},
                "WF_DONE": {"rank": 6},
            }
        })

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

    def test_research_backward_to_classify_advances_via_readbackward(self):
        # WF_RESEARCH (rank 2) -> WF_CLASSIFY (rank 1): backward by rank.
        # WF_RESEARCH declares WF_CLASSIFY in its readBackward allowlist (its
        # needs_implementation -> WF_CLASSIFY exit), so a read of
        # wf/WF_CLASSIFY from WF_RESEARCH completes this declared exit.
        ok, reason = mod.is_forward_read_transition("WF_RESEARCH", "WF_CLASSIFY")
        self.assertTrue(ok)
        self.assertIn("readBackward", reason)
        self.assertIn("WF_RESEARCH", reason)
        self.assertIn("WF_CLASSIFY", reason)

    def test_undeclared_backward_does_not_advance(self):
        # WF_EXECUTE (rank 4) -> WF_RESEARCH (rank 2): backward by rank.
        # WF_EXECUTE has no readBackward entry in the synthetic doc and
        # WF_EXECUTE -> WF_RESEARCH is not even a matrix edge here, so this
        # stays False.
        ok, reason = mod.is_forward_read_transition("WF_EXECUTE", "WF_RESEARCH")
        self.assertFalse(ok)
        self.assertIn("BLOCKED", reason)


class RealGraphReadBackwardTest(unittest.TestCase):
    """Regression guard against the REAL state-machine/states.json — the
    exact deadlock scenario and its declared fix, plus the other
    readBackward-declaring states. No cache seeding: these read the shipped
    graph directly."""

    def setUp(self):
        reset_caches()

    def tearDown(self):
        reset_caches()

    def test_research_to_classify_advances(self):
        ok, reason = mod.is_forward_read_transition("WF_RESEARCH", "WF_CLASSIFY")
        self.assertTrue(ok)
        self.assertIn("readBackward", reason)

    def test_execute_to_research_undeclared_stays_false(self):
        ok, reason = mod.is_forward_read_transition("WF_EXECUTE", "WF_RESEARCH")
        self.assertFalse(ok)

    def test_verify_to_execute_declared_backward_advances(self):
        ok, reason = mod.is_forward_read_transition("WF_VERIFY", "WF_EXECUTE")
        self.assertTrue(ok)
        self.assertIn("readBackward", reason)

    def test_done_to_classify_stays_false(self):
        # WF_DONE has no readBackward entry — post-completion re-entry is
        # owned by the prompt hook, not a read.
        ok, reason = mod.is_forward_read_transition("WF_DONE", "WF_CLASSIFY")
        self.assertFalse(ok)

    def test_execute_to_clarify_stays_false(self):
        ok, reason = mod.is_forward_read_transition("WF_EXECUTE", "WF_CLARIFY")
        self.assertFalse(ok)
        self.assertIn("WF_CLARIFY", reason)

    def test_every_readbackward_declaring_state_reaches_classify(self):
        # All of these are rank > WF_CLASSIFY's rank (1) EXCEPT WF_CONTINUE,
        # which shares rank 1 with WF_CLASSIFY — an equal-rank move counts as
        # an ordinary forward read (see test_forward_equal_rank_advances), so
        # it reaches WF_CLASSIFY without needing its readBackward declaration
        # at all. The others are strictly higher rank, so they only reach
        # WF_CLASSIFY via the declared readBackward allowlist.
        for state in ("WF_ARCH_REVIEW", "WF_EXECUTE", "WF_CHECKPOINT",
                      "WF_DEBUG_TDD", "WF_VERIFY"):
            ok, reason = mod.is_forward_read_transition(state, "WF_CLASSIFY")
            self.assertTrue(ok, f"{state} -> WF_CLASSIFY: {reason}")
            self.assertIn("readBackward", reason)

        ok, reason = mod.is_forward_read_transition("WF_CONTINUE", "WF_CLASSIFY")
        self.assertTrue(ok, reason)


class ForwardRankConstantTest(unittest.TestCase):
    def test_clarify_rank_is_negative_one(self):
        self.assertEqual(mod._FORWARD_RANK["WF_CLARIFY"], -1)

    def test_rank_ordering_is_monotonic_forward(self):
        rank = mod._FORWARD_RANK
        # WF_INIT is a subflow (documented procedure, not a states.json node)
        # and carries no "rank" field there — ranks come ONLY from states.json
        # now (no hardcoded fallback table), so subflows are simply absent
        # from this dict, not silently defaulted to 0.
        self.assertNotIn("WF_INIT", rank)
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


class DocClaimsGateTest(_StateManagerBase):
    """C4 doc-claims transition gate: transition_to refuses WF_VERIFY /
    WF_DONE while the WM '## Doc Claims Used' ledger has pending rows;
    confirmed/corrected rows and an absent section pass; --force overrides.
    Row parsing lives in core.doc_claims (shared parser module).
    """

    MATRIX = {
        "WF_EXECUTE": ["WF_CHECKPOINT", "WF_VERIFY", "WF_DONE"],
        "WF_VERIFY": ["WF_DONE", "WF_EXECUTE", "WF_CLASSIFY"],
        "WF_DONE": ["WF_CLASSIFY"],
    }

    def setUp(self):
        super().setUp()
        # Seed a known matrix so the gate tests are independent of
        # states.json edits; the doc-claims check runs after matrix
        # validation in the same non-force branch.
        mod._transition_matrix_cache = dict(self.MATRIX)

    def _sm_with_claims(self, claims_block, current_state="WF_EXECUTE"):
        """StateManager over a WM that carries the given Doc Claims section
        body (None = no section at all)."""
        body = _wm_markdown(current_state=current_state)
        if claims_block is not None:
            body += "\n## Doc Claims Used\n\n" + claims_block + "\n"
        path = os.path.join(self.memories_dir, "WM_20260101_120000.md")
        with open(path, "w") as f:
            f.write(body)
        return mod.StateManager(self.root)

    def test_pending_row_blocks_wf_verify(self):
        sm = self._sm_with_claims(
            "- mem:ref/REF_API → timeout=30s → pending\n")
        ok, msg = sm.transition_to("WF_VERIFY")
        self.assertFalse(ok)
        self.assertIn("Doc Claims Used has 1 blocking row(s)", msg)
        self.assertIn("mem:ref/REF_API", msg)
        self.assertIn("Confirm or correct each claim", msg)
        # The FSM did not move.
        self.assertEqual(sm.get_current_state(), "WF_EXECUTE")

    def test_pending_row_blocks_wf_done(self):
        # ASCII arrow variant: the parser tolerates '->' as well as '→'.
        sm = self._sm_with_claims(
            "- mem:ref/REF_API -> timeout=30s -> pending\n")
        ok, msg = sm.transition_to("WF_DONE")
        self.assertFalse(ok)
        self.assertIn("blocking row(s)", msg)
        self.assertEqual(sm.get_current_state(), "WF_EXECUTE")

    def test_confirmed_and_corrected_rows_pass(self):
        sm = self._sm_with_claims(
            "- mem:ref/REF_API → timeout=30s → confirmed\n"
            "- mem:dom/DOM_X → retries=3 → corrected → retries=5\n")
        ok, msg = sm.transition_to("WF_VERIFY")
        self.assertTrue(ok, msg)
        self.assertEqual(sm.get_current_state(), "WF_VERIFY")

    def test_corrected_without_true_value_blocks(self):
        # A row claiming correction but recording no true value cannot be
        # verified — it blocks like a pending row.
        sm = self._sm_with_claims(
            "- mem:ref/REF_API → timeout=30s → corrected\n")
        ok, msg = sm.transition_to("WF_VERIFY")
        self.assertFalse(ok)
        self.assertIn("blocking row(s)", msg)
        self.assertIn("MUST record the true value", msg)
        self.assertEqual(sm.get_current_state(), "WF_EXECUTE")

    def test_absent_section_passes(self):
        # Missing section = no rows = pass (zero-cost when ledger unused).
        sm = self._sm_with_claims(None)
        ok, msg = sm.transition_to("WF_VERIFY")
        self.assertTrue(ok, msg)

    def test_pending_rows_do_not_block_other_targets(self):
        # The gate fires only on WF_VERIFY / WF_DONE targets.
        sm = self._sm_with_claims(
            "- mem:ref/REF_API → timeout=30s → pending\n")
        ok, msg = sm.transition_to("WF_CHECKPOINT")
        self.assertTrue(ok, msg)

    def test_force_overrides_pending_rows(self):
        sm = self._sm_with_claims(
            "- mem:ref/REF_API → timeout=30s → pending\n")
        ok, msg = sm.transition_to("WF_DONE", force=True)
        self.assertTrue(ok, msg)
        self.assertEqual(sm.get_current_state(), "WF_DONE")


class PerformTransitionTest(_StateManagerBase):
    """Tests for the shared perform_transition() driver used by set_state.py
    and swe_wm_transition. Uses the real states.json (no matrix seeding) —
    the SID's WM starts at WF_RESEARCH, matching the deadlock scenario."""

    SID = "abcd1234"

    def setUp(self):
        super().setUp()
        self._write_wm(name=f"WM_{self.SID}", current_state="WF_RESEARCH", session_id=self.SID)
        # A real session has already written a .state file by the time it's
        # deep enough in the workflow to be at WF_RESEARCH — write_state_file
        # derives `prev_state` from what's already on disk
        # (write_working_memory_state reads read_state_file() for `prev`), so
        # seed one here to match a realistic prior transition into WF_RESEARCH.
        config.write_state_file(self.SID, "WF_RESEARCH", prev_state="WF_CLASSIFY")

    def _stream_path(self):
        stream_mod = import_core("swe_hooks.core.stream")
        return stream_mod.get_stream_path(self.SID)

    def test_research_to_classify_succeeds(self):
        result = mod.perform_transition(self.root, self.SID, "WF_CLASSIFY")
        self.assertTrue(result["success"], result)
        self.assertEqual(result["session_id"], self.SID)
        self.assertEqual(result["previous_state"], "WF_RESEARCH")
        self.assertEqual(result["new_state"], "WF_CLASSIFY")
        self.assertFalse(result["forced"])
        self.assertIn("wm_file", result)

    def test_research_to_classify_state_file_keys(self):
        mod.perform_transition(self.root, self.SID, "WF_CLASSIFY")
        state_file = config.read_state_file(self.SID)
        self.assertIsNotNone(state_file)
        self.assertEqual(state_file["current_state"], "WF_CLASSIFY")
        self.assertEqual(state_file["prev_state"], "WF_RESEARCH")

    def test_research_to_classify_stream_has_state_event(self):
        mod.perform_transition(self.root, self.SID, "WF_CLASSIFY")
        stream_path = self._stream_path()
        self.assertTrue(os.path.exists(stream_path))
        with open(stream_path) as f:
            lines = [line for line in f if line.strip()]
        events = [__import__("json").loads(line) for line in lines]
        state_events = [e for e in events if e.get("type") == "state"]
        self.assertTrue(
            any(e.get("from_s") == "WF_RESEARCH" and e.get("to_s") == "WF_CLASSIFY"
                for e in state_events),
            state_events,
        )

    def test_research_to_classify_appends_wm_transitions_line(self):
        mod.perform_transition(self.root, self.SID, "WF_CLASSIFY")
        wm_path = os.path.join(self.memories_dir, f"WM_{self.SID}.md")
        with open(wm_path) as f:
            content = f.read()
        self.assertIn("### Transitions", content)
        self.assertIn("WF_RESEARCH → WF_CLASSIFY", content)

    def test_subflow_target_rejected_even_with_force(self):
        result = mod.perform_transition(self.root, self.SID, "WF_INIT", force=True)
        self.assertFalse(result["success"])
        self.assertIn("subflow", result["error"])
        self.assertIn("subflows", result)

    def test_unknown_state_rejected(self):
        result = mod.perform_transition(self.root, self.SID, "WF_NOT_A_REAL_STATE")
        self.assertFalse(result["success"])
        self.assertIn("Unknown state", result["error"])
        self.assertIn("valid_states", result)

    def test_missing_session_id_rejected(self):
        result = mod.perform_transition(self.root, "", "WF_CLASSIFY")
        self.assertFalse(result["success"])
        self.assertIn("session_id", result["error"])

    def test_invalid_transition_rejected_without_force(self):
        # WF_RESEARCH -> WF_EXECUTE is not a declared matrix edge.
        result = mod.perform_transition(self.root, self.SID, "WF_EXECUTE")
        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_invalid_transition_accepted_with_force(self):
        result = mod.perform_transition(self.root, self.SID, "WF_EXECUTE", force=True)
        self.assertTrue(result["success"], result)
        self.assertEqual(result["new_state"], "WF_EXECUTE")
        self.assertTrue(result["forced"])

    def test_already_in_state_is_a_noop_failure(self):
        result = mod.perform_transition(self.root, self.SID, "WF_RESEARCH")
        self.assertFalse(result["success"])
        self.assertIn("Already in state", result["error"])

    def test_reason_is_echoed_on_success(self):
        result = mod.perform_transition(self.root, self.SID, "WF_CLASSIFY",
                                         reason="needs_implementation exit")
        self.assertEqual(result["reason"], "needs_implementation exit")



class BlanketConsentResetTest(_StateManagerBase):
    """Re-entry into WF_CLASSIFY from a later state clears the WM
    blanket-consent flag — single choke point StateManager.transition_to,
    reached by the prompt hook, read-advance (swe_post_read_state),
    swe_wm_transition MCP and set_state.py (both via perform_transition)."""

    SID = "c0ffee12"

    def _seed(self, state):
        path = self._write_wm(name=f"WM_{self.SID}", current_state=state,
                              session_id=self.SID)
        with open(path, "a") as f:
            f.write("## Context\n- blanket_consent: true (no questions)\n")
        config.write_state_file(self.SID, state, prev_state="WF_CLASSIFY")
        return path

    def _consent(self):
        session = import_core("swe_hooks.core.session")
        return session.wm_has_blanket_consent(self.root, self.SID)

    def _events(self, kind):
        stream_mod = import_core("swe_hooks.core.stream")
        path = stream_mod.get_stream_path(self.SID)
        if not os.path.exists(path):
            return []
        import json
        with open(path) as f:
            return [json.loads(l) for l in f if l.strip()
                    and json.loads(l).get("type") == kind]

    def test_resets_blanket_consent_rank_rule(self):
        for old in ("WF_RESEARCH", "WF_ARCH_REVIEW", "WF_EXECUTE", "WF_VERIFY",
                    "WF_DONE", "WF_CONTINUE", "WF_CHECKPOINT", "WF_DEBUG_TDD"):
            self.assertTrue(mod.resets_blanket_consent(old, "WF_CLASSIFY"), old)
        for old in ("WF_CLARIFY", "WF_ONBOARD", "WF_INIT", "WF_CLASSIFY"):
            self.assertFalse(mod.resets_blanket_consent(old, "WF_CLASSIFY"), old)
        self.assertFalse(mod.resets_blanket_consent("WF_EXECUTE", "WF_VERIFY"))

    def test_perform_transition_clears_flag(self):
        self._seed("WF_RESEARCH")
        self.assertTrue(self._consent())
        result = mod.perform_transition(self.root, self.SID, "WF_CLASSIFY")
        self.assertTrue(result["success"], result)
        self.assertFalse(self._consent())
        self.assertEqual(len(self._events("consent_reset")), 1)

    def test_transition_to_from_done_clears_flag(self):
        # Prompt-hook new-task path: WF_DONE -> WF_CLASSIFY via transition_to.
        self._seed("WF_DONE")
        sm = mod.StateManager(self.root, session_id=self.SID)
        ok, msg = sm.transition_to("WF_CLASSIFY")
        self.assertTrue(ok, msg)
        self.assertFalse(self._consent())

    def test_forced_pivot_from_execute_clears_flag(self):
        self._seed("WF_EXECUTE")
        result = mod.perform_transition(self.root, self.SID, "WF_CLASSIFY", force=True)
        self.assertTrue(result["success"], result)
        self.assertFalse(self._consent())

    def test_clarify_return_keeps_flag(self):
        self._seed("WF_CLARIFY")
        sm = mod.StateManager(self.root, session_id=self.SID)
        ok, msg = sm.transition_to("WF_CLASSIFY", force=True)
        self.assertTrue(ok, msg)
        self.assertTrue(self._consent())
        self.assertEqual(self._events("consent_reset"), [])

    def test_non_classify_transition_keeps_flag(self):
        self._seed("WF_EXECUTE")
        result = mod.perform_transition(self.root, self.SID, "WF_VERIFY")
        self.assertTrue(result["success"], result)
        self.assertTrue(self._consent())


class MultiTaskGateTest(_StateManagerBase):
    """USER-APPROVED RULE: WF_CLASSIFY -> WF_EXECUTE is refused when Current
    Task names 2+ independent tickets/jobs and WM lacks `parallel_agents:
    true`. Only fires on this exact edge; --force overrides it, same as the
    doc-claims gate.
    """

    MATRIX = {
        "WF_CLASSIFY": ["WF_ARCH_REVIEW", "WF_EXECUTE", "WF_RESEARCH", "WF_CLARIFY"],
        "WF_ARCH_REVIEW": ["WF_EXECUTE", "WF_CLASSIFY"],
    }

    def setUp(self):
        super().setUp()
        mod._transition_matrix_cache = dict(self.MATRIX)

    def _sm_with_task(self, task_body, current_state="WF_CLASSIFY"):
        content = (
            "# WORKING MEMORY\n\n"
            "## Workflow Context\n"
            f"**Current State**: {current_state}\n\n"
            "## Current Task\n"
            f"{task_body}\n"
        )
        path = os.path.join(self.memories_dir, "WM_20260101_120000.md")
        with open(path, "w") as f:
            f.write(content)
        return mod.StateManager(self.root)

    def test_multi_ticket_task_blocks_execute(self):
        sm = self._sm_with_task("Fix SPS-855 and SPS-856 today")
        ok, msg = sm.transition_to("WF_EXECUTE")
        self.assertFalse(ok)
        self.assertIn("separate tickets/jobs", msg)
        self.assertIn("WF_ARCH_REVIEW", msg)
        self.assertIn("parallel_agents", msg)
        self.assertEqual(sm.get_current_state(), "WF_CLASSIFY")

    def test_multi_ticket_task_allowed_with_parallel_agents_flag(self):
        sm = self._sm_with_task(
            "Fix SPS-855 and SPS-856 today\n- **parallel_agents**: true")
        ok, msg = sm.transition_to("WF_EXECUTE")
        self.assertTrue(ok, msg)
        self.assertEqual(sm.get_current_state(), "WF_EXECUTE")

    def test_multi_ticket_task_allowed_with_force(self):
        sm = self._sm_with_task("Fix SPS-855 and SPS-856 today")
        ok, msg = sm.transition_to("WF_EXECUTE", force=True)
        self.assertTrue(ok, msg)
        self.assertEqual(sm.get_current_state(), "WF_EXECUTE")

    def test_single_ticket_task_allowed(self):
        sm = self._sm_with_task("Fix SPS-855 only.")
        ok, msg = sm.transition_to("WF_EXECUTE")
        self.assertTrue(ok, msg)
        self.assertEqual(sm.get_current_state(), "WF_EXECUTE")

    def test_gate_does_not_fire_on_other_targets(self):
        # Same multi-ticket task, but targeting WF_ARCH_REVIEW (the correct
        # route) — must not be blocked.
        sm = self._sm_with_task("Fix SPS-855 and SPS-856 today")
        ok, msg = sm.transition_to("WF_ARCH_REVIEW")
        self.assertTrue(ok, msg)
        self.assertEqual(sm.get_current_state(), "WF_ARCH_REVIEW")

    def test_gate_does_not_fire_from_other_states(self):
        # Same multi-ticket text, but starting from WF_ARCH_REVIEW (already
        # routed correctly) -> WF_EXECUTE must not be blocked.
        sm = self._sm_with_task("Fix SPS-855 and SPS-856 today",
                                 current_state="WF_ARCH_REVIEW")
        ok, msg = sm.transition_to("WF_EXECUTE")
        self.assertTrue(ok, msg)
        self.assertEqual(sm.get_current_state(), "WF_EXECUTE")

    def test_missing_wm_file_passes(self):
        # No WM written at all — nothing to scan, degrade-to-no-op.
        sm = mod.StateManager(self.root)
        mod._transition_matrix_cache = dict(self.MATRIX)
        ok, msg = sm.transition_to("WF_EXECUTE")
        self.assertTrue(ok, msg)


if __name__ == "__main__":
    unittest.main()
