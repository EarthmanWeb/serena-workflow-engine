"""Tests for the new gate-conformance / spec-doc rollup functions added to
experiments/harness-ab/analyze.py (section 5 of the task-variant work):
spec_doc_pass_stats, gate_conformance_stats, doc_rule_pass_matrix, and their
wiring into aggregate()/format_markdown()."""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
HARNESS_DIR = os.path.join(REPO_ROOT, "experiments", "harness-ab")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


analyze = _load("harness_ab_analyze_gates", os.path.join(HARNESS_DIR, "analyze.py"))


def _row(arm, spec=None, doc=None, gates=None, doc_rules=None, trial=0):
    acc = {"total": 0, "passed": 0}
    if spec is not None:
        acc["spec"] = spec
    if doc is not None:
        acc["doc"] = doc
    if doc_rules is not None:
        acc["doc_rules"] = doc_rules
    return {
        "arm": arm, "trial": trial,
        "acceptance": acc,
        "regression": {"ok": True},
        "gates": gates,
        "wall_s": 1.0,
    }


class SpecDocPassStatsTest(unittest.TestCase):
    def test_mean_pass_pct_per_arm(self):
        rows = [
            _row("baseline", spec={"passed": 3, "total": 4}, doc={"passed": 2, "total": 2}),
            _row("baseline", spec={"passed": 2, "total": 4}, doc={"passed": 1, "total": 2}),
        ]
        stats = analyze.spec_doc_pass_stats(rows)
        self.assertAlmostEqual(stats["baseline"]["spec_pass_pct_mean"], 62.5)
        self.assertAlmostEqual(stats["baseline"]["doc_pass_pct_mean"], 75.0)

    def test_missing_category_is_none(self):
        rows = [_row("control")]
        stats = analyze.spec_doc_pass_stats(rows)
        self.assertIsNone(stats["control"]["spec_pass_pct_mean"])
        self.assertIsNone(stats["control"]["doc_pass_pct_mean"])

    def test_zero_total_category_excluded_not_zero(self):
        rows = [_row("v5", spec={"passed": 0, "total": 0})]
        stats = analyze.spec_doc_pass_stats(rows)
        self.assertIsNone(stats["v5"]["spec_pass_pct_mean"])


class GateConformanceStatsTest(unittest.TestCase):
    def test_rates_and_means(self):
        rows = [
            _row("baseline", gates={"init_chain_complete": True, "sweep_verified": True,
                                     "edits_before_sweep": 0, "doc_rule_memories_coverage": 1.0}),
            _row("baseline", gates={"init_chain_complete": False, "sweep_verified": True,
                                     "edits_before_sweep": 2, "doc_rule_memories_coverage": 0.5}),
        ]
        stats = analyze.gate_conformance_stats(rows)
        s = stats["baseline"]
        self.assertEqual(s["n_with_gates"], 2)
        self.assertAlmostEqual(s["init_chain_complete_rate"], 0.5)
        self.assertAlmostEqual(s["sweep_verified_rate"], 1.0)
        self.assertAlmostEqual(s["edits_before_sweep_mean"], 1.0)
        self.assertAlmostEqual(s["doc_rule_memories_coverage_mean"], 0.75)

    def test_rows_without_gates_field_excluded(self):
        rows = [_row("control", gates=None)]
        stats = analyze.gate_conformance_stats(rows)
        s = stats["control"]
        self.assertEqual(s["n_with_gates"], 0)
        self.assertIsNone(s["init_chain_complete_rate"])
        self.assertIsNone(s["sweep_verified_rate"])

    def test_mixed_gates_and_no_gates_rows(self):
        rows = [
            _row("v5", gates={"init_chain_complete": True, "sweep_verified": True,
                               "edits_before_sweep": 0, "doc_rule_memories_coverage": 1.0}),
            _row("v5", gates=None),
        ]
        stats = analyze.gate_conformance_stats(rows)
        self.assertEqual(stats["v5"]["n_with_gates"], 1)
        self.assertEqual(stats["v5"]["init_chain_complete_rate"], 1.0)


class DocRulePassMatrixTest(unittest.TestCase):
    def test_aggregates_across_runs(self):
        rows = [
            _row("baseline", doc_rules={"R1": {"passed": 1, "total": 1, "memory": "dom/DOM_X"}}),
            _row("baseline", doc_rules={"R1": {"passed": 0, "total": 1, "memory": "dom/DOM_X"}}),
        ]
        matrix = analyze.doc_rule_pass_matrix(rows)
        entry = matrix["baseline"]["R1"]
        self.assertEqual(entry["passed"], 1)
        self.assertEqual(entry["total"], 2)
        self.assertFalse(entry["ok"])
        self.assertEqual(entry["memory"], "dom/DOM_X")

    def test_no_doc_rules_returns_empty_dict_for_arm(self):
        rows = [_row("control")]
        matrix = analyze.doc_rule_pass_matrix(rows)
        self.assertEqual(matrix.get("control", {}), {})

    def test_full_pass_marks_ok_true(self):
        rows = [_row("v5", doc_rules={"R2": {"passed": 3, "total": 3, "memory": "ref/REF_Y"}})]
        matrix = analyze.doc_rule_pass_matrix(rows)
        self.assertTrue(matrix["v5"]["R2"]["ok"])

    def test_zero_total_rule_ok_is_none(self):
        rows = [_row("v5", doc_rules={"R3": {"passed": 0, "total": 0, "memory": "x"}})]
        matrix = analyze.doc_rule_pass_matrix(rows)
        self.assertIsNone(matrix["v5"]["R3"]["ok"])


class AggregateIncludesNewFieldsTest(unittest.TestCase):
    def test_aggregate_output_has_gate_conformance_and_doc_rule_matrix(self):
        rows = [
            _row("baseline", spec={"passed": 1, "total": 1}, doc={"passed": 1, "total": 1},
                 gates={"init_chain_complete": True, "sweep_verified": True,
                        "edits_before_sweep": 0, "doc_rule_memories_coverage": 1.0},
                 doc_rules={"R1": {"passed": 1, "total": 1, "memory": "dom/DOM_X"}}),
        ]
        agg = analyze.aggregate(rows)
        self.assertIn("gate_conformance", agg["arms"]["baseline"])
        self.assertIn("spec_pass_pct_mean", agg["arms"]["baseline"])
        self.assertIn("doc_pass_pct_mean", agg["arms"]["baseline"])
        self.assertIn("doc_rule_matrix", agg)
        self.assertIn("R1", agg["doc_rule_matrix"]["baseline"])

    def test_format_markdown_does_not_raise_with_new_fields(self):
        rows = [
            _row("baseline", spec={"passed": 1, "total": 2}, doc={"passed": 1, "total": 1},
                 gates={"init_chain_complete": True, "sweep_verified": False,
                        "edits_before_sweep": 1, "doc_rule_memories_coverage": 0.5},
                 doc_rules={"R1": {"passed": 1, "total": 1, "memory": "dom/DOM_X"}}),
            _row("control"),
        ]
        agg = analyze.aggregate(rows)
        md = analyze.format_markdown(agg)
        self.assertIn("spec_pass%", md)
        self.assertIn("init_chain_complete%", md)
        self.assertIn("R1", md)


if __name__ == "__main__":
    unittest.main()
