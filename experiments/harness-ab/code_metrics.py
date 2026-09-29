#!/usr/bin/env python3
"""Code metrics for a run's work git repo: size (LOC added/deleted, files
touched) and shape (function length, docstring coverage, cyclomatic proxy)
of the code the agent wrote, plus how many tests it wrote and how its
total added size compares to the reference solution.

Stdlib only (subprocess for git, ast for Python parsing). Pure functions
operate on already-collected data (git numstat lines, file contents,
source text); the only I/O is in collect_code_metrics() and its git/file
helpers, kept separate and thin so the parsing/aggregation logic
(loc metrics from numstat lines, per-function ast metrics, docstring
coverage, cyclomatic proxy) is directly unit-testable without a real git
repo.

These are size/shape PROXIES, not quality judgments -- a short function
isn't necessarily a good one, and 100% docstring coverage doesn't mean the
docstrings are useful. report.py's Code section labels them as such.
"""
import ast
import os
import subprocess

# Directories/files never counted as "code the agent added/modified",
# regardless of arm: the acceptance-test harness itself, Serena's memory
# tree, and any stray ledger/data files an agent might have left in the
# repo root. Matched as a path-component prefix (see _is_excluded_path).
EXCLUDED_PATH_PREFIXES = ("_acceptance/", ".serena/")
EXCLUDED_EXACT_SUFFIXES = (".ledger.json",)


def _is_excluded_path(path):
    """True if `path` (git-numstat style, forward-slash, repo-relative)
    should be excluded from every code-metric count. Pure."""
    for prefix in EXCLUDED_PATH_PREFIXES:
        if path.startswith(prefix) or f"/{prefix}" in path:
            return True
    for suffix in EXCLUDED_EXACT_SUFFIXES:
        if path.endswith(suffix):
            return True
    return False


# --------------------------------------------------------------------------
# git numstat parsing (pure).
# --------------------------------------------------------------------------


def parse_numstat(text):
    """Parse `git diff --numstat` output into a list of (added, deleted,
    path) tuples. added/deleted are int, or None for a binary file (git
    prints '-' for both). Excluded paths (see _is_excluded_path) are
    dropped. Pure."""
    out = []
    for line in (text or "").splitlines():
        line = line.rstrip("\n")
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added_s, deleted_s, path = parts
        if _is_excluded_path(path):
            continue
        added = None if added_s == "-" else int(added_s)
        deleted = None if deleted_s == "-" else int(deleted_s)
        out.append((added, deleted, path))
    return out


def loc_summary(numstat_rows):
    """Aggregate parse_numstat() rows into {"loc_added", "loc_deleted",
    "files_added", "files_modified", "files_total", "paths"}.

    A file counts as "added" when its deleted count is 0 (heuristic for a
    brand-new file in a numstat diff against a single base commit -- git
    numstat doesn't itself distinguish add/modify/rename, but for a
    fixture->final diff with no renames this is exact: a genuinely new file
    has nothing to delete against the base). Binary files (added=None) are
    counted in files_total/paths but contribute 0 to loc_added/deleted.
    Pure."""
    loc_added = loc_deleted = 0
    files_added = files_modified = 0
    paths = []
    for added, deleted, path in numstat_rows:
        paths.append(path)
        loc_added += added or 0
        loc_deleted += deleted or 0
        if (deleted or 0) == 0 and (added or 0) > 0:
            files_added += 1
        else:
            files_modified += 1
    return {
        "loc_added": loc_added,
        "loc_deleted": loc_deleted,
        "files_added": files_added,
        "files_modified": files_modified,
        "files_total": len(paths),
        "paths": paths,
    }


# --------------------------------------------------------------------------
# AST metrics over Python source (pure: operates on (path, source_text)
# pairs handed in by the caller).
# --------------------------------------------------------------------------

_COMPLEXITY_NODE_TYPES = (
    ast.If, ast.For, ast.While, ast.ExceptHandler, ast.BoolOp,
    ast.comprehension,
)


def _function_length(node):
    """Line count of a function/method definition, end_lineno - lineno + 1.
    Pure. Falls back to 1 if end_lineno is unavailable (pre-3.8 ASTs;
    unreachable on any Python this project targets, kept defensive)."""
    end = getattr(node, "end_lineno", None) or node.lineno
    return end - node.lineno + 1


def _has_docstring(node):
    return ast.get_docstring(node) is not None


def _is_public(name):
    return not name.startswith("_") or (name.startswith("__") and name.endswith("__"))


def _complexity_proxy(node):
    """Count of if/for/while/except/bool-op/comprehension nodes within a
    function body -- a simple cyclomatic-complexity proxy, not a real
    McCabe count (doesn't handle match statements or walrus/ternary
    specially). Descent stops at nested function/class defs, whose own
    complexity is counted under their own node, not their parent's (plain
    ast.walk can't express that boundary since it doesn't stop descending,
    so this recurses manually via iter_child_nodes). Pure."""
    count = 0
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(child, _COMPLEXITY_NODE_TYPES):
            count += 1
        count += _complexity_proxy(child)
    return count


def analyze_python_source(path, source):
    """Parse one Python file's source and return per-function metrics:
    {"path": path, "functions": [{"name", "length", "has_docstring",
    "is_public", "complexity"}], "parse_error": bool}.

    Nested functions/methods are all included (flattened), each with its
    own length/docstring/complexity -- a method inside a class is walked
    too. parse_error is True (and functions == []) for source that fails
    to parse (e.g. a non-Python or malformed file the caller mistakenly
    included). Pure."""
    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, ValueError):
        return {"path": path, "functions": [], "parse_error": True}

    functions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append({
                "name": node.name,
                "length": _function_length(node),
                "has_docstring": _has_docstring(node),
                "is_public": _is_public(node.name),
                "complexity": _complexity_proxy(node),
            })
    return {"path": path, "functions": functions, "parse_error": False}


def aggregate_ast_metrics(file_analyses):
    """Combine analyze_python_source() results across files into overall
    shape metrics: {"function_count", "avg_function_length",
    "max_function_length", "docstring_coverage", "avg_complexity",
    "longest_file"}.

    docstring_coverage is computed over PUBLIC functions/methods only
    (fraction with a docstring), None when there are no public functions.
    longest_file is (path, function_count) for the file with the most
    functions (a simple "biggest" proxy), or None if no files. Pure."""
    all_funcs = []
    per_file_counts = {}
    for fa in file_analyses:
        per_file_counts[fa["path"]] = len(fa["functions"])
        all_funcs.extend(fa["functions"])

    if not all_funcs:
        return {
            "function_count": 0, "avg_function_length": None,
            "max_function_length": None, "docstring_coverage": None,
            "avg_complexity": None, "longest_file": None,
        }

    lengths = [f["length"] for f in all_funcs]
    public_funcs = [f for f in all_funcs if f["is_public"]]
    docstring_coverage = (
        sum(1 for f in public_funcs if f["has_docstring"]) / len(public_funcs)
        if public_funcs else None
    )
    complexities = [f["complexity"] for f in all_funcs]

    longest_file = None
    if per_file_counts:
        longest_path, longest_n = max(per_file_counts.items(), key=lambda kv: kv[1])
        if longest_n > 0:
            longest_file = (longest_path, longest_n)

    return {
        "function_count": len(all_funcs),
        "avg_function_length": sum(lengths) / len(lengths),
        "max_function_length": max(lengths),
        "docstring_coverage": docstring_coverage,
        "avg_complexity": sum(complexities) / len(complexities),
        "longest_file": longest_file,
    }


# --------------------------------------------------------------------------
# Agent-written test count (pure: operates on (path, source_text) pairs
# for files under a tests/ path the caller has already filtered to).
# --------------------------------------------------------------------------


def count_test_methods(file_analyses_or_sources):
    """Count `def test_*` methods across a set of test files. Accepts
    either analyze_python_source() results (uses their `functions` list,
    filtered to names starting with 'test_') or raw (path, source) pairs
    (parsed fresh). Pure."""
    total = 0
    for item in file_analyses_or_sources:
        if isinstance(item, dict) and "functions" in item:
            total += sum(1 for f in item["functions"] if f["name"].startswith("test_"))
        else:
            path, source = item
            fa = analyze_python_source(path, source)
            total += sum(1 for f in fa["functions"] if f["name"].startswith("test_"))
    return total


# --------------------------------------------------------------------------
# git I/O helpers (thin; the parsing above is what's tested directly).
# --------------------------------------------------------------------------


def _git(run_dir, *args):
    """Run a git subcommand in run_dir, returning stdout text ('' on any
    failure -- a missing commit, not a git repo, etc. are all treated as
    'no data' rather than raised, so a malformed/partial run directory
    degrades to empty metrics instead of crashing the whole report)."""
    try:
        result = subprocess.run(
            ["git", "-C", run_dir] + list(args),
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return ""
        return result.stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _identity_commit(run_dir):
    """The first commit reachable from HEAD (the fixture/identity commit
    every run's work repo starts from) -- `git log --reverse` first line.
    Returns None if unavailable."""
    out = _git(run_dir, "log", "--reverse", "--format=%H")
    lines = [l for l in out.splitlines() if l.strip()]
    return lines[0] if lines else None


def numstat_between(run_dir, base_ref, target_ref="HEAD"):
    """git diff --numstat base_ref..target_ref (target_ref defaults to the
    worktree's current HEAD/working state via plain 'diff', so uncommitted
    final-tree changes are included when target_ref == 'HEAD' and the
    worktree is dirty -- callers wanting the committed B1 tree instead pass
    an explicit commit for both). Returns [] if base_ref is falsy/missing."""
    if not base_ref:
        return []
    if target_ref == "HEAD":
        # Diff against the current worktree state (includes uncommitted
        # changes), matching "final tree" semantics for a live checkout.
        text = _git(run_dir, "diff", "--numstat", base_ref)
    else:
        text = _git(run_dir, "diff", "--numstat", base_ref, target_ref)
    return parse_numstat(text)


def _read_source(run_dir, path):
    full = os.path.join(run_dir, path)
    try:
        with open(full, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _agent_py_files(paths):
    return [p for p in paths if p.endswith(".py")]


def _reference_loc(task_paths):
    """Total non-test .py LOC under the task's reference_solution dirs
    (task1 + pivot, when present). task_paths is the {"reference_solution":
    ..., "pivot_reference_solution": ...} shape acceptance.py's task-path
    resolution produces (read-only import from run.py/acceptance.py path
    conventions, never those modules' behavior). Returns None if neither
    path exists."""
    total = 0
    found = False
    for key in ("reference_solution", "pivot_reference_solution"):
        root = task_paths.get(key) if task_paths else None
        if not root or not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                if os.sep + "tests" + os.sep in (dirpath + os.sep) or "/tests/" in dirpath.replace(os.sep, "/"):
                    continue
                full = os.path.join(dirpath, fn)
                try:
                    with open(full, encoding="utf-8", errors="replace") as f:
                        total += sum(1 for _ in f)
                    found = True
                except OSError:
                    continue
    return total if found else None


def collect_code_metrics(run_dir, task_paths=None):
    """Full code-metrics collection for one run's work git repo.

    run_dir: path to the run's `work/` git checkout (fixture commit -> B1
    commit -> final worktree, per the two-phase run layout).
    task_paths: optional {"reference_solution": path, "pivot_reference_solution":
    path} for the "size vs reference" percentage; omitted/None skips that
    figure (returns None for it) rather than raising.

    Returns {"identity_commit", "b1_commit",
    "fixture_to_final": {loc/files summary}, "fixture_to_b1": {...},
    "ast": {function_count/avg_function_length/... from aggregate_ast_metrics
    on the final tree's agent-added/modified .py files, non-test},
    "agent_test_count": int,
    "size_vs_reference_pct": float|None}.

    Never raises: a run_dir that isn't a git repo, has no commits, or is
    otherwise unreadable yields a metrics dict of mostly-None/0 values
    (each git/file helper degrades independently) rather than propagating
    an exception into report.py's rendering pass."""
    identity = _identity_commit(run_dir)
    # B1 (benchmark1) commit: second commit in log order, when present
    # (single-phase/no-pivot runs only have the identity commit, so this
    # is None there and fixture_to_b1 comes back empty).
    log_out = _git(run_dir, "log", "--reverse", "--format=%H")
    commits = [l for l in log_out.splitlines() if l.strip()]
    b1_commit = commits[1] if len(commits) > 1 else None

    final_rows = numstat_between(run_dir, identity, "HEAD")
    final_summary = loc_summary(final_rows)

    b1_rows = numstat_between(run_dir, identity, b1_commit) if b1_commit else []
    b1_summary = loc_summary(b1_rows)

    # AST metrics: every agent-added/modified non-test .py file, read from
    # the current (final) worktree state.
    py_paths = [p for p in final_summary["paths"] if p.endswith(".py")]
    non_test_py_paths = [
        p for p in py_paths
        if "/tests/" not in f"/{p}" and not os.path.basename(p).startswith("test_")
    ]
    test_py_paths = [p for p in py_paths if p not in non_test_py_paths]

    file_analyses = []
    for p in non_test_py_paths:
        source = _read_source(run_dir, p)
        if source is None:
            continue
        file_analyses.append(analyze_python_source(p, source))
    ast_metrics = aggregate_ast_metrics(file_analyses)

    test_analyses = []
    for p in test_py_paths:
        source = _read_source(run_dir, p)
        if source is None:
            continue
        test_analyses.append(analyze_python_source(p, source))
    agent_test_count = count_test_methods(test_analyses)

    non_test_loc_added = 0
    for added, deleted, path in final_rows:
        if path in non_test_py_paths:
            non_test_loc_added += added or 0
        elif not path.endswith(".py"):
            continue

    ref_loc = _reference_loc(task_paths) if task_paths else None
    size_vs_reference_pct = (
        100.0 * non_test_loc_added / ref_loc if (ref_loc and non_test_loc_added is not None) else None
    )

    return {
        "identity_commit": identity,
        "b1_commit": b1_commit,
        "fixture_to_final": final_summary,
        "fixture_to_b1": b1_summary,
        "ast": ast_metrics,
        "agent_test_count": agent_test_count,
        "non_test_loc_added": non_test_loc_added,
        "reference_loc": ref_loc,
        "size_vs_reference_pct": size_vs_reference_pct,
    }
