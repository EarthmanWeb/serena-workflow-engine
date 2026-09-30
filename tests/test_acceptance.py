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

    def test_pivot_spec_prefix(self):
        self.assertEqual(
            acceptance.classify_test_category("test_x (_acceptance.pivot.test_pivot_spec_cli.T.test_x)"),
            "spec",
        )

    def test_pivot_doc_prefix(self):
        self.assertEqual(
            acceptance.classify_test_category("test_x (_acceptance.pivot.test_pivot_doc_audit.T.test_x)"),
            "doc",
        )

    def test_pivot_doc_bare_filename(self):
        self.assertEqual(acceptance.classify_test_category("test_pivot_doc_audit.py"), "doc")
        self.assertEqual(acceptance.classify_test_category("test_pivot_spec_cli"), "spec")


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


class ScanExpectedTestIdsTest(unittest.TestCase):
    """scan_expected_test_ids: AST-scans hidden_tests/*.py for TestCase
    subclasses + test_* methods, independent of whether the module actually
    imports cleanly when unittest tries to run it (see module docstring's
    root-cause note: an import-failed module still HAS a real, known set of
    expected test ids -- this function's whole point is computing that set
    without ever importing the file)."""

    def test_missing_dir_returns_empty(self):
        self.assertEqual(acceptance.scan_expected_test_ids("/nonexistent/dir", "_acceptance"), {})

    def test_simple_module_two_tests(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "test_spec_foo.py"), "w") as f:
                f.write(
                    "import unittest\n"
                    "class T(unittest.TestCase):\n"
                    "    def test_a(self):\n"
                    "        pass\n"
                    "    def test_b(self):\n"
                    "        pass\n"
                    "    def helper(self):\n"
                    "        pass\n"
                )
            expected = acceptance.scan_expected_test_ids(d, "_acceptance")
            self.assertEqual(
                expected["test_spec_foo"],
                {"_acceptance.test_spec_foo.T.test_a", "_acceptance.test_spec_foo.T.test_b"},
            )

    def test_module_that_fails_to_import_still_scanned(self):
        # A module whose TOP-LEVEL code raises (e.g. an import of a name
        # that doesn't exist in the agent's tree) can't be imported by
        # unittest at all -- but its source still parses fine, so the AST
        # scan still finds its test methods. This is exactly the
        # `test_pivot_doc_error_codes.py` shape from the real bug: it
        # imports `E_RETENTION_PERIODS` at module level, which doesn't
        # exist until the agent adds it.
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "test_doc_error_codes.py"), "w") as f:
                f.write(
                    "import unittest\n"
                    "from nonexistent_module import DOES_NOT_EXIST\n"
                    "class T(unittest.TestCase):\n"
                    "    def test_x(self):\n"
                    "        pass\n"
                )
            expected = acceptance.scan_expected_test_ids(d, "_acceptance.pivot")
            self.assertEqual(expected["test_doc_error_codes"],
                              {"_acceptance.pivot.test_doc_error_codes.T.test_x"})

    def test_syntax_error_module_yields_empty_set_not_raise(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "test_spec_broken.py"), "w") as f:
                f.write("def broken(:\n")
            expected = acceptance.scan_expected_test_ids(d, "_acceptance")
            self.assertEqual(expected["test_spec_broken"], set())

    def test_non_test_files_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "__init__.py"), "w") as f:
                f.write("")
            with open(os.path.join(d, "helpers.py"), "w") as f:
                f.write("class T:\n    def test_x(self): pass\n")
            expected = acceptance.scan_expected_test_ids(d, "_acceptance")
            self.assertEqual(expected, {})

    def test_non_testcase_class_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "test_spec_foo.py"), "w") as f:
                f.write("class T:\n    def test_x(self): pass\n")
            expected = acceptance.scan_expected_test_ids(d, "_acceptance")
            self.assertEqual(expected["test_spec_foo"], set())

    def test_multiple_classes_in_one_module(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "test_doc_x.py"), "w") as f:
                f.write(
                    "import unittest\n"
                    "class A(unittest.TestCase):\n"
                    "    def test_1(self): pass\n"
                    "class B(unittest.TestCase):\n"
                    "    def test_2(self): pass\n"
                )
            expected = acceptance.scan_expected_test_ids(d, "_acceptance")
            self.assertEqual(
                expected["test_doc_x"],
                {"_acceptance.test_doc_x.A.test_1", "_acceptance.test_doc_x.B.test_2"},
            )


class ScoreAgainstExpectedIdsTest(unittest.TestCase):
    """score_against_expected_ids: the core fix for the "unstable totals"
    bug -- an import-failed module's expected ids are scored individually
    ("import_error") instead of the whole run silently under-counting."""

    def test_all_pass(self):
        expected_by_module = {"test_spec_foo": {"_acceptance.test_spec_foo.T.test_a"}}
        test_results = [
            {"test_id": "test_a (_acceptance.test_spec_foo.T.test_a)",
             "method": "test_a", "path": "_acceptance.test_spec_foo.T.test_a", "status": "ok"},
        ]
        scored = acceptance.score_against_expected_ids(test_results, expected_by_module, "_acceptance")
        self.assertEqual(scored["total"], 1)
        self.assertEqual(scored["passed"], 1)
        self.assertEqual(scored["by_id"]["_acceptance.test_spec_foo.T.test_a"]["status"], "ok")

    def test_import_failed_module_scores_every_expected_id_as_import_error(self):
        # Real shape: unittest -v emits ONE line for the whole module --
        # "test_doc_error_codes (unittest.loader._FailedTest.test_doc_error_codes) ... ERROR"
        # -- which parse_verbose_unittest_output parses as method="test_doc_error_codes",
        # path="unittest.loader._FailedTest.test_doc_error_codes" (no module_prefix
        # lead-in on the path since the _FailedTest dotted name IS the bare module name
        # here, matching a single-phase acceptance_subdir="" layout).
        expected_by_module = {
            "test_doc_error_codes": {
                "_acceptance.test_doc_error_codes.T.test_x",
                "_acceptance.test_doc_error_codes.T.test_y",
            },
        }
        test_results = [
            {"test_id": "test_doc_error_codes (unittest.loader._FailedTest.test_doc_error_codes)",
             "method": "_acceptance.test_doc_error_codes",
             "path": "unittest.loader._FailedTest.test_doc_error_codes", "status": "error"},
        ]
        scored = acceptance.score_against_expected_ids(test_results, expected_by_module, "_acceptance")
        self.assertEqual(scored["total"], 2)
        self.assertEqual(scored["passed"], 0)
        self.assertEqual(scored["by_id"]["_acceptance.test_doc_error_codes.T.test_x"]["status"], "import_error")
        self.assertEqual(scored["by_id"]["_acceptance.test_doc_error_codes.T.test_y"]["status"], "import_error")

    def test_expected_id_with_no_actual_result_scores_missing(self):
        expected_by_module = {"test_spec_foo": {"_acceptance.test_spec_foo.T.test_a"}}
        scored = acceptance.score_against_expected_ids([], expected_by_module, "_acceptance")
        self.assertEqual(scored["total"], 1)
        self.assertEqual(scored["passed"], 0)
        self.assertEqual(scored["by_id"]["_acceptance.test_spec_foo.T.test_a"]["status"], "missing")

    def test_older_interpreter_path_shape_without_trailing_method(self):
        # Pre-3.11 unittest -v path doesn't repeat the method name:
        # "test_a (pkg.test_spec_foo.T)" -- score_against_expected_ids must
        # still reconstruct the same expected-id key by appending it.
        expected_by_module = {"test_spec_foo": {"_acceptance.test_spec_foo.T.test_a"}}
        test_results = [
            {"test_id": "test_a (_acceptance.test_spec_foo.T)",
             "method": "test_a", "path": "_acceptance.test_spec_foo.T", "status": "ok"},
        ]
        scored = acceptance.score_against_expected_ids(test_results, expected_by_module, "_acceptance")
        self.assertEqual(scored["passed"], 1)

    def test_actual_result_not_in_expected_set_is_ignored(self):
        expected_by_module = {"test_spec_foo": {"_acceptance.test_spec_foo.T.test_a"}}
        test_results = [
            {"test_id": "test_a (_acceptance.test_spec_foo.T.test_a)",
             "method": "test_a", "path": "_acceptance.test_spec_foo.T.test_a", "status": "ok"},
            {"test_id": "test_stray (_acceptance.test_spec_foo.T.test_stray)",
             "method": "test_stray", "path": "_acceptance.test_spec_foo.T.test_stray", "status": "ok"},
        ]
        scored = acceptance.score_against_expected_ids(test_results, expected_by_module, "_acceptance")
        self.assertEqual(scored["total"], 1)
        self.assertEqual(scored["passed"], 1)

    def test_fail_and_error_statuses_preserved(self):
        expected_by_module = {
            "test_spec_foo": {"_acceptance.test_spec_foo.T.test_a", "_acceptance.test_spec_foo.T.test_b"},
        }
        test_results = [
            {"test_id": "test_a (_acceptance.test_spec_foo.T.test_a)",
             "method": "test_a", "path": "_acceptance.test_spec_foo.T.test_a", "status": "fail"},
            {"test_id": "test_b (_acceptance.test_spec_foo.T.test_b)",
             "method": "test_b", "path": "_acceptance.test_spec_foo.T.test_b", "status": "error"},
        ]
        scored = acceptance.score_against_expected_ids(test_results, expected_by_module, "_acceptance")
        self.assertEqual(scored["by_id"]["_acceptance.test_spec_foo.T.test_a"]["status"], "fail")
        self.assertEqual(scored["by_id"]["_acceptance.test_spec_foo.T.test_b"]["status"], "error")
        self.assertEqual(scored["passed"], 0)

    def test_pivot_subdir_module_prefix_scopes_failed_test_matching(self):
        # A _FailedTest line for a module under the "pivot" acceptance_subdir
        # carries "_acceptance.pivot.<module>" as its dotted name (see
        # run.score_hidden_tests_dir's __init__.py-at-root note) -- must not
        # be confused with a same-named module under "task1".
        expected_by_module = {
            "test_doc_error_codes": {"_acceptance.pivot.test_doc_error_codes.T.test_x"},
        }
        test_results = [
            {"test_id": "test_doc_error_codes (unittest.loader._FailedTest._acceptance.pivot.test_doc_error_codes)",
             "method": "_acceptance.pivot.test_doc_error_codes",
             "path": "unittest.loader._FailedTest._acceptance.pivot.test_doc_error_codes", "status": "error"},
        ]
        scored = acceptance.score_against_expected_ids(test_results, expected_by_module, "_acceptance.pivot")
        self.assertEqual(scored["by_id"]["_acceptance.pivot.test_doc_error_codes.T.test_x"]["status"],
                          "import_error")


class CategorizeExpectedResultsTest(unittest.TestCase):
    def test_rolls_up_by_category(self):
        by_id = {
            "_acceptance.test_spec_a.T.test_1": {"status": "ok"},
            "_acceptance.test_spec_a.T.test_2": {"status": "fail"},
            "_acceptance.test_doc_b.T.test_3": {"status": "import_error"},
        }
        cats = acceptance.categorize_expected_results(by_id)
        self.assertEqual(cats["spec"], {"passed": 1, "total": 2})
        self.assertEqual(cats["doc"], {"passed": 0, "total": 1})
        self.assertEqual(cats["other"], {"passed": 0, "total": 0})

    def test_empty(self):
        cats = acceptance.categorize_expected_results({})
        self.assertEqual(cats["spec"], {"passed": 0, "total": 0})


class DocRulePassMatrixFromExpectedTest(unittest.TestCase):
    def test_rule_scored_against_import_error_module(self):
        rules = [{
            "id": "P6", "memory": "ref/REF_ERROR_HANDLING",
            "tests": [{"id": "test_doc_error_codes.T.test_x", "asserts": "..."}],
        }]
        by_id = {"_acceptance.pivot.test_doc_error_codes.T.test_x": {"status": "import_error"}}
        matrix = acceptance.doc_rule_pass_matrix_from_expected(by_id, rules)
        self.assertEqual(matrix["P6"], {
            "passed": 0, "total": 1, "memory": "ref/REF_ERROR_HANDLING", "summary": None, "ok": False,
        })

    def test_rule_all_pass(self):
        rules = [{"id": "P1", "memory": "x", "tests": ["test_x"]}]
        by_id = {"_acceptance.pivot.test_foo.T.test_x": {"status": "ok"}}
        matrix = acceptance.doc_rule_pass_matrix_from_expected(by_id, rules)
        self.assertTrue(matrix["P1"]["ok"])

    def test_no_matching_ids_total_zero_ok_none(self):
        rules = [{"id": "P1", "memory": "x", "tests": ["test_nonexistent"]}]
        by_id = {"_acceptance.pivot.test_foo.T.test_x": {"status": "ok"}}
        matrix = acceptance.doc_rule_pass_matrix_from_expected(by_id, rules)
        self.assertIsNone(matrix["P1"]["ok"])
        self.assertEqual(matrix["P1"]["total"], 0)


if __name__ == "__main__":
    unittest.main()
