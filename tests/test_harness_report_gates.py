"""Tests for the new gate-conformance/spec-doc chart functions added to
experiments/harness-ab/report.py: spec_doc_bar_rows, doc_rule_heatmap_rows,
gate_conformance_rows, memory_coverage_rows, and their SVG/table builders."""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(HERE, "..", "experiments", "harness-ab", "report.py")


def _load_report():
    spec = importlib.util.spec_from_file_location("harness_ab_report_gates", REPORT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


report = _load_report()


def _row(arm, trial=0, spec=None, doc=None, doc_rules=None, gates=None):
    acc = {"total": 0, "passed": 0}
    if spec is not None:
        acc["spec"] = spec
    if doc is not None:
        acc["doc"] = doc
    if doc_rules is not None:
        acc["doc_rules"] = doc_rules
    return {
        "run_id": f"{arm}-t{trial}", "arm": arm, "trial": trial,
        "acceptance": acc, "gates": gates,
    }


class SpecDocBarRowsTest(unittest.TestCase):
    def test_maps_arm_to_spec_doc_pct(self):
        rows = [_row("baseline", spec={"passed": 3, "total": 4}, doc={"passed": 2, "total": 2})]
        result = report.spec_doc_bar_rows(rows)
        self.assertAlmostEqual(result["baseline"]["spec"], 75.0)
        self.assertAlmostEqual(result["baseline"]["doc"], 100.0)

    def test_arm_with_no_data_is_none(self):
        result = report.spec_doc_bar_rows([])
        self.assertIsNone(result["control"]["spec"])
        self.assertIsNone(result["control"]["doc"])


class DocRuleHeatmapRowsTest(unittest.TestCase):
    def test_collects_rule_ids_and_cells(self):
        rows = [
            _row("baseline", trial=0, doc_rules={"R1": {"ok": True}, "R2": {"ok": False}}),
            _row("v5", trial=0, doc_rules={"R1": {"ok": False}}),
        ]
        rule_ids, per_cell = report.doc_rule_heatmap_rows(rows)
        self.assertEqual(rule_ids, ["R1", "R2"])
        self.assertTrue(per_cell[("baseline", "baseline-t0")]["R1"])
        self.assertFalse(per_cell[("baseline", "baseline-t0")]["R2"])
        self.assertFalse(per_cell[("v5", "v5-t0")]["R1"])

    def test_no_doc_rules_gives_empty(self):
        rule_ids, per_cell = report.doc_rule_heatmap_rows([_row("control")])
        self.assertEqual(rule_ids, [])
        self.assertEqual(per_cell, {})

    def test_ignores_non_arm_rows(self):
        rows = [_row("unknown-arm", doc_rules={"R1": {"ok": True}})]
        rule_ids, per_cell = report.doc_rule_heatmap_rows(rows)
        self.assertEqual(rule_ids, [])


class GateConformanceRowsTest(unittest.TestCase):
    def test_extracts_gate_fields(self):
        rows = [_row("baseline", gates={
            "init_chain_complete": True, "sweep_verified": True,
            "edits_before_sweep": 0, "doc_rule_memories_coverage": 1.0,
            "memories_read_channel": "serena+stream",
        })]
        result = report.gate_conformance_rows(rows)
        self.assertEqual(len(result), 1)
        r = result[0]
        self.assertTrue(r["has_gates"])
        self.assertTrue(r["init_chain_complete"])
        self.assertEqual(r["edits_before_sweep"], 0)

    def test_missing_gates_has_gates_false(self):
        rows = [_row("control", gates=None)]
        result = report.gate_conformance_rows(rows)
        self.assertFalse(result[0]["has_gates"])
        self.assertIsNone(result[0]["init_chain_complete"])


class MemoryCoverageRowsTest(unittest.TestCase):
    def test_counts_memories_read(self):
        rows = [_row("baseline", gates={
            "memories_read": ["wf/wf_init", "dom/dom_x"],
            "doc_rule_memories_coverage": 0.5,
            "memories_read_channel": "serena+stream",
        })]
        result = report.memory_coverage_rows(rows)
        self.assertEqual(result[0]["n_memories_read"], 2)
        self.assertEqual(result[0]["doc_rule_memories_coverage"], 0.5)

    def test_no_gates_zero_memories(self):
        rows = [_row("control", gates=None)]
        result = report.memory_coverage_rows(rows)
        self.assertEqual(result[0]["n_memories_read"], 0)


class ChartBuildersDoNotRaiseTest(unittest.TestCase):
    """SVG/table builders must render valid strings even with sparse/empty
    input (missing doc_rules, control arm with no gates, etc.) -- a report
    over a v1-shaped stamp with none of this data must still render."""

    def test_spec_doc_grouped_bar_chart_with_missing_data(self):
        svg, height = report.spec_doc_grouped_bar_chart({"baseline": {"spec": None, "doc": None}})
        self.assertIn("<svg", svg)
        self.assertGreater(height, 0)

    def test_doc_rule_heatmap_table_empty(self):
        html = report.doc_rule_heatmap_table([], {})
        self.assertIn("No doc_rules.json", html)

    def test_doc_rule_heatmap_table_with_data(self):
        html = report.doc_rule_heatmap_table(
            ["R1"], {("baseline", "baseline-t0"): {"R1": True}})
        self.assertIn("R1", html)
        self.assertIn("pass", html)

    def test_gate_conformance_table_empty(self):
        html = report.gate_conformance_table([])
        self.assertIn("<table", html)

    def test_gate_conformance_table_with_data(self):
        rows = report.gate_conformance_rows([_row("baseline", gates={
            "init_chain_complete": True, "sweep_verified": False,
            "edits_before_sweep": 2, "doc_rule_memories_coverage": 0.25,
            "memories_read_channel": "serena+stream",
        })])
        html = report.gate_conformance_table(rows)
        self.assertIn("yes", html)
        self.assertIn("no", html)

    def test_memory_coverage_dot_chart_empty(self):
        svg = report.memory_coverage_dot_chart([])
        self.assertIn("<svg", svg)

    def test_memory_coverage_dot_chart_with_data(self):
        rows = report.memory_coverage_rows([_row("baseline", gates={
            "memories_read": ["a/b"], "doc_rule_memories_coverage": 0.8,
            "memories_read_channel": "serena+stream",
        })])
        svg = report.memory_coverage_dot_chart(rows)
        self.assertIn("<circle", svg)


if __name__ == "__main__":
    unittest.main()
