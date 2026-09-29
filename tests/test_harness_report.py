#!/usr/bin/env python3
"""Tests for experiments/harness-ab/report.py.

Builds a synthetic runs.jsonl (3 arms x 3 trials, including one timed-out run
and one run missing metrics) in a temp dir, renders the report, and asserts
on the resulting HTML. Also unit-tests the pure scale-math helpers directly.
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(HERE, "..", "experiments", "harness-ab", "report.py")


def _load_report():
    spec = importlib.util.spec_from_file_location("harness_ab_report", REPORT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


report = _load_report()


# --------------------------------------------------------------------------
# Pure math helpers.
# --------------------------------------------------------------------------

class TestLinearScale(unittest.TestCase):
    def test_basic_mapping(self):
        scale = report.linear_scale((0, 10), (0, 100))
        self.assertAlmostEqual(scale(0), 0)
        self.assertAlmostEqual(scale(10), 100)
        self.assertAlmostEqual(scale(5), 50)

    def test_inverted_range(self):
        scale = report.linear_scale((0, 10), (100, 0))
        self.assertAlmostEqual(scale(0), 100)
        self.assertAlmostEqual(scale(10), 0)

    def test_degenerate_domain(self):
        scale = report.linear_scale((5, 5), (0, 100))
        self.assertAlmostEqual(scale(5), 50)
        self.assertAlmostEqual(scale(999), 50)

    def test_negative_domain(self):
        scale = report.linear_scale((-10, 10), (0, 100))
        self.assertAlmostEqual(scale(-10), 0)
        self.assertAlmostEqual(scale(0), 50)
        self.assertAlmostEqual(scale(10), 100)


class TestNiceTicks(unittest.TestCase):
    def test_simple_range(self):
        ticks = report.nice_ticks(0, 100, 5)
        self.assertTrue(len(ticks) >= 2)
        self.assertLessEqual(ticks[0], 0)
        self.assertGreaterEqual(ticks[-1], 100)

    def test_equal_bounds_zero(self):
        ticks = report.nice_ticks(0, 0, 5)
        self.assertIsInstance(ticks, list)
        self.assertTrue(len(ticks) >= 1)

    def test_equal_bounds_nonzero(self):
        ticks = report.nice_ticks(42, 42, 5)
        self.assertIsInstance(ticks, list)
        self.assertTrue(len(ticks) >= 1)

    def test_none_inputs(self):
        ticks = report.nice_ticks(None, None, 5)
        self.assertEqual(ticks, [0])

    def test_swapped_bounds(self):
        ticks = report.nice_ticks(100, 0, 5)
        self.assertLessEqual(ticks[0], 0)
        self.assertGreaterEqual(ticks[-1], 100)

    def test_small_range(self):
        ticks = report.nice_ticks(1, 3, 5)
        self.assertLessEqual(ticks[0], 1)
        self.assertGreaterEqual(ticks[-1], 3)


class TestMedian(unittest.TestCase):
    def test_odd(self):
        self.assertEqual(report.median([1, 3, 2]), 2)

    def test_even(self):
        self.assertEqual(report.median([1, 2, 3, 4]), 2.5)

    def test_empty(self):
        self.assertIsNone(report.median([]))

    def test_with_nones(self):
        self.assertEqual(report.median([1, None, 3, None, 2]), 2)


# --------------------------------------------------------------------------
# Data extraction helpers.
# --------------------------------------------------------------------------

class TestDataExtraction(unittest.TestCase):
    def setUp(self):
        self.rows = _synthetic_rows()

    def test_rows_for_metric_skips_missing(self):
        getter = lambda r: report.g(r, "metrics", "num_turns")
        out = report.rows_for_metric(self.rows, getter)
        arms_seen = {a for (a, _t, _v) in out}
        self.assertTrue(arms_seen.issubset(set(report.ARM_ORDER)))
        # the missing-metrics run should be excluded
        self.assertEqual(len(out), len(self.rows) - 1)

    def test_token_composition_rows_defaults_zero(self):
        comp = report.token_composition_rows(self.rows)
        self.assertEqual(len(comp), len(self.rows))
        for (_id, _arm, _trial, parts) in comp:
            for k in ("input", "output", "cache_creation", "cache_read"):
                self.assertIn(k, parts)
                self.assertIsInstance(parts[k], (int, float))

    def test_acceptance_rows(self):
        acc = report.acceptance_rows(self.rows)
        self.assertEqual(len(acc), len(self.rows))
        for r in acc:
            self.assertIn(r["arm"], report.ARM_ORDER)

    def test_tool_mix_rows_caps_and_folds_other(self):
        tool_order, per_arm = report.tool_mix_rows(self.rows, top_n=2)
        self.assertLessEqual(len(tool_order), 3)  # top_n + Other
        for arm in report.ARM_ORDER:
            self.assertIn(arm, per_arm)

    def test_compute_verdict_nonempty(self):
        agg = report.get_analyze().aggregate(self.rows)
        verdict = report.compute_verdict(agg)
        self.assertIsInstance(verdict, str)
        self.assertGreater(len(verdict), 0)

    def test_compute_verdict_empty_rows(self):
        agg = report.get_analyze().aggregate([])
        verdict = report.compute_verdict(agg)
        self.assertIsInstance(verdict, str)


# --------------------------------------------------------------------------
# Full render.
# --------------------------------------------------------------------------


def _synthetic_rows():
    rows = []
    for arm in report.ARM_ORDER:
        for trial in range(3):
            row = {
                "run_id": f"{arm}-t{trial}",
                "arm": arm,
                "trial": trial,
                "model": "claude-sonnet-5",
                "exit_code": 0,
                "timed_out": False,
                "wall_s": 100.0 + trial * 10 + (5 if arm == "v5" else 0),
                "metrics": {
                    "num_turns": 20 + trial + (2 if arm == "control" else 0),
                    "total_tokens": 50000 + trial * 1000,
                    "total_tool_calls": 30 + trial,
                    "hook_denials": 1 if arm != "control" else 0,
                    "stop_hook_blocks": 0,
                    "est_cost_usd": 0.5 + trial * 0.1,
                    "usage": {
                        "input_tokens": 10000 + trial * 100,
                        "output_tokens": 5000 + trial * 50,
                        "cache_creation_input_tokens": 2000,
                        "cache_read_input_tokens": 30000,
                    },
                    "tool_calls_by_name": {
                        "Read": 10, "Edit": 5, "Bash": 8, "Write": 2,
                        "Grep": 3, "Glob": 1, "Agent": 1, "TodoWrite": 1,
                        "WeirdTool": 1,
                    },
                    "assistant_turns_incl_subagents": 35 + trial + (4 if arm == "control" else 0),
                    "memory_file_reads": 3 + trial + (2 if arm != "control" else 0),
                },
                "acceptance": {"passed": 4, "total": 5, "ok": False, "failed_tests": ["test_x (tests.test_y.Z)"]},
                "regression": {"passed": 10, "total": 10, "ok": True, "failed_tests": []},
                "stream_metrics": {
                    "stream_event_counts": {"tool_call": 12, "state_transition": 3} if arm != "control" else {},
                    "final_workflow_state": "WF_VERIFY" if arm != "control" else None,
                },
            }
            rows.append(row)

    # one timed-out run
    rows[0]["timed_out"] = True
    rows[0]["exit_code"] = -1
    rows[0]["acceptance"] = {"passed": 0, "total": 5, "ok": False}
    rows[0]["regression"] = {"passed": 0, "total": 10, "ok": False}

    # one run missing metrics entirely
    rows[-1]["metrics"] = {}
    rows[-1]["acceptance"] = {}
    rows[-1]["regression"] = {}
    rows[-1]["stream_metrics"] = {}

    return rows


class TestRenderReport(unittest.TestCase):
    def setUp(self):
        self.rows = _synthetic_rows()
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
        self.html = report.render_report(self.rows, self.meta, title="Harness A/B Results")

    def test_html_written_to_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "report.html")
            with open(out_path, "w") as f:
                f.write(self.html)
            self.assertTrue(os.path.exists(out_path))
            self.assertGreater(os.path.getsize(out_path), 1000)

    def test_has_svg_per_chart_section(self):
        # dot/strip small multiples (5), token composition, acceptance,
        # friction, tool mix => at least 5 + 4 = 9 svg elements
        count = self.html.count("<svg")
        self.assertGreaterEqual(count, 9)

    def test_contains_every_arm_name(self):
        for arm in report.ARM_ORDER:
            self.assertIn(report.ARM_LABELS[arm], self.html)

    def test_contains_every_run_row(self):
        # every arm+trial combination appears in the per-run table (rendered
        # as "<arm label> t<trial>" in row labels / table cells)
        for arm in report.ARM_ORDER:
            for trial in range(3):
                self.assertIn(f"t{trial}", self.html)

    def test_no_nan_or_bare_none_text(self):
        # "isNaN" is legitimate JS; only reject NaN as rendered DATA (a bare
        # token, or inside a value/tooltip attribute).
        self.assertNotIn(">NaN<", self.html)
        self.assertNotIn(" NaN ", self.html)
        self.assertNotIn(">None<", self.html)
        self.assertNotIn('data-sort="nan"', self.html.lower())
        self.assertNotIn('data-tip="nan', self.html.lower())

    def test_missing_fields_render_em_dash(self):
        # the last synthetic run has empty metrics/acceptance/regression;
        # em-dash placeholder must appear somewhere for it
        self.assertIn("—", self.html)

    def test_tooltip_data_attributes_present(self):
        self.assertIn("data-tip=", self.html)

    def test_title_element(self):
        self.assertIn("<title>Harness A/B Results</title>", self.html)

    def test_no_dual_axis_hint(self):
        # sanity: we never render a second y-axis scale marker
        self.assertNotIn("secondary-axis", self.html)

    def test_arm_colors_no_aqua(self):
        # arm colors must be blue/orange/green — no aqua/teal/cyan hex families
        forbidden = ["#1baf7a", "#199e70", "#0bb", "#0bc", "#0cc"]
        for f in forbidden:
            self.assertNotIn(f, self.html.lower())
        self.assertIn(report.ARM_COLOR_LIGHT["baseline"], self.html)
        self.assertIn(report.ARM_COLOR_LIGHT["v5"], self.html)
        self.assertIn(report.ARM_COLOR_LIGHT["control"], self.html)

    def test_sortable_table_present(self):
        self.assertIn('id="run-table"', self.html)
        self.assertIn("data-sort-key", self.html)

    def test_verdict_present(self):
        self.assertIn('class="verdict"', self.html)

    def test_kpi_row_present(self):
        self.assertIn("kpi-card", self.html)

    def test_method_section_present(self):
        self.assertIn("Method &amp; caveats", self.html)

    def test_memory_consultations_chart_present(self):
        self.assertIn("Memory consultations", self.html)

    def test_turns_all_agents_label_present(self):
        self.assertIn("Turns (all agents)", self.html)
        self.assertIn("Turns (main-agent only)", self.html)

    def test_failed_tests_column_present(self):
        self.assertIn("Failed tests", self.html)
        self.assertIn("test_x", self.html)

    def test_verdict_uses_all_agent_language_not_bare_turns(self):
        # The verdict sentence must talk about "turns (all agents)" /
        # "tokens (all models)", never a bare "turns"/"tokens" that could be
        # misread as the main-agent-only figures.
        agg = report.get_analyze().aggregate(self.rows)
        verdict = report.compute_verdict(agg)
        if "vs baseline" in verdict:
            self.assertIn("turns (all agents)", verdict)
            self.assertIn("tokens (all models)", verdict)

    def test_notes_injects_findings_section(self):
        html = report.render_report(self.rows, self.meta, title="Harness A/B Results",
                                     notes_html="<p>Custom finding text ABC123.</p>")
        self.assertIn("Findings", html)
        self.assertIn("Custom finding text ABC123.", html)
        # Findings section must appear before the KPI row section in the
        # document body (the .kpi-card CSS class appears earlier still, in
        # the <style> block, so anchor on the body-only kpi-row section tag).
        self.assertLess(html.index("Custom finding text ABC123."), html.index('<section class="kpi-row">'))

    def test_no_notes_omits_findings_section(self):
        self.assertNotIn("Custom finding text", self.html)


class ShortTestNameTest(unittest.TestCase):
    def test_typical_unittest_id(self):
        self.assertEqual(
            report.short_test_name("test_foo (tests.test_bar.MyTest)"),
            "MyTest.test_foo",
        )

    def test_unrecognized_format_returned_as_is(self):
        self.assertEqual(report.short_test_name("weird-id"), "weird-id")

    def test_python311plus_dotted_method_shape(self):
        # Python 3.11+ repeats the method name at the end of the dotted path.
        self.assertEqual(
            report.short_test_name("test_fails (tests.test_sample.T.test_fails)"),
            "T.test_fails",
        )

    def test_none_and_empty(self):
        self.assertIsNone(report.short_test_name(None))
        self.assertEqual(report.short_test_name(""), "")


class FailedTestsCellTextTest(unittest.TestCase):
    def test_both_acceptance_and_regression_failures(self):
        acc = {"failed_tests": ["test_a (m.A)"]}
        reg = {"failed_tests": ["test_b (m.B)"]}
        text = report.failed_tests_cell_text(acc, reg)
        self.assertIn("A: A.test_a", text)
        self.assertIn("R: B.test_b", text)

    def test_no_failures_empty_string(self):
        self.assertEqual(report.failed_tests_cell_text({}, {}), "")
        self.assertEqual(
            report.failed_tests_cell_text({"failed_tests": []}, {"failed_tests": []}), ""
        )


class TestCLI(unittest.TestCase):
    def test_main_writes_file(self):
        rows = _synthetic_rows()
        meta = {"args": {"model": "claude-sonnet-5", "trials": 3}, "arms": [], "prepared": {},
                "auth": {}, "claude_version": ""}
        with tempfile.TemporaryDirectory() as tmp:
            stamp_dir = os.path.join(tmp, "stamp")
            os.makedirs(stamp_dir)
            with open(os.path.join(stamp_dir, "runs.jsonl"), "w") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
            with open(os.path.join(stamp_dir, "meta.json"), "w") as f:
                json.dump(meta, f)

            out_path = os.path.join(tmp, "out.html")
            rc = report.main([stamp_dir, "--out", out_path, "--title", "Test Title"])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(out_path))
            with open(out_path) as f:
                content = f.read()
            self.assertIn("<title>Test Title</title>", content)


if __name__ == "__main__":
    unittest.main()
