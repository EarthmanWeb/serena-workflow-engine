"""Tests for scripts/validate-graph.py's pure functions.

Runs the validator against the REAL state-machine/states.json (must report
zero errors — this is the regression guard for graph drift) and against small
synthetic graphs that each exercise exactly one failure mode: an unreachable
node, a node/matrix transitions mismatch, an uncapped cycle, and a missing
wf/ memory doc.

Loaded via _hookutil.load_script since "validate-graph.py" is not a valid
Python module name (hyphen).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hookutil import load_script  # noqa: E402

mod = load_script("scripts/validate-graph.py", modname="_script_validate_graph")


def _minimal_doc(states, matrix, subflows=None, loop_caps=None):
    """Build a minimal states.json-shaped dict for synthetic tests."""
    return {
        "states": states,
        "transitionMatrix": matrix,
        "subflows": subflows or [],
        "loopCaps": loop_caps or {},
    }


class RealStatesJsonTest(unittest.TestCase):
    """The regression guard: the shipped graph must validate clean."""

    def setUp(self):
        self.doc = mod.load_states_doc()
        self.wf_names = mod.list_wf_memory_names()

    def test_real_graph_has_zero_errors(self):
        result = mod.validate_graph(self.doc, wf_memory_names=self.wf_names)
        self.assertEqual(result["errors"], [], result["errors"])

    def test_real_graph_has_zero_warnings(self):
        result = mod.validate_graph(self.doc, wf_memory_names=self.wf_names)
        self.assertEqual(result["warnings"], [], result["warnings"])

    def test_real_graph_produces_adjacency_for_every_state(self):
        result = mod.validate_graph(self.doc, wf_memory_names=self.wf_names)
        adj = result["adjacency"]
        for name in self.doc["states"]:
            self.assertIn(name, adj, name)

    def test_real_graph_all_states_have_rank(self):
        for name, info in self.doc["states"].items():
            self.assertIn("rank", info, name)

    def test_real_graph_subflows_and_states_disjoint(self):
        subflows = set(self.doc.get("subflows", []))
        states = set(self.doc["states"].keys())
        self.assertEqual(subflows & states, set())

    def test_real_graph_jq_parseable(self):
        # load_states_doc already exercised json.load successfully in setUp;
        # this just asserts the top-level shape is what the rest of the
        # codebase (state_manager.py) expects.
        self.assertIn("transitionMatrix", self.doc)
        self.assertIn("states", self.doc)
        self.assertIn("readAdvance", self.doc)
        self.assertIn("loopCaps", self.doc)


class BuildAdjacencyTest(unittest.TestCase):
    def test_drops_sentinel_and_none(self):
        doc = _minimal_doc(
            states={"A": {"transitions": {}}, "B": {"transitions": {}}},
            matrix={"A": ["B", None, "(return_to_caller)"], "B": []},
        )
        adj = mod.build_adjacency(doc)
        self.assertEqual(adj["A"], ["B"])
        self.assertEqual(adj["B"], [])


class FindUnreachableTest(unittest.TestCase):
    def test_all_reachable(self):
        adj = {"SessionStart": ["A"], "A": ["B"], "B": []}
        self.assertEqual(mod.find_unreachable(adj), [])

    def test_reports_unreachable_node(self):
        adj = {"SessionStart": ["A"], "A": [], "B": ["A"]}
        # B is never a target of anything reachable from SessionStart.
        self.assertEqual(mod.find_unreachable(adj), ["B"])


class FindCyclesTest(unittest.TestCase):
    def test_self_loop_detected(self):
        adj = {"A": ["A"]}
        self.assertEqual(mod.find_cycles(adj), [["A"]])

    def test_two_node_cycle_detected(self):
        adj = {"A": ["B"], "B": ["A"]}
        cycles = mod.find_cycles(adj)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(sorted(cycles[0]), ["A", "B"])

    def test_acyclic_graph_has_no_cycles(self):
        adj = {"A": ["B"], "B": ["C"], "C": []}
        self.assertEqual(mod.find_cycles(adj), [])


class CycleIsCappedTest(unittest.TestCase):
    def test_directed_cap_covers_cycle(self):
        adj = {"A": ["B"], "B": ["A"]}
        self.assertTrue(mod.cycle_is_capped(["A", "B"], adj, {"A->B": 3}))

    def test_bidirectional_cap_covers_cycle(self):
        adj = {"A": ["B"], "B": ["A"]}
        self.assertTrue(mod.cycle_is_capped(["A", "B"], adj, {"A<->B": 3}))

    def test_uncovered_cycle_is_not_capped(self):
        adj = {"A": ["B"], "B": ["A"]}
        self.assertFalse(mod.cycle_is_capped(["A", "B"], adj, {"X->Y": 3}))


class ValidateGraphSyntheticTest(unittest.TestCase):
    """Each test exercises exactly one failure mode in isolation."""

    def _states(self, **overrides):
        base = {
            "A": {"rank": 0, "transitions": {"go": "B"}},
            "B": {"rank": 1, "transitions": {}, "terminal": True},
        }
        base.update(overrides)
        return base

    def test_unreachable_node_reported(self):
        doc = _minimal_doc(
            states=self._states(C={"rank": 2, "transitions": {}, "terminal": True}),
            matrix={"SessionStart": ["A"], "A": ["B"], "B": [], "C": []},
        )
        result = mod.validate_graph(doc)
        self.assertTrue(any("C is unreachable" in e for e in result["errors"]), result["errors"])

    def test_node_matrix_mismatch_reported(self):
        doc = _minimal_doc(
            states=self._states(),
            # Matrix row for A omits "B" that node.transitions declares.
            matrix={"SessionStart": ["A"], "A": [], "B": []},
        )
        result = mod.validate_graph(doc)
        self.assertTrue(any("mismatch" in e for e in result["errors"]), result["errors"])

    def test_uncapped_cycle_is_a_warning_not_error(self):
        doc = _minimal_doc(
            states={
                "A": {"rank": 0, "transitions": {"x": "B"}},
                "B": {"rank": 1, "transitions": {"y": "A"}},
            },
            matrix={"SessionStart": ["A"], "A": ["B"], "B": ["A"]},
            loop_caps={},
        )
        result = mod.validate_graph(doc)
        self.assertEqual(result["errors"], [])
        self.assertTrue(any("uncapped cycle" in w for w in result["warnings"]), result["warnings"])

    def test_capped_cycle_produces_no_warning(self):
        doc = _minimal_doc(
            states={
                "A": {"rank": 0, "transitions": {"x": "B"}},
                "B": {"rank": 1, "transitions": {"y": "A"}},
            },
            matrix={"SessionStart": ["A"], "A": ["B"], "B": ["A"]},
            loop_caps={"A<->B": 5},
        )
        result = mod.validate_graph(doc)
        self.assertEqual(result["warnings"], [])

    def test_missing_wf_doc_reported(self):
        doc = _minimal_doc(
            states=self._states(),
            matrix={"SessionStart": ["A"], "A": ["B"], "B": []},
        )
        # No memory doc for A or B at all.
        result = mod.validate_graph(doc, wf_memory_names=[])
        self.assertTrue(any("no memories/wf/A.md" in e for e in result["errors"]), result["errors"])
        self.assertTrue(any("no memories/wf/B.md" in e for e in result["errors"]), result["errors"])

    def test_stateless_doc_reported(self):
        doc = _minimal_doc(
            states=self._states(),
            matrix={"SessionStart": ["A"], "A": ["B"], "B": []},
        )
        result = mod.validate_graph(doc, wf_memory_names=["A", "B", "WF_GHOST"])
        self.assertTrue(any("WF_GHOST" in e and "neither a state" in e for e in result["errors"]), result["errors"])

    def test_subflow_satisfies_doc_check(self):
        doc = _minimal_doc(
            states=self._states(),
            matrix={"SessionStart": ["A"], "A": ["B"], "B": []},
            subflows=["WF_SUB"],
        )
        result = mod.validate_graph(doc, wf_memory_names=["A", "B", "WF_SUB"])
        self.assertEqual(result["errors"], [])

    def test_missing_rank_reported(self):
        doc = _minimal_doc(
            states={
                "A": {"transitions": {"go": "B"}},  # no rank
                "B": {"rank": 1, "transitions": {}, "terminal": True},
            },
            matrix={"SessionStart": ["A"], "A": ["B"], "B": []},
        )
        result = mod.validate_graph(doc)
        self.assertTrue(any("A has no 'rank'" in e for e in result["errors"]), result["errors"])

    def test_unknown_matrix_target_reported(self):
        doc = _minimal_doc(
            states=self._states(),
            matrix={"SessionStart": ["A"], "A": ["B", "GHOST"], "B": []},
        )
        result = mod.validate_graph(doc)
        self.assertTrue(any("unknown state 'GHOST'" in e for e in result["errors"]), result["errors"])

    def test_terminal_state_with_no_outedge_is_fine(self):
        doc = _minimal_doc(
            states=self._states(),
            matrix={"SessionStart": ["A"], "A": ["B"], "B": []},
        )
        result = mod.validate_graph(doc)
        self.assertFalse(any("no outgoing transitions" in e for e in result["errors"]), result["errors"])

    def test_nonterminal_state_with_no_outedge_is_an_error(self):
        doc = _minimal_doc(
            states={
                "A": {"rank": 0, "transitions": {"go": "B"}},
                "B": {"rank": 1, "transitions": {}},  # not terminal, no out-edge
            },
            matrix={"SessionStart": ["A"], "A": ["B"], "B": []},
        )
        result = mod.validate_graph(doc)
        self.assertTrue(any("B has no outgoing transitions" in e for e in result["errors"]), result["errors"])

    def test_readadvance_info_reports_matrix_edge_status(self):
        doc = _minimal_doc(
            states=self._states(),
            matrix={"SessionStart": ["A"], "A": ["B"], "B": []},
        )
        result = mod.validate_graph(doc)
        self.assertTrue(any("A(rank 0) -> B(rank 1)" in i and "matrix edge" in i for i in result["info"]))


class ReadBackwardValidationTest(unittest.TestCase):
    """Validates the readBackward per-state allowlist (check #9)."""

    def _states(self, **overrides):
        # B (rank 2) -> A (rank 1) is a declared transition (matches both
        # node.transitions and transitionMatrix) — the shape readBackward
        # exists to allow a read to still take.
        base = {
            "A": {"rank": 1, "transitions": {"forward": "B"}},
            "B": {"rank": 2, "transitions": {"back": "A"}},
        }
        base.update(overrides)
        return base

    def _matrix(self):
        return {"SessionStart": ["A"], "A": ["B"], "B": ["A"]}

    def test_valid_readbackward_declaration_passes(self):
        doc = _minimal_doc(
            states=self._states(B={"rank": 2, "transitions": {"back": "A"}, "readBackward": ["A"]}),
            matrix=self._matrix(),
        )
        result = mod.validate_graph(doc)
        self.assertEqual(
            [e for e in result["errors"] if "readBackward" in e], [], result["errors"])

    def test_undeclared_transition_target_reported(self):
        # C is not in B's transitions/matrix targets at all.
        doc = _minimal_doc(
            states={
                "A": {"rank": 1, "transitions": {"forward": "B"}},
                "B": {"rank": 2, "transitions": {"back": "A"}, "readBackward": ["C"]},
                "C": {"rank": 0, "transitions": {}, "terminal": True},
            },
            matrix={"SessionStart": ["A"], "A": ["B"], "B": ["A"], "C": []},
        )
        result = mod.validate_graph(doc)
        self.assertTrue(
            any("B.readBackward lists 'C'" in e and "not a declared transition target" in e
                for e in result["errors"]),
            result["errors"],
        )

    def test_over_rank_target_reported(self):
        # A declares readBackward -> B, but B's rank (2) is HIGHER than A's
        # own rank (1) — that's already a forward read, not a backward one.
        doc = _minimal_doc(
            states=self._states(A={"rank": 1, "transitions": {"forward": "B"}, "readBackward": ["B"]}),
            matrix=self._matrix(),
        )
        result = mod.validate_graph(doc)
        self.assertTrue(
            any("A.readBackward lists 'B'" in e and "HIGHER than" in e for e in result["errors"]),
            result["errors"],
        )

    def test_clarify_in_readbackward_reported(self):
        doc = _minimal_doc(
            states={
                "A": {"rank": 1, "transitions": {"forward": "B", "clarify": "WF_CLARIFY"}, "readBackward": ["WF_CLARIFY"]},
                "B": {"rank": 2, "transitions": {}},
                "WF_CLARIFY": {"rank": -1, "transitions": {"clarified": "(return_to_caller)"}},
            },
            matrix={
                "SessionStart": ["A"],
                "A": ["B", "WF_CLARIFY"],
                "B": [],
                "WF_CLARIFY": ["(return_to_caller)"],
            },
        )
        result = mod.validate_graph(doc)
        self.assertTrue(
            any("A.readBackward lists WF_CLARIFY" in e for e in result["errors"]),
            result["errors"],
        )

    def test_subflow_in_readbackward_reported(self):
        doc = _minimal_doc(
            states=self._states(A={"rank": 1, "transitions": {"forward": "B", "init": "WF_INIT"}, "readBackward": ["WF_INIT"]}),
            matrix={"SessionStart": ["A"], "A": ["B", "WF_INIT"], "B": ["A"]},
            subflows=["WF_INIT"],
        )
        result = mod.validate_graph(doc)
        self.assertTrue(
            any("A.readBackward lists 'WF_INIT'" in e and "subflow" in e for e in result["errors"]),
            result["errors"],
        )


if __name__ == "__main__":
    unittest.main()
