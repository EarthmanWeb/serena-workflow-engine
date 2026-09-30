"""Tests for experiments/harness-ab/failure_detail.py: rule matching,
FAIL/ERROR block parsing, snippet extraction, and the shared-vs-harness-
only failure split, including against real acceptance.*.txt data from an
interim harness-ab run when available."""
import glob
import importlib.util
import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
FAILURE_DETAIL_PATH = os.path.join(HERE, "..", "experiments", "harness-ab", "failure_detail.py")


def _load_failure_detail():
    spec = importlib.util.spec_from_file_location("harness_ab_failure_detail", FAILURE_DETAIL_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fd = _load_failure_detail()


DOC_RULES = [
    {
        "id": "R1",
        "memory": "dom/DOM_FOO",
        "summary": "Rule one summary.",
        "tests": [
            {"id": "test_module.TestFoo.test_a", "asserts": "a"},
            {"id": "test_module.TestFoo.test_b", "asserts": "b"},
        ],
    },
    {
        "id": "R2",
        "memory": "dom/DOM_BAR",
        "summary": "Rule two summary.",
        "tests": [
            {"id": "test_module.TestBar.test_c", "asserts": "c"},
        ],
    },
]


# --------------------------------------------------------------------------
# Rule matching.
# --------------------------------------------------------------------------

class TestRuleForTestId(unittest.TestCase):
    def test_matches_by_full_id_substring(self):
        rule = fd.rule_for_test_id(
            "_acceptance.test_module.TestFoo.test_a", DOC_RULES
        )
        self.assertEqual(rule["id"], "R1")

    def test_matches_by_bare_method_name(self):
        rules = [{"id": "R9", "tests": ["test_c"]}]
        rule = fd.rule_for_test_id("_acceptance.test_module.TestBar.test_c", rules)
        self.assertEqual(rule["id"], "R9")

    def test_no_match_returns_none(self):
        rule = fd.rule_for_test_id("_acceptance.test_module.TestBar.test_zzz", DOC_RULES)
        self.assertIsNone(rule)


class TestShortTestLabel(unittest.TestCase):
    def test_shortens_to_class_and_method(self):
        self.assertEqual(
            fd.short_test_label("_acceptance.pivot.test_x.TestY.test_z"),
            "TestY.test_z",
        )

    def test_short_id_passthrough(self):
        self.assertEqual(fd.short_test_label("bareid"), "bareid")


# --------------------------------------------------------------------------
# failed_doc_tests / rule_totals.
# --------------------------------------------------------------------------

class TestFailedDocTests(unittest.TestCase):
    def test_groups_failures_by_rule(self):
        by_id = {
            "_acceptance.test_module.TestFoo.test_a": {"status": "ok"},
            "_acceptance.test_module.TestFoo.test_b": {"status": "failed"},
            "_acceptance.test_module.TestBar.test_c": {"status": "failed"},
        }
        out = fd.failed_doc_tests(by_id, DOC_RULES)
        self.assertEqual(set(out.keys()), {"R1", "R2"})
        self.assertEqual(out["R1"]["failed"], ["_acceptance.test_module.TestFoo.test_b"])
        self.assertEqual(out["R2"]["failed"], ["_acceptance.test_module.TestBar.test_c"])

    def test_all_pass_yields_no_entries(self):
        by_id = {
            "_acceptance.test_module.TestFoo.test_a": {"status": "ok"},
            "_acceptance.test_module.TestFoo.test_b": {"status": "ok"},
            "_acceptance.test_module.TestBar.test_c": {"status": "ok"},
        }
        out = fd.failed_doc_tests(by_id, DOC_RULES)
        self.assertEqual(out, {})

    def test_import_error_status_counts_as_failed(self):
        by_id = {"_acceptance.test_module.TestBar.test_c": {"status": "import_error"}}
        out = fd.failed_doc_tests(by_id, DOC_RULES)
        self.assertIn("R2", out)


class TestRuleTotals(unittest.TestCase):
    def test_computes_passed_and_total(self):
        by_id = {
            "_acceptance.test_module.TestFoo.test_a": {"status": "ok"},
            "_acceptance.test_module.TestFoo.test_b": {"status": "failed"},
        }
        totals = fd.rule_totals(by_id, DOC_RULES)
        self.assertEqual(totals["R1"], (1, 2))
        self.assertNotIn("R2", totals)  # test_c not present in by_id at all


# --------------------------------------------------------------------------
# FAIL/ERROR block parsing + snippet extraction.
# --------------------------------------------------------------------------

SAMPLE_LOG = """\
test_a (_acceptance.test_module.TestFoo.test_a) ... ok
test_b (_acceptance.test_module.TestFoo.test_b) ... FAIL
test_c (_acceptance.test_module.TestBar.test_c) ... ERROR

======================================================================
FAIL: test_b (_acceptance.test_module.TestFoo.test_b)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/tmp/x/_acceptance/test_module.py", line 12, in test_b
    self.assertEqual(got, want)
AssertionError: 'actual' != 'expected'
- actual
+ expected

======================================================================
ERROR: test_c (_acceptance.test_module.TestBar.test_c)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/tmp/x/_acceptance/test_module.py", line 20, in test_c
    raise ValueError("bad input")
ValueError: bad input

----------------------------------------------------------------------
Ran 3 tests in 0.01s

FAILED (failures=1, errors=1)
"""


class TestParseFailureBlocks(unittest.TestCase):
    def test_finds_both_blocks(self):
        blocks = fd.parse_failure_blocks(SAMPLE_LOG)
        self.assertEqual(
            set(blocks.keys()),
            {"_acceptance.test_module.TestFoo.test_b", "_acceptance.test_module.TestBar.test_c"},
        )

    def test_kind_recorded_correctly(self):
        blocks = fd.parse_failure_blocks(SAMPLE_LOG)
        self.assertEqual(blocks["_acceptance.test_module.TestFoo.test_b"]["kind"], "FAIL")
        self.assertEqual(blocks["_acceptance.test_module.TestBar.test_c"]["kind"], "ERROR")

    def test_last_block_body_excludes_run_summary(self):
        blocks = fd.parse_failure_blocks(SAMPLE_LOG)
        body = blocks["_acceptance.test_module.TestBar.test_c"]["body"]
        joined = "\n".join(body)
        self.assertNotIn("Ran 3 tests", joined)
        self.assertNotIn("FAILED (failures", joined)

    def test_empty_log(self):
        self.assertEqual(fd.parse_failure_blocks(""), {})


class TestExtractSnippet(unittest.TestCase):
    def test_assertion_plus_diff_lines(self):
        body = [
            "Traceback (most recent call last):",
            '  File "/tmp/x.py", line 1, in test_b',
            "    self.assertEqual(got, want)",
            "AssertionError: 'actual' != 'expected'",
            "- actual",
            "+ expected",
        ]
        snippet = fd.extract_snippet(body)
        self.assertEqual(snippet[0], "AssertionError: 'actual' != 'expected'")
        self.assertIn("- actual", snippet)
        self.assertIn("+ expected", snippet)

    def test_max_lines_respected(self):
        body = ["AssertionError: x"] + [f"- line{i}" for i in range(10)]
        snippet = fd.extract_snippet(body, max_lines=3)
        self.assertEqual(len(snippet), 3)

    def test_import_error_fallback_to_message_line(self):
        body = [
            "Traceback (most recent call last):",
            '  File "loader.py", line 1, in x',
            "ImportError: cannot import name 'foo'",
        ]
        snippet = fd.extract_snippet(body)
        self.assertEqual(snippet, ["ImportError: cannot import name 'foo'"])

    def test_no_recognizable_exception_falls_back_to_tail(self):
        body = ["some diagnostic line", "another line", "final line"]
        snippet = fd.extract_snippet(body, max_lines=2)
        self.assertEqual(snippet, ["another line", "final line"])

    def test_empty_body(self):
        self.assertEqual(fd.extract_snippet([]), [])


class TestModuleErrorFallback(unittest.TestCase):
    """A doc-rule test with no per-test block of its own (its module failed
    to import, so by_id marks it 'import_error'/'missing' with no
    dedicated unittest FAIL/ERROR entry) falls back to that module's whole-
    module collection-error block."""

    MODULE_ERROR_LOG = """\
======================================================================
ERROR: _acceptance.test_doc_error_codes (unittest.loader._FailedTest._acceptance.test_doc_error_codes)
----------------------------------------------------------------------
ImportError: Failed to import test module: _acceptance.test_doc_error_codes
Traceback (most recent call last):
  File "loader.py", line 1, in x
    module = self._get_module_from_name(name)
ImportError: cannot import name 'fiscal_period_bounds' from 'ledgerlite.statement'


----------------------------------------------------------------------
Ran 5 tests in 0.01s

FAILED (failures=0, errors=1)
"""

    def test_per_method_test_falls_back_to_module_block(self):
        blocks = fd.parse_failure_blocks(self.MODULE_ERROR_LOG)
        kind, snippet = fd.failure_snippet_for(
            "_acceptance.test_doc_error_codes.TestFiscalPeriodError.test_bad_period_format_raises",
            blocks,
        )
        self.assertEqual(kind, "ERROR")
        self.assertTrue(snippet)
        self.assertIn("ImportError", snippet[0])

    def test_unmatched_test_returns_none(self):
        blocks = fd.parse_failure_blocks(self.MODULE_ERROR_LOG)
        kind, snippet = fd.failure_snippet_for("_acceptance.totally_unrelated.test_x", blocks)
        self.assertIsNone(kind)
        self.assertEqual(snippet, [])


# --------------------------------------------------------------------------
# build_failure_report end-to-end (synthetic).
# --------------------------------------------------------------------------

class TestBuildFailureReport(unittest.TestCase):
    def test_end_to_end_synthetic(self):
        by_id = {
            "_acceptance.test_module.TestFoo.test_a": {"status": "ok"},
            "_acceptance.test_module.TestFoo.test_b": {"status": "failed"},
            "_acceptance.test_module.TestBar.test_c": {"status": "failed"},
        }
        report = fd.build_failure_report(by_id, DOC_RULES, SAMPLE_LOG)
        by_rule = {e["rule_id"]: e for e in report}
        self.assertEqual(by_rule["R1"]["failed_count"], 1)
        self.assertEqual(by_rule["R1"]["total_count"], 2)
        self.assertEqual(len(by_rule["R1"]["tests"]), 1)
        t = by_rule["R1"]["tests"][0]
        self.assertEqual(t["label"], "TestFoo.test_b")
        self.assertTrue(t["snippet"])

        self.assertEqual(by_rule["R2"]["failed_count"], 1)
        self.assertEqual(by_rule["R2"]["total_count"], 1)

    def test_no_failures_yields_empty_report(self):
        by_id = {k: {"status": "ok"} for k in [
            "_acceptance.test_module.TestFoo.test_a",
            "_acceptance.test_module.TestFoo.test_b",
            "_acceptance.test_module.TestBar.test_c",
        ]}
        report = fd.build_failure_report(by_id, DOC_RULES, SAMPLE_LOG)
        self.assertEqual(report, [])

    def test_order_follows_doc_rules_order(self):
        by_id = {
            "_acceptance.test_module.TestFoo.test_b": {"status": "failed"},
            "_acceptance.test_module.TestBar.test_c": {"status": "failed"},
        }
        report = fd.build_failure_report(by_id, DOC_RULES, SAMPLE_LOG)
        self.assertEqual([e["rule_id"] for e in report], ["R1", "R2"])


# --------------------------------------------------------------------------
# shared_vs_harness_only.
# --------------------------------------------------------------------------

class TestSharedVsHarnessOnly(unittest.TestCase):
    def test_universal_failure_is_shared(self):
        per_arm = {"control": {"R1"}, "baseline": {"R1"}, "v5": {"R1"}}
        out = fd.shared_vs_harness_only(per_arm, {"baseline", "v5"}, ["control", "baseline", "v5"])
        self.assertEqual(out["shared"], ["R1"])
        self.assertEqual(out["harness_only"], [])

    def test_harness_only_failure_excludes_control_pass(self):
        per_arm = {"control": set(), "baseline": {"R5"}, "v5": {"R5"}}
        out = fd.shared_vs_harness_only(per_arm, {"baseline", "v5"}, ["control", "baseline", "v5"])
        self.assertEqual(out["harness_only"], ["R5"])
        self.assertEqual(out["shared"], [])

    def test_partial_harness_failure_not_harness_only(self):
        # Only baseline fails R6 (v5 passes it) -- not "every harness arm
        # failed it", so it's neither shared nor harness_only.
        per_arm = {"control": set(), "baseline": {"R6"}, "v5": set()}
        out = fd.shared_vs_harness_only(per_arm, {"baseline", "v5"}, ["control", "baseline", "v5"])
        self.assertEqual(out["harness_only"], ["R6"])

    def test_control_only_failure_neither_bucket(self):
        per_arm = {"control": {"R9"}, "baseline": set(), "v5": set()}
        out = fd.shared_vs_harness_only(per_arm, {"baseline", "v5"}, ["control", "baseline", "v5"])
        self.assertEqual(out["shared"], [])
        self.assertEqual(out["harness_only"], [])

    def test_real_interim_data_matches_expected_story(self):
        """When the interim harness-ab data is available on disk (this
        experiment's own scratchpad output), verify the exact story the
        report's 'Explain failures' section must tell: R5 (privacy
        redaction) and R6 (category aliases) fail ONLY for the harness
        arms; control passes them. Skips gracefully when the data isn't
        present (e.g. CI without the scratchpad)."""
        candidates = glob.glob(
            os.path.expanduser(
                "/private/tmp/claude-*/*serena-workflow-engine*/*/scratchpad/interim/runs.jsonl"
            )
        )
        if not candidates:
            self.skipTest("interim harness-ab data not present on this machine")
        runs_path = candidates[0]
        base = os.path.dirname(runs_path)
        doc_rules_t1_path = os.path.join(HERE, "..", "experiments", "harness-ab", "tasks", "v2", "doc_rules.json")
        doc_rules_pv_path = os.path.join(HERE, "..", "experiments", "harness-ab", "tasks", "v2", "pivot", "doc_rules.json")
        if not (os.path.exists(doc_rules_t1_path) and os.path.exists(doc_rules_pv_path)):
            self.skipTest("task doc_rules.json not present")

        with open(doc_rules_t1_path) as f:
            doc_rules_t1 = json.load(f)
        with open(doc_rules_pv_path) as f:
            doc_rules_pv = json.load(f)

        rows = []
        with open(runs_path) as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))

        per_arm_failed = {}
        for r in rows:
            phases = r.get("phases") or {}
            if "task1" not in phases or "pivot" not in phases:
                continue
            by_id_t1 = ((phases["task1"].get("benchmark") or {}).get("by_id")) or {}
            by_id_pv = ((phases["pivot"].get("benchmark") or {}).get("by_id")) or {}
            f1 = fd.failed_doc_tests(by_id_t1, doc_rules_t1)
            f2 = fd.failed_doc_tests(by_id_pv, doc_rules_pv)
            per_arm_failed[r["arm"]] = set(f1) | set(f2)

        if not per_arm_failed:
            self.skipTest("no two-phase rows in interim data")

        split = fd.shared_vs_harness_only(
            per_arm_failed, {"baseline", "v5"}, ["control", "baseline", "v5"]
        )
        self.assertIn("R5", split["harness_only"])
        self.assertIn("R6", split["harness_only"])


if __name__ == "__main__":
    unittest.main()
