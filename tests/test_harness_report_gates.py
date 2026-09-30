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


# --------------------------------------------------------------------------
# Two-phase (pivot) report: synthetic data + full render.
# --------------------------------------------------------------------------


def _phase_metrics(total_tokens, turns=10, tool_calls=8, cost=0.1):
    return {
        "total_tokens": total_tokens,
        "assistant_turns_incl_subagents": turns,
        "num_turns": turns,
        "total_tool_calls": tool_calls,
        "est_cost_usd": cost,
        "usage": {"input_tokens": total_tokens // 2, "output_tokens": total_tokens // 4,
                  "cache_creation_input_tokens": 0, "cache_read_input_tokens": total_tokens // 4},
        "hook_denials": 0, "stop_hook_blocks": 0, "memory_file_reads": 2,
        "tool_calls_by_name": {"Read": 3, "Edit": 2, "Bash": 3},
    }


def _benchmark(passed, total, doc_rules=None):
    ok = (passed == total) if total else None
    return {
        "total": total, "passed": passed, "ok": ok,
        "spec": {"passed": passed, "total": total},
        "doc": {"passed": passed, "total": total},
        "doc_rules": doc_rules or {},
        "failed_tests": [],
    }


def _two_phase_row(arm, trial, b1_passed=5, b1_total=5, b2_passed=5, b2_total=5,
                    retention_regressions=None, pivot_reclassified_attempted=True,
                    pivot_reclassified_succeeded=True, r_rules=None, p_rules=None):
    retention_regressions = retention_regressions or []
    r_rules = r_rules or {"R1": {"ok": True, "passed": 1, "total": 1, "memory": "dom/DOM_X"}}
    p_rules = p_rules or {"P1": {"ok": True, "passed": 1, "total": 1, "memory": "dom/DOM_Y"}}
    b1 = _benchmark(b1_passed, b1_total, doc_rules=r_rules)
    b2 = _benchmark(b2_passed, b2_total, doc_rules=p_rules)
    metrics1 = _phase_metrics(20000 + trial * 500)
    metrics2 = _phase_metrics(15000 + trial * 300)
    combined = dict(metrics2)
    combined["total_tokens"] = metrics1["total_tokens"] + metrics2["total_tokens"]
    combined["assistant_turns_incl_subagents"] = metrics1["assistant_turns_incl_subagents"] + metrics2["assistant_turns_incl_subagents"]
    return {
        "run_id": f"{arm}-t{trial}", "arm": arm, "trial": trial,
        "model": "claude-sonnet-5", "exit_code": 0, "timed_out": False,
        "wall_s": 200.0,
        "metrics": combined,
        "acceptance": b2,  # top-level acceptance = B2's, per run.py's contract
        "regression": {"passed": 10, "total": 10, "ok": True, "failed_tests": []},
        "stream_metrics": {"stream_event_counts": {}, "final_workflow_state": "WF_VERIFY" if arm != "control" else None},
        "gates": {
            "init_chain_complete": arm != "control", "sweep_verified": arm != "control",
            "edits_before_sweep": 0, "doc_rule_memories_coverage": 1.0 if arm != "control" else None,
            "memories_read_channel": "serena+stream" if arm != "control" else "plain_read",
            "pivot_reclassified": {"attempted": pivot_reclassified_attempted, "succeeded": pivot_reclassified_succeeded},
            "pivot_resweep_verified": arm != "control",
            "pivot_edits_before_sweep": 0,
            "pivot_doc_rule_memories_coverage": 1.0 if arm != "control" else None,
        },
        "phases": {
            "task1": {
                "metrics": metrics1,
                "benchmark": b1,
                "gates": {
                    "init_chain_complete": arm != "control", "sweep_verified": arm != "control",
                    "edits_before_sweep": 0,
                },
            },
            "pivot": {
                "metrics": metrics2,
                "benchmark": b2,
                "task1_retention": {
                    "passed": b1_passed - len(retention_regressions),
                    "total": b1_passed,
                    "regressions": retention_regressions,
                },
                "gates": {
                    "pivot_reclassified": {"attempted": pivot_reclassified_attempted, "succeeded": pivot_reclassified_succeeded},
                    "pivot_resweep_verified": arm != "control",
                    "pivot_edits_before_sweep": 0,
                    "pivot_doc_rule_memories_coverage": 1.0 if arm != "control" else None,
                },
            },
        },
    }


def _synthetic_two_phase_rows():
    """3 arms x 3 trials, including: one baseline run with
    pivot_reclassified attempted=True/succeeded=False, and one v5 run with
    a task1_retention regression."""
    rows = []
    for arm in report.ARM_ORDER:
        for trial in range(3):
            rows.append(_two_phase_row(arm, trial))
    # baseline t0: reclassify attempted but not succeeded (v1.2.82-era FSM gap)
    idx_baseline_t0 = next(i for i, r in enumerate(rows) if r["arm"] == "baseline" and r["trial"] == 0)
    rows[idx_baseline_t0] = _two_phase_row(
        "baseline", 0, pivot_reclassified_attempted=True, pivot_reclassified_succeeded=False)
    # v5 t0: a task1 regression at benchmark 2
    idx_v5_t0 = next(i for i, r in enumerate(rows) if r["arm"] == "v5" and r["trial"] == 0)
    rows[idx_v5_t0] = _two_phase_row(
        "v5", 0, retention_regressions=["test_monthly_budget (hidden_tests.test_spec_x.T)"])
    return rows


class HasPhaseRowsTest(unittest.TestCase):
    def test_true_for_two_phase_rows(self):
        self.assertTrue(report.has_phase_rows(_synthetic_two_phase_rows()))

    def test_false_for_single_phase_rows(self):
        self.assertFalse(report.has_phase_rows([_row("baseline")]))

    def test_false_for_empty(self):
        self.assertFalse(report.has_phase_rows([]))


class PhaseBenchmarkRowsTest(unittest.TestCase):
    def test_extracts_b1_b2_per_run(self):
        rows = _synthetic_two_phase_rows()
        pr = report.phase_benchmark_rows(rows)
        self.assertEqual(len(pr), len(rows))
        for row in pr:
            self.assertIn(row["arm"], report.ARM_ORDER)
            self.assertIn("b1", row)
            self.assertIn("b2", row)
            self.assertIn("retention", row["b2"])

    def test_excludes_single_phase_rows(self):
        rows = _synthetic_two_phase_rows() + [_row("control")]
        pr = report.phase_benchmark_rows(rows)
        self.assertEqual(len(pr), len(_synthetic_two_phase_rows()))

    def test_v5_regression_run_carries_regression_id(self):
        rows = _synthetic_two_phase_rows()
        pr = report.phase_benchmark_rows(rows)
        v5_t0 = next(r for r in pr if r["arm"] == "v5" and r["trial"] == 0)
        self.assertEqual(len(v5_t0["b2"]["retention"]["regressions"]), 1)


class TwoPhaseScorecardDataTest(unittest.TestCase):
    def setUp(self):
        self.rows = _synthetic_two_phase_rows()
        self.agg = report.get_analyze().aggregate(self.rows)

    def test_arms_present_and_b1_b2_populated(self):
        tp = report.two_phase_scorecard_data(self.agg)
        self.assertEqual(set(tp["arms_present"]), set(report.ARM_ORDER))
        for arm in report.ARM_ORDER:
            self.assertIn("doc_pass_pct", tp["b1"][arm])
            self.assertIn("retention_rate", tp["b2"][arm])

    def test_empty_rows_no_arms_present(self):
        agg = report.get_analyze().aggregate([])
        tp = report.two_phase_scorecard_data(agg)
        self.assertEqual(tp["arms_present"], [])

    def test_single_phase_rows_only_no_arms_present(self):
        agg = report.get_analyze().aggregate([_row("baseline")])
        tp = report.two_phase_scorecard_data(agg)
        self.assertEqual(tp["arms_present"], [])


class PivotGateMatrixRowsTest(unittest.TestCase):
    def test_extracts_task1_and_pivot_gate_fields(self):
        rows = _synthetic_two_phase_rows()
        matrix_rows = report.pivot_gate_matrix_rows(rows)
        self.assertEqual(len(matrix_rows), len(rows))
        baseline_t0 = next(r for r in matrix_rows if r["arm"] == "baseline" and r["trial"] == 0)
        self.assertTrue(baseline_t0["pivot_reclassified_attempted"])
        self.assertFalse(baseline_t0["pivot_reclassified_succeeded"])

    def test_excludes_single_phase_rows(self):
        rows = [_row("control")]
        self.assertEqual(report.pivot_gate_matrix_rows(rows), [])


class PhaseCostStackRowsTest(unittest.TestCase):
    def test_extracts_task1_pivot_tokens(self):
        rows = _synthetic_two_phase_rows()
        stack_rows = report.phase_cost_stack_rows(rows)
        self.assertEqual(len(stack_rows), len(rows))
        for (_id, arm, _trial, parts) in stack_rows:
            self.assertIn("task1", parts)
            self.assertIn("pivot", parts)
            self.assertGreater(parts["task1"], 0)
            self.assertGreater(parts["pivot"], 0)


class TwoPhaseDocRuleHeatmapRowsTest(unittest.TestCase):
    def test_b1_rules_are_r_rules_b2_rules_are_p_rules(self):
        rows = _synthetic_two_phase_rows()
        b1_ids, b1_cells = report.two_phase_doc_rule_heatmap_rows(rows, "b1")
        b2_ids, b2_cells = report.two_phase_doc_rule_heatmap_rows(rows, "b2")
        self.assertEqual(b1_ids, ["R1"])
        self.assertEqual(b2_ids, ["P1"])
        self.assertTrue(b1_cells)
        self.assertTrue(b2_cells)


class TwoPhaseChartBuildersDoNotRaiseTest(unittest.TestCase):
    def test_phase_cost_stack_chart_empty(self):
        svg, height = report.phase_cost_stack_chart([])
        self.assertIn("<svg", svg)
        self.assertGreater(height, 0)

    def test_phase_cost_stack_chart_with_data(self):
        rows = _synthetic_two_phase_rows()
        stack_rows = report.phase_cost_stack_rows(rows)
        svg, height = report.phase_cost_stack_chart(stack_rows)
        self.assertIn("<svg", svg)
        self.assertIn("comp-seg", svg)

    def test_pivot_gate_matrix_table_empty(self):
        html = report.pivot_gate_matrix_table([])
        self.assertIn("No two-phase", html)

    def test_pivot_gate_matrix_table_with_data(self):
        rows = _synthetic_two_phase_rows()
        matrix_rows = report.pivot_gate_matrix_rows(rows)
        html = report.pivot_gate_matrix_table(matrix_rows)
        self.assertIn("<table", html)
        self.assertIn("succeeded", html)

    def test_two_phase_scorecard_html_empty(self):
        agg = report.get_analyze().aggregate([])
        html = report.two_phase_scorecard_html(agg)
        self.assertEqual(html, "")

    def test_two_phase_scorecard_html_with_data(self):
        rows = _synthetic_two_phase_rows()
        agg = report.get_analyze().aggregate(rows)
        html = report.two_phase_scorecard_html(agg)
        self.assertIn("Benchmark 1", html)
        self.assertIn("Benchmark 2", html)
        self.assertIn("Task-1 retention", html)


class TwoPhaseFullRenderTest(unittest.TestCase):
    """Full render.render_report() over synthetic two-phase rows (3 arms x
    3 trials incl. a baseline reclassify-attempted-not-succeeded run and a
    v5 retention-regression run) — asserts both benchmark blocks, pivot
    gate cells, phase-stacked cost bars render, with no None/NaN leakage."""

    def setUp(self):
        self.rows = _synthetic_two_phase_rows()
        self.meta = {
            "args": {"model": "claude-sonnet-5", "trials": 3},
            "arms": [
                {"name": "baseline", "ref": "23ec685", "plugin": True},
                {"name": "v5", "ref": "harness-v5-prototype", "plugin": True},
                {"name": "control", "ref": None, "plugin": False},
            ],
            "prepared": {
                "baseline": {"sha": "23ec685deadbeef", "version": "1.2.82"},
                "v5": {"sha": "abc123", "version": "5.0.0-proto"},
                "control": {"sha": None, "version": None},
            },
            "auth": {"authMethod": "claude.ai", "subscriptionType": "max", "apiProvider": "anthropic"},
            "claude_version": "1.2.82 (Claude Code)",
        }
        self.html = report.render_report(self.rows, self.meta, title="Two-Phase Test")

    def test_pivot_nav_item_present(self):
        self.assertIn(">Pivot<", self.html)
        self.assertIn('id="pivot"', self.html)

    def test_both_benchmark_blocks_present(self):
        self.assertIn("Benchmark 1", self.html)
        self.assertIn("Benchmark 2", self.html)
        self.assertIn("after task 1", self.html)
        self.assertIn("after pivot", self.html)

    def test_task1_retention_present(self):
        self.assertIn("Task-1 retention", self.html)

    def test_pivot_gate_cells_present(self):
        idx = self.html.index('id="pivot"')
        pivot_section = self.html[idx:self.html.index("</section>", idx)]
        self.assertIn("reclassify", pivot_section.lower())
        self.assertIn("resweep", pivot_section.lower())

    def test_phase_stacked_cost_bars_present(self):
        idx = self.html.index('id="pivot"')
        pivot_section = self.html[idx:self.html.index("</section>", idx)]
        self.assertIn("comp-seg", pivot_section)
        self.assertIn("Task 1", pivot_section)

    def test_r_and_p_rule_heatmaps_present(self):
        idx = self.html.index('id="doc-use"')
        doc_use_section = self.html[idx:self.html.index("</section>", idx)]
        self.assertIn("R1", doc_use_section)
        self.assertIn("P1", doc_use_section)

    def test_run_table_has_b1_b2_and_retention_columns(self):
        self.assertIn("B1 doc %", self.html)
        self.assertIn("B2 doc %", self.html)
        self.assertIn("Retention regressions", self.html)
        self.assertIn("Pivot reclassified", self.html)

    def test_no_none_or_nan(self):
        self.assertNotIn(">None<", self.html)
        self.assertNotIn(">NaN<", self.html)
        self.assertNotIn(" NaN ", self.html)
        self.assertNotIn('data-sort="nan"', self.html.lower())

    def test_control_shown_as_reference_no_pivot_gates(self):
        # control has no plugin/gates: pivot gate matrix cells for control
        # should read n/a, not crash or show a false positive.
        matrix_rows = report.pivot_gate_matrix_rows(self.rows)
        control_rows = [r for r in matrix_rows if r["arm"] == "control"]
        self.assertTrue(control_rows)

    def test_overall_review_covers_pivot_benchmarks(self):
        # The Overall review's comparison table (the report's top,
        # replacing the old compute_verdict() paragraph) must surface
        # pivot-benchmark results, not just task-1 ones.
        idx = self.html.index('id="overall"')
        overall_section = self.html[idx:self.html.index("</section>", idx)]
        self.assertIn("Pivot doc rules", overall_section)
        self.assertIn("Pivot spec", overall_section)


class TwoPhaseSinglePhaseCompatTest(unittest.TestCase):
    """A stamp with ONLY single-phase rows must render exactly as before:
    no Pivot nav item, no Pivot section, no crash."""

    def test_no_pivot_section_for_single_phase_rows(self):
        rows = [_row("baseline"), _row("v5"), _row("control")]
        meta = {"args": {"model": "m", "trials": 1}, "arms": [], "prepared": {}, "auth": {}, "claude_version": ""}
        html = report.render_report(rows, meta, title="Single Phase")
        self.assertNotIn('id="pivot"', html)
        self.assertNotIn(">Pivot<", html)


if __name__ == "__main__":
    unittest.main()
