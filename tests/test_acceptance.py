"""Tests for experiments/harness-ab/acceptance.py pure functions."""
import importlib.util
import json
import os
import sys
import tempfile
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


acceptance = _load("harness_ab_acceptance", os.path.join(HARNESS_DIR, "acceptance.py"))

# Real-shaped output (Python 3.11+ interpreter this harness runs under, plus
# the older-format line for backward compat) captured from a live unittest -v
# run (see gate_conformance test module docstring for provenance approach).
VERBOSE_OUTPUT_311 = """test_error (test_x.T.test_error) ... ERROR
test_fail (test_x.T.test_fail) ... FAIL
test_pass (test_x.T.test_pass) ... ok
test_skip (test_x.T.test_skip) ... skipped 'x'

======================================================================
ERROR: test_error (test_x.T.test_error)
----------------------------------------------------------------------
Traceback (most recent call last):
ValueError

======================================================================
FAIL: test_fail (test_x.T.test_fail)
----------------------------------------------------------------------
AssertionError: False is not true

----------------------------------------------------------------------
Ran 4 tests in 0.001s

FAILED (failures=1, errors=1, skipped=1)
"""

VERBOSE_OUTPUT_OLD = """test_pass (tests.test_spec_foo.FooTest) ... ok
test_fail (tests.test_doc_bar.BarTest) ... FAIL
"""


class ParseVerboseUnittestOutputTest(unittest.TestCase):
    def test_parses_311_format(self):
        results = acceptance.parse_verbose_unittest_output(VERBOSE_OUTPUT_311)
        self.assertEqual(len(results), 4)
        statuses = {r["method"]: r["status"] for r in results}
        self.assertEqual(statuses["test_error"], "error")
        self.assertEqual(statuses["test_fail"], "fail")
        self.assertEqual(statuses["test_pass"], "ok")
        self.assertEqual(statuses["test_skip"], "skipped")

    def test_test_id_reconstruction_matches_summary_shape(self):
        results = acceptance.parse_verbose_unittest_output(VERBOSE_OUTPUT_311)
        pass_result = next(r for r in results if r["method"] == "test_pass")
        self.assertEqual(pass_result["test_id"], "test_pass (test_x.T.test_pass)")

    def test_parses_older_format(self):
        results = acceptance.parse_verbose_unittest_output(VERBOSE_OUTPUT_OLD)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["path"], "tests.test_spec_foo.FooTest")
        self.assertEqual(results[0]["status"], "ok")
        self.assertEqual(results[1]["status"], "fail")

    def test_expected_failure_counts_as_ok(self):
        text = "test_x (m.C) ... expected failure\n"
        results = acceptance.parse_verbose_unittest_output(text)
        self.assertEqual(results[0]["status"], "ok")

    def test_unexpected_success_counts_as_fail(self):
        text = "test_x (m.C) ... unexpected success\n"
        results = acceptance.parse_verbose_unittest_output(text)
        self.assertEqual(results[0]["status"], "fail")

    def test_empty_text(self):
        self.assertEqual(acceptance.parse_verbose_unittest_output(""), [])
        self.assertEqual(acceptance.parse_verbose_unittest_output(None), [])

    def test_no_matching_lines(self):
        self.assertEqual(acceptance.parse_verbose_unittest_output("garbage\nmore garbage\n"), [])


class ClassifyTestCategoryTest(unittest.TestCase):
    def test_spec_prefix(self):
        self.assertEqual(acceptance.classify_test_category("test_x (pkg.test_spec_foo.Cls)"), "spec")

    def test_doc_prefix(self):
        self.assertEqual(acceptance.classify_test_category("test_x (pkg.test_doc_bar.Cls)"), "doc")

    def test_other_prefix_v1_acceptance(self):
        self.assertEqual(acceptance.classify_test_category("test_x (pkg.test_acceptance_budget.Cls)"), "other")

    def test_bare_filename(self):
        self.assertEqual(acceptance.classify_test_category("test_spec_foo.py"), "spec")
        self.assertEqual(acceptance.classify_test_category("test_doc_bar"), "doc")

    def test_empty_returns_other(self):
        self.assertEqual(acceptance.classify_test_category(""), "other")
        self.assertEqual(acceptance.classify_test_category(None), "other")

    def test_nested_package_path(self):
        self.assertEqual(
            acceptance.classify_test_category("test_x (hidden_tests.test_spec_budget.T.test_x)"),
            "spec",
        )


class CategorizeResultsTest(unittest.TestCase):
    def test_mixed_categories(self):
        results = [
            {"path": "pkg.test_spec_a", "status": "ok"},
            {"path": "pkg.test_spec_b", "status": "fail"},
            {"path": "pkg.test_doc_c", "status": "ok"},
            {"path": "pkg.test_acceptance_d", "status": "ok"},
        ]
        cat = acceptance.categorize_results(results)
        self.assertEqual(cat["spec"], {"passed": 1, "total": 2})
        self.assertEqual(cat["doc"], {"passed": 1, "total": 1})
        self.assertEqual(cat["other"], {"passed": 1, "total": 1})

    def test_empty(self):
        cat = acceptance.categorize_results([])
        self.assertEqual(cat["spec"], {"passed": 0, "total": 0})
        self.assertEqual(cat["doc"], {"passed": 0, "total": 0})
        self.assertEqual(cat["other"], {"passed": 0, "total": 0})


class LoadDocRulesTest(unittest.TestCase):
    def test_missing_file_returns_empty(self):
        self.assertEqual(acceptance.load_doc_rules("/nonexistent/doc_rules.json"), [])

    def test_none_path_returns_empty(self):
        self.assertEqual(acceptance.load_doc_rules(None), [])

    def test_valid_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "doc_rules.json")
            data = [{"id": "R1", "memory": "dom/DOM_X", "summary": "s", "tests": ["test_a"]}]
            with open(path, "w") as f:
                json.dump(data, f)
            rules = acceptance.load_doc_rules(path)
            self.assertEqual(len(rules), 1)
            self.assertEqual(rules[0]["id"], "R1")

    def test_malformed_json_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "doc_rules.json")
            with open(path, "w") as f:
                f.write("{not valid json")
            self.assertEqual(acceptance.load_doc_rules(path), [])

    def test_non_list_json_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "doc_rules.json")
            with open(path, "w") as f:
                json.dump({"not": "a list"}, f)
            self.assertEqual(acceptance.load_doc_rules(path), [])

    def test_entries_without_id_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "doc_rules.json")
            data = [{"memory": "x"}, {"id": "R1", "memory": "y"}]
            with open(path, "w") as f:
                json.dump(data, f)
            rules = acceptance.load_doc_rules(path)
            self.assertEqual(len(rules), 1)
            self.assertEqual(rules[0]["id"], "R1")


class DocRulePassMatrixTest(unittest.TestCase):
    DOC_RULES = [
        {"id": "R1", "memory": "dom/DOM_LEDGER_RULES", "tests": ["test_monthly_short_month"]},
        {"id": "R2", "memory": "ref/REF_CLI_OUTPUT", "tests": ["test_cli_budget_report_format"]},
    ]

    def test_all_pass(self):
        results = [
            {"test_id": "test_monthly_short_month (m.T)", "method": "test_monthly_short_month", "status": "ok"},
            {"test_id": "test_cli_budget_report_format (m.T)", "method": "test_cli_budget_report_format", "status": "ok"},
        ]
        matrix = acceptance.doc_rule_pass_matrix(results, self.DOC_RULES)
        self.assertEqual(matrix["R1"], {"passed": 1, "total": 1, "memory": "dom/DOM_LEDGER_RULES", "summary": None, "ok": True})
        self.assertTrue(matrix["R2"]["ok"])

    def test_partial_fail(self):
        results = [
            {"test_id": "test_monthly_short_month (m.T)", "method": "test_monthly_short_month", "status": "fail"},
        ]
        matrix = acceptance.doc_rule_pass_matrix(results, self.DOC_RULES)
        self.assertFalse(matrix["R1"]["ok"])
        self.assertEqual(matrix["R1"]["passed"], 0)
        self.assertEqual(matrix["R1"]["total"], 1)

    def test_no_matching_tests_ok_is_none(self):
        matrix = acceptance.doc_rule_pass_matrix([], self.DOC_RULES)
        self.assertIsNone(matrix["R1"]["ok"])
        self.assertEqual(matrix["R1"]["total"], 0)

    def test_substring_match_on_full_test_id(self):
        rules = [{"id": "R1", "memory": "x", "tests": ["hidden_tests.test_spec_budget.T"]}]
        results = [{
            "test_id": "test_budget_report (hidden_tests.test_spec_budget.T.test_budget_report)",
            "method": "test_budget_report", "status": "ok",
        }]
        matrix = acceptance.doc_rule_pass_matrix(results, rules)
        self.assertEqual(matrix["R1"]["total"], 1)
        self.assertTrue(matrix["R1"]["ok"])

    def test_empty_doc_rules(self):
        self.assertEqual(acceptance.doc_rule_pass_matrix([{"method": "x", "status": "ok"}], []), {})

    # -- new object-shaped `tests` schema: {"id": ..., "asserts": ...} -----
    # (tasks/v2/doc_rules.json and pivot's doc_rules.json, rule ids P1...,
    # both now list tests this way; older files keep the plain-string form
    # exercised by the tests above.)

    def test_object_shaped_tests_all_pass(self):
        rules = [{
            "id": "R1", "memory": "dom/DOM_X", "summary": "s",
            "tests": [{"id": "test_monthly_short_month", "asserts": "..."}],
        }]
        results = [
            {"test_id": "test_monthly_short_month (m.T)", "method": "test_monthly_short_month", "status": "ok"},
        ]
        matrix = acceptance.doc_rule_pass_matrix(results, rules)
        self.assertEqual(matrix["R1"], {"passed": 1, "total": 1, "memory": "dom/DOM_X", "summary": "s", "ok": True})

    def test_object_shaped_tests_fail(self):
        rules = [{
            "id": "R1", "memory": "dom/DOM_X",
            "tests": [{"id": "test_monthly_short_month", "asserts": "..."}],
        }]
        results = [
            {"test_id": "test_monthly_short_month (m.T)", "method": "test_monthly_short_month", "status": "fail"},
        ]
        matrix = acceptance.doc_rule_pass_matrix(results, rules)
        self.assertFalse(matrix["R1"]["ok"])
        self.assertEqual(matrix["R1"]["passed"], 0)
        self.assertEqual(matrix["R1"]["total"], 1)

    def test_object_shaped_tests_match_by_full_test_id_substring(self):
        rules = [{"id": "P1", "memory": "x", "tests": [
            {"id": "hidden_tests.test_pivot_spec_budget.T", "asserts": "..."},
        ]}]
        results = [{
            "test_id": "test_x (hidden_tests.test_pivot_spec_budget.T.test_x)",
            "method": "test_x", "status": "ok",
        }]
        matrix = acceptance.doc_rule_pass_matrix(results, rules)
        self.assertEqual(matrix["P1"]["total"], 1)
        self.assertTrue(matrix["P1"]["ok"])

    def test_mixed_string_and_object_shaped_tests_in_same_rule(self):
        # Belt-and-suspenders: a rule mixing both shapes (shouldn't occur in
        # practice within one doc_rules.json, but the matcher must not
        # choke on it either way).
        rules = [{"id": "R1", "memory": "x", "tests": [
            "test_a", {"id": "test_b", "asserts": "..."},
        ]}]
        results = [
            {"test_id": "test_a (m.T)", "method": "test_a", "status": "ok"},
            {"test_id": "test_b (m.T)", "method": "test_b", "status": "ok"},
        ]
        matrix = acceptance.doc_rule_pass_matrix(results, rules)
        self.assertEqual(matrix["R1"], {"passed": 2, "total": 2, "memory": "x", "summary": None, "ok": True})

    def test_object_shaped_tests_no_id_key_does_not_match(self):
        rules = [{"id": "R1", "memory": "x", "tests": [{"asserts": "no id here"}]}]
        results = [{"test_id": "test_a (m.T)", "method": "test_a", "status": "ok"}]
        matrix = acceptance.doc_rule_pass_matrix(results, rules)
        self.assertIsNone(matrix["R1"]["ok"])
        self.assertEqual(matrix["R1"]["total"], 0)


class RuleTestIdTest(unittest.TestCase):
    """_rule_test_id: normalizes a 'tests' entry (either schema) to its bare
    id string, used directly by _test_id_matches."""

    def test_string_entry_returned_as_is(self):
        self.assertEqual(acceptance._rule_test_id("test_foo"), "test_foo")

    def test_object_entry_returns_id_field(self):
        self.assertEqual(acceptance._rule_test_id({"id": "test_foo", "asserts": "..."}), "test_foo")

    def test_object_entry_without_id_returns_none(self):
        self.assertIsNone(acceptance._rule_test_id({"asserts": "..."}))

    def test_none_entry_returns_none(self):
        self.assertIsNone(acceptance._rule_test_id(None))


if __name__ == "__main__":
    unittest.main()
