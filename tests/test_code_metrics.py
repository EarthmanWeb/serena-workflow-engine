"""Tests for experiments/harness-ab/code_metrics.py: numstat/AST parsing
(pure, direct) and collect_code_metrics() end-to-end against a synthetic
tiny git repo built in a temp dir."""
import importlib.util
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_METRICS_PATH = os.path.join(HERE, "..", "experiments", "harness-ab", "code_metrics.py")


def _load_code_metrics():
    spec = importlib.util.spec_from_file_location("harness_ab_code_metrics", CODE_METRICS_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cm = _load_code_metrics()


# --------------------------------------------------------------------------
# parse_numstat / loc_summary (pure).
# --------------------------------------------------------------------------

class TestParseNumstat(unittest.TestCase):
    def test_basic_rows(self):
        text = "10\t2\tledgerlite/foo.py\n5\t0\ttests/test_foo.py\n"
        rows = cm.parse_numstat(text)
        self.assertEqual(rows, [(10, 2, "ledgerlite/foo.py"), (5, 0, "tests/test_foo.py")])

    def test_binary_file_dashes(self):
        text = "-\t-\tledgerlite/data.bin\n"
        rows = cm.parse_numstat(text)
        self.assertEqual(rows, [(None, None, "ledgerlite/data.bin")])

    def test_excludes_acceptance_dir(self):
        text = "10\t0\t_acceptance/test_doc_x.py\n5\t0\tledgerlite/foo.py\n"
        rows = cm.parse_numstat(text)
        self.assertEqual(rows, [(5, 0, "ledgerlite/foo.py")])

    def test_excludes_serena_dir(self):
        text = "3\t0\t.serena/memory/MEMORY.md\n5\t0\tledgerlite/foo.py\n"
        rows = cm.parse_numstat(text)
        self.assertEqual(rows, [(5, 0, "ledgerlite/foo.py")])

    def test_excludes_ledger_json_suffix(self):
        text = "3\t0\tdata/store.ledger.json\n5\t0\tledgerlite/foo.py\n"
        rows = cm.parse_numstat(text)
        self.assertEqual(rows, [(5, 0, "ledgerlite/foo.py")])

    def test_empty_text(self):
        self.assertEqual(cm.parse_numstat(""), [])
        self.assertEqual(cm.parse_numstat(None), [])

    def test_ignores_malformed_lines(self):
        text = "not a numstat line\n10\t2\tledgerlite/foo.py\n"
        rows = cm.parse_numstat(text)
        self.assertEqual(rows, [(10, 2, "ledgerlite/foo.py")])


class TestLocSummary(unittest.TestCase):
    def test_new_file_counted_as_added(self):
        rows = [(20, 0, "ledgerlite/new.py")]
        s = cm.loc_summary(rows)
        self.assertEqual(s["files_added"], 1)
        self.assertEqual(s["files_modified"], 0)
        self.assertEqual(s["loc_added"], 20)
        self.assertEqual(s["loc_deleted"], 0)

    def test_modified_file_has_deletions(self):
        rows = [(5, 3, "ledgerlite/existing.py")]
        s = cm.loc_summary(rows)
        self.assertEqual(s["files_added"], 0)
        self.assertEqual(s["files_modified"], 1)

    def test_mixed_rows_aggregate(self):
        rows = [(20, 0, "a.py"), (5, 3, "b.py"), (None, None, "c.bin")]
        s = cm.loc_summary(rows)
        self.assertEqual(s["loc_added"], 25)
        self.assertEqual(s["loc_deleted"], 3)
        self.assertEqual(s["files_total"], 3)
        # c.bin: added/deleted None -> treated as 0/0 -> "modified" bucket
        # (deleted==0 and added==0, so the (deleted==0 and added>0) check
        # is False -> falls to files_modified).
        self.assertEqual(s["files_added"], 1)
        self.assertEqual(s["files_modified"], 2)

    def test_empty_rows(self):
        s = cm.loc_summary([])
        self.assertEqual(s["loc_added"], 0)
        self.assertEqual(s["files_total"], 0)
        self.assertEqual(s["paths"], [])


# --------------------------------------------------------------------------
# AST metrics (pure).
# --------------------------------------------------------------------------

class TestAnalyzePythonSource(unittest.TestCase):
    def test_simple_function_metrics(self):
        src = textwrap.dedent('''\
            def foo(x):
                """Docstring."""
                if x:
                    return 1
                return 0
        ''')
        fa = cm.analyze_python_source("m.py", src)
        self.assertFalse(fa["parse_error"])
        self.assertEqual(len(fa["functions"]), 1)
        f = fa["functions"][0]
        self.assertEqual(f["name"], "foo")
        self.assertTrue(f["has_docstring"])
        self.assertTrue(f["is_public"])
        self.assertEqual(f["length"], 5)
        self.assertEqual(f["complexity"], 1)  # one `if`

    def test_private_function_not_public(self):
        src = "def _helper():\n    pass\n"
        fa = cm.analyze_python_source("m.py", src)
        self.assertFalse(fa["functions"][0]["is_public"])

    def test_dunder_is_public(self):
        src = "class C:\n    def __init__(self):\n        pass\n"
        fa = cm.analyze_python_source("m.py", src)
        self.assertTrue(fa["functions"][0]["is_public"])

    def test_no_docstring(self):
        src = "def foo():\n    return 1\n"
        fa = cm.analyze_python_source("m.py", src)
        self.assertFalse(fa["functions"][0]["has_docstring"])

    def test_nested_functions_both_counted(self):
        src = textwrap.dedent('''\
            def outer():
                def inner():
                    return 1
                return inner()
        ''')
        fa = cm.analyze_python_source("m.py", src)
        names = sorted(f["name"] for f in fa["functions"])
        self.assertEqual(names, ["inner", "outer"])

    def test_complexity_excludes_nested_function_body(self):
        src = textwrap.dedent('''\
            def outer():
                def inner():
                    if True:
                        pass
                return 1
        ''')
        fa = cm.analyze_python_source("m.py", src)
        outer = next(f for f in fa["functions"] if f["name"] == "outer")
        inner = next(f for f in fa["functions"] if f["name"] == "inner")
        self.assertEqual(outer["complexity"], 0)
        self.assertEqual(inner["complexity"], 1)

    def test_syntax_error_reports_parse_error(self):
        fa = cm.analyze_python_source("bad.py", "def foo(:\n")
        self.assertTrue(fa["parse_error"])
        self.assertEqual(fa["functions"], [])

    def test_for_while_except_boolop_all_count(self):
        src = textwrap.dedent('''\
            def foo(x):
                try:
                    for i in x:
                        while i:
                            pass
                except ValueError:
                    pass
                if x and i:
                    pass
        ''')
        fa = cm.analyze_python_source("m.py", src)
        f = fa["functions"][0]
        # for, while, except, if, and (boolop) == 5
        self.assertEqual(f["complexity"], 5)


class TestAggregateAstMetrics(unittest.TestCase):
    def test_empty_input(self):
        agg = cm.aggregate_ast_metrics([])
        self.assertEqual(agg["function_count"], 0)
        self.assertIsNone(agg["avg_function_length"])
        self.assertIsNone(agg["docstring_coverage"])
        self.assertIsNone(agg["longest_file"])

    def test_docstring_coverage_public_only(self):
        src_a = textwrap.dedent('''\
            def pub_documented():
                """Doc."""
                return 1

            def pub_undocumented():
                return 2

            def _private_undocumented():
                return 3
        ''')
        fa = cm.analyze_python_source("a.py", src_a)
        agg = cm.aggregate_ast_metrics([fa])
        # 2 public funcs, 1 documented -> 0.5; private one excluded from
        # the denominator entirely.
        self.assertAlmostEqual(agg["docstring_coverage"], 0.5)
        self.assertEqual(agg["function_count"], 3)

    def test_longest_file_by_function_count(self):
        fa_small = cm.analyze_python_source("small.py", "def f():\n    pass\n")
        fa_big = cm.analyze_python_source(
            "big.py", "def f():\n    pass\n\n\ndef g():\n    pass\n"
        )
        agg = cm.aggregate_ast_metrics([fa_small, fa_big])
        self.assertEqual(agg["longest_file"], ("big.py", 2))

    def test_avg_and_max_function_length(self):
        fa = cm.analyze_python_source(
            "m.py",
            "def a():\n    return 1\n\n\ndef b():\n    x = 1\n    y = 2\n    return x + y\n",
        )
        agg = cm.aggregate_ast_metrics([fa])
        self.assertEqual(agg["max_function_length"], 4)
        self.assertAlmostEqual(agg["avg_function_length"], (2 + 4) / 2)


class TestCountTestMethods(unittest.TestCase):
    def test_counts_test_prefixed_defs_only(self):
        src = textwrap.dedent('''\
            class TestFoo:
                def test_one(self):
                    pass

                def test_two(self):
                    pass

                def helper(self):
                    pass
        ''')
        fa = cm.analyze_python_source("test_foo.py", src)
        self.assertEqual(cm.count_test_methods([fa]), 2)

    def test_accepts_raw_source_pairs(self):
        n = cm.count_test_methods([("test_x.py", "def test_a():\n    pass\n")])
        self.assertEqual(n, 1)

    def test_zero_when_no_test_methods(self):
        fa = cm.analyze_python_source("m.py", "def helper():\n    pass\n")
        self.assertEqual(cm.count_test_methods([fa]), 0)


# --------------------------------------------------------------------------
# collect_code_metrics() end-to-end against a synthetic tiny git repo.
# --------------------------------------------------------------------------


def _run_git(cwd, *args):
    subprocess.run(["git"] + list(args), cwd=cwd, check=True, capture_output=True)


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


class TestCollectCodeMetricsSyntheticRepo(unittest.TestCase):
    """Builds a tiny fixture->b1->final git history under a temp dir,
    mirroring a run's work/ layout, and exercises collect_code_metrics()
    against it end-to-end."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="code_metrics_test_")
        self.repo = os.path.join(self.tmp, "work")
        os.makedirs(self.repo)
        _run_git(self.repo, "init", "-q")
        _run_git(self.repo, "config", "user.email", "t@example.com")
        _run_git(self.repo, "config", "user.name", "Test")

        # Fixture (identity) commit: a stub package + one existing test.
        _write(os.path.join(self.repo, "pkg", "__init__.py"), "")
        _write(os.path.join(self.repo, "pkg", "core.py"), "def existing():\n    return 1\n")
        _write(os.path.join(self.repo, "tests", "test_core.py"),
               "def test_existing():\n    assert True\n")
        _run_git(self.repo, "add", "-A")
        _run_git(self.repo, "commit", "-q", "-m", "fixture")

        # B1 commit: agent adds a new module + a test for it.
        _write(
            os.path.join(self.repo, "pkg", "feature.py"),
            textwrap.dedent('''\
                def add(a, b):
                    """Add two numbers."""
                    return a + b

                def _internal(a):
                    if a:
                        return a
                    return None
            '''),
        )
        _write(
            os.path.join(self.repo, "tests", "test_feature.py"),
            textwrap.dedent('''\
                def test_add_positive():
                    assert True

                def test_add_negative():
                    assert True
            '''),
        )
        _run_git(self.repo, "add", "-A")
        _run_git(self.repo, "commit", "-q", "-m", "benchmark1")

        # Final: one more small edit on top of B1.
        _write(
            os.path.join(self.repo, "pkg", "feature.py"),
            textwrap.dedent('''\
                def add(a, b):
                    """Add two numbers."""
                    return a + b

                def subtract(a, b):
                    """Subtract b from a."""
                    return a - b

                def _internal(a):
                    if a:
                        return a
                    return None
            '''),
        )
        _run_git(self.repo, "add", "-A")
        _run_git(self.repo, "commit", "-q", "-m", "benchmark2")

    def test_identity_and_b1_commits_found(self):
        m = cm.collect_code_metrics(self.repo)
        self.assertIsNotNone(m["identity_commit"])
        self.assertIsNotNone(m["b1_commit"])

    def test_fixture_to_final_loc(self):
        m = cm.collect_code_metrics(self.repo)
        summary = m["fixture_to_final"]
        self.assertIn("pkg/feature.py", summary["paths"])
        self.assertIn("tests/test_feature.py", summary["paths"])
        self.assertGreater(summary["loc_added"], 0)
        # feature.py + test_feature.py are new files.
        self.assertGreaterEqual(summary["files_added"], 2)

    def test_fixture_to_b1_smaller_than_final(self):
        m = cm.collect_code_metrics(self.repo)
        self.assertLessEqual(m["fixture_to_b1"]["loc_added"], m["fixture_to_final"]["loc_added"])

    def test_ast_metrics_over_non_test_files(self):
        m = cm.collect_code_metrics(self.repo)
        ast_m = m["ast"]
        # add, subtract, _internal == 3 functions in the final feature.py;
        # existing() in pkg/core.py is untouched by the diff so it's
        # excluded (not an agent-added/modified file).
        self.assertEqual(ast_m["function_count"], 3)
        self.assertIsNotNone(ast_m["docstring_coverage"])

    def test_agent_test_count(self):
        m = cm.collect_code_metrics(self.repo)
        self.assertEqual(m["agent_test_count"], 2)

    def test_size_vs_reference_pct_none_without_task_paths(self):
        m = cm.collect_code_metrics(self.repo, task_paths=None)
        self.assertIsNone(m["size_vs_reference_pct"])

    def test_size_vs_reference_pct_computed(self):
        ref_dir = os.path.join(self.tmp, "reference_solution")
        _write(os.path.join(ref_dir, "pkg", "feature.py"), "def add(a, b):\n    return a + b\n" * 5)
        m = cm.collect_code_metrics(self.repo, task_paths={"reference_solution": ref_dir})
        self.assertIsNotNone(m["size_vs_reference_pct"])
        self.assertGreater(m["size_vs_reference_pct"], 0)

    def test_nonexistent_run_dir_degrades_gracefully(self):
        m = cm.collect_code_metrics(os.path.join(self.tmp, "does-not-exist"))
        self.assertIsNone(m["identity_commit"])
        self.assertEqual(m["fixture_to_final"]["loc_added"], 0)
        self.assertEqual(m["agent_test_count"], 0)


if __name__ == "__main__":
    unittest.main()
