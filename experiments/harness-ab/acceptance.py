#!/usr/bin/env python3
"""Per-test acceptance parsing/classification for experiments/harness-ab.

Pure functions only (no I/O) — parse `python3 -m unittest ... -v` verbose
output into per-test pass/fail results, classify each test id into a
category (spec/doc/other) by its module-qualified basename prefix, and roll
those up against a task's optional doc_rules.json.

Verbose unittest output line shapes (confirmed against the interpreter this
harness runs under, Python 3.11+, AND documented for older 3.x):
    "test_foo (tests.test_bar.MyTest) ... ok"
    "test_foo (tests.test_bar.MyTest.test_foo) ... ok"        (3.11+: repeats
                                                                 the method
                                                                 name in the
                                                                 dotted path)
    "test_foo (tests.test_bar.MyTest) ... FAIL"
    "test_foo (tests.test_bar.MyTest) ... ERROR"
    "test_foo (tests.test_bar.MyTest) ... skipped 'reason text'"
    "test_foo (tests.test_bar.MyTest) ... expected failure"
    "test_foo (tests.test_bar.MyTest) ... unexpected success"
"""
import ast
import json
import os
import re

VERBOSE_TEST_LINE_RE = re.compile(
    r"^(?P<method>\S+)\s+\((?P<path>[\w.]+)\)\s*\.\.\.\s*(?P<status>ok|FAIL|ERROR|"
    r"skipped(?:\s+'[^']*')?|expected failure|unexpected success)\s*$",
    re.MULTILINE,
)

_STATUS_MAP = {
    "ok": "ok",
    "FAIL": "fail",
    "ERROR": "error",
    "expected failure": "ok",       # xfail counts as a pass for our purposes
    "unexpected success": "fail",   # unexpected success counts as a failure
}


def _normalize_status(raw_status):
    raw_status = raw_status.strip()
    if raw_status.startswith("skipped"):
        return "skipped"
    return _STATUS_MAP.get(raw_status, raw_status.lower())


def parse_verbose_unittest_output(text):
    """Parse `python -m unittest ... -v` output into a list of per-test
    result dicts: [{"test_id": "test_foo (tests.test_bar.MyTest)",
                     "method": "test_foo", "path": "tests.test_bar.MyTest",
                     "status": "ok"|"fail"|"error"|"skipped"}, ...]

    `test_id` is reconstructed exactly as unittest's own `FAIL:`/`ERROR:`
    summary lines format it: "method (path)" — matching run.py's existing
    parse_failed_test_ids() id shape, so results from both parsers can be
    correlated on the same key. Order-preserving; malformed/non-matching
    lines are skipped. Pure — text in, list out."""
    results = []
    for m in VERBOSE_TEST_LINE_RE.finditer(text or ""):
        method = m.group("method")
        path = m.group("path")
        status = _normalize_status(m.group("status"))
        results.append({
            "test_id": f"{method} ({path})",
            "method": method,
            "path": path,
            "status": status,
        })
    return results


def classify_test_category(test_id_or_method):
    """Classify a test id (or bare method/file basename) into
    'spec' | 'doc' | 'other' by its `test_spec_*` / `test_doc_*` file-prefix
    convention (v2 tasks) — falls back to 'other' for v1's `test_acceptance_*`
    convention and anything else. Pure.

    Also matches the pivot phase's own `test_pivot_spec_*` / `test_pivot_doc_*`
    file-prefix convention (tasks/<task>/pivot/hidden_tests/) — checked via
    substring containment (`"pivot_spec_" in seg`) rather than a second
    `seg.startswith(...)` so a segment is only ever tested for BOTH prefixes
    with two checks total, not four: the plain `test_spec_`/`test_doc_`
    startswith check never matches a `test_pivot_spec_*` segment (it starts
    with `test_pivot_`, not `test_spec_`), so both conventions need their own
    check, but "pivot_spec_"/"pivot_doc_" as a substring anywhere after
    `test_` covers the pivot convention without a second full prefix set.

    Accepts either a full unittest test id ("test_x (pkg.test_spec_foo.Cls)")
    or a bare module/file basename ("test_spec_foo.py" / "test_spec_foo").
    """
    if not test_id_or_method:
        return "other"
    s = str(test_id_or_method)
    # Extract the dotted path component if this looks like a full test id.
    m = re.search(r"\(([\w.]+)\)", s)
    haystack = m.group(1) if m else s
    segments = re.split(r"[./]", haystack)
    for seg in segments:
        if seg.startswith("test_spec_") or "pivot_spec_" in seg:
            return "spec"
        if seg.startswith("test_doc_") or "pivot_doc_" in seg:
            return "doc"
    return "other"


def scan_expected_test_ids(hidden_tests_dir, module_prefix):
    """AST-scan every `test_*.py` file directly under `hidden_tests_dir` for
    top-level `unittest.TestCase` subclasses and their `test_*` methods, and
    return the STATIC set of expected test ids in the exact dotted shape
    `-v` output uses: "<module_prefix>.<module>.<Class>.<method>" (e.g.
    "_acceptance.pivot.test_pivot_doc_error_codes.TestRetentionErrorCode.
    test_error_code_constant_defined") — matching run.py's
    score_hidden_tests_dir() copy layout, where hidden_tests_dir's files
    land at work_dir/_acceptance/<acceptance_subdir>/ and `-t .` discovery
    names them "_acceptance.<acceptance_subdir>.<module>...." (empty
    acceptance_subdir for the single-phase layout collapses to
    "_acceptance.<module>....").

    A class counts as a TestCase subclass if ANY of its declared base
    expressions is literally named `TestCase` (bare `TestCase`) or ends in
    `.TestCase` (e.g. `unittest.TestCase`) — a conservative syntactic match;
    a class inherits from a *custom* base that is itself a TestCase subclass
    defined elsewhere is NOT detected (none of this harness's hidden_tests
    fixtures do that — every TestCase subclass inherits directly from
    unittest.TestCase, confirmed by grep across tasks/v2/**/hidden_tests).
    Nested classes are walked too (ast.walk covers the whole tree), which is
    intentionally permissive: any test method unittest's own discovery would
    find, this scan also finds.

    `module_prefix` is the dotted id prefix before the module name --
    "_acceptance" for the single-phase layout, "_acceptance.pivot" /
    "_acceptance.task1" for a pivot run's two nested subdirs (see
    run.py's score_hidden_tests_dir `acceptance_subdir` param). Pass the
    prefix WITHOUT a trailing dot.

    Returns a dict {module_basename: {test_id, ...}} -- keyed by the bare
    module filename (no .py) so a caller can report import-failed modules
    (unittest's _FailedTest line names the whole module, not a class/method)
    against exactly the ids that module was expected to contribute. A file
    that fails to parse (syntax error) or isn't valid Python contributes an
    empty id set for that module rather than raising -- the module will
    still show up as an entry (empty set) so callers can tell "0 expected
    tests found by static scan" from "module wasn't discovered on disk at
    all". Missing/non-existent hidden_tests_dir returns {}."""
    out = {}
    if not hidden_tests_dir or not os.path.isdir(hidden_tests_dir):
        return out
    for fn in sorted(os.listdir(hidden_tests_dir)):
        if not fn.startswith("test_") or not fn.endswith(".py"):
            continue
        module = fn[:-3]
        ids = set()
        path = os.path.join(hidden_tests_dir, fn)
        try:
            with open(path) as f:
                source = f.read()
            tree = ast.parse(source, filename=fn)
        except (OSError, SyntaxError, ValueError):
            out[module] = ids
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not _is_testcase_class(node):
                continue
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name.startswith("test_"):
                    ids.add(f"{module_prefix}.{module}.{node.name}.{item.name}")
        out[module] = ids
    return out


def _is_testcase_class(class_def):
    """True iff any base expression of `class_def` is literally named
    `TestCase` or ends in `.TestCase` (e.g. `unittest.TestCase`). Pure."""
    for base in class_def.bases:
        if isinstance(base, ast.Name) and base.id == "TestCase":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "TestCase":
            return True
    return False


def score_against_expected_ids(test_results, expected_by_module, module_prefix):
    """Score a verbose-unittest run against the STATIC expected-id set from
    scan_expected_test_ids(), so a module that fails to import (reported by
    unittest as a single `_FailedTest`/ERROR line, see module docstring)
    scores every one of ITS expected test ids individually (each as
    "import_error"), keeping the module's full test count in the
    total/passed denominators rather than a single opaque result.

    test_results: parse_verbose_unittest_output()'s list for one run.
    expected_by_module: scan_expected_test_ids()'s return value.
    module_prefix: same dotted prefix passed to scan_expected_test_ids
        (used to recognize a `_FailedTest`-shaped result's `path`, which
        unittest emits as the bare module dotted name, e.g.
        "_acceptance.pivot.test_pivot_doc_error_codes").

    Returns {"total": n, "passed": n, "by_id": {expected_id: {"status":
    "ok"|"fail"|"error"|"skipped"|"import_error"|"missing"}}}. "total"/
    "passed" are computed over the union of every expected id across all
    modules in expected_by_module -- an expected id NOT present as an
    "ok" (or xfail-as-ok) actual result is scored "missing" (test simply
    never ran / was never reported, e.g. discovery skipped a file) unless
    its whole module is import-failed, in which case every one of that
    module's expected ids is scored "import_error" instead of "missing"
    (more specific/diagnostic than the generic fallback). An actual result
    whose id doesn't correspond to any expected id (e.g. a test the agent
    added on its own, or a stale id) is ignored for scoring purposes -- only
    expected ids count toward total/passed. Pure."""
    all_expected = set()
    for ids in expected_by_module.values():
        all_expected |= ids

    by_actual_id = {}
    import_failed_modules = set()
    for r in test_results or []:
        path = r.get("path") or ""
        # unittest.loader._FailedTest's `-v` line shape:
        #   "<module> (unittest.loader._FailedTest.<module>) ... ERROR"
        # parse_verbose_unittest_output() parses that as method=<module>,
        # path="unittest.loader._FailedTest.<module>" -- the failed
        # module's own dotted name is the METHOD field here, not path.
        if path.startswith("unittest.loader._FailedTest."):
            failed_module_id = r.get("method") or ""
            prefix = f"{module_prefix}."
            if failed_module_id.startswith(prefix):
                module_basename = failed_module_id[len(prefix):]
                if module_basename in expected_by_module:
                    import_failed_modules.add(module_basename)
            continue
        method = r.get("method") or ""
        # Reconstruct "<module_prefix>.<module>.<Class>.<method>" from the
        # actual result's path, which (Python 3.11+) already repeats the
        # method name at the end: "<prefix>.<module>.<Class>.<method>".
        # Older interpreters' path omits the trailing method segment
        # ("<prefix>.<module>.<Class>") -- append it in that case so both
        # shapes normalize to the same expected-id key.
        if path.endswith(f".{method}"):
            full_id = path
        else:
            full_id = f"{path}.{method}" if path else method
        by_actual_id[full_id] = r.get("status")

    by_id = {}
    passed = 0
    for expected_id in all_expected:
        # expected_id shape: "<prefix>.<module>.<Class>.<method>"
        rest = expected_id[len(module_prefix) + 1:] if module_prefix else expected_id
        module_basename = rest.split(".", 1)[0]
        if module_basename in import_failed_modules:
            by_id[expected_id] = {"status": "import_error"}
            continue
        status = by_actual_id.get(expected_id)
        if status is None:
            by_id[expected_id] = {"status": "missing"}
            continue
        by_id[expected_id] = {"status": status}
        if status == "ok":
            passed += 1

    return {"total": len(all_expected), "passed": passed, "by_id": by_id}


def categorize_expected_results(by_id):
    """Roll up score_against_expected_ids()'s `by_id` dict into per-category
    (spec/doc/other) pass/total counts, using classify_test_category() on
    each expected id (which already carries the module name -> prefix
    classification works unchanged). Returns the same shape as
    categorize_results(). Pure."""
    out = {
        "spec": {"passed": 0, "total": 0},
        "doc": {"passed": 0, "total": 0},
        "other": {"passed": 0, "total": 0},
    }
    for expected_id, result in (by_id or {}).items():
        cat = classify_test_category(expected_id)
        out[cat]["total"] += 1
        if result.get("status") == "ok":
            out[cat]["passed"] += 1
    return out


def categorize_results(test_results):
    """Given parse_verbose_unittest_output()'s list, roll up pass/total per
    category. Returns {"spec": {"passed": n, "total": n},
                        "doc": {"passed": n, "total": n},
                        "other": {"passed": n, "total": n}}. Pure."""
    out = {
        "spec": {"passed": 0, "total": 0},
        "doc": {"passed": 0, "total": 0},
        "other": {"passed": 0, "total": 0},
    }
    for r in test_results or []:
        cat = classify_test_category(r.get("path") or r.get("test_id"))
        out[cat]["total"] += 1
        if r.get("status") == "ok":
            out[cat]["passed"] += 1
    return out


def load_doc_rules(path):
    """Load a task's optional doc_rules.json: a list of
    {"id": str, "memory": str, "summary": str, "tests": [...], "quote": str}.

    'tests' entries come in two schemas (both accepted, see _rule_test_id /
    _test_id_matches): older files use a plain test-id string per entry;
    newer files (which also add the top-level "quote" field) use an object
    {"id": "<test id>", "asserts": "<human-readable description>"} per
    entry. 'quote' and 'asserts' are documentation-only and never consulted
    by doc_rule_pass_matrix.

    Returns [] when the file doesn't exist or fails to parse (never
    raises)."""
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
    except (ValueError, OSError):
        return []
    if not isinstance(data, list):
        return []
    return [r for r in data if isinstance(r, dict) and r.get("id")]


def _rule_test_id(rule_test):
    """Normalize one doc_rules.json 'tests' entry to its bare id string.

    Older doc_rules.json files list 'tests' as plain strings (the bare
    method name or a test-id substring). Newer files (schema with 'quote')
    list them as objects {"id": "<test id>", "asserts": "..."} — 'asserts'
    is documentation-only (a human-readable description of what the test
    checks) and never participates in matching. Returns None for anything
    that yields no usable id (e.g. a dict with no 'id' key)."""
    if isinstance(rule_test, dict):
        return rule_test.get("id")
    return rule_test


def _test_id_matches(rule_test, actual_test_id, actual_method):
    """A doc_rules.json 'tests' entry may reference either the bare method
    name (e.g. "test_monthly_budget_short_month") or a full test id/substring
    of one — as a plain string (older schema) or as an object
    {"id": ..., "asserts": ...} (newer schema; see _rule_test_id). Match
    either way."""
    rule_test = _rule_test_id(rule_test)
    if not rule_test:
        return False
    if rule_test == actual_method:
        return True
    return rule_test in actual_test_id


def doc_rule_pass_matrix_from_expected(by_id, doc_rules):
    """Per doc_rules.json rule, compute {"passed": n, "total": n, "memory":
    str, "summary": str, "ok": bool} from score_against_expected_ids()'s
    `by_id` dict (expected_id -> {"status": ...}) instead of a raw
    parse_verbose_unittest_output() list -- so a doc_rules.json rule whose
    tests live in an import-failed module score those tests "failed"
    (status "import_error"/"missing" both count as not-passed) rather than
    silently reporting total=0/ok=None for that rule, the way the raw
    (test-results-only) doc_rule_pass_matrix() does when the module never
    produced an actual per-test result line at all.

    A doc_rules.json 'tests' entry (see _rule_test_id/_test_id_matches) is a
    bare method name or a test-id substring (e.g.
    "test_pivot_doc_fingerprint.TestFingerprintFormula.
    test_first_import_matches_expected_fingerprint", i.e.
    "<module>.<Class>.<method>" with no "_acceptance.<prefix>." lead-in) --
    matched here as a substring of the full expected id
    ("_acceptance.<prefix>.<module>.<Class>.<method>"), or an exact match of
    just the trailing method component. Pure."""
    out = {}
    for rule in doc_rules or []:
        rid = rule.get("id")
        if not rid:
            continue
        wanted = rule.get("tests") or []
        matched_ids = []
        for expected_id, result in (by_id or {}).items():
            method = expected_id.rsplit(".", 1)[-1]
            if any(_test_id_matches(w, expected_id, method) for w in wanted):
                matched_ids.append((expected_id, result))
        total = len(matched_ids)
        passed = sum(1 for _eid, r in matched_ids if r.get("status") == "ok")
        ok = (passed == total) if total > 0 else None
        out[rid] = {
            "passed": passed,
            "total": total,
            "memory": rule.get("memory"),
            "summary": rule.get("summary"),
            "ok": ok,
        }
    return out


def doc_rule_pass_matrix(test_results, doc_rules):
    """Per doc_rules.json rule, compute {"passed": n, "total": n, "memory":
    str} from the tests it references, by matching against
    parse_verbose_unittest_output()'s results. Returns
    {rule_id: {"passed": n, "total": n, "memory": str, "ok": bool}}.

    A rule with no matching tests found in test_results gets
    total=0/passed=0/ok=None (distinguishing "rule tests didn't run at all"
    from "rule tests ran and failed"). Pure."""
    by_method = {}
    for r in test_results or []:
        by_method.setdefault(r.get("method"), []).append(r)

    out = {}
    for rule in doc_rules or []:
        rid = rule.get("id")
        if not rid:
            continue
        wanted = rule.get("tests") or []
        matched = []
        for r in test_results or []:
            test_id = r.get("test_id") or ""
            method = r.get("method") or ""
            if any(_test_id_matches(w, test_id, method) for w in wanted):
                matched.append(r)
        total = len(matched)
        passed = sum(1 for r in matched if r.get("status") == "ok")
        ok = (passed == total) if total > 0 else None
        out[rid] = {
            "passed": passed,
            "total": total,
            "memory": rule.get("memory"),
            "summary": rule.get("summary"),
            "ok": ok,
        }
    return out
