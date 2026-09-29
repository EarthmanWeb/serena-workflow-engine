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
        if seg.startswith("test_spec_"):
            return "spec"
        if seg.startswith("test_doc_"):
            return "doc"
    return "other"


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
    {"id": str, "memory": str, "summary": str, "tests": [test_id, ...]}.
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


def _test_id_matches(rule_test, actual_test_id, actual_method):
    """A doc_rules.json 'tests' entry may reference either the bare method
    name (e.g. "test_monthly_budget_short_month") or a full test id/substring
    of one. Match either way."""
    if not rule_test:
        return False
    if rule_test == actual_method:
        return True
    return rule_test in actual_test_id


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
