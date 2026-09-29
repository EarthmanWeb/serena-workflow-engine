#!/usr/bin/env python3
"""Harness A/B results report: renders one self-contained HTML file comparing
all runs of the A/B/control experiment.

Usage:
    python3 experiments/harness-ab/report.py <results>/<stamp> [--out report.html] [--title ...]

Stdlib only. Reuses analyze.py's aggregate() (imported by path, read-only use)
for per-arm summary stats; this module additionally extracts the per-run rows
needed for charts (dot plots, token composition, tool mix, friction) that
aggregate() doesn't compute.

Pure/testable pieces (no I/O) are free functions, exercised directly by
tests/test_harness_report.py: linear_scale, nice_ticks, median, plus the
data-extraction helpers (rows_for_metric, tool_mix_rows, token_composition_rows,
friction_rows, compute_verdict) and the SVG-building functions.
"""
import argparse
import html as html_mod
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYZE_PATH = os.path.join(HERE, "analyze.py")
FAILURE_DETAIL_PATH = os.path.join(HERE, "failure_detail.py")
CODE_METRICS_PATH = os.path.join(HERE, "code_metrics.py")

# --------------------------------------------------------------------------
# Import analyze.py by path (read-only use of aggregate()).
# --------------------------------------------------------------------------


def _load_analyze():
    spec = importlib.util.spec_from_file_location("harness_ab_analyze", ANALYZE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_analyze = None


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_failure_detail = None
_code_metrics = None


def get_failure_detail():
    global _failure_detail
    if _failure_detail is None:
        _failure_detail = _load_module(FAILURE_DETAIL_PATH, "harness_ab_failure_detail")
    return _failure_detail


def get_code_metrics():
    global _code_metrics
    if _code_metrics is None:
        _code_metrics = _load_module(CODE_METRICS_PATH, "harness_ab_code_metrics")
    return _code_metrics


def get_analyze():
    global _analyze
    if _analyze is None:
        _analyze = _load_analyze()
    return _analyze


# --------------------------------------------------------------------------
# Arms / palette (validated: node scripts/validate_palette.js — see report; PASS
# in both modes on the first three slots of the dataviz skill's default
# categorical palette, all-pairs).
# --------------------------------------------------------------------------

# Arm colors: blue / orange / green (no aqua/teal/cyan). Green is a re-stepped
# slot within the default palette's green hue family (not the documented-default
# #008300 step, which FAILs CVD separation vs orange under protanopia at
# --pairs all) — light #006300 / dark #008f00 both clear every hard gate;
# dark clears CVD in the 6-8 WARN band vs orange (ΔE 6.3), which is legal only
# with secondary encoding (direct row labels + legend + tooltip + table
# fallback, all present on every chart here). See report.py's docstring at
# the bottom of this file / task report for full validator output.
ARM_ORDER = ["baseline", "v5", "control"]
ARM_LABELS = {
    "baseline": "baseline (SWE v1.2.82)",
    "v5": "v5 (SWE prototype)",
    "control": "control (no plugin)",
}
ARM_COLOR_LIGHT = {"baseline": "#2a78d6", "v5": "#eb6834", "control": "#006300"}
ARM_COLOR_DARK = {"baseline": "#3987e5", "v5": "#d95926", "control": "#008f00"}

# Sequential (neutral-ish blue ramp) for token composition, NOT the arm colors.
COMPOSITION_LIGHT = {
    "input": "#cde2fb",
    "output": "#6da7ec",
    "cache_creation": "#2a78d6",
    "cache_read": "#104281",
}
COMPOSITION_DARK = {
    "input": "#9ec5f4",
    "output": "#5598e7",
    "cache_creation": "#3987e5",
    "cache_read": "#184f95",
}

TOOL_TOP_N = 8

# --------------------------------------------------------------------------
# Pure math helpers (tested directly).
# --------------------------------------------------------------------------


def linear_scale(domain, rng):
    """Return a function mapping a value in `domain` (lo, hi) linearly to
    `rng` (lo, hi). Degenerate domain (lo == hi) maps everything to the
    midpoint of rng."""
    d0, d1 = domain
    r0, r1 = rng

    if d1 == d0:
        mid = (r0 + r1) / 2.0

        def _scale_const(_v):
            return mid

        return _scale_const

    def _scale(v):
        t = (v - d0) / (d1 - d0)
        return r0 + t * (r1 - r0)

    return _scale


def nice_ticks(lo, hi, n=5):
    """Return a list of 'nice' tick values spanning at least [lo, hi],
    approximately n ticks. Pure. Handles lo == hi and lo > hi defensively."""
    if lo is None or hi is None:
        return [0]
    if hi < lo:
        lo, hi = hi, lo
    if hi == lo:
        if hi == 0:
            return [0, 1]
        step = _nice_num(abs(hi) / max(n - 1, 1), round_=True)
        base = _nice_num(hi, round_=False)
        lo, hi = 0, base if base > 0 else 1
    span = hi - lo
    if span <= 0:
        span = 1
    raw_step = span / max(n - 1, 1)
    step = _nice_num(raw_step, round_=True)
    if step <= 0:
        step = 1
    nice_lo = 0 if lo >= 0 else -(((-lo) // step + 1) * step)
    nice_lo = min(nice_lo, (lo // step) * step)
    ticks = []
    t = (lo // step) * step
    # start at or below lo, step until >= hi
    t = 0 if lo >= 0 else t
    while t < lo:
        t += step
    if t > lo:
        t -= step
    vals = []
    cur = t
    guard = 0
    while cur <= hi + step * 0.5 and guard < 1000:
        vals.append(round(cur, 10))
        cur += step
        guard += 1
    if not vals:
        vals = [lo, hi]
    return vals


def _nice_num(x, round_=True):
    if x <= 0:
        return 1
    exp = int(_floor_log10(x))
    frac = x / (10 ** exp)
    if round_:
        if frac < 1.5:
            nf = 1
        elif frac < 3:
            nf = 2
        elif frac < 7:
            nf = 5
        else:
            nf = 10
    else:
        if frac <= 1:
            nf = 1
        elif frac <= 2:
            nf = 2
        elif frac <= 5:
            nf = 5
        else:
            nf = 10
    return nf * (10 ** exp)


def _floor_log10(x):
    import math
    return math.floor(math.log10(x))


def median(values):
    values = sorted(v for v in values if v is not None)
    n = len(values)
    if n == 0:
        return None
    mid = n // 2
    if n % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


# --------------------------------------------------------------------------
# Data loading / extraction.
# --------------------------------------------------------------------------


def load_meta(stamp_dir):
    path = os.path.join(stamp_dir, "meta.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def load_rows(stamp_dir):
    analyze = get_analyze()
    return analyze.load_runs(stamp_dir)


def g(d, *path, default=None):
    """Safe nested-get: g(row, 'metrics', 'usage', 'input_tokens')."""
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur if cur is not None else default


def _tool_calls(r):
    """total_tool_calls is current; fall back to the old ambiguous
    `tool_calls` key for pre-fix rows."""
    m = g(r, "metrics", default={}) or {}
    if "total_tool_calls" in m:
        return m.get("total_tool_calls")
    return m.get("tool_calls")


METRIC_DOT_SPECS = [
    # Primary turns metric: assistant_turns_incl_subagents (main + every
    # subagent). num_turns (main-agent only) is kept as a secondary/
    # diagnostic dot chart right after it — see run.parse_transcript's
    # docstring for why num_turns alone can be misleadingly low on a
    # subagent-delegating run.
    ("assistant_turns_incl_subagents", "Turns (all agents)", lambda r: g(r, "metrics", "assistant_turns_incl_subagents")),
    ("num_turns", "Turns (main-agent only)", lambda r: g(r, "metrics", "num_turns")),
    ("total_tokens", "Total tokens", lambda r: g(r, "metrics", "total_tokens")),
    ("output_tokens", "Output tokens", lambda r: g(r, "metrics", "usage", "output_tokens")),
    ("wall_s", "Wall time (s)", lambda r: r.get("wall_s")),
    ("tool_calls", "Tool calls", _tool_calls),
    ("memory_file_reads", "Memory consultations", lambda r: g(r, "metrics", "memory_file_reads")),
]


def rows_for_metric(rows, getter):
    """Extract (arm, trial, value) triples for one metric across all runs,
    dropping rows with a missing value for that metric. Pure."""
    out = []
    for r in rows:
        arm = r.get("arm")
        if arm not in ARM_ORDER:
            continue
        v = getter(r)
        if isinstance(v, (int, float)):
            out.append((arm, r.get("trial"), float(v)))
    return out


def token_composition_rows(rows):
    """Per run: (run_id, arm, trial, {input, output, cache_creation, cache_read})."""
    out = []
    for r in rows:
        arm = r.get("arm")
        if arm not in ARM_ORDER:
            continue
        usage = g(r, "metrics", "usage", default={}) or {}
        parts = {
            "input": usage.get("input_tokens") or 0,
            "output": usage.get("output_tokens") or 0,
            "cache_creation": usage.get("cache_creation_input_tokens") or 0,
            "cache_read": usage.get("cache_read_input_tokens") or 0,
        }
        out.append((r.get("run_id") or f"{arm}-t{r.get('trial')}", arm, r.get("trial"), parts))
    return out


def acceptance_rows(rows):
    out = []
    for r in rows:
        arm = r.get("arm")
        if arm not in ARM_ORDER:
            continue
        acc = r.get("acceptance") or {}
        total = acc.get("total") or 0
        passed = acc.get("passed") or 0
        pct = (100.0 * passed / total) if total else 0.0
        reg = r.get("regression") or {}
        out.append({
            "run_id": r.get("run_id") or f"{arm}-t{r.get('trial')}",
            "arm": arm,
            "trial": r.get("trial"),
            "passed": passed,
            "total": total,
            "pct": pct,
            "acc_ok": acc.get("ok"),
            "reg_ok": reg.get("ok"),
        })
    return out


def friction_rows(rows):
    out = []
    for r in rows:
        arm = r.get("arm")
        if arm not in ARM_ORDER:
            continue
        out.append({
            "run_id": r.get("run_id") or f"{arm}-t{r.get('trial')}",
            "arm": arm,
            "trial": r.get("trial"),
            "hook_denials": g(r, "metrics", "hook_denials", default=0) or 0,
            "stop_hook_blocks": g(r, "metrics", "stop_hook_blocks", default=0) or 0,
        })
    return out


def stream_event_table(rows, top_n=6):
    """Per plugin arm, top-N stream event type counts. Returns
    {arm: [(event_type, count), ...]} sorted desc, plugin arms only."""
    totals = {}
    for r in rows:
        arm = r.get("arm")
        if arm not in ("baseline", "v5"):
            continue
        counts = g(r, "stream_metrics", "stream_event_counts", default={}) or {}
        d = totals.setdefault(arm, {})
        for k, v in counts.items():
            if isinstance(v, (int, float)):
                d[k] = d.get(k, 0) + v
    out = {}
    for arm, counts in totals.items():
        items = sorted(counts.items(), key=lambda kv: -kv[1])[:top_n]
        out[arm] = items
    return out


def tool_mix_rows(rows, top_n=TOOL_TOP_N):
    """Per arm, aggregate tool_calls_by_name across runs; fold the tail past
    top_n into 'Other'. Returns (tool_order, {arm: {tool: count}})."""
    totals = {}
    for r in rows:
        arm = r.get("arm")
        if arm not in ARM_ORDER:
            continue
        by_name = g(r, "metrics", "tool_calls_by_name", default={}) or {}
        d = totals.setdefault(arm, {})
        for k, v in by_name.items():
            if isinstance(v, (int, float)):
                d[k] = d.get(k, 0) + v

    grand = {}
    for arm, d in totals.items():
        for k, v in d.items():
            grand[k] = grand.get(k, 0) + v
    ranked = sorted(grand.items(), key=lambda kv: -kv[1])
    top_tools = [k for k, _ in ranked[:top_n]]

    per_arm = {}
    for arm in ARM_ORDER:
        d = totals.get(arm, {})
        row = {t: d.get(t, 0) for t in top_tools}
        other = sum(v for k, v in d.items() if k not in top_tools)
        row["Other"] = other
        per_arm[arm] = row

    tool_order = top_tools + (["Other"] if any(per_arm[a].get("Other") for a in ARM_ORDER) or True else [])
    return tool_order, per_arm


def spec_doc_bar_rows(rows):
    """Per arm: {"spec": pct|None, "doc": pct|None} mean pass rate, for the
    grouped spec-vs-doc bar chart. Pure."""
    analyze = get_analyze()
    stats = analyze.spec_doc_pass_stats(rows)
    out = {}
    for arm in ARM_ORDER:
        s = stats.get(arm, {})
        out[arm] = {
            "spec": s.get("spec_pass_pct_mean"),
            "doc": s.get("doc_pass_pct_mean"),
        }
    return out


def doc_rule_heatmap_rows(rows):
    """(rule_ids, {(arm, run_id): {rule_id: bool|None}}) for the arm-run x
    doc-rule heatmap. bool is the per-run per-rule pass/fail (rule_result
    "ok"); None means that rule had no tests recorded for that run (task has
    no doc_rules, or an older row predating the field). Pure."""
    rule_ids = set()
    per_cell = {}
    for r in rows:
        arm = r.get("arm")
        if arm not in ARM_ORDER:
            continue
        run_id = r.get("run_id") or f"{arm}-t{r.get('trial')}"
        acc = r.get("acceptance") or {}
        doc_rules = acc.get("doc_rules") or {}
        if not isinstance(doc_rules, dict) or not doc_rules:
            continue
        cell = per_cell.setdefault((arm, run_id), {})
        for rule_id, rule_result in doc_rules.items():
            if not isinstance(rule_result, dict):
                continue
            rule_ids.add(rule_id)
            cell[rule_id] = rule_result.get("ok")
    return sorted(rule_ids), per_cell


def gate_conformance_rows(rows):
    """Per run: gate-conformance table row (init/sweep/edits-before-sweep/
    doc-rule-coverage), for the conformance table chart. Pure."""
    out = []
    for r in rows:
        arm = r.get("arm")
        if arm not in ARM_ORDER:
            continue
        gates = r.get("gates") or {}
        out.append({
            "run_id": r.get("run_id") or f"{arm}-t{r.get('trial')}",
            "arm": arm,
            "trial": r.get("trial"),
            "has_gates": isinstance(r.get("gates"), dict),
            "init_chain_complete": gates.get("init_chain_complete"),
            "sweep_verified": gates.get("sweep_verified"),
            "edits_before_sweep": gates.get("edits_before_sweep"),
            "doc_rule_memories_coverage": gates.get("doc_rule_memories_coverage"),
            "memories_read_channel": gates.get("memories_read_channel"),
        })
    return out


def memory_coverage_rows(rows):
    """Per run: (arm, trial, n_memories_read, doc_rule_coverage) for the
    memory-coverage dot plot. Pure."""
    out = []
    for r in rows:
        arm = r.get("arm")
        if arm not in ARM_ORDER:
            continue
        gates = r.get("gates") or {}
        memories_read = gates.get("memories_read") or []
        out.append({
            "run_id": r.get("run_id") or f"{arm}-t{r.get('trial')}",
            "arm": arm,
            "trial": r.get("trial"),
            "n_memories_read": len(memories_read) if isinstance(memories_read, list) else 0,
            "doc_rule_memories_coverage": gates.get("doc_rule_memories_coverage"),
            "channel": gates.get("memories_read_channel"),
        })
    return out


# --------------------------------------------------------------------------
# Two-phase (pivot) data extraction.
#
# A pivot row carries phases.task1.{metrics,benchmark,gates} and
# phases.pivot.{metrics,benchmark,gates,task1_retention} (see run.py's
# run_one_pivot / analyze.py's pivot_benchmark_stats+pivot_gate_stats
# docstrings for the exact field names this reads). A single-phase row (or
# one from a task with no pivot/) has no "phases" key at all and is
# excluded from every function below rather than treated as zero data.
# --------------------------------------------------------------------------


def has_phase_rows(rows):
    """True iff at least one row in `rows` is two-phase (carries a
    `phases` dict with both task1 and pivot). Pure."""
    return any(isinstance(r.get("phases"), dict) and "task1" in r["phases"] and "pivot" in r["phases"]
               for r in rows)


def _phase_benchmark_pct(benchmark, category):
    """Pass % (0-100) for one acceptance category on a
    phases.<phase>.benchmark dict, or None when that category recorded no
    tests. Pure."""
    if not isinstance(benchmark, dict):
        return None
    cat = benchmark.get(category) or {}
    total = cat.get("total") or 0
    if not total:
        return None
    return 100.0 * (cat.get("passed") or 0) / total


def phase_benchmark_rows(rows):
    """Per two-phase run: {"run_id", "arm", "trial", "b1": {"spec","doc",
    "success_x_n","doc_rules"}, "b2": {...same..., "retention": {"passed",
    "total","regressions"}}}. Non-pivot rows are excluded. Pure."""
    out = []
    for r in rows:
        arm = r.get("arm")
        if arm not in ARM_ORDER:
            continue
        phases = r.get("phases")
        if not isinstance(phases, dict) or "task1" not in phases or "pivot" not in phases:
            continue
        t1 = phases.get("task1") or {}
        pv = phases.get("pivot") or {}
        b1 = t1.get("benchmark") or {}
        b2 = pv.get("benchmark") or {}
        retention = pv.get("task1_retention") or {}

        def _success_x_n(b):
            total = b.get("total") or 0
            passed = b.get("passed") or 0
            return f"{passed}/{total}" if total else None

        out.append({
            "run_id": r.get("run_id") or f"{arm}-t{r.get('trial')}",
            "arm": arm,
            "trial": r.get("trial"),
            "b1": {
                "spec": _phase_benchmark_pct(b1, "spec"),
                "doc": _phase_benchmark_pct(b1, "doc"),
                "success_x_n": _success_x_n(b1),
                "ok": bool(b1.get("ok")) if b1.get("total") else None,
                "doc_rules": b1.get("doc_rules") or {},
            },
            "b2": {
                "spec": _phase_benchmark_pct(b2, "spec"),
                "doc": _phase_benchmark_pct(b2, "doc"),
                "success_x_n": _success_x_n(b2),
                "ok": bool(b2.get("ok")) if b2.get("total") else None,
                "doc_rules": b2.get("doc_rules") or {},
                "retention": {
                    "passed": retention.get("passed"),
                    "total": retention.get("total"),
                    "regressions": retention.get("regressions") or [],
                },
            },
        })
    return out


def two_phase_scorecard_data(agg):
    """Per-arm Benchmark 1 / Benchmark 2 scorecard values (doc-rule pass %,
    spec pass %, full success x/n, plus B2's task-1 retention x/n), pulled
    from analyze.pivot_benchmark_stats() output. Pure.

    Returns {"arms_present": [...], "b1": {arm: {...}}, "b2": {arm: {...}}}
    — empty dict for an arm with no pivot rows (n_pivot == 0) rather than
    zeros, so the caller can render "not measured" instead of "0%"."""
    pivot_bench = agg.get("pivot_benchmarks") or {}
    present = [a for a in ARM_ORDER if (pivot_bench.get(a) or {}).get("n_pivot")]

    b1_out, b2_out = {}, {}
    for arm in present:
        pb = pivot_bench[arm]
        n = pb["n_pivot"]
        b1 = pb["b1"]
        b2 = pb["b2"]
        ret = pb["task1_retention"]
        b1_out[arm] = {
            "doc_pass_pct": b1.get("doc_pass_pct_mean"),
            "spec_pass_pct": b1.get("spec_pass_pct_mean"),
            "success_rate": b1.get("success_rate"),
            "success_x_n": (f"{round(b1['success_rate'] * n)}/{n}" if b1.get("success_rate") is not None else None),
        }
        b2_out[arm] = {
            "doc_pass_pct": b2.get("doc_pass_pct_mean"),
            "spec_pass_pct": b2.get("spec_pass_pct_mean"),
            "success_rate": b2.get("success_rate"),
            "success_x_n": (f"{round(b2['success_rate'] * n)}/{n}" if b2.get("success_rate") is not None else None),
            "retention_rate": ret.get("rate_mean"),
            "retention_regressions": ret.get("total_regressions"),
        }
    return {"arms_present": present, "b1": b1_out, "b2": b2_out}


def pivot_gate_matrix_rows(rows):
    """Per two-phase run: task1 gate checks + pivot gate checks, for the
    combined task-1/pivot gate-conformance ✓/✗ matrix. Pure. Non-pivot rows
    excluded."""
    out = []
    for r in rows:
        arm = r.get("arm")
        if arm not in ARM_ORDER:
            continue
        phases = r.get("phases")
        if not isinstance(phases, dict) or "task1" not in phases or "pivot" not in phases:
            continue
        t1_gates = (phases.get("task1") or {}).get("gates") or {}
        pv_gates = (phases.get("pivot") or {}).get("gates") or {}
        reclass = pv_gates.get("pivot_reclassified") or {}
        out.append({
            "run_id": r.get("run_id") or f"{arm}-t{r.get('trial')}",
            "arm": arm,
            "trial": r.get("trial"),
            "t1_init_chain_complete": t1_gates.get("init_chain_complete"),
            "t1_sweep_verified": t1_gates.get("sweep_verified"),
            "t1_edits_before_sweep": t1_gates.get("edits_before_sweep"),
            "pivot_reclassified_attempted": reclass.get("attempted"),
            "pivot_reclassified_succeeded": reclass.get("succeeded"),
            "pivot_resweep_verified": pv_gates.get("pivot_resweep_verified"),
            "pivot_edits_before_sweep": pv_gates.get("pivot_edits_before_sweep"),
            "pivot_doc_rule_memories_coverage": pv_gates.get("pivot_doc_rule_memories_coverage"),
        })
    return out


def _load_run_module():
    """Import run.py by path (read-only use of parse_transcript()), same
    pattern as _load_analyze(). Never invokes `claude -p` or any subprocess
    -- parse_transcript is a pure lines-in/dict-out parser."""
    run_path = os.path.join(HERE, "run.py")
    spec = importlib.util.spec_from_file_location("harness_ab_run", run_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_run_mod = None


def _get_run_mod():
    global _run_mod
    if _run_mod is None:
        _run_mod = _load_run_module()
    return _run_mod


def _phase_tokens_from_transcript(stamp_dir, run_id, phase):
    """Fallback for a pivot row whose phases.<phase>.metrics is missing/
    empty (e.g. a stamp that was --rescore'd, which only recomputes
    acceptance, not per-phase metrics -- see run.py's _reparse_pivot_row
    docstring for the --reparse path that would normally populate this).
    Re-derives total_tokens for one phase by parsing
    <stamp_dir>/runs/<run_id>/transcript.<phase>.jsonl with run.py's own
    parse_transcript(), the same authoritative all-models-incl-subagents
    total used everywhere else in this report. Returns None (not 0) when
    stamp_dir is unavailable or the transcript file doesn't exist, so the
    caller can distinguish "couldn't recover" from "genuinely zero"."""
    if not stamp_dir or not run_id:
        return None
    path = os.path.join(stamp_dir, "runs", run_id, f"transcript.{phase}.jsonl")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            lines = f.readlines()
        run_mod = _get_run_mod()
        metrics = run_mod.parse_transcript(lines)
        return metrics.get("total_tokens")
    except Exception:
        return None


def phase_cost_stack_rows(rows, stamp_dir=None):
    """Per two-phase run: (run_id, arm, trial, {"task1": tokens, "pivot":
    tokens}) for the phase-stacked token cost chart. Pure w.r.t. `rows`;
    `stamp_dir`, when given, is used ONLY as a fallback to recover tokens
    by re-parsing the phase transcripts when phases.<phase>.metrics.
    total_tokens is missing (see _phase_tokens_from_transcript) -- a stamp
    with populated phase metrics never touches disk here. Non-pivot rows
    excluded."""
    out = []
    for r in rows:
        arm = r.get("arm")
        if arm not in ARM_ORDER:
            continue
        phases = r.get("phases")
        if not isinstance(phases, dict) or "task1" not in phases or "pivot" not in phases:
            continue
        run_id = r.get("run_id") or f"{arm}-t{r.get('trial')}"
        t1_tok = g(phases, "task1", "metrics", "total_tokens")
        if not t1_tok:
            t1_tok = _phase_tokens_from_transcript(stamp_dir, run_id, "task1") or 0
        pv_tok = g(phases, "pivot", "metrics", "total_tokens")
        if not pv_tok:
            pv_tok = _phase_tokens_from_transcript(stamp_dir, run_id, "pivot") or 0
        out.append((
            run_id, arm, r.get("trial"),
            {"task1": t1_tok, "pivot": pv_tok},
        ))
    return out


def two_phase_doc_rule_heatmap_rows(rows, phase, benchmark_key="doc_rules"):
    """(rule_ids, {(arm, run_id): {rule_id: bool|None}}) for one benchmark's
    doc-rule heatmap (phase == "b1" or "b2"), reading
    phase_benchmark_rows()-shaped per-run b1/b2 dicts. Pure."""
    rule_ids = set()
    per_cell = {}
    for pr in phase_benchmark_rows(rows):
        key = (pr["arm"], pr["run_id"])
        doc_rules = pr[phase].get(benchmark_key) or {}
        if not isinstance(doc_rules, dict) or not doc_rules:
            continue
        cell = per_cell.setdefault(key, {})
        for rule_id, rule_result in doc_rules.items():
            if not isinstance(rule_result, dict):
                continue
            rule_ids.add(rule_id)
            cell[rule_id] = rule_result.get("ok")
    return sorted(rule_ids), per_cell


# --------------------------------------------------------------------------
# Overall review (top-of-report single comparison block).
#
# Replaces the old auto-generated multi-sentence verdict paragraph: one
# plain non-contradictory sentence + one comparison table with raw x/y
# counts, grouped under Correctness / Process / Efficiency. Reads only
# `rows` (per-run dicts) plus a couple of aggregate() fields (gate rates),
# never phases.*.metrics directly for tokens -- those go through
# phase_cost_stack_rows() so the transcript-fallback recovery (see
# _phase_tokens_from_transcript) benefits this table too.
# --------------------------------------------------------------------------


def _xy(passed, total):
    """('x/y', pct|None) for a passed/total pair. None total -> ('—', None)."""
    if not total:
        return "—", None
    return f"{passed}/{total}", 100.0 * passed / total


def strict_best_arm(values, higher_is_better=True):
    """Pick the single strict-winner arm from {arm: value|None}, or None
    when there is no data, a tie among the best values, or every present
    value is zero (a 0/1 "success" tie across every arm is not a winner —
    see the Overall review's 'never tag ties/all-zero rows' rule). Pure.

    values with None are ignored entirely (not counted as 0, not counted
    as a candidate)."""
    present = {a: v for a, v in values.items() if v is not None}
    if not present:
        return None
    if all(v == 0 for v in present.values()):
        return None
    best_val = max(present.values()) if higher_is_better else min(present.values())
    winners = [a for a, v in present.items() if v == best_val]
    if len(winners) != 1:
        return None
    return winners[0]


def overall_review_rows(rows, agg, stamp_dir=None):
    """Per-arm data for the Overall review comparison table + its one-line
    verdict. Pure w.r.t. `rows`/`agg`; `stamp_dir` only feeds the phase
    token fallback (see phase_cost_stack_rows). Returns:

    {"arms_present": [...], "n_per_arm": {arm: n}, "has_pivot": bool,
     "cells": {arm: {
        "t1_spec": (x/y str, pct|None), "t1_doc": (...), "pv_spec": (...),
        "pv_doc": (...), "all_doc": (...), "t1_retention": (...),
        "read_all_memories_pct": float|None,
        "gates": {"t1_init": bool|None, "t1_sweep": bool|None,
                  "pv_resweep": bool|None},
        "total_tokens": float|None, "turns": float|None, "wall_s": float|None,
        "tool_calls": float|None, "memory_reads": float|None,
        "vs_no_harness": {"tokens_pct": float|None, "turns_pct": float|None,
                           "wall_pct": float|None},
     }}}

    Values are summed (not averaged) across an arm's runs, matching the
    "show raw counts x/y everywhere" requirement -- with n=1/arm in the
    current data this is identical to that one run's numbers, but stays
    correct if n grows."""
    by_arm = {}
    for r in rows:
        arm = r.get("arm")
        if arm not in ARM_ORDER:
            continue
        by_arm.setdefault(arm, []).append(r)
    present = [a for a in ARM_ORDER if a in by_arm]
    has_pivot = has_phase_rows(rows)

    phase_tok_by_run = {}
    if has_pivot:
        for (run_id, arm, trial, parts) in phase_cost_stack_rows(rows, stamp_dir=stamp_dir):
            phase_tok_by_run[run_id] = parts

    cells = {}
    for arm in present:
        arm_rows = by_arm[arm]
        n = len(arm_rows)

        t1_spec_p = t1_spec_t = t1_doc_p = t1_doc_t = 0
        pv_spec_p = pv_spec_t = pv_doc_p = pv_doc_t = 0
        ret_p = ret_t = 0
        any_phase = False
        for r in arm_rows:
            phases = r.get("phases")
            if not isinstance(phases, dict) or "task1" not in phases or "pivot" not in phases:
                continue
            any_phase = True
            b1 = (phases.get("task1") or {}).get("benchmark") or {}
            b2 = (phases.get("pivot") or {}).get("benchmark") or {}
            ret = (phases.get("pivot") or {}).get("task1_retention") or {}
            t1_spec_p += (b1.get("spec") or {}).get("passed") or 0
            t1_spec_t += (b1.get("spec") or {}).get("total") or 0
            t1_doc_p += (b1.get("doc") or {}).get("passed") or 0
            t1_doc_t += (b1.get("doc") or {}).get("total") or 0
            pv_spec_p += (b2.get("spec") or {}).get("passed") or 0
            pv_spec_t += (b2.get("spec") or {}).get("total") or 0
            pv_doc_p += (b2.get("doc") or {}).get("passed") or 0
            pv_doc_t += (b2.get("doc") or {}).get("total") or 0
            ret_p += ret.get("passed") or 0
            ret_t += ret.get("total") or 0

        # gate rates: strict boolean AND across an arm's runs (all must
        # pass for the arm-level glyph to read yes); None when no run in
        # this arm carries that gate at all (e.g. control has no phases).
        def _gate_all(getter):
            vals = [getter(r) for r in arm_rows if any_phase]
            vals = [v for v in vals if isinstance(v, bool)]
            if not vals:
                return None
            return all(vals)

        t1_init = _gate_all(lambda r: g(r, "phases", "task1", "gates", "init_chain_complete"))
        t1_sweep = _gate_all(lambda r: g(r, "phases", "task1", "gates", "sweep_verified"))
        pv_resweep = _gate_all(lambda r: g(r, "phases", "pivot", "gates", "pivot_resweep_verified"))

        # read-all-rule-memories coverage: mean of doc_rule_memories_coverage
        # (pivot-phase gates, i.e. the run's final/combined coverage) across
        # this arm's runs; None when not recorded for any run.
        cov_vals = [g(r, "gates", "doc_rule_memories_coverage") for r in arm_rows]
        cov_vals = [v for v in cov_vals if isinstance(v, (int, float))]
        read_all_pct = (100.0 * sum(cov_vals) / len(cov_vals)) if cov_vals else None

        total_tokens = sum(g(r, "metrics", "total_tokens") or 0 for r in arm_rows) or None
        turns = sum(g(r, "metrics", "assistant_turns_incl_subagents") or 0 for r in arm_rows) or None
        wall_s = sum(r.get("wall_s") or 0 for r in arm_rows) or None
        tool_calls = sum(_tool_calls(r) or 0 for r in arm_rows) or None
        memory_reads = sum(g(r, "metrics", "memory_file_reads") or 0 for r in arm_rows) or None

        cells[arm] = {
            "n": n,
            "t1_spec": _xy(t1_spec_p, t1_spec_t),
            "t1_doc": _xy(t1_doc_p, t1_doc_t),
            "pv_spec": _xy(pv_spec_p, pv_spec_t),
            "pv_doc": _xy(pv_doc_p, pv_doc_t),
            "all_doc": _xy(t1_doc_p + pv_doc_p, t1_doc_t + pv_doc_t),
            "t1_retention": _xy(ret_p, ret_t),
            "has_pivot_rows": any_phase,
            "read_all_memories_pct": read_all_pct,
            "gates": {"t1_init": t1_init, "t1_sweep": t1_sweep, "pv_resweep": pv_resweep},
            "total_tokens": total_tokens,
            "turns": turns,
            "wall_s": wall_s,
            "tool_calls": tool_calls,
            "memory_reads": memory_reads,
        }

    control_arm = "control" if "control" in present else None
    ctrl = cells.get(control_arm) if control_arm else None
    for arm in present:
        c = cells[arm]
        vs = {"tokens_pct": None, "turns_pct": None, "wall_pct": None}
        if ctrl and arm != control_arm:
            for key, ck in (("tokens_pct", "total_tokens"), ("turns_pct", "turns"), ("wall_pct", "wall_s")):
                v, cv = c.get(ck), ctrl.get(ck)
                if v is not None and cv:
                    vs[key] = 100.0 * (v - cv) / cv
        c["vs_no_harness"] = vs

    n_per_arm = {a: cells[a]["n"] for a in present}
    return {"arms_present": present, "n_per_arm": n_per_arm, "has_pivot": has_pivot,
            "cells": cells, "control_arm": control_arm}


def overall_review_verdict(review):
    """One plain, non-contradictory sentence (<=25 words): which arm scored
    best on documented rules overall (all doc-rule tests, task1+pivot, by
    pct) and that arm's token cost relative to the no-harness control.
    Pure. This is the short headline; cost_vs_benefit_verdict() below
    answers the "is the harness worth it" question this sentence doesn't
    have room for."""
    present = review["arms_present"]
    cells = review["cells"]
    if not present:
        return "No runs to report."

    doc_vals = {a: cells[a]["all_doc"][1] for a in present}
    best_arm = strict_best_arm(doc_vals, higher_is_better=True)

    if best_arm is None:
        return "No documented-rule test results recorded for any arm yet (directional, n=1/arm)."

    best_xy, best_pct = cells[best_arm]["all_doc"]
    label = ARM_LABELS.get(best_arm, best_arm).split(" (")[0]
    sentence = f"{label} scored best on documented rules overall ({best_xy}, {best_pct:.0f}%)"

    control_arm = review["control_arm"]
    if control_arm and best_arm != control_arm:
        vs = cells[best_arm]["vs_no_harness"].get("tokens_pct")
        if vs is not None:
            direction = "more" if vs > 0 else "fewer"
            sentence += f", using {abs(vs):.0f}% {direction} tokens than no harness"
    elif control_arm and best_arm == control_arm:
        sentence += " — with no harness running at all"

    return sentence + "."


def cost_vs_benefit_lines(review):
    """Per-harness-arm cost-vs-benefit line answering "is using a harness
    worth the extra turns and tokens?" — e.g. "baseline: 1.9x tokens, 1.5x
    turns vs no harness -> task-1 doc compliance LOWER (33/58 vs 47/58),
    pivot equal (16/34)."

    Returns [{"arm": str, "label": str, "tokens_x": float|None,
    "turns_x": float|None, "t1_doc_cmp": "LOWER"|"HIGHER"|"EQUAL"|None,
    "t1_doc_xy": str, "t1_doc_ctrl_xy": str, "pv_doc_cmp": ...,
    "pv_doc_xy": str, "pv_doc_ctrl_xy": str}] for every present arm other
    than control, ordered by ARM_ORDER. Pure."""
    present = review["arms_present"]
    cells = review["cells"]
    control_arm = review["control_arm"]
    if not control_arm or control_arm not in cells:
        return []
    ctrl = cells[control_arm]

    def _cmp(arm_pct, ctrl_pct):
        if arm_pct is None or ctrl_pct is None:
            return None
        if arm_pct > ctrl_pct:
            return "HIGHER"
        if arm_pct < ctrl_pct:
            return "LOWER"
        return "EQUAL"

    out = []
    for arm in present:
        if arm == control_arm:
            continue
        c = cells[arm]
        vs = c.get("vs_no_harness") or {}
        tokens_pct = vs.get("tokens_pct")
        turns_pct = vs.get("turns_pct")
        tokens_x = (1.0 + tokens_pct / 100.0) if tokens_pct is not None else None
        turns_x = (1.0 + turns_pct / 100.0) if turns_pct is not None else None

        t1_xy, t1_pct = c["t1_doc"]
        t1_ctrl_xy, t1_ctrl_pct = ctrl["t1_doc"]
        pv_xy, pv_pct = c["pv_doc"]
        pv_ctrl_xy, pv_ctrl_pct = ctrl["pv_doc"]

        out.append({
            "arm": arm,
            "label": ARM_LABELS.get(arm, arm).split(" (")[0],
            "tokens_x": tokens_x,
            "turns_x": turns_x,
            "t1_doc_cmp": _cmp(t1_pct, t1_ctrl_pct),
            "t1_doc_xy": t1_xy,
            "t1_doc_ctrl_xy": t1_ctrl_xy,
            "pv_doc_cmp": _cmp(pv_pct, pv_ctrl_pct),
            "pv_doc_xy": pv_xy,
            "pv_doc_ctrl_xy": pv_ctrl_xy,
        })
    return out


def _cost_vs_benefit_line_text(line):
    """Render one cost_vs_benefit_lines() entry as plain text, e.g.
    'baseline: 1.9x tokens, 1.5x turns vs no harness -> task-1 doc
    compliance LOWER (33/58 vs 47/58), pivot equal (16/34).' Pure."""
    bits = []
    if line["tokens_x"] is not None:
        bits.append(f'{line["tokens_x"]:.1f}× tokens')
    if line["turns_x"] is not None:
        bits.append(f'{line["turns_x"]:.1f}× turns')
    cost_str = ", ".join(bits) if bits else "cost not recorded"

    def _phase_bit(cmp_, xy, ctrl_xy, phase_label):
        if cmp_ is None:
            return f"{phase_label} not recorded"
        if cmp_ == "EQUAL":
            return f"{phase_label} equal ({xy})"
        return f"{phase_label} compliance {cmp_} ({xy} vs {ctrl_xy})"

    t1_bit = _phase_bit(line["t1_doc_cmp"], line["t1_doc_xy"], line["t1_doc_ctrl_xy"], "task-1 doc")
    pv_bit = _phase_bit(line["pv_doc_cmp"], line["pv_doc_xy"], line["pv_doc_ctrl_xy"], "pivot doc")

    return f'{line["label"]}: {cost_str} vs no harness → {t1_bit}, {pv_bit}.'


def cost_vs_benefit_verdict(review):
    """Answer "Is using a harness worth the extra turns and tokens?"
    plainly, from the data, with the n=1 caveat. Pure.

    A harness arm "wins" the cost-vs-benefit question only if it beats
    control on BOTH task-1 and pivot doc-rule pct while costing no more
    than control (strict, symmetric with strict_best_arm's no-ties rule).
    Otherwise the answer is "no" (cost paid without matching gain) unless
    every harness arm ties or is unmeasured, in which case it's
    "inconclusive"."""
    lines = cost_vs_benefit_lines(review)
    if not lines:
        return {"question": "Is using a harness worth the extra turns and tokens?",
                "answer": "No control arm to compare against.", "lines": []}

    any_win = any(
        (l["t1_doc_cmp"] in ("HIGHER", "EQUAL") and l["pv_doc_cmp"] in ("HIGHER", "EQUAL")
         and (l["t1_doc_cmp"] == "HIGHER" or l["pv_doc_cmp"] == "HIGHER"))
        for l in lines
    )
    pv_gain_bits = [
        f'{l["label"]}’s only gain was {l["pv_doc_xy"]} pivot doc tests vs {l["pv_doc_ctrl_xy"]} for no harness'
        for l in lines if l["pv_doc_cmp"] == "HIGHER" and l["t1_doc_cmp"] != "HIGHER"
    ]

    if any_win:
        answer = "On this run, yes for at least one arm — it matched or beat no-harness documented-rule compliance without costing more."
    else:
        answer = "On this run, no — the harness cost more tokens/turns and did not improve documented-rule compliance over no harness."
        if pv_gain_bits:
            answer += " " + "; ".join(pv_gain_bits) + "."
    answer += " n=1 per arm — directional, not statistically powered."

    return {
        "question": "Is using a harness worth the extra turns and tokens?",
        "answer": answer,
        "lines": lines,
    }


# --------------------------------------------------------------------------
# Delegation: did an arm use subagents to cut time/cost? Top-level metrics
# only (subagent_launches/messages/main_tokens/total_tokens) -- no
# per-phase subagent breakdown exists in runs.jsonl, so phase columns
# always read "—".
# --------------------------------------------------------------------------


def delegation_rows(rows):
    """Per-run delegation data: subagent launches/messages, main-vs-
    subagent token split, wall time. Pure.

    Returns [{"run_id", "arm", "trial", "subagent_launches",
    "subagent_messages", "main_tokens", "subagent_tokens", "total_tokens",
    "wall_s"}], ordered by ARM_ORDER then trial. subagent_tokens is
    total_tokens - main_tokens when both are present, else None. No
    per-phase subagent fields exist in this experiment's runs.jsonl, so
    this is top-level-metrics-only (report.py's rendering shows '—' for
    any phase-level ask)."""
    out = []
    for r in rows:
        arm = r.get("arm")
        if arm not in ARM_ORDER:
            continue
        main_tok = g(r, "metrics", "main_tokens")
        total_tok = g(r, "metrics", "total_tokens")
        subagent_tok = (total_tok - main_tok) if (isinstance(main_tok, (int, float)) and isinstance(total_tok, (int, float))) else None
        out.append({
            "run_id": r.get("run_id") or f"{arm}-t{r.get('trial')}",
            "arm": arm,
            "trial": r.get("trial"),
            "subagent_launches": g(r, "metrics", "subagent_launches"),
            "subagent_messages": g(r, "metrics", "subagent_messages"),
            "main_tokens": main_tok,
            "subagent_tokens": subagent_tok,
            "total_tokens": total_tok,
            "wall_s": r.get("wall_s"),
        })
    out.sort(key=lambda r: (ARM_ORDER.index(r["arm"]) if r["arm"] in ARM_ORDER else 99, r["trial"] or 0))
    return out


def delegation_takeaway(deleg_rows):
    """One-line takeaway computed from delegation_rows(): which arms
    launched subagents, and whether the fastest/cheapest arm did so.
    States only what the data supports (no launches recorded for any arm
    -> a plain 'no arm parallelized meaningfully' sentence; some launches
    -> names which arm(s) and whether the arm with the lowest wall_s/
    total_tokens was among them). Pure."""
    if not deleg_rows:
        return "No delegation data recorded."

    launches_by_arm = {}
    for r in deleg_rows:
        n = r.get("subagent_launches") or 0
        launches_by_arm[r["arm"]] = launches_by_arm.get(r["arm"], 0) + n

    any_launches = any(v > 0 for v in launches_by_arm.values())

    fastest = min(
        (r for r in deleg_rows if r.get("wall_s") is not None),
        key=lambda r: r["wall_s"], default=None,
    )
    cheapest = min(
        (r for r in deleg_rows if r.get("total_tokens") is not None),
        key=lambda r: r["total_tokens"], default=None,
    )

    launch_bits = ", ".join(
        f'{ARM_LABELS.get(a, a).split(" (")[0]} launched {n}'
        for a, n in launches_by_arm.items()
    )

    if not any_launches:
        sentence = f"This trial: {launch_bits} subagent(s) — no arm parallelized meaningfully."
        if fastest:
            fastest_label = ARM_LABELS.get(fastest["arm"], fastest["arm"]).split(" (")[0]
            sentence += f" {fastest_label} was still fastest ({fmt_num(fastest['wall_s'], 0)}s) without delegating."
        return sentence

    sentence = f"This trial: {launch_bits} subagent(s)."
    if fastest and cheapest:
        fastest_label = ARM_LABELS.get(fastest["arm"], fastest["arm"]).split(" (")[0]
        fastest_launched = (launches_by_arm.get(fastest["arm"]) or 0) > 0
        if not fastest_launched:
            sentence += f" {fastest_label} was fastest without delegating — the arm(s) that did delegate weren't faster or cheaper."
    return sentence


# --------------------------------------------------------------------------
# Code metrics: size/shape of the code the agent wrote, vs the reference
# solution. Proxies, not quality judgments (see code_metrics.py).
# --------------------------------------------------------------------------


def code_metrics_task_paths(stamp_dir, meta):
    """Resolve {"reference_solution", "pivot_reference_solution"} paths for
    code_metrics.collect_code_metrics()'s size-vs-reference figure, from
    this experiment's fixed tasks/v2 layout (read-only path convention
    shared with acceptance.py's task-path resolution, never that module's
    behavior). Falls back to None (skip the figure) if the task dir can't
    be located."""
    task_dir = os.path.join(HERE, "tasks", "v2")
    if not os.path.isdir(task_dir):
        return None
    return {
        "reference_solution": os.path.join(task_dir, "reference_solution"),
        "pivot_reference_solution": os.path.join(task_dir, "pivot", "reference_solution"),
    }


def code_metrics_rows(rows, stamp_dir):
    """Per-run code metrics (collect_code_metrics() on each run's work/
    git repo), for the Code section's table + charts. Reads from disk
    (git + file reads under stamp_dir/runs/<run_id>/work) -- NOT pure, but
    isolated here so report.py's other data functions stay pure. Returns
    [] if stamp_dir is falsy or a run's work/ dir doesn't exist (skips
    that run rather than raising)."""
    if not stamp_dir:
        return []
    cm = get_code_metrics()
    task_paths = code_metrics_task_paths(stamp_dir, {})
    out = []
    for r in rows:
        arm = r.get("arm")
        if arm not in ARM_ORDER:
            continue
        run_id = r.get("run_id") or f"{arm}-t{r.get('trial')}"
        work_dir = os.path.join(stamp_dir, "runs", run_id, "work")
        if not os.path.isdir(work_dir):
            continue
        m = cm.collect_code_metrics(work_dir, task_paths)
        out.append({
            "run_id": run_id, "arm": arm, "trial": r.get("trial"),
            "metrics": m,
        })
    out.sort(key=lambda r: (ARM_ORDER.index(r["arm"]) if r["arm"] in ARM_ORDER else 99, r["trial"] or 0))
    return out


# --------------------------------------------------------------------------
# Explain failures: per-arm doc-rule failures grouped by rule, with a
# short expected-vs-actual snippet per failing test, plus the shared-vs-
# harness-only split.
# --------------------------------------------------------------------------


def _task_doc_rules_paths():
    """Fixed doc_rules.json paths for this experiment's tasks/v2 layout.
    Pure (no I/O -- callers pass these to failure_detail's json-loading,
    or json.load them directly; missing files are handled by the caller)."""
    task_dir = os.path.join(HERE, "tasks", "v2")
    return {
        "task1": os.path.join(task_dir, "doc_rules.json"),
        "pivot": os.path.join(task_dir, "pivot", "doc_rules.json"),
    }


def _load_doc_rules_json(path):
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
    except (ValueError, OSError):
        return []
    return data if isinstance(data, list) else []


def failure_report_rows(rows, stamp_dir):
    """Per-arm failure-detail data for the Explain failures section, plus
    the shared-vs-harness-only rule split. Reads doc_rules.json (this
    module's own tasks/v2 fixtures) and each run's acceptance.*.txt log
    from disk -- not pure, isolated here like code_metrics_rows().

    Returns {"by_arm": {arm: {"task1": [failure_detail entries],
    "pivot": [...]}}, "split": {"shared": [...], "harness_only": [...]}}.
    harness_arms is every present arm except 'control'."""
    fd = get_failure_detail()
    doc_rules_paths = _task_doc_rules_paths()
    doc_rules_t1 = _load_doc_rules_json(doc_rules_paths["task1"])
    doc_rules_pv = _load_doc_rules_json(doc_rules_paths["pivot"])

    by_arm = {}
    per_arm_failed_rules = {}
    all_arms = []
    for r in rows:
        arm = r.get("arm")
        if arm not in ARM_ORDER:
            continue
        phases = r.get("phases")
        if not isinstance(phases, dict) or "task1" not in phases or "pivot" not in phases:
            continue
        if arm not in all_arms:
            all_arms.append(arm)
        run_id = r.get("run_id") or f"{arm}-t{r.get('trial')}"
        run_dir = os.path.join(stamp_dir, "runs", run_id) if stamp_dir else None

        by_id_t1 = g(phases, "task1", "benchmark", "by_id") or {}
        by_id_pv = g(phases, "pivot", "benchmark", "by_id") or {}
        text_t1 = fd.load_acceptance_text(run_dir, "acceptance.task1.b1.txt") if run_dir else ""
        text_pv = fd.load_acceptance_text(run_dir, "acceptance.pivot.b2.txt") if run_dir else ""

        rep_t1 = fd.build_failure_report(by_id_t1, doc_rules_t1, text_t1)
        rep_pv = fd.build_failure_report(by_id_pv, doc_rules_pv, text_pv)

        entry = by_arm.setdefault(arm, {"task1": [], "pivot": []})
        entry["task1"].extend(rep_t1)
        entry["pivot"].extend(rep_pv)

        failed_ids = {e["rule_id"] for e in rep_t1} | {e["rule_id"] for e in rep_pv}
        per_arm_failed_rules.setdefault(arm, set()).update(failed_ids)

    harness_arms = [a for a in all_arms if a != "control"]
    split = fd.shared_vs_harness_only(per_arm_failed_rules, harness_arms, all_arms) if all_arms else {"shared": [], "harness_only": []}

    return {"by_arm": by_arm, "split": split, "arms_present": [a for a in ARM_ORDER if a in by_arm]}


def compute_verdict(agg):
    """Plain-language one-sentence verdict from aggregate() output. Pure.

    Prioritizes doc pass % and gate conformance (section 5's steer: proving
    the plugin's docs-driven domain-rule compliance and gate usage matters
    more here than the raw acceptance success rate) — leads with the best
    doc_pass_pct_mean arm and its init_chain_complete/sweep_verified rates
    when any arm has gate/doc data, falling back to the plain
    acceptance-success-rate verdict (the pre-existing behavior) when neither
    is present (e.g. a v1-shaped stamp reparsed before doc_rules existed)."""
    arms = agg.get("arms", {})
    present = [a for a in ARM_ORDER if a in arms]
    if not present:
        return "No runs to report."

    parts = []

    # Pivot lead sentence (section 2's priority: B1 & B2 doc-rule pass % by
    # arm, then task-1 retention) — prepended before the single-phase
    # doc-pass/success-rate/cost sentences below, which still apply (they
    # read top-level acceptance/gates, i.e. benchmark 2's, on pivot rows).
    pivot_bench = agg.get("pivot_benchmarks") or {}
    pivot_present = [a for a in present if (pivot_bench.get(a) or {}).get("n_pivot")]
    if pivot_present:
        best_b_arm, best_b1, best_b2 = None, -1, -1
        for a in pivot_present:
            pb = pivot_bench[a]
            d1 = pb["b1"].get("doc_pass_pct_mean")
            d2 = pb["b2"].get("doc_pass_pct_mean")
            score = max(v for v in (d1, d2, -1) if v is not None)
            if score > best_b1:
                best_b1, best_b_arm = score, a
                best_b2 = d2
        if best_b_arm is not None:
            pb = pivot_bench[best_b_arm]
            d1 = pb["b1"].get("doc_pass_pct_mean")
            d2 = pb["b2"].get("doc_pass_pct_mean")
            ret = pb["task1_retention"]
            bits = []
            if d1 is not None:
                bits.append(f"B1 doc-rule pass {d1:.0f}%")
            if d2 is not None:
                bits.append(f"B2 doc-rule pass {d2:.0f}%")
            ret_rate = ret.get("rate_mean")
            ret_str = f", task-1 retention {ret_rate:.0f}%" if ret_rate is not None else ""
            regressions = ret.get("total_regressions") or 0
            reg_str = f" ({regressions} task-1 regression(s) across all pivot runs)" if regressions else ""
            parts.append(
                f"{ARM_LABELS.get(best_b_arm, best_b_arm)} led the pivot benchmarks "
                f"({', '.join(bits)}{ret_str}){reg_str}."
            )

    best_doc_arm, best_doc_pct = None, -1
    for a in present:
        pct = arms[a].get("doc_pass_pct_mean")
        if pct is not None and pct > best_doc_pct:
            best_doc_pct, best_doc_arm = pct, a

    if best_doc_arm is not None:
        gc = arms[best_doc_arm].get("gate_conformance") or {}
        init_rate = gc.get("init_chain_complete_rate")
        sweep_rate = gc.get("sweep_verified_rate")
        gate_bits = []
        if init_rate is not None:
            gate_bits.append(f"init-chain complete {init_rate * 100:.0f}%")
        if sweep_rate is not None:
            gate_bits.append(f"sweep verified {sweep_rate * 100:.0f}%")
        gate_str = f" ({', '.join(gate_bits)})" if gate_bits else ""
        parts.append(
            f"{ARM_LABELS.get(best_doc_arm, best_doc_arm)} had the highest doc-rule pass rate "
            f"({best_doc_pct:.0f}%){gate_str}."
        )

    best_arm, best_rate = None, -1
    for a in present:
        rate = arms[a].get("success_rate")
        if rate is not None and rate > best_rate:
            best_rate, best_arm = rate, a

    if best_arm is not None:
        parts.append(
            f"{ARM_LABELS.get(best_arm, best_arm)} had the highest acceptance success rate "
            f"({best_rate * 100:.0f}%)."
        )
    elif not parts:
        parts.append("No arm had measurable acceptance results.")

    if "baseline" in arms:
        base = arms["baseline"]
        for a in present:
            if a == "baseline":
                continue
            deltas = arms[a].get("vs_baseline_pct") or {}
            # All-agent turns and all-model tokens only — never the
            # main-agent-only num_turns/main_tokens figures, which can be
            # misleadingly low on a run that delegated heavily to subagents.
            turns_d = deltas.get("assistant_turns_incl_subagents")
            tok_d = deltas.get("total_tokens")
            bits = []
            if turns_d is not None:
                bits.append(f"{turns_d:+.0f}% turns (all agents)")
            if tok_d is not None:
                bits.append(f"{tok_d:+.0f}% tokens (all models)")
            if bits:
                parts.append(f"{ARM_LABELS.get(a, a)} vs baseline: {', '.join(bits)} (median).")
    return " ".join(parts)


# --------------------------------------------------------------------------
# Scorecard (top-of-report 3-column comparison).
# --------------------------------------------------------------------------

# (row key, label, unit, "higher_is_better") — unit and direction drive
# fmt + the delta arrow/wording. All values pulled from aggregate() output.
SCORECARD_ROWS = [
    ("doc_pass_pct_mean", "Doc-rule pass %", "pct", True),
    ("spec_pass_pct_mean", "Spec pass %", "pct", True),
    ("success_rate", "Full success (x/n)", "frac", True),
    ("total_tokens_median", "Median total tokens", "num", False),
    ("turns_median", "Median turns (all agents)", "num", False),
    ("wall_s_median", "Median wall time", "wall", False),
]


def scorecard_data(agg):
    """Per-arm scorecard values + delta vs control (the no-harness
    reference), for the top scorecard. Pure.

    Returns {"rows": [{"key", "label", "unit", "higher_is_better",
    "cells": {arm: {"value": float|None, "n": int|None, "delta_pct":
    float|None}}, "best_arm": str|None}], "arms_present": [...]}.

    delta_pct is None for the control column itself (it IS the reference)
    and for any arm/row where either value is missing or control's value is
    0/None (divide-by-zero guard). "best" is picked per row among arms with
    a non-None value, respecting higher_is_better; ties keep the first arm
    in ARM_ORDER."""
    arms = agg.get("arms", {})
    present = [a for a in ARM_ORDER if a in arms]
    control_arm = "control" if "control" in present else None

    def _raw(arm, key):
        s = arms.get(arm, {})
        if key == "success_rate":
            n = s.get("n")
            rate = s.get("success_rate")
            passed = round(rate * n) if (rate is not None and n) else None
            return rate, (f"{passed}/{n}" if n else None)
        if key == "total_tokens_median":
            return s.get("stats", {}).get("total_tokens", {}).get("median"), None
        if key == "turns_median":
            return s.get("stats", {}).get("assistant_turns_incl_subagents", {}).get("median"), None
        if key == "wall_s_median":
            return s.get("stats", {}).get("wall_s", {}).get("median"), None
        return s.get(key), None

    out_rows = []
    for key, label, unit, higher_is_better in SCORECARD_ROWS:
        cells = {}
        for arm in present:
            val, extra = _raw(arm, key)
            cells[arm] = {"value": val, "extra": extra, "delta_pct": None}
        ctrl_val = cells.get(control_arm, {}).get("value") if control_arm else None
        for arm in present:
            if arm == control_arm:
                continue
            v = cells[arm]["value"]
            if v is None or ctrl_val is None or ctrl_val == 0:
                continue
            cells[arm]["delta_pct"] = 100.0 * (v - ctrl_val) / ctrl_val

        best_arm = None
        best_val = None
        for arm in present:
            v = cells[arm]["value"]
            if v is None:
                continue
            if best_val is None or (v > best_val if higher_is_better else v < best_val):
                best_val, best_arm = v, arm

        out_rows.append({
            "key": key, "label": label, "unit": unit,
            "higher_is_better": higher_is_better,
            "cells": cells, "best_arm": best_arm,
        })

    return {"rows": out_rows, "arms_present": present, "control_arm": control_arm}


def parse_notes_lines(text):
    """Parse the simple notes line-format: one finding per line, each
    starting with '- ' (markdown-bullet style); blank lines ignored. Returns
    a list of finding strings (bullet marker + surrounding whitespace
    stripped). Pure.

    Backward compat: if NO line matches the '- text' shape (e.g. the file is
    an HTML fragment, the pre-existing --notes contract), returns an empty
    list so the caller falls back to rendering the raw text as an HTML
    fragment instead."""
    if not text:
        return []
    findings = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^[-*]\s+(.*\S)\s*$", line)
        if m:
            findings.append(m.group(1))
    return findings


def key_findings(agg, notes_findings=None, max_findings=5):
    """3-5 short one-sentence findings for the scorecard's findings-card
    row. Pure. Prefers author-supplied notes_findings (parsed via
    parse_notes_lines) when given; otherwise derives up to max_findings
    generic findings from aggregate() output (doc pass rate leader, success
    rate leader, cost/turns deltas vs control)."""
    if notes_findings:
        return list(notes_findings[:max_findings])

    arms = agg.get("arms", {})
    present = [a for a in ARM_ORDER if a in arms]
    findings = []

    sc = scorecard_data(agg)
    for row in sc["rows"]:
        if len(findings) >= max_findings:
            break
        if row["key"] not in ("doc_pass_pct_mean", "success_rate"):
            continue
        best = row["best_arm"]
        if best is None:
            continue
        cell = row["cells"][best]
        if row["unit"] == "pct" and cell["value"] is not None:
            findings.append(f"{ARM_LABELS.get(best, best)} led {row['label'].lower()} at {cell['value']:.0f}%.")
        elif row["unit"] == "frac" and cell["extra"]:
            findings.append(f"{ARM_LABELS.get(best, best)} had the best full-success rate ({cell['extra']}).")

    control_arm = sc["control_arm"]
    if control_arm and len(findings) < max_findings:
        for arm in present:
            if arm == control_arm or len(findings) >= max_findings:
                continue
            deltas = arms[arm].get("vs_baseline_pct") or {}
            tok_d = deltas.get("total_tokens") if "baseline" != control_arm else None
        # Prefer a direct vs-control token/turns comparison when both sides
        # have data (vs_baseline_pct is baseline-relative, not
        # control-relative, so recompute directly from the scorecard).
        for row in sc["rows"]:
            if row["key"] != "total_tokens_median" or len(findings) >= max_findings:
                continue
            for arm in present:
                if arm == control_arm:
                    continue
                d = row["cells"].get(arm, {}).get("delta_pct")
                if d is not None:
                    direction = "more" if d > 0 else "fewer"
                    findings.append(f"{ARM_LABELS.get(arm, arm)} used {abs(d):.0f}% {direction} tokens than no harness.")
                    break

    if not findings:
        findings.append("Not enough comparable data across arms to summarize yet.")
    return findings[:max_findings]


# --------------------------------------------------------------------------
# SVG helpers.
# --------------------------------------------------------------------------


def esc(s):
    return html_mod.escape("" if s is None else str(s), quote=True)


def fmt_num(v, digits=0):
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "—"
    try:
        if digits == 0:
            return f"{v:,.0f}"
        return f"{v:,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def fmt_pct(v, digits=0):
    if v is None:
        return "—"
    try:
        return f"{v:.{digits}f}%"
    except (TypeError, ValueError):
        return "—"


def fmt_cost(v):
    if v is None:
        return "—"
    try:
        return f"${v:.3f}"
    except (TypeError, ValueError):
        return "—"


def svg_open(width, height, extra_class=""):
    return (
        f'<svg class="chart-svg {esc(extra_class)}" viewBox="0 0 {width} {height}" '
        f'width="100%" height="{height}" preserveAspectRatio="xMinYMin meet" role="img">'
    )


def dot_strip_chart(rows, metric_key, metric_label, width=560, height=170):
    """One dot/strip small-multiple: dots per arm row, median tick."""
    pad_left = 150
    pad_right = 24
    pad_top = 14
    pad_bottom = 30
    plot_w = width - pad_left - pad_right
    row_h = (height - pad_top - pad_bottom) / max(len(ARM_ORDER), 1)

    vals = [v for (_a, _t, v) in rows]
    lo = min(vals) if vals else 0
    hi = max(vals) if vals else 1
    if lo == hi:
        lo, hi = (lo - 1, hi + 1) if lo else (0, 1)
    ticks = nice_ticks(lo, hi, 5)
    t_lo, t_hi = min(ticks[0], lo), max(ticks[-1], hi)
    xscale = linear_scale((t_lo, t_hi), (pad_left, width - pad_right))

    parts = [svg_open(width, height)]
    parts.append(
        f'<text x="{pad_left}" y="10" class="chart-title" font-size="13">{esc(metric_label)}</text>'
    )

    # gridlines + tick labels
    for tv in ticks:
        x = xscale(tv)
        parts.append(
            f'<line x1="{x:.1f}" y1="{pad_top}" x2="{x:.1f}" y2="{height - pad_bottom}" '
            f'class="grid-line" />'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{height - pad_bottom + 14}" class="tick-label" '
            f'font-size="12" text-anchor="middle">{fmt_num(tv)}</text>'
        )

    by_arm = {a: [] for a in ARM_ORDER}
    for (arm, trial, v) in rows:
        by_arm.setdefault(arm, []).append((trial, v))

    for i, arm in enumerate(ARM_ORDER):
        cy = pad_top + row_h * i + row_h / 2
        parts.append(
            f'<text x="{pad_left - 10}" y="{cy + 3:.1f}" text-anchor="end" '
            f'class="row-label" font-size="12">{esc(ARM_LABELS[arm])}</text>'
        )
        avals = [v for (_t, v) in by_arm.get(arm, [])]
        med = median(avals)
        color = f'var(--arm-{arm})'
        for (trial, v) in by_arm.get(arm, []):
            cx = xscale(v)
            parts.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="{color}" '
                f'stroke="var(--surface-1)" stroke-width="2" class="mark-dot" '
                f'data-tip="{esc(ARM_LABELS[arm])} trial {esc(trial)}: {fmt_num(v, 1)}">'
                f'<title>{esc(ARM_LABELS[arm])} trial {esc(trial)}: {fmt_num(v, 1)}</title></circle>'
            )
        if med is not None:
            mx = xscale(med)
            parts.append(
                f'<line x1="{mx:.1f}" y1="{cy - row_h * 0.32:.1f}" x2="{mx:.1f}" '
                f'y2="{cy + row_h * 0.32:.1f}" stroke="var(--text-secondary)" '
                f'stroke-width="2" class="median-tick">'
                f'<title>{esc(ARM_LABELS[arm])} median: {fmt_num(med, 1)}</title></line>'
            )

    parts.append("</svg>")
    return "".join(parts)


def token_composition_chart(comp_rows, width=640, row_h=22, gap=6):
    """Stacked horizontal bar per run: input/output/cache_creation/cache_read.
    Grouped by arm (rows ordered by arm, then trial). Sequential blue ramp,
    not arm colors; arm shown via row label + color chip."""
    pad_left = 190
    pad_right = 90
    pad_top = 46
    pad_bottom = 10
    ordered = sorted(comp_rows, key=lambda r: (ARM_ORDER.index(r[1]) if r[1] in ARM_ORDER else 99, r[2] if r[2] is not None else 0))
    n = len(ordered)
    height = pad_top + pad_bottom + n * (row_h + gap)
    plot_w = width - pad_left - pad_right

    totals = [sum(parts.values()) for (_id, _a, _t, parts) in ordered]
    max_total = max(totals) if totals else 1
    if max_total <= 0:
        max_total = 1
    xscale = linear_scale((0, max_total), (0, plot_w))

    keys = ["input", "output", "cache_creation", "cache_read"]
    key_labels = {"input": "Input", "output": "Output", "cache_creation": "Cache creation", "cache_read": "Cache read"}

    parts_html = [svg_open(width, height)]
    parts_html.append(
        f'<text x="0" y="12" class="chart-title" font-size="13">Token composition per run</text>'
    )
    # legend (sequential ramp swatches), on its own row below the title
    lx = 0
    ly = 32
    for k in keys:
        parts_html.append(f'<rect x="{lx}" y="{ly - 8}" width="10" height="10" fill="{COMPOSITION_LIGHT[k]}" class="legend-swatch" data-key="{k}" />')
        parts_html.append(f'<text x="{lx + 14}" y="{ly}" class="legend-label" font-size="12">{esc(key_labels[k])}</text>')
        lx += 14 + len(key_labels[k]) * 6 + 16

    y = pad_top + 8
    for (run_id, arm, trial, comp) in ordered:
        cy = y
        color = f'var(--arm-{arm})'
        parts_html.append(
            f'<rect x="{pad_left - 178}" y="{cy - 9}" width="9" height="9" fill="{color}" rx="2" />'
        )
        parts_html.append(
            f'<text x="{pad_left - 165}" y="{cy}" class="row-label" font-size="12">'
            f'{esc(ARM_LABELS.get(arm, arm))} t{esc(trial)}</text>'
        )
        x = pad_left
        total = sum(comp.values()) or 0
        for k in keys:
            v = comp.get(k, 0)
            if v <= 0:
                continue
            w = max(xscale(v) - 0, 0)
            parts_html.append(
                f'<rect x="{x:.1f}" y="{cy - row_h + 4:.1f}" width="{max(w - 2, 0):.1f}" '
                f'height="{row_h - 8}" fill="{COMPOSITION_LIGHT[k]}" class="comp-seg" '
                f'data-key="{k}" '
                f'data-tip="{esc(key_labels[k])}: {fmt_num(v)} tokens">'
                f'<title>{esc(ARM_LABELS.get(arm, arm))} t{esc(trial)} — {esc(key_labels[k])}: {fmt_num(v)}</title>'
                f'</rect>'
            )
            x += w
        parts_html.append(
            f'<text x="{x + 6:.1f}" y="{cy - row_h / 2 + 4:.1f}" class="tick-label" '
            f'font-size="12">{fmt_num(total)}</text>'
        )
        y += row_h + gap

    parts_html.append("</svg>")
    return "".join(parts_html), height


PHASE_KEYS = ("task1", "pivot")
PHASE_LABELS = {"task1": "Task 1", "pivot": "Pivot"}
# Sequential ramp reused for phase segments (not arm colors — arm shown via
# row label + color chip, same convention as token_composition_chart).
PHASE_LIGHT = {"task1": "#cde2fb", "pivot": "#2a78d6"}
PHASE_DARK = {"task1": "#9ec5f4", "pivot": "#3987e5"}


def phase_cost_stack_chart(stack_rows, width=640, row_h=22, gap=6):
    """Stacked horizontal bar per two-phase run: task1 tokens | pivot
    tokens. Same layout convention as token_composition_chart. Pure."""
    pad_left = 190
    pad_right = 90
    pad_top = 46
    pad_bottom = 10
    ordered = sorted(stack_rows, key=lambda r: (ARM_ORDER.index(r[1]) if r[1] in ARM_ORDER else 99, r[2] if r[2] is not None else 0))
    n = len(ordered)
    height = pad_top + pad_bottom + n * (row_h + gap)
    plot_w = width - pad_left - pad_right

    totals = [sum(parts.values()) for (_id, _a, _t, parts) in ordered]
    max_total = max(totals) if totals else 1
    if max_total <= 0:
        max_total = 1
    xscale = linear_scale((0, max_total), (0, plot_w))

    parts_html = [svg_open(width, height)]
    parts_html.append('<text x="0" y="12" class="chart-title" font-size="13">Tokens by phase per run</text>')
    lx = 0
    ly = 32
    for k in PHASE_KEYS:
        parts_html.append(f'<rect x="{lx}" y="{ly - 8}" width="10" height="10" fill="{PHASE_LIGHT[k]}" class="legend-swatch" data-key="{k}" />')
        parts_html.append(f'<text x="{lx + 14}" y="{ly}" class="legend-label" font-size="12">{esc(PHASE_LABELS[k])}</text>')
        lx += 14 + len(PHASE_LABELS[k]) * 6 + 16

    y = pad_top + 8
    if not ordered:
        parts_html.append('<text x="0" y="60" class="tick-label" font-size="12">No two-phase (pivot) runs.</text>')
    for (run_id, arm, trial, phase_parts) in ordered:
        cy = y
        color = f'var(--arm-{arm})'
        parts_html.append(f'<rect x="{pad_left - 178}" y="{cy - 9}" width="9" height="9" fill="{color}" rx="2" />')
        parts_html.append(
            f'<text x="{pad_left - 165}" y="{cy}" class="row-label" font-size="12">'
            f'{esc(ARM_LABELS.get(arm, arm))} t{esc(trial)}</text>'
        )
        x = pad_left
        total = sum(phase_parts.values()) or 0
        for k in PHASE_KEYS:
            v = phase_parts.get(k, 0)
            if v <= 0:
                continue
            w = max(xscale(v) - 0, 0)
            parts_html.append(
                f'<rect x="{x:.1f}" y="{cy - row_h + 4:.1f}" width="{max(w - 2, 0):.1f}" '
                f'height="{row_h - 8}" fill="{PHASE_LIGHT[k]}" class="comp-seg" '
                f'data-key="{k}" '
                f'data-tip="{esc(PHASE_LABELS[k])}: {fmt_num(v)} tokens">'
                f'<title>{esc(ARM_LABELS.get(arm, arm))} t{esc(trial)} — {esc(PHASE_LABELS[k])}: {fmt_num(v)}</title>'
                f'</rect>'
            )
            x += w
        parts_html.append(
            f'<text x="{x + 6:.1f}" y="{cy - row_h / 2 + 4:.1f}" class="tick-label" '
            f'font-size="12">{fmt_num(total)}</text>'
        )
        y += row_h + gap

    parts_html.append("</svg>")
    return "".join(parts_html), height


def acceptance_bar_chart(acc_rows, width=640, row_h=20, gap=6):
    pad_left = 150
    pad_right = 60
    pad_top = 32
    pad_bottom = 10
    ordered = sorted(acc_rows, key=lambda r: (ARM_ORDER.index(r["arm"]) if r["arm"] in ARM_ORDER else 99, r["trial"] if r["trial"] is not None else 0))
    n = len(ordered)
    height = pad_top + pad_bottom + n * (row_h + gap)
    plot_w = width - pad_left - pad_right
    xscale = linear_scale((0, 100), (0, plot_w))

    parts = [svg_open(width, height)]
    parts.append(f'<text x="0" y="12" class="chart-title" font-size="13">Acceptance pass rate per run (0-100%)</text>')

    y = pad_top + 8
    for r in ordered:
        cy = y
        color = f'var(--arm-{r["arm"]})'
        parts.append(f'<text x="{pad_left - 8}" y="{cy}" text-anchor="end" class="row-label" font-size="12">{esc(ARM_LABELS.get(r["arm"], r["arm"]))} t{esc(r["trial"])}</text>')
        w = xscale(r["pct"])
        parts.append(
            f'<rect x="{pad_left}" y="{cy - row_h + 4:.1f}" width="{max(w, 0):.1f}" height="{row_h - 8}" '
            f'fill="{color}" rx="4" class="mark-bar" '
            f'data-tip="{fmt_pct(r["pct"])} ({r["passed"]}/{r["total"]})">'
            f'<title>{esc(ARM_LABELS.get(r["arm"], r["arm"]))} t{esc(r["trial"])}: {fmt_pct(r["pct"])} '
            f'({r["passed"]}/{r["total"]}) regression_ok={r["reg_ok"]}</title></rect>'
        )
        parts.append(f'<text x="{pad_left + w + 6:.1f}" y="{cy - row_h/2 + 4:.1f}" class="tick-label" font-size="12">{fmt_pct(r["pct"])}</text>')
        if r["reg_ok"] is False:
            parts.append(
                f'<circle cx="{pad_left - 130:.1f}" cy="{cy - row_h/2:.1f}" r="3.5" fill="var(--status-critical)">'
                f'<title>regression FAILED</title></circle>'
            )
        y += row_h + gap

    parts.append("</svg>")
    return "".join(parts), height


def friction_chart(fric_rows, width=640, row_h=20, gap=6):
    pad_left = 150
    pad_right = 40
    pad_top = 34
    pad_bottom = 10
    ordered = sorted(fric_rows, key=lambda r: (ARM_ORDER.index(r["arm"]) if r["arm"] in ARM_ORDER else 99, r["trial"] if r["trial"] is not None else 0))
    n = len(ordered)
    height = pad_top + pad_bottom + n * (row_h + gap)
    plot_w = width - pad_left - pad_right

    max_v = max([max(r["hook_denials"], r["stop_hook_blocks"]) for r in ordered], default=0)
    max_v = max(max_v, 1)
    xscale = linear_scale((0, max_v), (0, plot_w / 2 - 10))

    parts = [svg_open(width, height)]
    parts.append(f'<text x="0" y="12" class="chart-title" font-size="13">Harness friction per run (hook denials / stop-hook blocks)</text>')
    parts.append(f'<text x="{pad_left}" y="26" class="legend-label" font-size="12">denials</text>')
    parts.append(f'<text x="{pad_left + plot_w/2 + 10:.1f}" y="26" class="legend-label" font-size="12">stop blocks</text>')

    y = pad_top + 10
    for r in ordered:
        cy = y
        color = f'var(--arm-{r["arm"]})'
        parts.append(f'<text x="{pad_left - 8}" y="{cy}" text-anchor="end" class="row-label" font-size="12">{esc(ARM_LABELS.get(r["arm"], r["arm"]))} t{esc(r["trial"])}</text>')
        w1 = xscale(r["hook_denials"])
        parts.append(
            f'<rect x="{pad_left}" y="{cy - row_h + 4:.1f}" width="{max(w1,0):.1f}" height="{row_h - 8}" fill="{color}" '
            f'class="mark-bar" data-tip="denials: {r["hook_denials"]}">'
            f'<title>{esc(ARM_LABELS.get(r["arm"], r["arm"]))} t{esc(r["trial"])} denials: {r["hook_denials"]}</title></rect>'
        )
        cx2 = pad_left + plot_w / 2 + 10
        w2 = xscale(r["stop_hook_blocks"])
        parts.append(
            f'<rect x="{cx2:.1f}" y="{cy - row_h + 4:.1f}" width="{max(w2,0):.1f}" height="{row_h - 8}" fill="{color}" '
            f'opacity="0.55" class="mark-bar" data-tip="stop blocks: {r["stop_hook_blocks"]}">'
            f'<title>{esc(ARM_LABELS.get(r["arm"], r["arm"]))} t{esc(r["trial"])} stop blocks: {r["stop_hook_blocks"]}</title></rect>'
        )
        y += row_h + gap

    parts.append("</svg>")
    return "".join(parts), height


def tool_mix_chart(tool_order, per_arm, width=640, height=220):
    pad_left = 150
    pad_right = 24
    pad_top = 34
    pad_bottom = 30
    plot_w = width - pad_left - pad_right
    row_h = (height - pad_top - pad_bottom) / max(len(ARM_ORDER), 1)

    totals = [sum(per_arm.get(a, {}).values()) for a in ARM_ORDER]
    max_total = max(totals) if totals else 1
    max_total = max(max_total, 1)
    xscale = linear_scale((0, max_total), (0, plot_w))

    # Fixed order palette for tool segments: sequential-ish neutral scale reused
    # across arms (not arm colors) — a small fixed set of grays/blues by rank.
    ramp = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#104281", "#0d366b", "#898781"]

    parts = [svg_open(width, height)]
    parts.append(f'<text x="0" y="12" class="chart-title" font-size="13">Tool mix by arm (top {TOOL_TOP_N} + Other)</text>')

    for i, arm in enumerate(ARM_ORDER):
        cy = pad_top + row_h * i + row_h / 2
        parts.append(f'<text x="{pad_left - 10}" y="{cy + 3:.1f}" text-anchor="end" class="row-label" font-size="12">{esc(ARM_LABELS[arm])}</text>')
        row = per_arm.get(arm, {})
        x = pad_left
        for j, tool in enumerate(tool_order):
            v = row.get(tool, 0)
            if v <= 0:
                continue
            w = xscale(v)
            fill = ramp[min(j, len(ramp) - 1)]
            parts.append(
                f'<rect x="{x:.1f}" y="{cy - row_h*0.32:.1f}" width="{max(w-2,0):.1f}" height="{row_h*0.64:.1f}" '
                f'fill="{fill}" class="tool-seg" data-tip="{esc(tool)}: {fmt_num(v)} calls">'
                f'<title>{esc(ARM_LABELS[arm])} — {esc(tool)}: {fmt_num(v)} calls</title></rect>'
            )
            x += w

    # legend
    lx = pad_left
    ly = height - 8
    for j, tool in enumerate(tool_order):
        fill = ramp[min(j, len(ramp) - 1)]
        parts.append(f'<rect x="{lx}" y="{ly - 8}" width="9" height="9" fill="{fill}" />')
        label = tool if len(tool) <= 12 else tool[:11] + "…"
        parts.append(f'<text x="{lx + 12}" y="{ly}" class="legend-label" font-size="12">{esc(label)}</text>')
        lx += 12 + len(label) * 5.5 + 10
        if lx > width - 60:
            lx = pad_left
            ly += 12

    parts.append("</svg>")
    return "".join(parts)


def stream_event_heatmap(table):
    """Small table of top event types by arm (sequential single-hue for a
    lightweight heatmap of counts)."""
    if not table:
        return "<p class=\"muted\">No stream events recorded (control arm has no plugin; plugin arms may not have run yet).</p>"
    all_events = []
    seen = set()
    for arm in ("baseline", "v5"):
        for k, _v in table.get(arm, []):
            if k not in seen:
                seen.add(k)
                all_events.append(k)
    max_v = 0
    for arm in ("baseline", "v5"):
        for _k, v in table.get(arm, []):
            max_v = max(max_v, v)
    max_v = max(max_v, 1)

    rows_html = []
    for ev in all_events:
        cells = []
        for arm in ("baseline", "v5"):
            v = dict(table.get(arm, [])).get(ev, 0)
            t = min(v / max_v, 1.0)
            # single hue (blue) sequential ramp via alpha
            cells.append(f'<td class="heat-cell" style="--heat-t:{t:.3f}" data-tip="{esc(ev)} ({esc(arm)}): {v}"><span class="sr-only">{esc(ev)}: </span>{fmt_num(v)}</td>')
        rows_html.append(f'<tr><th scope="row">{esc(ev)}</th>{"".join(cells)}</tr>')

    return (
        '<table class="heatmap-table"><thead><tr><th scope="col">event type</th>'
        f'<th scope="col">{esc(ARM_LABELS["baseline"])}</th><th scope="col">{esc(ARM_LABELS["v5"])}</th></tr></thead>'
        f'<tbody>{"".join(rows_html)}</tbody></table>'
    )


def spec_doc_grouped_bar_chart(spec_doc_by_arm, width=640, row_h=20, gap=8, pair_gap=4):
    """Grouped bars: spec vs doc pass % per arm. Arm color distinguishes the
    arm; spec vs doc distinguished by fill lightness (spec = full arm color,
    doc = lightened via opacity) with a legend + direct row labels, never
    relying on hue alone."""
    pad_left = 190
    pad_right = 60
    pad_top = 30
    pad_bottom = 10
    arms_present = [a for a in ARM_ORDER if a in spec_doc_by_arm]
    n = len(arms_present)
    height = pad_top + pad_bottom + n * (2 * row_h + pair_gap + gap)
    plot_w = width - pad_left - pad_right
    xscale = linear_scale((0, 100), (0, plot_w))

    parts = [svg_open(width, height)]
    parts.append('<text x="0" y="12" class="chart-title" font-size="13">Spec vs doc-rule pass % per arm (mean across runs)</text>')
    # legend
    parts.append(f'<rect x="{pad_left - 178}" y="18" width="10" height="10" fill="var(--arm-baseline)" />')
    parts.append(f'<text x="{pad_left - 164}" y="27" class="legend-label" font-size="12">spec</text>')
    parts.append(f'<rect x="{pad_left - 130}" y="18" width="10" height="10" fill="var(--arm-baseline)" opacity="0.45" />')
    parts.append(f'<text x="{pad_left - 116}" y="27" class="legend-label" font-size="12">doc</text>')

    y = pad_top + 6
    for arm in arms_present:
        vals = spec_doc_by_arm[arm]
        color = f'var(--arm-{arm})'
        parts.append(f'<text x="{pad_left - 8}" y="{y + row_h - 4:.1f}" text-anchor="end" class="row-label" font-size="12">{esc(ARM_LABELS.get(arm, arm))}</text>')
        for key, opacity, label in (("spec", 1.0, "spec"), ("doc", 0.45, "doc")):
            v = vals.get(key)
            cy = y
            if v is None:
                parts.append(f'<text x="{pad_left}" y="{cy + row_h/2:.1f}" class="tick-label" font-size="12">no {label} tests</text>')
            else:
                w = max(xscale(v), 0)
                parts.append(
                    f'<rect x="{pad_left}" y="{cy:.1f}" width="{w:.1f}" height="{row_h - 4}" '
                    f'fill="{color}" opacity="{opacity}" rx="3" class="mark-bar" '
                    f'data-tip="{esc(ARM_LABELS.get(arm, arm))} {label}: {fmt_pct(v)}">'
                    f'<title>{esc(ARM_LABELS.get(arm, arm))} {label}: {fmt_pct(v)}</title></rect>'
                )
                parts.append(f'<text x="{pad_left + w + 6:.1f}" y="{cy + row_h/2 + 3:.1f}" class="tick-label" font-size="12">{label} {fmt_pct(v)}</text>')
            y += row_h
        y += pair_gap + gap

    parts.append("</svg>")
    return "".join(parts), height


def doc_rule_heatmap_table(rule_ids, per_cell):
    """Sequential single-hue (blue) heatmap table: rows = arm-run, columns =
    doc rule id, cell = pass (✓)/fail (✗)/no-data (–) with a text label
    always shown alongside the icon (never icon-only)."""
    if not rule_ids:
        return '<p class="muted">No doc_rules.json for this task, or no runs have per-rule results yet.</p>'
    cells_keys = sorted(per_cell.keys(), key=lambda k: (ARM_ORDER.index(k[0]) if k[0] in ARM_ORDER else 99, k[1]))
    if not cells_keys:
        return '<p class="muted">No doc-rule results recorded for any run.</p>'

    head = "".join(f'<th scope="col">{esc(rid)}</th>' for rid in rule_ids)
    rows_html = []
    for (arm, run_id) in cells_keys:
        cell_vals = per_cell[(arm, run_id)]
        tds = []
        for rid in rule_ids:
            ok = cell_vals.get(rid)
            if ok is True:
                t, icon, label = 1.0, "✓", "pass"
            elif ok is False:
                t, icon, label = 0.15, "✗", "fail"
            else:
                t, icon, label = 0.0, "–", "no data"
            tds.append(
                f'<td class="heat-cell" style="--heat-t:{t:.3f}" '
                f'data-tip="{esc(rid)} ({esc(run_id)}): {label}">'
                f'<span class="sr-only">{esc(rid)}: </span>{icon} {label}</td>'
            )
        rows_html.append(f'<tr><th scope="row">{esc(ARM_LABELS.get(arm, arm))} {esc(run_id)}</th>{"".join(tds)}</tr>')

    return (
        '<table class="heatmap-table"><thead><tr><th scope="col">run</th>'
        f'{head}</tr></thead><tbody>{"".join(rows_html)}</tbody></table>'
    )


def gate_conformance_table(gate_rows):
    """Per-run gate-conformance table: init chain / sweep verified / edits
    before sweep / doc-rule coverage, each cell a checkmark/cross PLUS a
    text label (never icon-only)."""
    ordered = sorted(gate_rows, key=lambda r: (ARM_ORDER.index(r["arm"]) if r["arm"] in ARM_ORDER else 99, r["trial"] if r["trial"] is not None else 0))

    def _bool_cell(v):
        if v is True:
            return '<td class="gate-ok">✓ yes</td>'
        if v is False:
            return '<td class="gate-fail">✗ no</td>'
        return '<td class="muted">– n/a</td>'

    rows_html = []
    for r in ordered:
        edits = r.get("edits_before_sweep")
        edits_cell = (
            f'<td class="gate-ok">✓ 0</td>' if edits == 0
            else (f'<td class="gate-fail">✗ {edits}</td>' if isinstance(edits, (int, float)) else '<td class="muted">– n/a</td>')
        )
        cov = r.get("doc_rule_memories_coverage")
        cov_cell = f'<td>{fmt_pct(cov * 100 if isinstance(cov, (int, float)) else None)}</td>' if cov is not None else '<td class="muted">– n/a</td>'
        rows_html.append(
            f'<tr><td>{esc(ARM_LABELS.get(r["arm"], r["arm"]))}</td><td>{esc(r["trial"])}</td>'
            f'{_bool_cell(r.get("init_chain_complete"))}{_bool_cell(r.get("sweep_verified"))}'
            f'{edits_cell}{cov_cell}<td>{esc(r.get("memories_read_channel") or "–")}</td></tr>'
        )

    return (
        '<table class="fallback-table"><thead><tr><th>arm</th><th>trial</th>'
        '<th>init chain complete</th><th>sweep verified</th>'
        '<th>edits before sweep</th><th>doc-rule coverage</th><th>memory channel</th></tr></thead>'
        f'<tbody>{"".join(rows_html)}</tbody></table>'
    )


def pivot_gate_matrix_table(pivot_gate_rows):
    """Per-run task-1 + pivot gate-conformance ✓/✗ matrix (see
    pivot_gate_matrix_rows), for two-phase runs only. Same
    checkmark/cross-plus-text-label convention as gate_conformance_table.
    Empty input renders an explanatory muted message rather than an empty
    table, matching doc_rule_heatmap_table's empty-state convention.

    Column groups (Task 1 | Pivot) are marked with a spanning header row
    so the table stays readable when horizontally scrolled inside its
    card (see .table-wrap's overflow-x); a footnote flags the task-1
    sweep-verified value as unconfirmed pending phase-windowing (see the
    interim findings note on this)."""
    if not pivot_gate_rows:
        return '<p class="muted">No two-phase (pivot) runs in this stamp.</p>'

    ordered = sorted(pivot_gate_rows, key=lambda r: (ARM_ORDER.index(r["arm"]) if r["arm"] in ARM_ORDER else 99, r["trial"] if r["trial"] is not None else 0))

    def _bool_cell(v):
        if v is True:
            return '<td class="gate-ok">✓ yes</td>'
        if v is False:
            return '<td class="gate-fail">✗ no</td>'
        return '<td class="muted">– n/a</td>'

    def _int_cell(v, zero_ok=True):
        if not isinstance(v, (int, float)):
            return '<td class="muted">– n/a</td>'
        if zero_ok and v == 0:
            return f'<td class="gate-ok">✓ 0</td>'
        return f'<td class="gate-fail">✗ {v}</td>'

    rows_html = []
    for r in ordered:
        cov = r.get("pivot_doc_rule_memories_coverage")
        cov_cell = (
            f'<td>{fmt_pct(cov * 100)}</td>' if isinstance(cov, (int, float)) else '<td class="muted">– n/a</td>'
        )
        rows_html.append(
            f'<tr><td>{esc(ARM_LABELS.get(r["arm"], r["arm"]))}</td><td>{esc(r["trial"])}</td>'
            f'{_bool_cell(r.get("t1_init_chain_complete"))}{_bool_cell(r.get("t1_sweep_verified"))}'
            f'{_int_cell(r.get("t1_edits_before_sweep"))}'
            f'{_bool_cell(r.get("pivot_reclassified_attempted"))}'
            f'{_bool_cell(r.get("pivot_reclassified_succeeded"))}'
            f'{_bool_cell(r.get("pivot_resweep_verified"))}'
            f'{_int_cell(r.get("pivot_edits_before_sweep"))}'
            f'{cov_cell}</tr>'
        )

    return (
        '<div class="table-wrap"><table class="fallback-table gate-matrix-table">'
        '<thead>'
        '<tr class="gate-group-row"><th></th><th></th>'
        '<th colspan="3" class="gate-group-head">Task 1</th>'
        '<th colspan="5" class="gate-group-head">Pivot</th></tr>'
        '<tr><th>arm</th><th>trial</th>'
        '<th>init chain</th><th>sweep verified&#8224;</th><th>edits before sweep</th>'
        '<th>reclassify attempted</th><th>reclassify succeeded</th>'
        '<th>resweep verified</th><th>edits before resweep</th>'
        '<th>pivot doc-rule coverage</th></tr>'
        '</thead>'
        f'<tbody>{"".join(rows_html)}</tbody></table></div>'
        '<p class="section-subtitle" style="margin-top:6px">&#8224; task-1 sweep-verified value is unconfirmed pending phase-windowing.</p>'
    )


def memory_coverage_dot_chart(mem_rows, width=640, height=170):
    """Dot plot: doc-rule memory coverage (%) per run, arm-colored, with
    n_memories_read shown in the tooltip/fallback table."""
    pad_left = 150
    pad_right = 24
    pad_top = 14
    pad_bottom = 30
    plot_w = width - pad_left - pad_right
    arms_present = [a for a in ARM_ORDER if any(r["arm"] == a for r in mem_rows)]
    row_h = (height - pad_top - pad_bottom) / max(len(arms_present) or 1, 1)
    xscale = linear_scale((0, 100), (pad_left, width - pad_right))

    parts = [svg_open(width, height)]
    parts.append('<text x="0" y="10" class="chart-title" font-size="13">Doc-rule memory coverage per run (% of task doc_rules memories read)</text>')
    for tv in (0, 25, 50, 75, 100):
        x = xscale(tv)
        parts.append(f'<line x1="{x:.1f}" y1="{pad_top}" x2="{x:.1f}" y2="{height - pad_bottom}" class="grid-line" />')
        parts.append(f'<text x="{x:.1f}" y="{height - pad_bottom + 14}" class="tick-label" font-size="12" text-anchor="middle">{tv}%</text>')

    by_arm = {a: [] for a in arms_present}
    for r in mem_rows:
        if r["arm"] in by_arm:
            by_arm[r["arm"]].append(r)

    for i, arm in enumerate(arms_present):
        cy = pad_top + row_h * i + row_h / 2
        parts.append(f'<text x="{pad_left - 10}" y="{cy + 3:.1f}" text-anchor="end" class="row-label" font-size="12">{esc(ARM_LABELS.get(arm, arm))}</text>')
        for r in by_arm.get(arm, []):
            cov = r.get("doc_rule_memories_coverage")
            if cov is None:
                continue
            cx = xscale(cov * 100)
            color = f'var(--arm-{arm})'
            parts.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="{color}" stroke="var(--surface-1)" '
                f'stroke-width="2" class="mark-dot" '
                f'data-tip="{esc(ARM_LABELS.get(arm, arm))} t{esc(r["trial"])}: {fmt_pct(cov*100)} coverage, {r["n_memories_read"]} memories read">'
                f'<title>{esc(ARM_LABELS.get(arm, arm))} t{esc(r["trial"])}: {fmt_pct(cov*100)} coverage, {r["n_memories_read"]} memories read</title></circle>'
            )
    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------
# Per-run table.
# --------------------------------------------------------------------------


def short_test_name(test_id):
    """Shorten a unittest test id to 'Class.method'. Pure.

    Handles both observed shapes of the parenthesized part:
      - 'test_foo (tests.test_bar.MyTest)'            (older Python)
      - 'test_foo (tests.test_bar.MyTest.test_foo)'    (3.11+: full dotted
        path incl. the method name again)
    Falls back to the raw id when it doesn't match the expected shape."""
    m = re.match(r"^(\S+)\s+\(([\w.]+)\)$", test_id or "")
    if not m:
        return test_id
    method, path = m.group(1), m.group(2)
    segments = path.split(".")
    if segments and segments[-1] == method:
        segments = segments[:-1]
    cls = segments[-1] if segments else path
    return f"{cls}.{method}"


def failed_tests_cell_text(acc, reg):
    """Combine acceptance + regression failed_tests into one short display
    string for the per-run table cell (acceptance first, prefixed 'A:' /
    'R:' when both have failures). Empty string when neither has any."""
    acc_failed = [short_test_name(t) for t in (acc.get("failed_tests") or [])]
    reg_failed = [short_test_name(t) for t in (reg.get("failed_tests") or [])]
    parts = []
    if acc_failed:
        parts.append("A: " + ", ".join(acc_failed))
    if reg_failed:
        parts.append("R: " + ", ".join(reg_failed))
    return "; ".join(parts)


def per_run_table(rows):
    ordered = sorted(rows, key=lambda r: (ARM_ORDER.index(r.get("arm")) if r.get("arm") in ARM_ORDER else 99, r.get("trial") if r.get("trial") is not None else 0))
    any_pivot = any(isinstance(r.get("phases"), dict) and "task1" in r["phases"] and "pivot" in r["phases"] for r in rows)
    head_cols = [
        ("arm", "Arm"), ("trial", "Trial"), ("success", "Success"),
        ("acc", "Acceptance"), ("reg", "Regression"),
        ("failed_tests", "Failed tests"),
        ("turns", "Turns (all agents)"), ("turns_main", "Turns (main)"),
        ("total_tokens", "Total tokens"), ("output_tokens", "Output tokens"),
        ("cache_read", "Cache read"), ("tool_calls", "Tool calls"),
        ("memory_reads", "Memory consultations"),
        ("denials", "Denials"), ("stop_blocks", "Stop blocks"),
        ("wall_s", "Wall (s)"), ("cost", "Est. cost"), ("exit", "Exit/timeout"),
        ("state", "Final state"),
    ]
    if any_pivot:
        head_cols += [
            ("b1_doc", "B1 doc %"), ("b1_spec", "B1 spec %"),
            ("b2_doc", "B2 doc %"), ("b2_spec", "B2 spec %"),
            ("retention_regressions", "Retention regressions"),
            ("pivot_reclassified", "Pivot reclassified"),
        ]
    ths = "".join(f'<th scope="col" data-sort-key="{k}" tabindex="0" role="button">{esc(label)}<span class="sort-indicator" aria-hidden="true"></span></th>' for k, label in head_cols)

    trs = []
    for r in ordered:
        arm = r.get("arm")
        acc = r.get("acceptance") or {}
        reg = r.get("regression") or {}
        m = r.get("metrics") or {}
        usage = m.get("usage") or {}
        cost = m.get("est_cost_usd")
        success = acc.get("ok")
        exit_code = r.get("exit_code")
        timed_out = r.get("timed_out")
        exit_str = f'timeout' if timed_out else (str(exit_code) if exit_code is not None else "—")
        state = g(r, "stream_metrics", "final_workflow_state")

        def cell(val, sort_val=None, cls=""):
            sv = sort_val if sort_val is not None else val
            return f'<td data-sort="{esc(sv)}" class="{cls}">{esc(val)}</td>'

        tool_calls_val = m.get("total_tool_calls") if "total_tool_calls" in m else m.get("tool_calls")
        failed_str = failed_tests_cell_text(acc, reg)

        row_cells = [
            cell(ARM_LABELS.get(arm, arm), sort_val=arm),
            cell(r.get("trial")),
            cell("yes" if success else ("no" if success is False else "—"), sort_val=1 if success else 0, cls="success-yes" if success else ("success-no" if success is False else "")),
            cell(f'{acc.get("passed", "—")}/{acc.get("total", "—")}', sort_val=acc.get("passed") or 0),
            cell("ok" if reg.get("ok") else ("fail" if reg.get("ok") is False else "—"), sort_val=1 if reg.get("ok") else 0),
            cell(failed_str or "—", sort_val=failed_str),
            cell(fmt_num(m.get("assistant_turns_incl_subagents")), sort_val=m.get("assistant_turns_incl_subagents") or 0),
            cell(fmt_num(m.get("num_turns")), sort_val=m.get("num_turns") or 0),
            cell(fmt_num(m.get("total_tokens")), sort_val=m.get("total_tokens") or 0),
            cell(fmt_num(usage.get("output_tokens")), sort_val=usage.get("output_tokens") or 0),
            cell(fmt_num(usage.get("cache_read_input_tokens")), sort_val=usage.get("cache_read_input_tokens") or 0),
            cell(fmt_num(tool_calls_val), sort_val=tool_calls_val or 0),
            cell(fmt_num(m.get("memory_file_reads")), sort_val=m.get("memory_file_reads") or 0),
            cell(fmt_num(m.get("hook_denials")), sort_val=m.get("hook_denials") or 0),
            cell(fmt_num(m.get("stop_hook_blocks")), sort_val=m.get("stop_hook_blocks") or 0),
            cell(fmt_num(r.get("wall_s"), 1), sort_val=r.get("wall_s") or 0),
            cell(fmt_cost(cost), sort_val=cost or 0),
            cell(exit_str, sort_val=exit_str),
            cell(state or "—", sort_val=state or ""),
        ]

        if any_pivot:
            phases = r.get("phases")
            has_phases = isinstance(phases, dict) and "task1" in phases and "pivot" in phases
            if has_phases:
                b1 = (phases.get("task1") or {}).get("benchmark") or {}
                b2 = (phases.get("pivot") or {}).get("benchmark") or {}
                retention = (phases.get("pivot") or {}).get("task1_retention") or {}
                reclass = g(phases, "pivot", "gates", "pivot_reclassified", default={}) or {}
                b1_doc = _phase_benchmark_pct(b1, "doc")
                b1_spec = _phase_benchmark_pct(b1, "spec")
                b2_doc = _phase_benchmark_pct(b2, "doc")
                b2_spec = _phase_benchmark_pct(b2, "spec")
                n_regressions = len(retention.get("regressions") or [])
                if reclass.get("succeeded"):
                    reclass_str = "succeeded"
                elif reclass.get("attempted"):
                    reclass_str = "attempted only"
                else:
                    reclass_str = "no"
                row_cells += [
                    cell(fmt_pct(b1_doc), sort_val=b1_doc if b1_doc is not None else -1),
                    cell(fmt_pct(b1_spec), sort_val=b1_spec if b1_spec is not None else -1),
                    cell(fmt_pct(b2_doc), sort_val=b2_doc if b2_doc is not None else -1),
                    cell(fmt_pct(b2_spec), sort_val=b2_spec if b2_spec is not None else -1),
                    cell(n_regressions, sort_val=n_regressions, cls="gate-fail" if n_regressions else "gate-ok"),
                    cell(reclass_str, sort_val=reclass_str),
                ]
            else:
                row_cells += [cell("—", sort_val=-1) for _ in range(4)] + [cell("—", sort_val=0), cell("—", sort_val="")]

        trs.append(f'<tr>{"".join(row_cells)}</tr>')

    return f'<table class="run-table" id="run-table"><thead><tr>{ths}</tr></thead><tbody>{"".join(trs)}</tbody></table>'


# --------------------------------------------------------------------------
# KPI row.
# --------------------------------------------------------------------------


def kpi_row(agg):
    """Legacy per-arm KPI cards. Still used as the "Data" fallback under the
    new scorecard (kept + tested for backward compat with existing markup
    expectations: '.kpi-card' must appear somewhere in the document)."""
    arms = agg.get("arms", {})
    cells = []
    for arm in ARM_ORDER:
        s = arms.get(arm)
        if not s:
            continue
        stats = s.get("stats", {})
        cells.append(f"""
        <div class="kpi-card" style="--arm-accent: var(--arm-{arm})">
          <div class="kpi-arm"><span class="chip" style="background:var(--arm-{arm})"></span>{esc(ARM_LABELS.get(arm, arm))}</div>
          <dl class="kpi-list">
            <div><dt>success rate</dt><dd>{fmt_pct((s.get('success_rate') or 0) * 100)}</dd></div>
            <div><dt>median turns (all agents)</dt><dd>{fmt_num(stats.get('assistant_turns_incl_subagents', {}).get('median'), 1)}</dd></div>
            <div><dt>median turns (main-agent)</dt><dd>{fmt_num(stats.get('num_turns', {}).get('median'), 1)}</dd></div>
            <div><dt>median total tokens</dt><dd>{fmt_num(stats.get('total_tokens', {}).get('median'))}</dd></div>
            <div><dt>median wall time</dt><dd>{fmt_num(stats.get('wall_s', {}).get('median'), 0)}s</dd></div>
            <div><dt>median est. cost <span class="muted">(notional)</span></dt><dd>{fmt_cost(stats.get('est_cost_usd', {}).get('median'))}</dd></div>
          </dl>
        </div>""")
    return "".join(cells)


def _scorecard_cell_html(row, arm, control_arm):
    """One scorecard body cell: big value + small delta-vs-control line.
    control_arm's own cell shows just the value (it IS the reference, so no
    self-delta) labeled 'reference'."""
    cell = row["cells"].get(arm, {})
    val = cell.get("value")
    unit = row["unit"]
    extra = cell.get("extra")

    if unit == "pct":
        value_str = fmt_pct(val)
    elif unit == "frac":
        value_str = extra or "—"
    elif unit == "wall":
        value_str = f"{fmt_num(val, 0)}s" if val is not None else "—"
    else:
        value_str = fmt_num(val)

    is_best = row.get("best_arm") == arm and val is not None
    best_tag = ' <span class="best-tag">best</span>' if is_best else ""
    value_cls = "scorecard-value best" if is_best else "scorecard-value"

    if arm == control_arm:
        delta_html = '<div class="scorecard-delta muted">reference</div>'
    else:
        d = cell.get("delta_pct")
        if d is None:
            delta_html = '<div class="scorecard-delta muted">—</div>'
        else:
            arrow = "▲" if d > 0 else ("▼" if d < 0 else "–")
            delta_html = (
                f'<div class="scorecard-delta" data-tip="{esc(ARM_LABELS.get(arm, arm))} vs no harness: {d:+.0f}%">'
                f'{arrow} {abs(d):.0f}% <span class="muted">vs no harness</span></div>'
            )

    arm_label_short = esc(ARM_LABELS.get(arm, arm).split(" (")[0])
    return (
        f'<td class="scorecard-cell" data-sort="{val if val is not None else ""}" '
        f'data-arm-label="{arm_label_short}">'
        f'<div class="{value_cls}">{value_str}{best_tag}</div>{delta_html}</td>'
    )


def scorecard_html(agg):
    """Top scorecard: 3-column arm comparison, 6 key rows, each cell a big
    number + small delta-vs-control line. Control column itself reads
    'reference' instead of a self-delta. Falls back to an em-dash row when a
    metric has no data for any arm (v1 rows: doc/spec pct are None for
    every arm) rather than hiding the row, so the row count stays fixed and
    the 'not measured in this run' framing is explicit."""
    sc = scorecard_data(agg)
    present = sc["arms_present"]
    control_arm = sc["control_arm"]
    if not present:
        return '<p class="muted">No runs to report.</p>'

    head_cells = []
    for arm in present:
        chip = f'<span class="chip" style="background:var(--arm-{arm})"></span>'
        sub = "no harness" if arm == control_arm else esc(ARM_LABELS.get(arm, arm).split(" (")[-1].rstrip(")"))
        head_cells.append(
            f'<th scope="col" class="scorecard-head"><div class="scorecard-head-arm">{chip}{esc(ARM_LABELS.get(arm, arm).split(" (")[0])}</div>'
            f'<div class="scorecard-head-ver muted">{sub}</div></th>'
        )

    body_rows = []
    any_data = {row["key"]: any(row["cells"].get(a, {}).get("value") is not None for a in present) for row in sc["rows"]}
    for row in sc["rows"]:
        if not any_data[row["key"]]:
            cells_html = "".join(
                f'<td class="scorecard-cell" data-arm-label="{esc(ARM_LABELS.get(a, a).split(" (")[0])}">'
                f'<div class="scorecard-value muted">not measured</div></td>' for a in present
            )
        else:
            cells_html = "".join(_scorecard_cell_html(row, a, control_arm) for a in present)
        body_rows.append(f'<tr><th scope="row" class="scorecard-row-label">{esc(row["label"])}</th>{cells_html}</tr>')

    return (
        '<div class="scorecard-wrap"><table class="scorecard-table">'
        f'<thead><tr><th scope="col" class="scorecard-corner"></th>{"".join(head_cells)}</tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody></table></div>'
    )


def _two_phase_scorecard_block_html(title, subtitle, block_data, present, control_arm, retention=False):
    """One labeled scorecard block ("Benchmark 1 — after task 1" /
    "Benchmark 2 — after pivot"): doc-rule pass %, spec pass %, full
    success x/n per arm, plus (B2 only) task-1 retention x/n. Same
    big-value/delta-line cell convention as _scorecard_cell_html, but the
    delta is omitted here (this block reads pivot_benchmark_stats output,
    which doesn't carry a vs_baseline/vs_control shape) — cells show the
    value only, best-tagged per row."""
    rows_spec = [("doc_pass_pct", "Doc-rule pass %", "pct"), ("spec_pass_pct", "Spec pass %", "pct"),
                 ("success_x_n", "Full success (x/n)", "raw")]
    if retention:
        rows_spec.append(("retention_x_n", "Task-1 retention (x/n)", "raw"))

    head_cells = []
    for arm in present:
        chip = f'<span class="chip" style="background:var(--arm-{arm})"></span>'
        sub = "no harness" if arm == control_arm else esc(ARM_LABELS.get(arm, arm).split(" (")[-1].rstrip(")"))
        head_cells.append(
            f'<th scope="col" class="scorecard-head"><div class="scorecard-head-arm">{chip}{esc(ARM_LABELS.get(arm, arm).split(" (")[0])}</div>'
            f'<div class="scorecard-head-ver muted">{sub}</div></th>'
        )

    body_rows = []
    for key, label, unit in rows_spec:
        best_arm, best_val = None, None
        cell_vals = {}
        for arm in present:
            d = block_data.get(arm, {})
            if key == "retention_x_n":
                val = d.get("retention_rate")
                extra = None
                if d.get("retention_rate") is not None and "success_x_n" in d:
                    n = d["success_x_n"].split("/")[-1] if d.get("success_x_n") else None
                    extra = f"{fmt_pct(d.get('retention_rate'))}"
                    regressions = d.get("retention_regressions") or 0
                    if regressions:
                        extra += f" ({regressions} regression(s))"
            elif unit == "pct":
                val = d.get(key)
                extra = None
            else:
                val = None
                extra = d.get(key)
            cell_vals[arm] = (val, extra)
            if val is not None and (best_val is None or val > best_val):
                best_val, best_arm = val, arm

        cells_html = []
        any_val = any(v is not None or e is not None for (v, e) in cell_vals.values())
        for arm in present:
            arm_label_short = esc(ARM_LABELS.get(arm, arm).split(" (")[0])
            val, extra = cell_vals[arm]
            if val is None and extra is None:
                cells_html.append(f'<td class="scorecard-cell" data-arm-label="{arm_label_short}"><div class="scorecard-value muted">not measured</div></td>')
                continue
            is_best = (arm == best_arm and val is not None)
            best_tag = ' <span class="best-tag">best</span>' if is_best else ""
            value_cls = "scorecard-value best" if is_best else "scorecard-value"
            display = fmt_pct(val) if unit == "pct" else (extra or "—")
            cells_html.append(f'<td class="scorecard-cell" data-arm-label="{arm_label_short}"><div class="{value_cls}">{display}{best_tag}</div></td>')
        if not any_val:
            cells_html = [
                f'<td class="scorecard-cell" data-arm-label="{esc(ARM_LABELS.get(a, a).split(" (")[0])}">'
                f'<div class="scorecard-value muted">not measured</div></td>' for a in present
            ]
        body_rows.append(f'<tr><th scope="row" class="scorecard-row-label">{esc(label)}</th>{"".join(cells_html)}</tr>')

    return f"""
    <div class="two-phase-block">
      <h3>{esc(title)}</h3>
      <p class="section-subtitle">{esc(subtitle)}</p>
      <div class="scorecard-wrap"><table class="scorecard-table">
        <thead><tr><th scope="col" class="scorecard-corner"></th>{"".join(head_cells)}</tr></thead>
        <tbody>{"".join(body_rows)}</tbody>
      </table></div>
    </div>"""


def two_phase_scorecard_html(agg):
    """Two labeled scorecard blocks ("Benchmark 1 — after task 1" /
    "Benchmark 2 — after pivot"), each a per-arm doc/spec/success table;
    B2 additionally shows task-1 retention x/n. Empty string when no arm
    has any pivot rows (single-phase stamp) -- caller omits the Pivot
    section entirely in that case."""
    tp = two_phase_scorecard_data(agg)
    present = tp["arms_present"]
    if not present:
        return ""
    control_arm = "control" if "control" in present else None
    b1_html = _two_phase_scorecard_block_html(
        "Benchmark 1 — after task 1",
        "Scored on the tree immediately after task 1, before the pivot prompt is ever shown.",
        tp["b1"], present, control_arm, retention=False)
    b2_html = _two_phase_scorecard_block_html(
        "Benchmark 2 — after pivot",
        "Scored on the final tree after the pivot phase; retention is task-1's own hidden tests re-run on this tree.",
        tp["b2"], present, control_arm, retention=True)
    return f'<div class="two-phase-scorecard-grid">{b1_html}{b2_html}</div>'


# --------------------------------------------------------------------------
# Overall review: the top-of-report single comparison block.
# --------------------------------------------------------------------------

_OVERALL_ROW_DEFS = [
    ("t1_spec", "Task 1 spec", True),
    ("t1_doc", "Task 1 doc rules", True),
    ("pv_spec", "Pivot spec", True),
    ("pv_doc", "Pivot doc rules", True),
    ("all_doc", "All doc rules combined", True),
    ("t1_retention", "Task-1 retention after pivot", True),
]


def _overall_cell_html(xy, pct, is_best):
    best_tag = ' <span class="best-tag">best</span>' if is_best else ""
    pct_str = f' <span class="muted">({pct:.0f}%)</span>' if pct is not None else ""
    cls = "overall-value best" if is_best else "overall-value"
    return f'<td class="overall-cell"><div class="{cls}">{esc(xy)}{pct_str}{best_tag}</div></td>'


def overall_review_table_html(review):
    """Full Overall review comparison table: Correctness / Process / Code /
    Efficiency row groups, one column per arm. "best" is tagged only on
    strict per-row winners (see strict_best_arm -- never on ties or
    all-zero rows)."""
    present = review["arms_present"]
    cells = review["cells"]
    control_arm = review["control_arm"]
    if not present:
        return '<p class="muted">No runs to report.</p>'

    head_cells = []
    for arm in present:
        chip = f'<span class="chip" style="background:var(--arm-{arm})"></span>'
        ver = ARM_LABELS.get(arm, arm).split(" (")[-1].rstrip(")")
        head_cells.append(
            f'<th scope="col" class="overall-head"><div class="overall-head-arm">{chip}'
            f'{esc(ARM_LABELS.get(arm, arm).split(" (")[0])}</div>'
            f'<div class="overall-head-ver muted">{esc(ver)}</div></th>'
        )

    def _group_header(label):
        return f'<tr class="overall-group-row"><th colspan="{len(present) + 1}">{esc(label)}</th></tr>'

    body = ['<thead><tr><th scope="col" class="overall-corner"></th>' + "".join(head_cells) + "</tr></thead><tbody>"]

    body.append(_group_header("Correctness"))
    body.append('<tr class="overall-note-row"><td colspan="' + str(len(present) + 1) + '" class="overall-note">strict convention-compliance tests; a failed rule means the documented convention was not applied, not broken code (spec tests all passed everywhere)</td></tr>')
    for key, label, higher in _OVERALL_ROW_DEFS:
        vals = {a: cells[a][key][1] for a in present}
        best = strict_best_arm(vals, higher_is_better=higher)
        row_cells = "".join(_overall_cell_html(cells[a][key][0], cells[a][key][1], a == best) for a in present)
        body.append(f'<tr><th scope="row" class="overall-row-label">{esc(label)}</th>{row_cells}</tr>')

    body.append(_group_header("Process"))
    cov_vals = {a: cells[a]["read_all_memories_pct"] for a in present}
    cov_best = strict_best_arm(cov_vals, higher_is_better=True)
    cov_cells = "".join(
        f'<td class="overall-cell"><div class="{"overall-value best" if a == cov_best else "overall-value"}">{fmt_pct(cells[a]["read_all_memories_pct"])}{" <span class=\"best-tag\">best</span>" if a == cov_best else ""}</div></td>'
        for a in present
    )
    body.append(f'<tr><th scope="row" class="overall-row-label">Rule-memory coverage</th>{cov_cells}</tr>')

    def _gate_glyph(arm, gate_key):
        c = cells[arm]
        if not c.get("has_pivot_rows") and arm == control_arm:
            return '<td class="overall-cell"><span class="muted">n/a &mdash; no harness</span></td>'
        v = c["gates"].get(gate_key)
        if v is True:
            return '<td class="overall-cell"><span class="gate-ok">&#10003;</span></td>'
        if v is False:
            return '<td class="overall-cell"><span class="gate-fail">&#10007;</span></td>'
        return '<td class="overall-cell"><span class="muted">&mdash;</span></td>'

    for gate_key, gate_label in (("t1_init", "Init chain complete"), ("t1_sweep", "Sweep verified"), ("pv_resweep", "Pivot resweep verified")):
        row_cells = "".join(_gate_glyph(a, gate_key) for a in present)
        body.append(f'<tr><th scope="row" class="overall-row-label">{esc(gate_label)}</th>{row_cells}</tr>')

    body.append(_group_header("Code"))
    body.append('<tr class="overall-note-row"><td colspan="' + str(len(present) + 1) + '" class="overall-note">size/shape proxies, not quality judgments</td></tr>')
    code = review.get("code_cells") or {}
    for key, label, higher in (
        ("loc_added", "LOC added", None), ("files_added", "Files added", None),
        ("agent_test_count", "Tests the agent wrote", True),
        ("avg_function_length", "Avg function length", False),
        ("docstring_coverage", "Docstring coverage", True),
        ("size_vs_reference_pct", "Size vs reference", None),
    ):
        vals = {a: (code.get(a) or {}).get(key) for a in present}
        best = strict_best_arm(vals, higher_is_better=higher) if higher is not None else None
        row_cells = []
        for a in present:
            v = vals.get(a)
            if key == "docstring_coverage":
                vs = fmt_pct(v * 100) if v is not None else "—"
            elif key == "size_vs_reference_pct":
                vs = fmt_pct(v) if v is not None else "—"
            elif key == "avg_function_length":
                vs = f"{v:.1f}" if v is not None else "—"
            else:
                vs = fmt_num(v) if v is not None else "—"
            is_best = (a == best)
            best_tag = ' <span class="best-tag">best</span>' if is_best else ""
            cls = "overall-value best" if is_best else "overall-value"
            row_cells.append(f'<td class="overall-cell"><div class="{cls}">{vs}{best_tag}</div></td>')
        body.append(f'<tr><th scope="row" class="overall-row-label">{esc(label)}</th>{"".join(row_cells)}</tr>')

    body.append(_group_header("Efficiency"))
    ctrl_vals = cells.get(control_arm) if control_arm else None
    for key, label, unit in (
        ("total_tokens", "Tokens (M)", "M"), ("turns", "Turns", "num"),
        ("wall_s", "Wall time", "wall"), ("tool_calls", "Tool calls", "num"),
        ("memory_reads", "Memory reads", "num"),
    ):
        vals = {a: cells[a].get(key) for a in present}
        best = strict_best_arm(vals, higher_is_better=False)
        row_cells = []
        for a in present:
            v = vals.get(a)
            if v is None:
                vs = "—"
            elif unit == "M":
                vs = f"{v / 1e6:.1f}M"
            elif unit == "wall":
                m, s = divmod(int(v), 60)
                vs = f"{m}:{s:02d}"
            else:
                vs = fmt_num(v)
            is_best = (a == best)
            best_tag = ' <span class="best-tag">best</span>' if is_best else ""
            cls = "overall-value best" if is_best else "overall-value"
            delta = ""
            if ctrl_vals and a != control_arm and v is not None:
                cv = ctrl_vals.get(key)
                if cv:
                    d = 100.0 * (v - cv) / cv
                    delta = f'<div class="overall-delta muted">{d:+.0f}% vs no harness</div>'
            row_cells.append(f'<td class="overall-cell"><div class="{cls}">{vs}{best_tag}</div>{delta}</td>')
        body.append(f'<tr><th scope="row" class="overall-row-label">{esc(label)}</th>{"".join(row_cells)}</tr>')

    body.append("</tbody>")
    return f'<div class="overall-wrap"><table class="overall-table">{"".join(body)}</table></div>'


def cost_vs_benefit_html(review):
    """Renders the "Is using a harness worth it?" heading + answer +
    per-arm cost-vs-benefit lines, as the Overall review's lead block."""
    cv = cost_vs_benefit_verdict(review)
    lines_html = "".join(f'<li>{esc(_cost_vs_benefit_line_text(l))}</li>' for l in cv["lines"])
    lines_block = f'<ul class="cost-benefit-lines">{lines_html}</ul>' if lines_html else ""
    return f"""
    <div class="cost-benefit-block">
      <h3>{esc(cv["question"])}</h3>
      <p class="cost-benefit-answer">{esc(cv["answer"])}</p>
      {lines_block}
    </div>"""


def quadrant_chart(review, width=560, height=360):
    """Cost-vs-compliance scatter/quadrant: x = tokens (M), y = combined
    doc-rule pass % (task1+pivot), one dot per arm, direct labels."""
    present = review["arms_present"]
    cells = review["cells"]
    points = []
    for arm in present:
        c = cells[arm]
        tok = c.get("total_tokens")
        _xy_str, pct = c["all_doc"]
        if tok is None or pct is None:
            continue
        points.append((arm, tok / 1e6, pct))

    pad_left, pad_right, pad_top, pad_bottom = 56, 24, 42, 40
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    xs = [p[1] for p in points] or [0, 1]
    ys = [p[2] for p in points] or [0, 100]
    x_lo, x_hi = min(0, min(xs)), max(xs) * 1.15 if xs else 1
    y_lo, y_hi = 0, 100

    x_ticks = nice_ticks(x_lo, x_hi, 5)
    xscale = linear_scale((min(x_ticks[0], x_lo), max(x_ticks[-1], x_hi)), (pad_left, width - pad_right))
    y_ticks = [0, 25, 50, 75, 100]
    yscale = linear_scale((y_lo, y_hi), (height - pad_bottom, pad_top))

    parts = [svg_open(width, height)]
    parts.append(f'<text x="0" y="12" class="chart-title" font-size="13">Cost vs. documented-rule compliance</text>')
    parts.append(f'<text x="0" y="30" class="legend-label" font-size="12">doc-rule pass % &#8593; (y) &middot; tokens (M) &#8594; (x)</text>')

    for tv in x_ticks:
        x = xscale(tv)
        parts.append(f'<line x1="{x:.1f}" y1="{pad_top}" x2="{x:.1f}" y2="{height - pad_bottom}" class="grid-line" />')
        parts.append(f'<text x="{x:.1f}" y="{height - pad_bottom + 16}" class="tick-label" font-size="12" text-anchor="middle">{tv:g}M</text>')
    for tv in y_ticks:
        y = yscale(tv)
        parts.append(f'<line x1="{pad_left}" y1="{y:.1f}" x2="{width - pad_right}" y2="{y:.1f}" class="grid-line" />')
        parts.append(f'<text x="{pad_left - 8}" y="{y + 4:.1f}" class="tick-label" font-size="12" text-anchor="end">{tv}%</text>')

    for arm, tok_m, pct in points:
        cx, cy = xscale(tok_m), yscale(pct)
        color = f'var(--arm-{arm})'
        label = ARM_LABELS.get(arm, arm).split(" (")[0]
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="7" fill="{color}" stroke="var(--surface-1)" '
            f'stroke-width="2" class="mark-dot" data-tip="{esc(label)}: {tok_m:.1f}M tokens, {pct:.0f}% doc-rule pass">'
            f'<title>{esc(label)}: {tok_m:.1f}M tokens, {pct:.0f}% doc-rule pass</title></circle>'
        )
        parts.append(
            f'<text x="{cx + 10:.1f}" y="{cy + 4:.1f}" class="row-label" font-size="12">{esc(label)}</text>'
        )

    parts.append("</svg>")
    return "".join(parts), height


# --------------------------------------------------------------------------
# Delegation: subagent usage per arm.
# --------------------------------------------------------------------------


def delegation_table_html(deleg_rows):
    if not deleg_rows:
        return '<p class="muted">No delegation data recorded.</p>'
    rows_html = []
    for r in deleg_rows:
        main_pct = (
            f'{100.0 * r["main_tokens"] / r["total_tokens"]:.0f}%'
            if (r.get("main_tokens") is not None and r.get("total_tokens")) else "—"
        )
        rows_html.append(
            f'<tr><td>{esc(ARM_LABELS.get(r["arm"], r["arm"]))}</td><td>{esc(r["trial"])}</td>'
            f'<td>{fmt_num(r.get("subagent_launches"))}</td><td>{fmt_num(r.get("subagent_messages"))}</td>'
            f'<td>{fmt_num(r.get("main_tokens"))}</td><td>{fmt_num(r.get("subagent_tokens"))}</td>'
            f'<td>{main_pct}</td><td>{fmt_num(r.get("wall_s"), 0)}s</td>'
            f'<td class="muted">—</td><td class="muted">—</td></tr>'
        )
    return (
        '<table class="fallback-table"><thead><tr><th>arm</th><th>trial</th>'
        '<th>subagent launches</th><th>subagent messages</th>'
        '<th>main tokens</th><th>subagent tokens</th><th>main %</th><th>wall time</th>'
        '<th>task1-phase launches</th><th>pivot-phase launches</th></tr></thead>'
        f'<tbody>{"".join(rows_html)}</tbody></table>'
    )


def delegation_chart(deleg_rows, width=560, row_h=26, gap=8):
    """Paired horizontal bar per arm: main tokens vs subagent tokens."""
    by_arm = {}
    for r in deleg_rows:
        by_arm.setdefault(r["arm"], {"main": 0, "sub": 0})
        by_arm[r["arm"]]["main"] += r.get("main_tokens") or 0
        by_arm[r["arm"]]["sub"] += r.get("subagent_tokens") or 0

    arms = [a for a in ARM_ORDER if a in by_arm]
    pad_left, pad_right, pad_top = 130, 130, 20
    plot_w = width - pad_left - pad_right
    height = pad_top + len(arms) * (2 * row_h + gap) + 16

    max_v = max([v for d in by_arm.values() for v in d.values()] + [1])
    # Bars scale to at most 78% of plot_w, leaving headroom in pad_right
    # for the "main 17,204,795" label text after the bar's end.
    xscale = linear_scale((0, max_v / 0.78), (0, plot_w))

    parts = [svg_open(width, height)]
    parts.append(f'<text x="0" y="12" class="chart-title" font-size="13">Main vs. subagent tokens per arm</text>')

    y = pad_top + 14
    for arm in arms:
        d = by_arm[arm]
        label = ARM_LABELS.get(arm, arm).split(" (")[0]
        parts.append(f'<text x="{pad_left - 10}" y="{y + row_h:.1f}" text-anchor="end" class="row-label" font-size="12">{esc(label)}</text>')
        for key, dy, cls in (("main", 0, "main"), ("sub", row_h, "sub")):
            w = xscale(d[key])
            color = f'var(--arm-{arm})' if key == "main" else f'color-mix(in oklab, var(--arm-{arm}) 55%, var(--surface-1))'
            parts.append(
                f'<rect x="{pad_left}" y="{y + dy:.1f}" width="{w:.1f}" height="{row_h - 4}" fill="{color}" '
                f'class="mark-bar" data-tip="{esc(label)} {key} tokens: {fmt_num(d[key])}">'
                f'<title>{esc(label)} {key} tokens: {fmt_num(d[key])}</title></rect>'
            )
            parts.append(f'<text x="{pad_left + w + 6:.1f}" y="{y + dy + row_h/2:.1f}" class="tick-label" font-size="12">{"main" if key=="main" else "sub"} {fmt_num(d[key])}</text>')
        y += 2 * row_h + gap

    parts.append("</svg>")
    return "".join(parts), height


# --------------------------------------------------------------------------
# Code metrics section.
# --------------------------------------------------------------------------


def code_metrics_summary_by_arm(cmr_rows):
    """Aggregate code_metrics_rows() (per-run) into per-arm summary cells
    for the Overall review's Code group + the Code section's table. Sums
    LOC/files/tests across an arm's runs; averages the ast shape metrics.
    Pure."""
    by_arm = {}
    for r in cmr_rows:
        arm = r["arm"]
        m = r["metrics"]
        entry = by_arm.setdefault(arm, {
            "loc_added": 0, "files_added": 0, "agent_test_count": 0,
            "avg_function_length_vals": [], "docstring_coverage_vals": [],
            "size_vs_reference_pct_vals": [], "n": 0,
        })
        ft = m["fixture_to_final"]
        entry["loc_added"] += ft["loc_added"]
        entry["files_added"] += ft["files_added"]
        entry["agent_test_count"] += m["agent_test_count"]
        if m["ast"]["avg_function_length"] is not None:
            entry["avg_function_length_vals"].append(m["ast"]["avg_function_length"])
        if m["ast"]["docstring_coverage"] is not None:
            entry["docstring_coverage_vals"].append(m["ast"]["docstring_coverage"])
        if m["size_vs_reference_pct"] is not None:
            entry["size_vs_reference_pct_vals"].append(m["size_vs_reference_pct"])
        entry["n"] += 1

    out = {}
    for arm, e in by_arm.items():
        out[arm] = {
            "loc_added": e["loc_added"],
            "files_added": e["files_added"],
            "agent_test_count": e["agent_test_count"],
            "avg_function_length": (sum(e["avg_function_length_vals"]) / len(e["avg_function_length_vals"])) if e["avg_function_length_vals"] else None,
            "docstring_coverage": (sum(e["docstring_coverage_vals"]) / len(e["docstring_coverage_vals"])) if e["docstring_coverage_vals"] else None,
            "size_vs_reference_pct": (sum(e["size_vs_reference_pct_vals"]) / len(e["size_vs_reference_pct_vals"])) if e["size_vs_reference_pct_vals"] else None,
        }
    return out


def code_metrics_table_html(cmr_rows):
    if not cmr_rows:
        return '<p class="muted">No code-metrics data (work/ git repo not found for any run).</p>'
    rows_html = []
    for r in cmr_rows:
        m = r["metrics"]
        ft = m["fixture_to_final"]
        ast_m = m["ast"]
        avg_len = f'{ast_m["avg_function_length"]:.1f}' if ast_m["avg_function_length"] is not None else "—"
        docstring_cov = fmt_pct(ast_m["docstring_coverage"] * 100) if ast_m["docstring_coverage"] is not None else "—"
        complexity = f'{ast_m["avg_complexity"]:.1f}' if ast_m["avg_complexity"] is not None else "—"
        longest = esc(ast_m["longest_file"][0]) if ast_m["longest_file"] else "—"
        size_vs_ref = fmt_pct(m["size_vs_reference_pct"]) if m["size_vs_reference_pct"] is not None else "—"
        rows_html.append(
            f'<tr><td>{esc(ARM_LABELS.get(r["arm"], r["arm"]))}</td><td>{esc(r["trial"])}</td>'
            f'<td>{fmt_num(ft["loc_added"])}</td><td>{fmt_num(ft["loc_deleted"])}</td>'
            f'<td>{fmt_num(ft["files_added"])}</td><td>{fmt_num(ft["files_modified"])}</td>'
            f'<td>{fmt_num(m["agent_test_count"])}</td>'
            f'<td>{avg_len}</td><td>{docstring_cov}</td><td>{complexity}</td>'
            f'<td>{longest}</td><td>{size_vs_ref}</td></tr>'
        )
    return (
        '<table class="fallback-table"><thead><tr><th>arm</th><th>trial</th>'
        '<th>LOC added</th><th>LOC deleted</th><th>files added</th><th>files modified</th>'
        '<th>tests written</th><th>avg fn length</th><th>docstring coverage</th>'
        '<th>avg complexity</th><th>longest file</th><th>size vs reference</th></tr></thead>'
        f'<tbody>{"".join(rows_html)}</tbody></table>'
    )


def code_metrics_loc_chart(cmr_summary, width=520, row_h=28, gap=10):
    """Small bar chart: LOC added per arm (fixture->final, agent-added +
    modified, non-excluded paths)."""
    arms = [a for a in ARM_ORDER if a in cmr_summary]
    pad_left, pad_right, pad_top = 100, 60, 20
    plot_w = width - pad_left - pad_right
    height = pad_top + len(arms) * (row_h + gap) + 10
    max_v = max([cmr_summary[a]["loc_added"] for a in arms] + [1])
    xscale = linear_scale((0, max_v * 1.1), (0, plot_w))

    parts = [svg_open(width, height)]
    parts.append(f'<text x="0" y="12" class="chart-title" font-size="13">LOC added per arm</text>')
    y = pad_top
    for arm in arms:
        v = cmr_summary[arm]["loc_added"]
        w = xscale(v)
        label = ARM_LABELS.get(arm, arm).split(" (")[0]
        parts.append(f'<text x="{pad_left - 10}" y="{y + row_h/2 + 4:.1f}" text-anchor="end" class="row-label" font-size="12">{esc(label)}</text>')
        parts.append(
            f'<rect x="{pad_left}" y="{y:.1f}" width="{w:.1f}" height="{row_h - 4}" fill="var(--arm-{arm})" '
            f'class="mark-bar" data-tip="{esc(label)}: {fmt_num(v)} LOC added"><title>{esc(label)}: {fmt_num(v)} LOC added</title></rect>'
        )
        parts.append(f'<text x="{pad_left + w + 6:.1f}" y="{y + row_h/2 + 4:.1f}" class="tick-label" font-size="12">{fmt_num(v)}</text>')
        y += row_h + gap
    parts.append("</svg>")
    return "".join(parts), height


def code_metrics_shape_dot_chart(cmr_summary, width=520, height=170):
    """Dot chart: avg function length (x, lines) vs docstring coverage
    (color intensity via position on a 0-100% secondary track), one dot
    per arm. Simple two-row layout: length dots on one scale, coverage %
    on a second row for direct comparability."""
    arms = [a for a in ARM_ORDER if a in cmr_summary]
    pad_left, pad_right, pad_top, pad_bottom = 150, 24, 14, 30
    plot_w = width - pad_left - pad_right

    lengths = [cmr_summary[a]["avg_function_length"] for a in arms if cmr_summary[a]["avg_function_length"] is not None]
    lo, hi = (min(lengths), max(lengths)) if lengths else (0, 1)
    if lo == hi:
        lo, hi = max(0, lo - 5), hi + 5
    ticks = nice_ticks(lo, hi, 4)
    t_lo, t_hi = min(ticks[0], lo), max(ticks[-1], hi)
    # Dots occupy only the left ~55% of the plot area (extend the domain's
    # upper bound well past t_hi) so the "N.N lines, NN% docstrings" label
    # after each dot has room before the card's right edge.
    xscale = linear_scale((t_lo, t_lo + (t_hi - t_lo) / 0.55), (pad_left, width - pad_right))

    row_h = (height - pad_top - pad_bottom) / max(len(arms), 1)
    parts = [svg_open(width, height)]
    parts.append(f'<text x="{pad_left}" y="10" class="chart-title" font-size="13">Avg function length (dot) &amp; docstring coverage (label)</text>')
    for tv in ticks:
        x = xscale(tv)
        parts.append(f'<line x1="{x:.1f}" y1="{pad_top}" x2="{x:.1f}" y2="{height - pad_bottom}" class="grid-line" />')
        parts.append(f'<text x="{x:.1f}" y="{height - pad_bottom + 14}" class="tick-label" font-size="12" text-anchor="middle">{tv:g}</text>')

    for i, arm in enumerate(arms):
        cy = pad_top + row_h * i + row_h / 2
        label = ARM_LABELS.get(arm, arm).split(" (")[0]
        parts.append(f'<text x="{pad_left - 10}" y="{cy + 4:.1f}" text-anchor="end" class="row-label" font-size="12">{esc(label)}</text>')
        v = cmr_summary[arm]["avg_function_length"]
        cov = cmr_summary[arm]["docstring_coverage"]
        if v is not None:
            cx = xscale(v)
            parts.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6" fill="var(--arm-{arm})" stroke="var(--surface-1)" stroke-width="2" '
                f'class="mark-dot" data-tip="{esc(label)}: {v:.1f} lines avg, {fmt_pct(cov*100) if cov is not None else "—"} docstring coverage">'
                f'<title>{esc(label)}: {v:.1f} lines avg, {fmt_pct(cov*100) if cov is not None else "—"} docstring coverage</title></circle>'
            )
            cov_str = fmt_pct(cov * 100) if cov is not None else "—"
            parts.append(f'<text x="{cx + 10:.1f}" y="{cy + 4:.1f}" class="tick-label" font-size="12">{v:.1f} lines, {cov_str} docstrings</text>')
    parts.append("</svg>")
    return "".join(parts), height


# --------------------------------------------------------------------------
# Explain failures section.
# --------------------------------------------------------------------------


def _failure_rule_block_html(entry):
    tests_html = "".join(
        f'<li><code>{esc(t["label"])}</code> ({esc(t["kind"])})'
        + (f'<div class="failure-snippet">{"".join(f"<div>{esc(s)}</div>" for s in t["snippet"])}</div>' if t["snippet"] else "")
        + "</li>"
        for t in entry["tests"]
    )
    return f"""
    <div class="failure-rule-block">
      <div class="failure-rule-head">
        <strong>{esc(entry["rule_id"])}</strong> <span class="muted">{esc(entry["memory"] or "")}</span>
        <span class="failure-rule-count">{entry["failed_count"]}/{entry["total_count"]} tests failed</span>
      </div>
      <p class="failure-rule-summary">{esc(entry["summary"] or "")}</p>
      <details class="table-fallback"><summary>{len(entry["tests"])} failing test(s)</summary>
        <ul class="failure-test-list">{tests_html}</ul>
      </details>
    </div>"""


def failure_detail_html(fr, review):
    """Full Explain failures section body: per-arm rule-grouped failures
    (task1 then pivot) + the shared-vs-harness-only note."""
    present = fr["arms_present"]
    if not present:
        return '<p class="muted">No two-phase (pivot) runs with doc-rule data to explain.</p>'

    arm_blocks = []
    for arm in present:
        entry = fr["by_arm"].get(arm, {"task1": [], "pivot": []})
        t1_blocks = "".join(_failure_rule_block_html(e) for e in entry["task1"])
        pv_blocks = "".join(_failure_rule_block_html(e) for e in entry["pivot"])
        if not t1_blocks and not pv_blocks:
            body = '<p class="muted">No failing doc-rule tests for this arm.</p>'
        else:
            body = (
                (f'<h4>Task 1</h4>{t1_blocks}' if t1_blocks else '<h4>Task 1</h4><p class="muted">No failing doc-rule tests.</p>')
                + (f'<h4>Pivot</h4>{pv_blocks}' if pv_blocks else '<h4>Pivot</h4><p class="muted">No failing doc-rule tests.</p>')
            )
        chip = f'<span class="chip" style="background:var(--arm-{arm})"></span>'
        arm_blocks.append(f"""
        <div class="chart-card failure-arm-card">
          <div class="chart-card-title">{chip}{esc(ARM_LABELS.get(arm, arm))}</div>
          {body}
        </div>""")

    split = fr["split"]
    shared = split.get("shared") or []
    harness_only = split.get("harness_only") or []
    split_bits = []
    if shared:
        split_bits.append(f'<strong>Shared failures</strong> (every arm, including no harness): {", ".join(esc(r) for r in shared)}.')
    if harness_only:
        split_bits.append(f'<strong>Harness-only failures</strong> (every harness arm failed it, no-harness control passed it): {", ".join(esc(r) for r in harness_only)} &mdash; this asymmetry is the key story: the harness introduced its own convention misses that the no-harness run avoided.')
    split_html = (
        "".join(f'<p class="section-takeaway">{bit}</p>' for bit in split_bits)
        if split_bits else ""
    )

    return f'{split_html}<div class="chart-grid">{"".join(arm_blocks)}</div>'


def findings_cards_html(findings):
    """3-5 short finding cards (one sentence each). Pure rendering of a list
    of pre-computed finding strings (see key_findings)."""
    if not findings:
        return ""
    cards = "".join(f'<div class="finding-card">{esc(f)}</div>' for f in findings)
    return f'<div class="findings-grid">{cards}</div>'


# --------------------------------------------------------------------------
# Full HTML assembly.
# --------------------------------------------------------------------------

CSS = """
:root {
  color-scheme: light;
  --surface-1: #fcfcfb;
  --page-plane: #f9f9f7;
  --text-primary: #0b0b0b;
  --text-secondary: #52514e;
  --text-muted: #898781;
  --gridline: #e1e0d9;
  --baseline-axis: #c3c2b7;
  --border: rgba(11,11,11,0.10);
  --status-good: #0ca30c;
  --status-critical: #d03b3b;
  --arm-baseline: #2a78d6;
  --arm-v5: #eb6834;
  --arm-control: #006300;
  --success-good: #006300;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --surface-1: #1a1a19;
    --page-plane: #0d0d0d;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted: #898781;
    --gridline: #2c2c2a;
    --baseline-axis: #383835;
    --border: rgba(255,255,255,0.10);
    --status-good: #0ca30c;
    --status-critical: #e66767;
    --arm-baseline: #3987e5;
    --arm-v5: #d95926;
    --arm-control: #008f00;
    --success-good: #0ca30c;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface-1: #1a1a19;
  --page-plane: #0d0d0d;
  --text-primary: #ffffff;
  --text-secondary: #c3c2b7;
  --text-muted: #898781;
  --gridline: #2c2c2a;
  --baseline-axis: #383835;
  --border: rgba(255,255,255,0.10);
  --status-good: #0ca30c;
  --status-critical: #e66767;
  --arm-baseline: #3987e5;
  --arm-v5: #d95926;
  --arm-control: #008f00;
  --success-good: #0ca30c;
}
* { box-sizing: border-box; }
html, body {
  margin: 0; padding: 0;
  background: var(--page-plane);
  color: var(--text-primary);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  max-width: 100%;
  overflow-x: hidden;
}
body { padding: 0 0 48px; }
main { max-width: 1100px; margin: 0 auto; min-width: 0; padding: 0 16px; }

/* Type scale: 28/20/16/14/12, tabular numbers on anything that must align. */
h1, h2, h3 { font-weight: 600; }
h1 { font-size: 1.75rem; margin: 0 0 4px; line-height: 1.2; }
h2 { font-size: 1.25rem; margin: 0 0 4px; }
h3 { font-size: 1rem; margin: 0 0 6px; }
p { line-height: 1.5; color: var(--text-secondary); font-size: 1rem; max-width: 70ch; }
p + p { margin-top: 8px; }
.muted { color: var(--text-muted); }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); }
.eyebrow {
  font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--text-muted); margin: 0 0 6px;
}
.tabular-nums { font-variant-numeric: tabular-nums; }

header.report-header {
  border-bottom: 1px solid var(--border);
  padding: 20px 16px 16px;
  margin-bottom: 8px;
  max-width: 1100px;
  margin-left: auto;
  margin-right: auto;
  box-sizing: border-box;
}
.meta-line { font-size: 0.8rem; color: var(--text-muted); margin-top: 4px; overflow-wrap: break-word; }
.verdict { font-size: 0.95rem; color: var(--text-primary); margin-top: 10px; max-width: 70ch; }

/* Sticky section nav */
nav.section-nav {
  position: sticky; top: 0; z-index: 40;
  padding-top: env(safe-area-inset-top, 0px);
  background: color-mix(in oklab, var(--surface-1) 92%, transparent);
  backdrop-filter: blur(6px);
  border-bottom: 1px solid var(--border);
  margin-bottom: 16px;
}
nav.section-nav ul {
  list-style: none; margin: 0; padding: 0 16px;
  max-width: 1100px; width: 100%; box-sizing: border-box;
  margin-left: auto; margin-right: auto;
  display: flex; gap: 4px; overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
nav.section-nav li { flex: 0 0 auto; }
nav.section-nav a {
  display: block; padding: 10px 10px; font-size: 0.82rem; font-weight: 600;
  color: var(--text-secondary); text-decoration: none; white-space: nowrap;
  border-bottom: 2px solid transparent;
}
nav.section-nav a:hover, nav.section-nav a:focus-visible { color: var(--text-primary); border-bottom-color: var(--gridline); }

/* Section takeaway headline */
section.report-section { margin: 0 0 48px; scroll-margin-top: 56px; }
section.report-section > h2 { margin-bottom: 2px; }
.section-takeaway {
  font-size: 1rem; color: var(--text-primary); font-weight: 600;
  margin: 2px 0 16px; max-width: 70ch;
}
.section-subtitle { font-size: 0.85rem; color: var(--text-muted); margin: 0 0 14px; max-width: 70ch; }

/* Scorecard */
.scorecard-wrap { overflow-x: auto; }
table.scorecard-table {
  border-collapse: separate; border-spacing: 0; width: 100%;
  font-variant-numeric: tabular-nums;
}
.scorecard-corner { width: 30%; }
th.scorecard-head {
  text-align: left; padding: 8px 14px; border-bottom: 2px solid var(--border);
  vertical-align: bottom;
}
.scorecard-head-arm { display: flex; align-items: center; gap: 7px; font-size: 0.95rem; font-weight: 700; }
.scorecard-head-ver { font-size: 0.72rem; margin-top: 2px; }
th.scorecard-row-label {
  text-align: left; padding: 10px 14px 10px 4px; font-size: 0.82rem; font-weight: 600;
  color: var(--text-secondary); border-bottom: 1px solid var(--border); white-space: nowrap;
}
td.scorecard-cell {
  padding: 10px 14px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top;
}
.scorecard-value { font-size: 1.3rem; font-weight: 700; display: flex; align-items: baseline; gap: 6px; }
.scorecard-value.best { color: var(--text-primary); }
.best-tag {
  font-size: 0.62rem; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase;
  color: var(--text-muted); border: 1px solid var(--border); border-radius: 3px; padding: 1px 4px;
}
.scorecard-delta { font-size: 0.78rem; color: var(--text-secondary); margin-top: 3px; }
.scorecard-delta .muted { font-size: 0.78rem; }
tr:last-child .scorecard-cell, tr:last-child th.scorecard-row-label { border-bottom: none; }

/* Two-phase (pivot) scorecard blocks */
.two-phase-scorecard-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(min(420px, 100%), 1fr));
  gap: 20px; margin-top: 4px;
}
.two-phase-block h3 { margin-bottom: 2px; }

/* Findings cards: auto-fit equal-height grid */
.findings-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr));
  grid-auto-rows: 1fr;
  gap: 10px; margin-top: 12px;
}
.finding-card {
  border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px;
  background: var(--surface-1); font-size: 0.88rem; line-height: 1.45; color: var(--text-primary);
  height: 100%; box-sizing: border-box;
}

/* Overall review */
.run-count-tag {
  display: inline-block; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.03em;
  text-transform: uppercase; color: var(--text-muted); border: 1px solid var(--border);
  border-radius: 3px; padding: 1px 6px; margin-left: 6px; vertical-align: middle;
}
.cost-benefit-block {
  border: 1px solid var(--border); border-radius: 10px; padding: 16px 18px;
  background: var(--surface-1); margin-bottom: 18px;
}
.cost-benefit-block h3 { margin: 0 0 8px; font-size: 1.05rem; }
.cost-benefit-answer { font-size: 0.95rem; color: var(--text-primary); font-weight: 600; margin: 0 0 8px; max-width: 72ch; }
.cost-benefit-lines { margin: 8px 0 0; padding-left: 18px; font-size: 0.85rem; color: var(--text-secondary); line-height: 1.6; }
.overall-wrap { overflow-x: auto; }
table.overall-table { border-collapse: separate; border-spacing: 0; width: 100%; font-variant-numeric: tabular-nums; }
.overall-corner { width: 22%; }
th.overall-head { text-align: left; padding: 8px 12px; border-bottom: 2px solid var(--border); vertical-align: bottom; }
.overall-head-arm { display: flex; align-items: center; gap: 7px; font-size: 0.9rem; font-weight: 700; }
.overall-head-ver { font-size: 0.7rem; margin-top: 2px; }
tr.overall-group-row th {
  text-align: left; padding: 14px 12px 4px 4px; font-size: 0.72rem; font-weight: 700;
  letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-muted);
  border-bottom: 1px solid var(--border);
}
tr.overall-note-row .overall-note {
  font-size: 0.76rem; color: var(--text-muted); padding: 2px 4px 8px; font-style: italic;
}
th.overall-row-label {
  text-align: left; padding: 8px 12px 8px 4px; font-size: 0.82rem; font-weight: 600;
  color: var(--text-secondary); border-bottom: 1px solid var(--border); white-space: nowrap;
}
td.overall-cell { padding: 8px 12px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }
.overall-value { font-size: 1.05rem; font-weight: 700; display: flex; align-items: baseline; gap: 6px; }
.overall-value.best { color: var(--text-primary); }
.overall-delta { font-size: 0.74rem; margin-top: 2px; }

/* Explain failures */
.failure-arm-card { min-width: 0; }
.failure-rule-block { border-top: 1px solid var(--border); padding: 10px 0; }
.failure-rule-block:first-of-type { border-top: none; padding-top: 4px; }
.failure-rule-head { font-size: 0.85rem; display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; }
.failure-rule-count { font-size: 0.76rem; color: var(--status-critical); font-weight: 600; margin-left: auto; }
.failure-rule-summary { font-size: 0.8rem; margin: 4px 0 6px; }
.failure-test-list { margin: 6px 0 0; padding-left: 16px; font-size: 0.8rem; }
.failure-test-list li { margin-bottom: 8px; }
.failure-snippet {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.74rem;
  background: color-mix(in oklab, var(--surface-1) 88%, var(--text-primary) 6%);
  border-radius: 4px; padding: 4px 8px; margin-top: 4px; overflow-x: auto; white-space: pre;
}

/* Gate matrix column groups */
table.gate-matrix-table th.gate-group-head {
  text-align: center; background: color-mix(in oklab, var(--surface-1) 85%, var(--text-primary) 6%);
}

.kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr));
  gap: 10px;
}
.kpi-card {
  border: 1px solid var(--border);
  border-left: 3px solid var(--arm-accent);
  border-radius: 6px;
  padding: 10px 12px;
  background: var(--surface-1);
}
.kpi-arm { font-weight: 600; font-size: 0.9rem; display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.chip { display: inline-block; width: 10px; height: 10px; border-radius: 2px; flex: 0 0 auto; }
.kpi-list { margin: 0; display: grid; gap: 3px; }
.kpi-list > div { display: flex; justify-content: space-between; gap: 8px; font-size: 0.82rem; }
.kpi-list dt { color: var(--text-muted); }
.kpi-list dd { margin: 0; font-variant-numeric: tabular-nums; font-weight: 600; }

/* Chart cards: one chart per card, generous whitespace */
.chart-card {
  border: 1px solid var(--border); border-radius: 10px; padding: 16px;
  background: var(--surface-1); min-width: 0; margin-bottom: 14px;
}
.chart-card:last-child { margin-bottom: 0; }
.chart-card-title { font-size: 0.95rem; font-weight: 700; margin: 0 0 2px; }
.chart-card-subtitle { font-size: 0.78rem; color: var(--text-muted); margin: 0 0 12px; }
.chart-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(340px, 100%), 1fr)); gap: 14px; min-width: 0; }
.chart-grid > .chart-card { margin-bottom: 0; }

.small-multiples { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(320px, 100%), 1fr)); gap: 8px 16px; min-width: 0; }
.small-multiples > .chart-card { min-width: 0; }
.chart-svg { display: block; background: var(--surface-1); max-width: 100%; height: auto; }
.chart-title { fill: var(--text-primary); font-weight: 600; }
.tick-label, .legend-label { fill: var(--text-muted); }
.row-label { fill: var(--text-secondary); }
.grid-line { stroke: var(--gridline); stroke-width: 1; }
.mark-dot, .mark-bar, .comp-seg, .tool-seg { cursor: pointer; }
.mark-dot:hover, .mark-bar:hover, .comp-seg:hover, .tool-seg:hover { opacity: 0.8; }

details.table-fallback { margin-top: 10px; font-size: 0.82rem; }
details.table-fallback summary { cursor: pointer; color: var(--text-secondary); font-weight: 600; }
details.table-fallback summary:hover { color: var(--text-primary); }
.fallback-table-wrap { overflow-x: auto; }
.fallback-table { border-collapse: collapse; width: 100%; margin-top: 6px; font-variant-numeric: tabular-nums; font-size: 0.8rem; }
.fallback-table th, .fallback-table td { text-align: left; padding: 3px 8px; border-bottom: 1px solid var(--border); }

.heatmap-table { border-collapse: collapse; font-size: 0.8rem; font-variant-numeric: tabular-nums; }
.heatmap-table th, .heatmap-table td { padding: 4px 9px; text-align: right; border-bottom: 1px solid var(--border); }
.heatmap-table th:first-child, .heatmap-table td:first-child { text-align: left; }
.heat-cell { background: color-mix(in oklab, var(--arm-baseline) calc(var(--heat-t) * 70%), var(--surface-1)); }

.table-wrap { overflow-x: auto; }
table.run-table { border-collapse: collapse; width: 100%; font-size: 0.8rem; font-variant-numeric: tabular-nums; min-width: 900px; }
table.run-table th, table.run-table td { padding: 5px 9px; border-bottom: 1px solid var(--border); text-align: right; white-space: nowrap; }
table.run-table th:first-child, table.run-table td:first-child { text-align: left; }
table.run-table tbody tr:nth-child(even) { background: color-mix(in oklab, var(--surface-1) 92%, var(--text-primary) 3%); }
table.run-table thead th { cursor: pointer; color: var(--text-secondary); font-weight: 600; user-select: none; position: sticky; top: 0; background: var(--surface-1); }
table.run-table thead th:hover { color: var(--text-primary); }
.sort-indicator::after { content: ""; }
.sort-indicator.asc::after { content: " \\2191"; }
.sort-indicator.desc::after { content: " \\2193"; }
.success-yes { color: var(--success-good); font-weight: 600; }
.success-no { color: var(--status-critical); font-weight: 600; }
.gate-ok { color: var(--success-good); font-weight: 600; }
.gate-fail { color: var(--status-critical); font-weight: 600; }

.method-section ul { padding-left: 18px; color: var(--text-secondary); font-size: 0.85rem; line-height: 1.55; margin: 0; }
.method-section li { margin-bottom: 4px; }
details.method-full { margin-top: 12px; font-size: 0.82rem; }
details.method-full summary { cursor: pointer; color: var(--text-secondary); font-weight: 600; }

/* Tooltip */
#viz-tooltip {
  position: fixed; pointer-events: none; z-index: 50;
  background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 4px; padding: 4px 8px; font-size: 0.78rem;
  color: var(--text-primary); box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  display: none; white-space: nowrap;
}

@media (max-width: 720px) {
  main { padding: 0 16px; }
  .scorecard-wrap table.scorecard-table,
  .scorecard-wrap thead,
  .scorecard-wrap tbody,
  .scorecard-wrap tr { display: block; width: 100%; }
  .scorecard-wrap thead { display: none; }
  .scorecard-wrap tr {
    border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; margin-bottom: 12px;
  }
  .scorecard-wrap th.scorecard-row-label {
    display: block; border-bottom: none; padding: 8px 0 2px; white-space: normal;
  }
  .scorecard-wrap td.scorecard-cell { display: block; border-bottom: none; padding: 2px 0 8px; }
  .scorecard-wrap td.scorecard-cell::before {
    content: attr(data-arm-label); display: block; font-size: 0.7rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-muted); margin-bottom: 2px;
  }
}

@media (max-width: 480px) {
  h1 { font-size: 1.4rem; }
  h2 { font-size: 1.1rem; }
  .kpi-row { grid-template-columns: 1fr; }
  table.run-table { font-size: 0.75rem; }
}
"""

JS = """
(function () {
  var tip = document.getElementById('viz-tooltip');
  function showTip(evt, text) {
    if (!tip || !text) return;
    tip.textContent = text;
    tip.style.display = 'block';
    var x = evt.clientX + 12, y = evt.clientY + 12;
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
  }
  function hideTip() { if (tip) tip.style.display = 'none'; }
  document.addEventListener('pointermove', function (evt) {
    var el = evt.target.closest('[data-tip]');
    if (el) { showTip(evt, el.getAttribute('data-tip')); }
    else { hideTip(); }
  });
  document.addEventListener('pointerleave', hideTip, true);
  document.querySelectorAll('[data-tip]').forEach(function (el) {
    el.addEventListener('focus', function () {
      var r = el.getBoundingClientRect();
      showTip({ clientX: r.left, clientY: r.top }, el.getAttribute('data-tip'));
    });
    el.addEventListener('blur', hideTip);
    el.setAttribute('tabindex', el.getAttribute('tabindex') || '0');
  });

  var table = document.getElementById('run-table');
  if (table) {
    var state = { key: null, dir: 1 };
    table.querySelectorAll('thead th').forEach(function (th, idx) {
      function sortBy() {
        var key = th.getAttribute('data-sort-key');
        var dir = (state.key === key) ? -state.dir : 1;
        state.key = key; state.dir = dir;
        table.querySelectorAll('thead th .sort-indicator').forEach(function (s) {
          s.classList.remove('asc', 'desc');
        });
        var ind = th.querySelector('.sort-indicator');
        if (ind) ind.classList.add(dir === 1 ? 'asc' : 'desc');
        var tbody = table.querySelector('tbody');
        var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
        rows.sort(function (a, b) {
          var av = a.children[idx].getAttribute('data-sort');
          var bv = b.children[idx].getAttribute('data-sort');
          var an = parseFloat(av), bn = parseFloat(bv);
          var bothNumeric = av !== '' && bv !== '' && !isNaN(an) && !isNaN(bn);
          var cmp = bothNumeric ? (an - bn) : av.localeCompare(bv);
          return cmp * dir;
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
      }
      th.addEventListener('click', sortBy);
      th.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sortBy(); }
      });
    });
  }
})();
"""


def build_fallback_table(rows_2d, headers):
    ths = "".join(f"<th>{esc(h)}</th>" for h in headers)
    trs = []
    for row in rows_2d:
        tds = "".join(f"<td>{esc(c)}</td>" for c in row)
        trs.append(f"<tr>{tds}</tr>")
    return f'<div class="fallback-table-wrap"><table class="fallback-table"><thead><tr>{ths}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'


def _takeaway_doc_use(agg):
    """One-line takeaway headline for the Documentation use section. Falls
    back to a compact 'not measured' line when no arm has spec/doc data
    (v1-shaped rows)."""
    arms = agg.get("arms", {})
    present = [a for a in ARM_ORDER if a in arms]
    control = "control" if "control" in present else None
    doc_vals = {a: arms[a].get("doc_pass_pct_mean") for a in present}
    if all(v is None for v in doc_vals.values()):
        return "Doc-rule and spec pass rates not measured in this run."
    best_arm, best_v = None, -1
    for a in present:
        v = doc_vals.get(a)
        if v is not None and v > best_v:
            best_v, best_arm = v, a
    if best_arm is None:
        return "Doc-rule and spec pass rates not measured in this run."
    ctrl_v = doc_vals.get(control) if control else None
    if control and best_arm != control and ctrl_v is not None:
        return f"Harness arms passed {best_v:.0f}% of doc-rule tests vs {ctrl_v:.0f}% without."
    return f"{ARM_LABELS.get(best_arm, best_arm)} passed {best_v:.0f}% of doc-rule tests."


def _takeaway_gates(agg):
    arms = agg.get("arms", {})
    present = [a for a in ARM_ORDER if a in arms and a != "control"]
    rates = [arms[a].get("gate_conformance", {}).get("init_chain_complete_rate") for a in present]
    rates = [r for r in rates if r is not None]
    if not rates:
        return "Gate conformance not measured in this run."
    avg = 100.0 * sum(rates) / len(rates)
    return f"Harness arms completed the init chain in {avg:.0f}% of runs; the control arm has no gates (no harness)."


def _takeaway_cost(agg):
    arms = agg.get("arms", {})
    if "baseline" not in arms:
        present = [a for a in ARM_ORDER if a in arms]
        if not present:
            return "No cost/turns data to report."
        a = present[0]
        tok = arms[a].get("stats", {}).get("total_tokens", {}).get("median")
        return f"Median total tokens: {fmt_num(tok)}." if tok is not None else "No cost/turns data to report."
    bits = []
    for a in ARM_ORDER:
        if a == "baseline" or a not in arms:
            continue
        d = (arms[a].get("vs_baseline_pct") or {}).get("total_tokens")
        if d is not None:
            bits.append(f"{ARM_LABELS.get(a, a)} {d:+.0f}% tokens vs baseline")
    if not bits:
        return "Token/turn deltas vs baseline not available."
    return "; ".join(bits) + " (median)."


def _takeaway_tools(rows):
    tool_order, per_arm = tool_mix_rows(rows)
    if not tool_order:
        return "No tool-call data recorded."
    top_tool = tool_order[0]
    totals = {a: per_arm.get(a, {}).get(top_tool, 0) for a in ARM_ORDER}
    leader = max(totals, key=lambda a: totals[a]) if totals else None
    if leader is None or totals.get(leader, 0) == 0:
        return "No tool-call data recorded."
    return f"{esc(top_tool)} was the most-used tool overall, led by {ARM_LABELS.get(leader, leader)}."


def render_report(rows, meta, title="Harness A/B Results", notes_html=None, notes_text=None, stamp_dir=None):
    analyze = get_analyze()
    agg = analyze.aggregate(rows)
    arms_present = agg.get("arms", {})

    args_meta = meta.get("args") or {}
    model = args_meta.get("model") or "—"
    trials = args_meta.get("trials")
    claude_version = meta.get("claude_version") or "—"
    auth = meta.get("auth") or {}
    auth_mode = auth.get("authMethod") or "—"

    n_per_arm = {a: arms_present.get(a, {}).get("n", 0) for a in ARM_ORDER}
    trials_str = ", ".join(f"{ARM_LABELS.get(a, a)}: n={n_per_arm[a]}" for a in ARM_ORDER if a in arms_present)

    # --- Overall review: one-sentence verdict + full comparison table,
    # first block on the page (replaces the old multi-sentence
    # compute_verdict() paragraph, which could read as self-contradictory
    # across its independently-computed sentences). ---
    overall_review = overall_review_rows(rows, agg, stamp_dir=stamp_dir)
    code_metrics_data = code_metrics_rows(rows, stamp_dir) if stamp_dir else []
    overall_review["code_cells"] = code_metrics_summary_by_arm(code_metrics_data)
    verdict = overall_review_verdict(overall_review)
    n_run_note = "1 run per arm — directional" if all(v <= 1 for v in n_per_arm.values() if v) else f"n={n_per_arm}"
    overall_table_html = overall_review_table_html(overall_review)
    cost_benefit_html = cost_vs_benefit_html(overall_review)
    quadrant_svg, _quadrant_h = quadrant_chart(overall_review)
    quadrant_card = f"""
    <div class="chart-card">
      <div class="chart-card-subtitle">Tokens (M) vs. combined doc-rule pass % (task1+pivot), one dot per arm.</div>
      {quadrant_svg}
    </div>"""

    import datetime
    date_str = datetime.date.today().isoformat()

    # --- scorecard + findings ---
    scorecard_table_html = scorecard_html(agg)
    notes_findings = parse_notes_lines(notes_text) if notes_text else []
    # Backward compat: an HTML-fragment --notes file (no '- text' lines
    # matched) still renders verbatim as its own Findings section, exactly
    # as the previous report did.
    legacy_notes_html = notes_html if (notes_html and not notes_findings) else None
    findings = key_findings(agg, notes_findings)
    findings_html = findings_cards_html(findings)

    # --- KPI row (kept as the scorecard's "Data" fallback) ---
    kpi_html = kpi_row(agg)

    # --- dot/strip small multiples (split: cost-relevant metrics render in
    # the Cost section; the rest — memory consultations — in Documentation
    # use) ---
    COST_METRIC_KEYS = {
        "assistant_turns_incl_subagents", "num_turns", "total_tokens",
        "output_tokens", "wall_s", "tool_calls",
    }
    dot_chart_cards = {}
    for key, label, getter in METRIC_DOT_SPECS:
        mrows = rows_for_metric(rows, getter)
        svg = dot_strip_chart(mrows, key, label)
        by_arm_vals = {}
        for arm, trial, v in mrows:
            by_arm_vals.setdefault(arm, []).append((trial, v))
        table_rows = []
        for arm in ARM_ORDER:
            for trial, v in sorted(by_arm_vals.get(arm, [])):
                table_rows.append((ARM_LABELS.get(arm, arm), trial, fmt_num(v, 1)))
        fallback = build_fallback_table(table_rows, ["arm", "trial", label])
        dot_chart_cards[key] = f"""
        <div class="chart-card">
          <div class="chart-card-title">{esc(label)}</div>
          <div class="chart-card-subtitle">Per run, dot per trial, median tick per arm.</div>
          {svg}
          <details class="table-fallback"><summary>Data</summary>{fallback}</details>
        </div>"""
    cost_dot_cards = "".join(dot_chart_cards[k] for k, _l, _g in METRIC_DOT_SPECS if k in COST_METRIC_KEYS)
    other_dot_cards = "".join(dot_chart_cards[k] for k, _l, _g in METRIC_DOT_SPECS if k not in COST_METRIC_KEYS)

    # --- token composition ---
    comp_rows = token_composition_rows(rows)
    comp_svg, _comp_h = token_composition_chart(comp_rows)
    comp_fallback_rows = []
    for (run_id, arm, trial, parts) in sorted(comp_rows, key=lambda r: (ARM_ORDER.index(r[1]) if r[1] in ARM_ORDER else 99, r[2] or 0)):
        comp_fallback_rows.append((
            ARM_LABELS.get(arm, arm), trial, fmt_num(parts.get("input")), fmt_num(parts.get("output")),
            fmt_num(parts.get("cache_creation")), fmt_num(parts.get("cache_read"))
        ))
    comp_fallback = build_fallback_table(comp_fallback_rows, ["arm", "trial", "input", "output", "cache creation", "cache read"])
    comp_card = f"""
    <div class="chart-card">
      <div class="chart-card-title">Token composition per run</div>
      <div class="chart-card-subtitle">Input / output / cache creation / cache read, tokens, stacked per run.</div>
      {comp_svg}
      <details class="table-fallback" open><summary>Data</summary>{comp_fallback}</details>
    </div>"""

    # --- acceptance ---
    acc_rows = acceptance_rows(rows)
    acc_svg, _acc_h = acceptance_bar_chart(acc_rows)
    acc_fallback = build_fallback_table(
        [(ARM_LABELS.get(r["arm"], r["arm"]), r["trial"], f'{r["passed"]}/{r["total"]}', fmt_pct(r["pct"]), r["reg_ok"]) for r in sorted(acc_rows, key=lambda r: (ARM_ORDER.index(r["arm"]) if r["arm"] in ARM_ORDER else 99, r["trial"] or 0))],
        ["arm", "trial", "passed/total", "pct", "regression ok"]
    )
    acc_card = f"""
    <div class="chart-card">
      <div class="chart-card-title">Acceptance pass rate per run</div>
      <div class="chart-card-subtitle">Percent of acceptance tests passed, 0-100%, per run.</div>
      {acc_svg}
      <details class="table-fallback"><summary>Data</summary>{acc_fallback}</details>
    </div>"""

    # --- friction ---
    fric_rows = friction_rows(rows)
    fric_svg, _fric_h = friction_chart(fric_rows)
    fric_fallback = build_fallback_table(
        [(ARM_LABELS.get(r["arm"], r["arm"]), r["trial"], r["hook_denials"], r["stop_hook_blocks"]) for r in sorted(fric_rows, key=lambda r: (ARM_ORDER.index(r["arm"]) if r["arm"] in ARM_ORDER else 99, r["trial"] or 0))],
        ["arm", "trial", "hook denials", "stop-hook blocks"]
    )
    stream_table_html = stream_event_heatmap(stream_event_table(rows))
    fric_card = f"""
    <div class="chart-card">
      <div class="chart-card-title">Harness friction per run</div>
      <div class="chart-card-subtitle">Hook denials and stop-hook blocks, count per run.</div>
      {fric_svg}
      <details class="table-fallback"><summary>Data</summary>{fric_fallback}</details>
    </div>
    <div class="chart-card">
      <div class="chart-card-title">Top stream event types by arm</div>
      <div class="chart-card-subtitle">Plugin arms only (control has no SWE stream).</div>
      {stream_table_html}
    </div>"""

    # --- tool mix ---
    tool_order, per_arm_tools = tool_mix_rows(rows)
    tool_svg = tool_mix_chart(tool_order, per_arm_tools)
    tool_fallback_rows = []
    for arm in ARM_ORDER:
        row = per_arm_tools.get(arm, {})
        tool_fallback_rows.append([ARM_LABELS.get(arm, arm)] + [fmt_num(row.get(t, 0)) for t in tool_order])
    tool_fallback = build_fallback_table(tool_fallback_rows, ["arm"] + tool_order)
    tool_card = f"""
    <div class="chart-card">
      <div class="chart-card-title">Tool mix by arm</div>
      <div class="chart-card-subtitle">Top {TOOL_TOP_N} tools + Other, call count, stacked per arm.</div>
      {tool_svg}
      <details class="table-fallback"><summary>Data</summary>{tool_fallback}</details>
    </div>"""

    # --- spec vs doc pass % ---
    spec_doc_by_arm = spec_doc_bar_rows(rows)
    spec_doc_svg, _spec_doc_h = spec_doc_grouped_bar_chart(spec_doc_by_arm)
    spec_doc_fallback = build_fallback_table(
        [(ARM_LABELS.get(a, a), fmt_pct(spec_doc_by_arm[a]["spec"]), fmt_pct(spec_doc_by_arm[a]["doc"]))
         for a in ARM_ORDER if a in spec_doc_by_arm],
        ["arm", "spec pass %", "doc pass %"]
    )
    spec_doc_card = f"""
    <div class="chart-card">
      <div class="chart-card-title">Spec vs doc-rule pass rate</div>
      <div class="chart-card-subtitle">Mean pass % across runs, per arm; spec (full color) vs doc-rule (lightened).</div>
      {spec_doc_svg}
      <details class="table-fallback" open><summary>Data</summary>{spec_doc_fallback}</details>
    </div>"""

    # --- doc-rule heatmap ---
    rule_ids, per_cell = doc_rule_heatmap_rows(rows)
    doc_rule_heatmap_html = doc_rule_heatmap_table(rule_ids, per_cell)
    doc_rule_card = f"""
    <div class="chart-card">
      <div class="chart-card-title">Doc-rule pass/fail by run</div>
      <div class="chart-card-subtitle">Runs &times; rules; hover a column header for the source memory.</div>
      <div class="table-wrap">{doc_rule_heatmap_html}</div>
    </div>"""

    # --- memory coverage dot plot ---
    mem_rows_data = memory_coverage_rows(rows)
    mem_coverage_svg = memory_coverage_dot_chart(mem_rows_data)
    mem_coverage_fallback = build_fallback_table(
        [(ARM_LABELS.get(r["arm"], r["arm"]), r["trial"], r["n_memories_read"],
          fmt_pct(r["doc_rule_memories_coverage"] * 100 if r["doc_rule_memories_coverage"] is not None else None),
          r.get("channel") or "–")
         for r in sorted(mem_rows_data, key=lambda r: (ARM_ORDER.index(r["arm"]) if r["arm"] in ARM_ORDER else 99, r["trial"] or 0))],
        ["arm", "trial", "memories read (n)", "doc-rule coverage", "channel"]
    )
    mem_coverage_card = f"""
    <div class="chart-card">
      <div class="chart-card-title">Memory consultation coverage</div>
      <div class="chart-card-subtitle">% of task doc_rules memories read, per run, 0-100%.</div>
      {mem_coverage_svg}
      <details class="table-fallback"><summary>Data</summary>{mem_coverage_fallback}</details>
    </div>"""

    # --- gate conformance table ---
    gate_rows_data = gate_conformance_rows(rows)
    gate_table_html = gate_conformance_table(gate_rows_data)
    gate_card = f"""
    <div class="chart-card">
      <div class="chart-card-title">Gate conformance per run</div>
      <div class="chart-card-subtitle">Init chain, sweep verification, edits-before-sweep, doc-rule coverage; control is n/a (no harness).</div>
      <div class="table-wrap">{gate_table_html}</div>
    </div>"""

    # --- two-phase (pivot) content: scorecard blocks, B1/B2 doc-use,
    # pivot gate matrix, phase-stacked cost chart. Empty/absent for a
    # single-phase stamp -- has_pivot gates every pivot-only section below
    # so a v1/v2-single-phase report renders exactly as before. ---
    has_pivot_data = has_phase_rows(rows)
    two_phase_scorecard_table_html = two_phase_scorecard_html(agg) if has_pivot_data else ""

    b1_rule_ids, b1_per_cell = two_phase_doc_rule_heatmap_rows(rows, "b1") if has_pivot_data else ([], {})
    b2_rule_ids, b2_per_cell = two_phase_doc_rule_heatmap_rows(rows, "b2") if has_pivot_data else ([], {})
    b1_heatmap_html = doc_rule_heatmap_table(b1_rule_ids, b1_per_cell)
    b2_heatmap_html = doc_rule_heatmap_table(b2_rule_ids, b2_per_cell)
    pivot_doc_rule_card = f"""
    <div class="chart-card">
      <div class="chart-card-title">Benchmark 1 doc-rule pass/fail by run (task1 rules R*)</div>
      <div class="chart-card-subtitle">Scored on the tree right after task 1, before the pivot prompt.</div>
      <div class="table-wrap">{b1_heatmap_html}</div>
    </div>
    <div class="chart-card">
      <div class="chart-card-title">Benchmark 2 doc-rule pass/fail by run (pivot rules P*)</div>
      <div class="chart-card-subtitle">Scored on the final tree after the pivot phase.</div>
      <div class="table-wrap">{b2_heatmap_html}</div>
    </div>"""

    pivot_gate_rows_data = pivot_gate_matrix_rows(rows) if has_pivot_data else []
    # pivot_gate_matrix_table() already wraps its own table in .table-wrap
    # (9 columns -- too wide for a 2-up chart-grid cell without horizontal
    # scroll) -- this card is rendered full-width below, outside
    # chart-grid, rather than nested a second time.
    pivot_gate_matrix_html = pivot_gate_matrix_table(pivot_gate_rows_data)
    pivot_gate_card = f"""
    <div class="chart-card">
      <div class="chart-card-title">Task-1 + pivot gate conformance per run</div>
      <div class="chart-card-subtitle">Task-1 init/sweep, then pivot-phase reclassify/resweep/edits/doc-memory coverage; control is n/a (no harness).</div>
      {pivot_gate_matrix_html}
    </div>"""

    phase_cost_rows_data = phase_cost_stack_rows(rows, stamp_dir=stamp_dir) if has_pivot_data else []
    phase_cost_svg, _phase_cost_h = phase_cost_stack_chart(phase_cost_rows_data)
    phase_cost_fallback_rows = []
    for (run_id, arm, trial, parts) in sorted(phase_cost_rows_data, key=lambda r: (ARM_ORDER.index(r[1]) if r[1] in ARM_ORDER else 99, r[2] or 0)):
        phase_cost_fallback_rows.append((ARM_LABELS.get(arm, arm), trial, fmt_num(parts.get("task1")), fmt_num(parts.get("pivot"))))
    phase_cost_fallback = build_fallback_table(phase_cost_fallback_rows, ["arm", "trial", "task1 tokens", "pivot tokens"])
    phase_cost_card = f"""
    <div class="chart-card">
      <div class="chart-card-title">Tokens by phase per run</div>
      <div class="chart-card-subtitle">Task 1 vs pivot phase, tokens, stacked per run.</div>
      {phase_cost_svg}
      <details class="table-fallback" open><summary>Data</summary>{phase_cost_fallback}</details>
    </div>"""
    pivot_medians = {}
    pb = agg.get("pivot_benchmarks") or {}
    for a in ARM_ORDER:
        if a in pb:
            pivot_medians[a] = pb[a]["phase_medians"]
    phase_cost_median_rows = [
        (ARM_LABELS.get(a, a), fmt_num(pm["task1"].get("total_tokens")), fmt_num(pm["pivot"].get("total_tokens")))
        for a, pm in pivot_medians.items()
    ]
    phase_cost_median_fallback = build_fallback_table(phase_cost_median_rows, ["arm", "task1 tokens (median)", "pivot tokens (median)"])

    doc_use_takeaway = _takeaway_doc_use(agg)
    gates_takeaway = _takeaway_gates(agg)
    cost_takeaway = _takeaway_cost(agg)
    tools_takeaway = _takeaway_tools(rows)

    # --- delegation (subagent usage) ---
    deleg_rows_data = delegation_rows(rows)
    deleg_takeaway = delegation_takeaway(deleg_rows_data)
    deleg_table_html = delegation_table_html(deleg_rows_data)
    deleg_svg, _deleg_h = delegation_chart(deleg_rows_data)
    delegation_card = f"""
    <div class="chart-card">
      <div class="chart-card-title">Main vs. subagent tokens</div>
      <div class="chart-card-subtitle">Per arm, summed across runs; phase-level subagent fields are not recorded (shown as &mdash;).</div>
      {deleg_svg}
      <details class="table-fallback"><summary>Data</summary>{deleg_table_html}</details>
    </div>"""

    # --- code metrics ---
    code_table_html = code_metrics_table_html(code_metrics_data)
    code_loc_svg, _code_loc_h = code_metrics_loc_chart(overall_review["code_cells"])
    code_shape_svg, _code_shape_h = code_metrics_shape_dot_chart(overall_review["code_cells"])
    code_loc_card = f"""
    <div class="chart-card">
      <div class="chart-card-title">LOC added per arm</div>
      <div class="chart-card-subtitle">Agent-added/modified non-excluded LOC, fixture &rarr; final tree. Proxy for size, not quality.</div>
      {code_loc_svg}
    </div>"""
    code_shape_card = f"""
    <div class="chart-card">
      <div class="chart-card-title">Function length &amp; docstring coverage</div>
      <div class="chart-card-subtitle">Avg length (lines) and docstring coverage, per arm. Proxies for shape, not quality.</div>
      {code_shape_svg}
    </div>"""
    code_metrics_section_html = f"""
    <div class="chart-grid">{code_loc_card}{code_shape_card}</div>
    <div class="chart-card" style="margin-top:14px">
      <div class="chart-card-title">Code metrics by run</div>
      <div class="chart-card-subtitle">Proxies for size/shape, not quality judgments.</div>
      <div class="table-wrap">{code_table_html}</div>
    </div>"""

    # --- explain failures ---
    failure_rows_data = failure_report_rows(rows, stamp_dir) if stamp_dir else {"by_arm": {}, "split": {"shared": [], "harness_only": []}, "arms_present": []}
    explain_failures_html = failure_detail_html(failure_rows_data, overall_review)

    # --- per-run table ---
    run_table_html = per_run_table(rows)

    # --- method section ---
    arms_meta = meta.get("arms") or []
    prepared = meta.get("prepared") or {}
    arm_method_items = []
    for a in arms_meta:
        name = a.get("name")
        p = prepared.get(name, {})
        sha = p.get("sha")
        ver = p.get("version")
        arm_method_items.append(
            f"<li><strong>{esc(ARM_LABELS.get(name, name))}</strong>: ref {esc(a.get('ref'))}"
            + (f", commit {esc(sha)}" if sha else "")
            + (f", plugin version {esc(ver)}" if ver else "")
            + "</li>"
        )

    method_items_html = ''.join(arm_method_items) if arm_method_items else '<li>Arm metadata not recorded in meta.json.</li>'
    method_summary_html = f"""
    <ul>
      {method_items_html}
      <li>Task: see the fixture under <code>experiments/harness-ab/tasks/</code> for this stamp.</li>
      <li>Isolation: each plugin arm runs from a full <code>git clone --no-hardlinks</code> (never a worktree); each CLAUDE.md is content-addressed by its sha256 prefix.</li>
      <li>n is small ({esc(trials_str) or 'see scorecard'}) &mdash; treat deltas as directional hypotheses, not statistically powered conclusions.</li>
    </ul>
    """
    method_full_html = f"""
    <ul>
      {method_items_html}
      <li>Isolation: each plugin arm runs from a full <code>git clone --no-hardlinks</code> (never a worktree) with <code>origin</code> removed; runs use <code>--setting-sources project,local</code> so operator user settings never load; the subprocess environment is scrubbed of <code>CLAUDE*</code>/<code>SWE_*</code>/<code>ANTHROPIC_*</code> vars.</li>
      <li>Auth: subscription (<code>claude.ai</code>) auth is required before any run; recorded auth mode for this experiment: <strong>{esc(auth_mode)}</strong>.</li>
      <li>n is small ({esc(trials_str) or 'see scorecard'}) &mdash; treat deltas as directional hypotheses, not statistically powered conclusions.</li>
      <li>The <code>control</code> arm has no SWE plugin or MCP servers loaded, but can still read <code>.serena/memory/</code> files as plain text if present in the fixture &mdash; &quot;no plugin&quot; is not the same guarantee as &quot;no visible workflow artifacts.&quot;</li>
      <li>Cost figures are Claude Code's own <strong>notional</strong> cost estimate on a subscription plan, not an actual charge.</li>
      <li>Model: {esc(model)} &middot; Claude Code {esc(claude_version)} &middot; auth: {esc(auth_mode)}.</li>
    </ul>
    """

    nav_items = [
        ("overall", "Overall"),
        ("explain-failures", "Explain failures"),
        ("scorecard", "Scorecard"),
        ("doc-use", "Documentation use"),
        ("gates", "Gates"),
        ("cost", "Cost"),
        ("code", "Code"),
        ("tools", "Tools"),
        ("runs", "Runs"),
        ("method", "Method"),
    ]
    if has_pivot_data:
        nav_items.insert(3, ("pivot", "Pivot"))
    nav_html = "".join(f'<li><a href="#{sid}">{esc(label)}</a></li>' for sid, label in nav_items)

    findings_section_html = (
        f'<section class="report-section findings-section"><div class="eyebrow">Key findings</div>{findings_html}</section>'
        if findings_html else ""
    )
    legacy_findings_section_html = (
        f'<section class="report-section findings-section"><h2>Findings</h2>{legacy_notes_html}</section>'
        if legacy_notes_html else ""
    )

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
body {{ font-family: 'Inter', system-ui, -apple-system, "Segoe UI", sans-serif; }}
{CSS}
</style>
</head>
<body>
  <header class="report-header">
    <h1>{esc(title)}</h1>
    <div class="meta-line">{esc(date_str)} &middot; model {esc(model)} &middot; trials/arm: {esc(trials_str) if trials_str else esc(str(trials))} &middot; claude {esc(claude_version)} &middot; auth: {esc(auth_mode)}</div>
    <p class="verdict">{esc(verdict)} <span class="run-count-tag">{esc(n_run_note)}</span></p>
  </header>

  <nav class="section-nav" aria-label="Report sections">
    <ul>{nav_html}</ul>
  </nav>

<main>
  {legacy_findings_section_html}

  <section class="report-section" id="overall">
    <div class="eyebrow">Overall review</div>
    {cost_benefit_html}
    <h2 style="margin-top:20px">Arm comparison</h2>
    <p class="section-subtitle">One column per arm; "best" is tagged only on strict per-row winners &mdash; never on ties or all-zero rows.</p>
    {overall_table_html}
    <div class="chart-grid" style="margin-top:14px">
      {quadrant_card}
    </div>
    {findings_section_html}
  </section>

  <section class="report-section" id="explain-failures">
    <div class="eyebrow">Where and why it failed</div>
    <h2>Explain failures</h2>
    <p class="section-subtitle">Every failed/errored doc-rule test, grouped by the memory rule it belongs to, with an expected-vs-actual snippet.</p>
    {explain_failures_html}
  </section>

  <section class="report-section" id="scorecard">
    <div class="eyebrow">At a glance</div>
    <h2>Scorecard</h2>
    <p class="section-subtitle">Legacy per-metric scorecard, kept as supporting detail under the Overall review above. One column per arm; delta is vs control (no harness).</p>
    <details class="table-fallback"><summary>Data</summary>
      {scorecard_table_html}
      <div class="kpi-row" style="margin-top:14px">{kpi_html}</div>
    </details>
  </section>

  {f'''<section class="report-section" id="pivot">
    <div class="eyebrow">Two-phase</div>
    <h2>Pivot: benchmark 1 vs benchmark 2</h2>
    <p class="section-subtitle">Benchmark 1 scores the tree right after task 1 (before the pivot prompt); benchmark 2 scores the final tree after the pivot phase, and adds task-1 retention (task 1's own hidden tests re-run on the final tree).</p>
    {two_phase_scorecard_table_html}
    <div class="chart-grid" style="margin-top:16px">
      {phase_cost_card}
    </div>
    <div style="margin-top:14px">
      {pivot_gate_card}
    </div>
    <details class="table-fallback"><summary>Phase token/turn medians by arm</summary>{phase_cost_median_fallback}</details>
  </section>''' if has_pivot_data else ""}

  <section class="report-section" id="doc-use">
    <div class="eyebrow">Documentation use</div>
    <h2>Spec &amp; doc-rule compliance</h2>
    <p class="section-takeaway">{esc(doc_use_takeaway)}</p>
    <div class="chart-grid">
      {spec_doc_card}
      {other_dot_cards}
    </div>
    {doc_rule_card}
    {f'<div class="chart-grid" style="margin-top:14px">{pivot_doc_rule_card}</div>' if has_pivot_data else ""}
  </section>

  <section class="report-section" id="gates">
    <div class="eyebrow">Gates</div>
    <h2>Gate conformance</h2>
    <p class="section-takeaway">{esc(gates_takeaway)}</p>
    <div class="chart-grid">
      {gate_card}
      {mem_coverage_card}
    </div>
    {f'<p class="section-subtitle" style="margin-top:14px">Pivot-phase gate conformance (reclassify/resweep/edits/doc-memory coverage) is in the <a href="#pivot">Pivot</a> section above.</p>' if has_pivot_data else ""}
  </section>

  <section class="report-section" id="cost">
    <div class="eyebrow">Cost</div>
    <h2>Tokens, turns &amp; wall time</h2>
    <p class="section-takeaway">{esc(cost_takeaway)}</p>
    <div class="chart-grid">
      {cost_dot_cards}
    </div>
    <details class="table-fallback"><summary>Token composition (main + subagent split)</summary>
      {comp_card}
    </details>
    {f'<p class="section-subtitle" style="margin-top:8px">Per-phase token breakdown (task1 | pivot) is in the <a href="#pivot">Pivot</a> section above.</p>' if has_pivot_data else ""}

    <h3 style="margin-top:24px">Delegation</h3>
    <p class="section-takeaway">{esc(deleg_takeaway)}</p>
    <div class="chart-grid">
      {delegation_card}
    </div>
  </section>

  <section class="report-section" id="code">
    <div class="eyebrow">Code</div>
    <h2>Code metrics</h2>
    <p class="section-subtitle">Size/shape proxies (LOC, function length, docstring coverage, tests written, size vs. reference solution) &mdash; not quality judgments.</p>
    {code_metrics_section_html}
  </section>

  <section class="report-section" id="tools">
    <div class="eyebrow">Tools</div>
    <h2>Tool mix &amp; friction</h2>
    <p class="section-takeaway">{esc(tools_takeaway)}</p>
    <div class="chart-grid">
      {tool_card}
      {acc_card}
      {fric_card}
    </div>
  </section>

  <section class="report-section" id="runs">
    <div class="eyebrow">Detail</div>
    <h2>Per-run detail</h2>
    <p class="section-takeaway">{len(rows)} runs across {len([a for a in ARM_ORDER if a in arms_present])} arms. Sortable; click a column header.</p>
    <details class="table-fallback">
      <summary>Per-run table ({len(rows)} rows)</summary>
      <div class="table-wrap">
        {run_table_html}
      </div>
    </details>
  </section>

  <section class="report-section method-section" id="method">
    <div class="eyebrow">Method</div>
    <h2>Method &amp; caveats</h2>
    {method_summary_html}
    <details class="method-full"><summary>Full method &amp; caveats</summary>{method_full_html}</details>
  </section>
</main>
<div id="viz-tooltip"></div>
<script>{JS}</script>
</body>
</html>
"""
    return doc


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv=None):
    p = argparse.ArgumentParser(description="Render harness A/B results as one self-contained HTML report")
    p.add_argument("stamp_dir", help="path to <results>/<stamp> directory (containing runs.jsonl, meta.json)")
    p.add_argument("--out", default="report.html", help="output HTML path (default report.html)")
    p.add_argument("--title", default="Harness A/B Results", help="report title (default: 'Harness A/B Results')")
    p.add_argument("--notes", default=None, metavar="FILE",
                    help="path to a findings file: either the simple line "
                         "format (one finding per line, '- text') rendered "
                         "as individual key-finding cards, or (backward "
                         "compat) a trusted HTML fragment injected verbatim "
                         "as a 'Findings' section when no '- text' line "
                         "matches. Not escaped in the HTML-fragment case — "
                         "the file's content is the author's own write-up, "
                         "not untrusted data.")
    args = p.parse_args(argv)

    rows = load_rows(args.stamp_dir)
    meta = load_meta(args.stamp_dir)

    notes_html = None
    notes_text = None
    if args.notes:
        with open(args.notes) as f:
            notes_text = f.read()
        notes_html = notes_text

    doc = render_report(rows, meta, title=args.title, notes_html=notes_html, notes_text=notes_text,
                         stamp_dir=args.stamp_dir)

    with open(args.out, "w") as f:
        f.write(doc)

    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
