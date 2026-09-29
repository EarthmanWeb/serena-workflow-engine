#!/usr/bin/env python3
"""Map failed/errored doc-rule acceptance tests to their doc_rules.json
rule, and extract a short assertion snippet from the raw acceptance.*.txt
unittest output for each one.

Stdlib only. Pure functions, exercised directly by
tests/test_code_metrics.py's sibling test_harness_report.py (or its own
tests/test_failure_detail.py if present) -- no I/O beyond reading the files
callers hand in.

Used by report.py's "Explain failures" section (right after the Overall
review): for every doc-rule test a run's by_id marks not-ok, find which
rule (R*/P*) it belongs to (via doc_rules.json's tests[].id substring/
suffix match -- same matching rule as acceptance.py's
_test_id_matches/doc_rule_pass_matrix_from_expected, reimplemented here
read-only against a plain by_id dict rather than importing acceptance.py),
then pull that test's FAIL/ERROR block out of the acceptance.*.txt log and
reduce it to a short "expected vs actual" snippet.
"""
import os
import re


# --------------------------------------------------------------------------
# Rule matching (mirrors acceptance.py's _rule_test_id / _test_id_matches;
# reimplemented here so this module stays a read-only, dependency-free
# sibling of acceptance.py rather than importing it).
# --------------------------------------------------------------------------


def _rule_test_id(rule_test):
    """Normalize one doc_rules.json 'tests' entry (str or {"id":...} dict)
    to its bare id string. Pure."""
    if isinstance(rule_test, dict):
        return rule_test.get("id")
    return rule_test


def _test_id_matches(rule_test, actual_test_id, actual_method):
    """True if a doc_rules.json 'tests' entry refers to actual_test_id
    (exact method-name match, or substring of the full id). Pure."""
    rule_test = _rule_test_id(rule_test)
    if not rule_test:
        return False
    if rule_test == actual_method:
        return True
    return rule_test in actual_test_id


def rule_for_test_id(test_id, doc_rules):
    """Return the doc_rules.json rule dict ({"id","memory","summary",...})
    that owns `test_id`, or None if no rule references it. Pure."""
    method = test_id.rsplit(".", 1)[-1]
    for rule in doc_rules or []:
        wanted = rule.get("tests") or []
        if any(_test_id_matches(w, test_id, method) for w in wanted):
            return rule
    return None


def short_test_label(test_id):
    """Shorten a full expected-id ('_acceptance.pivot.test_x.TestY.test_z'
    or '_acceptance.test_x.TestY.test_z') to 'TestY.test_z'. Falls back to
    the bare method name for anything with fewer than 2 dotted segments.
    Pure."""
    parts = test_id.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return test_id


# --------------------------------------------------------------------------
# Failing-test discovery from a run's by_id map.
# --------------------------------------------------------------------------


def failed_doc_tests(by_id, doc_rules):
    """From a phase benchmark's by_id map ({test_id: {"status": ...}}), find
    every test that (a) maps to a doc_rules.json rule and (b) did not pass
    (status != "ok"), grouped by rule id.

    Returns {rule_id: {"rule": <rule dict>, "failed": [test_id, ...]}}
    ordered by first appearance of the rule in doc_rules (insertion order
    of the dict follows doc_rules order). A rule with zero failing tests is
    omitted entirely. Pure."""
    by_rule_id = {r.get("id"): r for r in (doc_rules or []) if r.get("id")}
    out = {}
    # Iterate doc_rules first so rule order in the result matches
    # doc_rules.json order (readable, stable across runs).
    for rule in doc_rules or []:
        rid = rule.get("id")
        if not rid:
            continue
        failed_ids = []
        for test_id, result in (by_id or {}).items():
            if not isinstance(result, dict):
                continue
            if result.get("status") == "ok":
                continue
            method = test_id.rsplit(".", 1)[-1]
            wanted = rule.get("tests") or []
            if any(_test_id_matches(w, test_id, method) for w in wanted):
                failed_ids.append(test_id)
        if failed_ids:
            out[rid] = {"rule": rule, "failed": sorted(failed_ids)}
    return out


def rule_totals(by_id, doc_rules):
    """{rule_id: (passed, total)} for every rule with >=1 matched test in
    by_id, from a phase's by_id map. Pure. Companion to failed_doc_tests --
    used to render 'x/y tests failed' per rule alongside the failure
    listing."""
    out = {}
    for rule in doc_rules or []:
        rid = rule.get("id")
        if not rid:
            continue
        wanted = rule.get("tests") or []
        passed = total = 0
        for test_id, result in (by_id or {}).items():
            if not isinstance(result, dict):
                continue
            method = test_id.rsplit(".", 1)[-1]
            if any(_test_id_matches(w, test_id, method) for w in wanted):
                total += 1
                if result.get("status") == "ok":
                    passed += 1
        if total:
            out[rid] = (passed, total)
    return out


# --------------------------------------------------------------------------
# Snippet extraction from a raw acceptance.*.txt unittest log.
# --------------------------------------------------------------------------

_BLOCK_HEADER_RE = re.compile(
    r"^(?P<kind>FAIL|ERROR): (?P<method>\S+) \((?P<full_id>[^)]+)\)\s*$"
)
_DIVIDER_RE = re.compile(r"^-{5,}$")
_BLOCK_SPLIT_RE = re.compile(r"^={5,}$")


def _iter_blocks(text):
    """Yield (kind, method, full_id, body_lines) for every FAIL:/ERROR:
    block in a unittest verbose-with-tracebacks log (the
    '====...\\nFAIL: name (full.id)\\n----...\\n<traceback/body>\\n' shape
    unittest's TextTestRunner produces). Pure (operates on `text` only)."""
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        if _BLOCK_SPLIT_RE.match(lines[i]):
            # Next non-blank line should be the FAIL:/ERROR: header.
            j = i + 1
            if j < n:
                m = _BLOCK_HEADER_RE.match(lines[j])
                if m:
                    k = j + 1
                    # Skip the '----' divider line.
                    if k < n and _DIVIDER_RE.match(lines[k]):
                        k += 1
                    body_start = k
                    body_end = body_start
                    while body_end < n and not _BLOCK_SPLIT_RE.match(lines[body_end]):
                        # Stop at the run-summary '----' divider (the one
                        # right before "Ran N tests ...") too, in case this
                        # is the log's last block and has no trailing '='.
                        if (_DIVIDER_RE.match(lines[body_end])
                                and body_end + 1 < n
                                and lines[body_end + 1].startswith("Ran ")):
                            break
                        body_end += 1
                    body = lines[body_start:body_end]
                    # Trim trailing blank lines from the body.
                    while body and not body[-1].strip():
                        body.pop()
                    yield m.group("kind"), m.group("method"), m.group("full_id"), body
                    i = body_end
                    continue
        i += 1


def parse_failure_blocks(text):
    """Parse a full acceptance.*.txt log into {full_test_id: {"kind":
    "FAIL"|"ERROR", "body": [str, ...]}}. Pure. full_test_id is the
    parenthesized id from the block header (e.g.
    '_acceptance.test_doc_audit_log.TestAuditLog.
    test_audit_log_count_reflects_entry_count_exact'), which matches the
    keys used in a phase's benchmark.by_id map."""
    out = {}
    for kind, _method, full_id, body in _iter_blocks(text or ""):
        out[full_id] = {"kind": kind, "body": body}
    return out


# Lines to skip entirely when building a snippet: traceback frame lines,
# the 'Traceback (most recent call last):' header, and blank lines.
_SKIP_LINE_RE = re.compile(r"^\s*(Traceback \(most recent call last\):|File \"|~+\^*~*$)")


def extract_snippet(body_lines, max_lines=3):
    """Reduce a FAIL/ERROR block's body to a <= max_lines snippet: prefer
    the AssertionError line and the '-'/'+' diff lines unittest emits right
    after it (expected vs actual); for an ImportError/other exception,
    fall back to the last non-frame line (the exception message itself).
    Pure. Returns a list of stripped strings, possibly empty."""
    lines = [ln for ln in body_lines if not _SKIP_LINE_RE.match(ln)]
    lines = [ln.rstrip() for ln in lines if ln.strip()]
    if not lines:
        return []

    # Prefer an AssertionError (or other "<Type>: ..." exception) line plus
    # any immediately-following '-'/'+' diff lines (assertEqual's multi-line
    # diff output), which together read as "expected vs actual".
    assert_idx = None
    for idx, ln in enumerate(lines):
        stripped = ln.strip()
        if re.match(r"^[A-Za-z_][A-Za-z0-9_.]*(Error|Exception):", stripped):
            assert_idx = idx
            break
    if assert_idx is not None:
        snippet = [lines[assert_idx].strip()]
        idx = assert_idx + 1
        while idx < len(lines) and len(snippet) < max_lines:
            stripped = lines[idx].strip()
            if stripped.startswith("-") or stripped.startswith("+"):
                snippet.append(stripped)
                idx += 1
            else:
                break
        return snippet[:max_lines]

    # No recognizable exception line (defensive fallback): last few
    # non-frame lines, which is usually the most informative tail.
    return lines[-max_lines:]


def _module_error_block(test_id, blocks):
    """Fall back to a whole-module collection-error block (unittest's
    'unittest.loader._FailedTest.<module>' entry, produced when a test
    module fails to import) for a test_id whose own per-test block doesn't
    exist -- true for every method in that module when the module-level
    ImportError prevented per-test execution (their by_id status is
    'import_error'/'missing', synthesized rather than run). Matches by
    module prefix: '_acceptance.pivot.test_x.TestY.test_z' ->
    '_acceptance.pivot.test_x'. Pure."""
    module = test_id.rsplit(".", 2)[0] if test_id.count(".") >= 2 else test_id
    key = f"unittest.loader._FailedTest.{module}"
    return blocks.get(key)


def failure_snippet_for(test_id, blocks):
    """Convenience: (kind, snippet_lines) for one test_id from a
    parse_failure_blocks() result, or (None, []) if no block (own or a
    module-level import error) can be found for it (e.g. an 'ok' test, or a
    log that didn't match the expected unittest verbose format).

    A test with no dedicated FAIL/ERROR block of its own (its module failed
    to import, so unittest never produced a per-test entry for it) falls
    back to that module's single collection-error block, so every failing
    doc-rule test still gets a snippet."""
    block = blocks.get(test_id) or _module_error_block(test_id, blocks)
    if not block:
        return None, []
    return block["kind"], extract_snippet(block["body"])


# --------------------------------------------------------------------------
# Per-arm rendering data: rule-grouped failures + shared-vs-harness-only
# split.
# --------------------------------------------------------------------------


def build_failure_report(by_id, doc_rules, acceptance_text):
    """Combine failed_doc_tests + rule_totals + snippet extraction into the
    per-arm data report.py's "Explain failures" section renders.

    Returns a list of {"rule_id", "memory", "summary", "failed_count",
    "total_count", "tests": [{"test_id", "label", "kind", "snippet"}]}
    ordered by doc_rules.json order. Pure w.r.t. its arguments (no I/O --
    callers read acceptance_text from disk themselves)."""
    failed = failed_doc_tests(by_id, doc_rules)
    totals = rule_totals(by_id, doc_rules)
    blocks = parse_failure_blocks(acceptance_text or "")

    out = []
    for rule in doc_rules or []:
        rid = rule.get("id")
        if rid not in failed:
            continue
        entry = failed[rid]
        passed, total = totals.get(rid, (0, 0))
        failed_count = total - passed
        tests = []
        for test_id in entry["failed"]:
            kind, snippet = failure_snippet_for(test_id, blocks)
            tests.append({
                "test_id": test_id,
                "label": short_test_label(test_id),
                "kind": kind or "FAIL",
                "snippet": snippet,
            })
        out.append({
            "rule_id": rid,
            "memory": rule.get("memory"),
            "summary": rule.get("summary"),
            "failed_count": failed_count,
            "total_count": total,
            "tests": tests,
        })
    return out


def shared_vs_harness_only(per_arm_failed_rule_ids, harness_arms, all_arms):
    """Given {arm: set(rule_id)} of rules with >=1 failing test per arm,
    compute the "shared failures" story: rules failed by every arm in
    `all_arms` (universal), vs rules failed ONLY by harness arms (i.e. an
    arm in `harness_arms`, not `all_arms - harness_arms`) and never by the
    non-harness arm(s).

    Returns {"shared": sorted[rule_id], "harness_only": sorted[rule_id]}.
    A rule_id lands in "harness_only" when every harness arm that has any
    failure data for it failed it, AND no non-harness arm failed it, AND
    at least one non-harness arm exists and ran that rule at all (i.e. the
    rule isn't simply absent from every arm's failure set). Pure."""
    all_arms = list(all_arms)
    harness_arms = set(harness_arms)
    non_harness_arms = [a for a in all_arms if a not in harness_arms]

    all_rule_ids = set()
    for s in per_arm_failed_rule_ids.values():
        all_rule_ids |= set(s)

    shared = set()
    harness_only = set()
    for rid in all_rule_ids:
        failed_by = {a for a in all_arms if rid in (per_arm_failed_rule_ids.get(a) or set())}
        if not failed_by:
            continue
        if failed_by == set(all_arms):
            shared.add(rid)
            continue
        if non_harness_arms and failed_by and failed_by <= harness_arms and not (failed_by & set(non_harness_arms)):
            harness_only.add(rid)

    return {"shared": sorted(shared), "harness_only": sorted(harness_only)}


def load_acceptance_text(run_dir, filename):
    """Read <run_dir>/<filename> (e.g. 'acceptance.task1.b1.txt'), or
    return '' if missing/unreadable. Thin I/O wrapper kept separate from
    the pure parsing functions above so tests never need real files."""
    path = os.path.join(run_dir, filename)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""
