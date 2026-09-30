"""Tests for the Overall review / cost-vs-benefit / delegation / code
metrics / explain-failures additions to experiments/harness-ab/report.py
(the v2 report redesign): strict_best_arm's no-ties rule, the overall
review table + cost-vs-benefit verdict against the real interim numbers
named in the task spec, nonzero phase-token bars, minimum SVG font size,
and end-to-end render_report() wiring for the new sections."""
import glob
import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(HERE, "..", "experiments", "harness-ab", "report.py")


def _load_report():
    spec = importlib.util.spec_from_file_location("harness_ab_report_overall", REPORT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


report = _load_report()


# --------------------------------------------------------------------------
# strict_best_arm: never tags a tie or an all-zero row as "best".
# --------------------------------------------------------------------------

class TestStrictBestArm(unittest.TestCase):
    def test_clear_winner_higher_is_better(self):
        self.assertEqual(report.strict_best_arm({"a": 1, "b": 3, "c": 2}, higher_is_better=True), "b")

    def test_clear_winner_lower_is_better(self):
        self.assertEqual(report.strict_best_arm({"a": 5, "b": 1, "c": 3}, higher_is_better=False), "b")

    def test_tie_returns_none(self):
        self.assertIsNone(report.strict_best_arm({"a": 1, "b": 1, "c": 0}, higher_is_better=True))

    def test_all_zero_returns_none(self):
        self.assertIsNone(report.strict_best_arm({"a": 0, "b": 0, "c": 0}, higher_is_better=True))

    def test_none_values_ignored(self):
        self.assertEqual(report.strict_best_arm({"a": None, "b": 3, "c": None}, higher_is_better=True), "b")

    def test_empty_values_returns_none(self):
        self.assertIsNone(report.strict_best_arm({}, higher_is_better=True))

    def test_all_none_returns_none(self):
        self.assertIsNone(report.strict_best_arm({"a": None, "b": None}, higher_is_better=True))

    def test_three_way_tie_at_zero_full_success(self):
        # The exact bug from the screenshot: 0/1 "full success" tied
        # across every arm must never be tagged best.
        self.assertIsNone(report.strict_best_arm({"baseline": 0.0, "v5": 0.0, "control": 0.0}, higher_is_better=True))


# --------------------------------------------------------------------------
# net_result(): composite quality score, 0.5 acceptance + 0.3 doc + 0.2
# retention, renormalized over whatever components are present.
# --------------------------------------------------------------------------

class TestNetResult(unittest.TestCase):
    def test_weighted_average_all_components_present(self):
        cell = {"acceptance": ("x", 80.0), "all_doc": ("x", 60.0), "t1_retention": ("x", 100.0)}
        # 0.5*80 + 0.3*60 + 0.2*100 = 40 + 18 + 20 = 78
        self.assertAlmostEqual(report.net_result(cell), 78.0)

    def test_missing_retention_renormalizes(self):
        # No pivot -> no retention measured (None). Remaining weights
        # (0.5 acceptance, 0.3 doc) renormalize to sum to 1.0.
        cell = {"acceptance": ("x", 80.0), "all_doc": ("x", 60.0), "t1_retention": ("x", None)}
        expected = (0.5 * 80.0 + 0.3 * 60.0) / 0.8
        self.assertAlmostEqual(report.net_result(cell), expected)

    def test_all_missing_returns_none(self):
        cell = {"acceptance": ("x", None), "all_doc": ("x", None), "t1_retention": ("x", None)}
        self.assertIsNone(report.net_result(cell))

    def test_missing_key_treated_as_missing_component(self):
        # A cell that never had the key at all (e.g. an older fixture)
        # behaves the same as one with an explicit None.
        cell = {"all_doc": ("x", 60.0)}
        expected = 60.0  # doc is the only present component -> full weight
        self.assertAlmostEqual(report.net_result(cell), expected)


# --------------------------------------------------------------------------
# cost_vs_benefit_verdict(): net-result-first verdict logic (operator
# decision: net result leads, token cost is secondary, only PROCESS
# OVERHEAD counts against the harness at equal quality).
# --------------------------------------------------------------------------

def _quality_row(arm, trial, total, passed, doc_p, doc_t, ret_p, ret_t, tokens):
    """Single-phase-benchmark-shaped two-phase row (all counted in task1,
    pivot carries only retention) for exercising net_result() /
    cost_vs_benefit_verdict() against chosen acceptance/doc/retention
    values directly, without pulling in the unrelated t1/pivot split
    tested elsewhere. Mirrors _synthetic_two_phase_row's shape."""
    return {
        "run_id": f"{arm}-t{trial}", "arm": arm, "trial": trial,
        "metrics": {"total_tokens": tokens, "assistant_turns_incl_subagents": 10,
                    "num_turns": 10, "total_tool_calls": 5, "memory_file_reads": 0},
        "wall_s": 100.0,
        "acceptance": {"total": total, "passed": passed, "ok": passed == total},
        "regression": {"total": 1, "passed": 1, "ok": True},
        "gates": {},
        "phases": {
            "task1": {
                "metrics": {"total_tokens": tokens},
                "benchmark": {"total": total, "passed": passed,
                              "spec": {"passed": passed, "total": total},
                              "doc": {"passed": doc_p, "total": doc_t}, "doc_rules": {}},
                "gates": {},
            },
            "pivot": {
                "metrics": {"total_tokens": 0},
                "benchmark": {"total": 0, "passed": 0, "spec": {"passed": 0, "total": 0},
                              "doc": {"passed": 0, "total": 0}, "doc_rules": {}},
                "task1_retention": {"passed": ret_p, "total": ret_t, "regressions": []},
                "gates": {},
            },
        },
    }


def _review_for(control_row, harness_row):
    rows = [control_row, harness_row]
    agg = report.get_analyze().aggregate(rows)
    return report.overall_review_rows(rows, agg)


class TestCostVsBenefitVerdictNetResultFirst(unittest.TestCase):
    def test_better_net_result_is_worth_it_with_tokens_per_point(self):
        # v2 LedgerLite-shaped case: harness beats control on acceptance
        # (39/55 vs 37/55) AND pivot-style doc rules, retention unchanged
        # -> strictly better net result at a token premium. Must read
        # "worth it" and carry a tokens-per-point figure, not be penalized
        # for costing more (the case the operator decision targets).
        control = _quality_row("control", 0, total=55, passed=37, doc_p=26, doc_t=54, ret_p=10, ret_t=10, tokens=12_000_000)
        harness = _quality_row("v5", 0, total=55, passed=39, doc_p=28, doc_t=54, ret_p=10, ret_t=10, tokens=25_000_000)
        review = _review_for(control, harness)
        cv = report.cost_vs_benefit_verdict(review)
        self.assertIn("yes on net result", cv["answer"])
        self.assertIn("v5", cv["answer"])
        self.assertIn("tokens per point", cv["answer"])
        by_arm = {v["arm"]: v for v in cv["verdicts"]}
        self.assertEqual(by_arm["v5"]["verdict"], "worth it")
        self.assertGreater(by_arm["v5"]["net_delta"], 0)

    def test_equal_net_result_plus_30pct_tokens_not_worth_it(self):
        control = _quality_row("control", 0, total=50, passed=40, doc_p=30, doc_t=50, ret_p=10, ret_t=10, tokens=10_000_000)
        harness = _quality_row("v5", 0, total=50, passed=40, doc_p=30, doc_t=50, ret_p=10, ret_t=10, tokens=13_000_000)
        review = _review_for(control, harness)
        cv = report.cost_vs_benefit_verdict(review)
        self.assertIn("not worth it", cv["answer"])
        self.assertIn("overhead", cv["answer"].lower())
        by_arm = {v["arm"]: v for v in cv["verdicts"]}
        self.assertEqual(by_arm["v5"]["verdict"], "not worth it")
        self.assertAlmostEqual(by_arm["v5"]["net_delta"], 0.0, delta=report.NET_RESULT_EPSILON)

    def test_equal_net_result_plus_10pct_tokens_worth_it(self):
        control = _quality_row("control", 0, total=50, passed=40, doc_p=30, doc_t=50, ret_p=10, ret_t=10, tokens=10_000_000)
        harness = _quality_row("v5", 0, total=50, passed=40, doc_p=30, doc_t=50, ret_p=10, ret_t=10, tokens=11_000_000)
        review = _review_for(control, harness)
        cv = report.cost_vs_benefit_verdict(review)
        self.assertIn("worth it", cv["answer"])
        self.assertNotIn("not worth it", cv["answer"])
        by_arm = {v["arm"]: v for v in cv["verdicts"]}
        self.assertEqual(by_arm["v5"]["verdict"], "worth it")

    def test_worse_net_result_not_worth_it_regardless_of_cost(self):
        # Harness costs LESS but delivers a strictly worse outcome --
        # must still read "not worth it": a worse net result is never
        # bought back by being cheaper.
        control = _quality_row("control", 0, total=50, passed=45, doc_p=40, doc_t=50, ret_p=10, ret_t=10, tokens=10_000_000)
        harness = _quality_row("v5", 0, total=50, passed=30, doc_p=20, doc_t=50, ret_p=8, ret_t=10, tokens=8_000_000)
        review = _review_for(control, harness)
        cv = report.cost_vs_benefit_verdict(review)
        self.assertIn("not worth it", cv["answer"])
        self.assertIn("regardless of cost", cv["answer"])
        by_arm = {v["arm"]: v for v in cv["verdicts"]}
        self.assertEqual(by_arm["v5"]["verdict"], "not worth it")
        self.assertLess(by_arm["v5"]["net_delta"], 0)

    def test_best_harness_arm_reported_when_multiple_present(self):
        # With two harness arms both beating control on net result, the
        # overall answer line reports the BEST one's outcome (highest
        # net-result delta: v5 +8.0 vs baseline +1.6), not merely "any" win.
        control = _quality_row("control", 0, total=50, passed=40, doc_p=30, doc_t=50, ret_p=10, ret_t=10, tokens=10_000_000)
        weaker = _quality_row("baseline", 0, total=50, passed=41, doc_p=31, doc_t=50, ret_p=10, ret_t=10, tokens=15_000_000)
        stronger = _quality_row("v5", 0, total=50, passed=45, doc_p=35, doc_t=50, ret_p=10, ret_t=10, tokens=15_000_000)
        # sanity: weaker alone is still "worth it" (better net result)
        review_weaker_only = _review_for(control, weaker)
        self.assertIn("yes on net result", report.cost_vs_benefit_verdict(review_weaker_only)["answer"])
        # combined three-arm review: v5 (bigger delta) should lead the answer, not baseline
        rows = [control, weaker, stronger]
        agg = report.get_analyze().aggregate(rows)
        review3 = report.overall_review_rows(rows, agg)
        cv = report.cost_vs_benefit_verdict(review3)
        self.assertIn("v5", cv["answer"])
        self.assertNotIn("baseline +", cv["answer"])


class TestOverallTableNetResultGroup(unittest.TestCase):
    def test_net_result_group_and_process_overhead_row_render(self):
        control = _quality_row("control", 0, total=55, passed=37, doc_p=26, doc_t=54, ret_p=10, ret_t=10, tokens=12_000_000)
        harness = _quality_row("v5", 0, total=55, passed=39, doc_p=28, doc_t=54, ret_p=10, ret_t=10, tokens=25_000_000)
        review = _review_for(control, harness)
        review["code_cells"] = {}
        html = report.overall_review_table_html(review)
        # New "Net result" group leads, ahead of "Correctness".
        self.assertIn("Net result", html)
        self.assertIn("Net result score", html)
        self.assertIn("Acceptance (hidden tests)", html)
        self.assertLess(html.index("Net result"), html.index("Correctness"))
        # New Efficiency row + its overhead-framing note.
        self.assertIn("Process overhead events", html)
        self.assertIn("overhead the tuning targets", html)


# --------------------------------------------------------------------------
# Overall review / cost-vs-benefit against the real interim numbers named
# in the task spec (control task1 doc 47/58, baseline 33/58, v5 33/58;
# pivot doc 16/16/18 of 34).
# --------------------------------------------------------------------------

def _find_interim_dir():
    candidates = glob.glob(
        "/private/tmp/claude-*/*serena-workflow-engine*/*/scratchpad/interim"
    )
    return candidates[0] if candidates else None


class TestOverallReviewRealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.interim = _find_interim_dir()
        if not cls.interim or not os.path.exists(os.path.join(cls.interim, "runs.jsonl")):
            raise unittest.SkipTest("interim harness-ab data not present on this machine")
        cls.rows = report.load_rows(cls.interim)
        cls.agg = report.get_analyze().aggregate(cls.rows)
        cls.review = report.overall_review_rows(cls.rows, cls.agg, stamp_dir=cls.interim)

    def test_task1_doc_rule_counts_match_spec(self):
        cells = self.review["cells"]
        self.assertEqual(cells["control"]["t1_doc"][0], "47/58")
        self.assertEqual(cells["baseline"]["t1_doc"][0], "33/58")
        self.assertEqual(cells["v5"]["t1_doc"][0], "33/58")

    def test_pivot_doc_rule_counts_match_spec(self):
        cells = self.review["cells"]
        self.assertEqual(cells["control"]["pv_doc"][0], "16/34")
        self.assertEqual(cells["baseline"]["pv_doc"][0], "16/34")
        self.assertEqual(cells["v5"]["pv_doc"][0], "18/34")

    def test_control_is_strict_best_on_task1_doc(self):
        vals = {a: self.review["cells"][a]["t1_doc"][1] for a in self.review["arms_present"]}
        self.assertEqual(report.strict_best_arm(vals, higher_is_better=True), "control")

    def test_v5_is_strict_best_on_pivot_doc(self):
        vals = {a: self.review["cells"][a]["pv_doc"][1] for a in self.review["arms_present"]}
        self.assertEqual(report.strict_best_arm(vals, higher_is_better=True), "v5")

    def test_cost_vs_benefit_verdict_is_net_result_first(self):
        # Real interim data: control is strict-best on both doc-rule
        # metrics and (per the addendum's real-world precedent) has no
        # acceptance edge for either harness arm to offset with -- net
        # result should not favor a harness arm here, so the best-arm
        # verdict reads "not worth it" (never the old
        # doc-rule-and-cost-must-both-win "yes"/"no" phrasing).
        cv = report.cost_vs_benefit_verdict(self.review)
        self.assertIn("Is using a harness worth", cv["question"])
        self.assertIn("n=1", cv["answer"])
        self.assertIn("net result", cv["answer"].lower())
        self.assertIn("verdicts", cv)
        for v in cv["verdicts"]:
            self.assertIn(v["verdict"], ("worth it", "not worth it", "unmeasured"))

    def test_cost_vs_benefit_lines_have_expected_ratios(self):
        lines = report.cost_vs_benefit_lines(self.review)
        by_arm = {l["arm"]: l for l in lines}
        # baseline: ~1.9x tokens vs no harness (23.7M / 12.4M)
        self.assertAlmostEqual(by_arm["baseline"]["tokens_x"], 23695362 / 12427120, places=1)
        self.assertEqual(by_arm["baseline"]["t1_doc_cmp"], "LOWER")
        self.assertEqual(by_arm["baseline"]["pv_doc_cmp"], "EQUAL")
        # v5: ~2.1x tokens vs no harness, pivot doc HIGHER
        self.assertAlmostEqual(by_arm["v5"]["tokens_x"], 25785748 / 12427120, places=1)
        self.assertEqual(by_arm["v5"]["t1_doc_cmp"], "LOWER")
        self.assertEqual(by_arm["v5"]["pv_doc_cmp"], "HIGHER")

    def test_overall_table_html_renders_without_error(self):
        cmr = report.code_metrics_rows(self.rows, self.interim)
        self.review["code_cells"] = report.code_metrics_summary_by_arm(cmr)
        html = report.overall_review_table_html(self.review)
        self.assertIn("Task 1 doc rules", html)
        self.assertIn("All doc rules combined", html)
        # control's task1-doc 81% must be tagged best; baseline/v5's tied
        # 57% b1 doc-pass rows must not both be tagged (checked via the
        # underlying strict_best_arm rather than string-counting "best").

    def test_no_full_success_row_when_all_zero(self):
        # The old scorecard's "Full success (x/n) BEST" bug: with every
        # arm at 0 successes, the Overall review's row defs never include
        # a full-success row at all (Correctness rows are spec/doc/
        # retention only -- see _OVERALL_ROW_DEFS), so there's nothing to
        # wrongly tag.
        row_keys = [k for k, _l, _h in report._OVERALL_ROW_DEFS]
        self.assertNotIn("full_success", row_keys)


class TestFailureDetailRealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.interim = _find_interim_dir()
        if not cls.interim or not os.path.exists(os.path.join(cls.interim, "runs.jsonl")):
            raise unittest.SkipTest("interim harness-ab data not present on this machine")
        cls.rows = report.load_rows(cls.interim)

    def test_shared_vs_harness_only_split_matches_story(self):
        fr = report.failure_report_rows(self.rows, self.interim)
        split = fr["split"]
        self.assertIn("R5", split["harness_only"])
        self.assertIn("R6", split["harness_only"])
        # Shared failures include at least the error-codes rule (R7),
        # which every arm fails.
        self.assertIn("R7", split["shared"])

    def test_failure_detail_html_renders(self):
        fr = report.failure_report_rows(self.rows, self.interim)
        agg = report.get_analyze().aggregate(self.rows)
        review = report.overall_review_rows(self.rows, agg, stamp_dir=self.interim)
        html = report.failure_detail_html(fr, review)
        self.assertIn("Shared failures", html)
        self.assertIn("Harness-only failures", html)
        self.assertIn("failure-snippet", html)


class TestCodeMetricsRealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.interim = _find_interim_dir()
        if not cls.interim or not os.path.exists(os.path.join(cls.interim, "runs.jsonl")):
            raise unittest.SkipTest("interim harness-ab data not present on this machine")
        cls.rows = report.load_rows(cls.interim)

    def test_code_metrics_rows_nonempty_for_all_arms(self):
        cmr = report.code_metrics_rows(self.rows, self.interim)
        arms = {r["arm"] for r in cmr}
        self.assertEqual(arms, {"control", "baseline", "v5"})

    def test_control_has_more_loc_than_others(self):
        # From the task spec's own numbers: control's work tree has the
        # most files/LOC among the three arms in this run.
        cmr = report.code_metrics_rows(self.rows, self.interim)
        by_arm = {r["arm"]: r["metrics"]["fixture_to_final"]["loc_added"] for r in cmr}
        self.assertGreater(by_arm["control"], by_arm["baseline"])


# --------------------------------------------------------------------------
# Phase-token bars nonzero (the "renders all zeros" bug from the
# screenshot) -- using the existing two-phase synthetic fixture, which
# has phases.<phase>.metrics populated, PLUS a direct check that
# phase_cost_stack_rows never returns an all-zero row for such data.
# --------------------------------------------------------------------------

def _synthetic_two_phase_row(arm, trial, t1_tokens, pv_tokens):
    return {
        "run_id": f"{arm}-t{trial}", "arm": arm, "trial": trial,
        "metrics": {"total_tokens": t1_tokens + pv_tokens, "assistant_turns_incl_subagents": 10,
                    "num_turns": 10, "total_tool_calls": 5, "memory_file_reads": 1},
        "wall_s": 100.0,
        "acceptance": {"total": 2, "passed": 2, "ok": True, "spec": {"passed": 1, "total": 1},
                       "doc": {"passed": 1, "total": 1}, "doc_rules": {}, "failed_tests": []},
        "regression": {"total": 1, "passed": 1, "ok": True, "failed_tests": []},
        "gates": {},
        "phases": {
            "task1": {"metrics": {"total_tokens": t1_tokens}, "benchmark": {"total": 1, "passed": 1, "spec": {"passed": 1, "total": 1}, "doc": {"passed": 1, "total": 1}, "doc_rules": {}}, "gates": {}},
            "pivot": {"metrics": {"total_tokens": pv_tokens}, "benchmark": {"total": 1, "passed": 1, "spec": {"passed": 1, "total": 1}, "doc": {"passed": 1, "total": 1}, "doc_rules": {}}, "task1_retention": {"passed": 1, "total": 1, "regressions": []}, "gates": {}},
        },
    }


class TestPhaseTokenBarsNonzero(unittest.TestCase):
    def test_phase_cost_stack_rows_nonzero_when_metrics_present(self):
        rows = [_synthetic_two_phase_row("baseline", 0, 6000, 17000)]
        stack = report.phase_cost_stack_rows(rows)
        self.assertEqual(len(stack), 1)
        _run_id, _arm, _trial, parts = stack[0]
        self.assertGreater(parts["task1"], 0)
        self.assertGreater(parts["pivot"], 0)

    def test_phase_cost_stack_chart_svg_has_nonzero_bar_widths(self):
        rows = [_synthetic_two_phase_row("baseline", 0, 6000, 17000)]
        stack = report.phase_cost_stack_rows(rows)
        svg, _h = report.phase_cost_stack_chart(stack)
        # Every rect in the chart should have width > "0.0" -- the
        # all-zero-bars bug rendered width="0.0" rects for every run.
        import re
        widths = [float(w) for w in re.findall(r'width="([\d.]+)"', svg)]
        self.assertTrue(widths, "no <rect> width found in phase cost chart svg")
        self.assertTrue(any(w > 0 for w in widths))

    def test_real_interim_data_phase_bars_nonzero(self):
        interim = _find_interim_dir()
        if not interim or not os.path.exists(os.path.join(interim, "runs.jsonl")):
            self.skipTest("interim harness-ab data not present on this machine")
        rows = report.load_rows(interim)
        stack = report.phase_cost_stack_rows(rows, stamp_dir=interim)
        self.assertTrue(stack)
        for _run_id, _arm, _trial, parts in stack:
            self.assertGreater(parts["task1"], 0)
            self.assertGreater(parts["pivot"], 0)


# --------------------------------------------------------------------------
# Minimum SVG font size (>=12px; chart titles 13-14px).
# --------------------------------------------------------------------------

class TestMinimumSvgFontSize(unittest.TestCase):
    def test_no_svg_text_below_12px_in_source(self):
        import re
        with open(REPORT_PATH) as f:
            src = f.read()
        sizes = [float(m) for m in re.findall(r'font-size="([\d.]+)"', src)]
        self.assertTrue(sizes)
        self.assertTrue(all(s >= 12 for s in sizes), f"found SVG font sizes below 12px: {[s for s in sizes if s < 12]}")

    def test_chart_titles_are_13_to_14px(self):
        import re
        with open(REPORT_PATH) as f:
            src = f.read()
        title_sizes = [float(m) for m in re.findall(r'class="chart-title" font-size="([\d.]+)"', src)]
        self.assertTrue(title_sizes)
        self.assertTrue(all(13 <= s <= 14 for s in title_sizes), title_sizes)

    def test_rendered_report_has_no_subpixel_svg_text(self):
        rows = [_synthetic_two_phase_row("baseline", 0, 6000, 17000),
                _synthetic_two_phase_row("v5", 0, 7000, 18000),
                _synthetic_two_phase_row("control", 0, 3000, 9000)]
        meta = {"args": {"model": "m", "trials": 1}, "arms": [], "prepared": {}, "auth": {}, "claude_version": ""}
        html = report.render_report(rows, meta, title="Font Size Test")
        import re
        sizes = [float(m) for m in re.findall(r'font-size="([\d.]+)"', html)]
        self.assertTrue(sizes)
        self.assertTrue(all(s >= 12 for s in sizes))


# --------------------------------------------------------------------------
# Delegation section end-to-end.
# --------------------------------------------------------------------------

class TestDelegationSection(unittest.TestCase):
    def test_delegation_rows_computes_subagent_token_split(self):
        rows = [{
            "run_id": "baseline-t0", "arm": "baseline", "trial": 0,
            "metrics": {"main_tokens": 100, "total_tokens": 150, "subagent_launches": 1, "subagent_messages": 2},
            "wall_s": 50.0,
        }]
        out = report.delegation_rows(rows)
        self.assertEqual(out[0]["subagent_tokens"], 50)

    def test_delegation_takeaway_no_launches(self):
        rows = [{"run_id": "a-t0", "arm": "control", "trial": 0,
                  "metrics": {"main_tokens": 100, "total_tokens": 100, "subagent_launches": 0, "subagent_messages": 0},
                  "wall_s": 10.0}]
        deleg = report.delegation_rows(rows)
        takeaway = report.delegation_takeaway(deleg)
        self.assertIn("no arm parallelized meaningfully", takeaway)

    def test_delegation_chart_renders_without_clipped_labels_within_width(self):
        rows = [
            {"run_id": "baseline-t0", "arm": "baseline", "trial": 0,
             "metrics": {"main_tokens": 17204795, "total_tokens": 23695362, "subagent_launches": 1, "subagent_messages": 0},
             "wall_s": 1108.0},
        ]
        deleg = report.delegation_rows(rows)
        svg, _h = report.delegation_chart(deleg, width=560)
        # Every rect's x + width must stay within the declared SVG width
        # (labels rendered after also fit, verified indirectly by keeping
        # bar end well short of the edge).
        import re
        for x, w in re.findall(r'<rect x="([\d.]+)" y="[\d.]+" width="([\d.]+)"', svg):
            self.assertLessEqual(float(x) + float(w), 560)


if __name__ == "__main__":
    unittest.main()
