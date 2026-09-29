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

# --------------------------------------------------------------------------
# Import analyze.py by path (read-only use of aggregate()).
# --------------------------------------------------------------------------


def _load_analyze():
    spec = importlib.util.spec_from_file_location("harness_ab_analyze", ANALYZE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_analyze = None


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

    best_doc_arm, best_doc_pct = None, -1
    for a in present:
        pct = arms[a].get("doc_pass_pct_mean")
        if pct is not None and pct > best_doc_pct:
            best_doc_pct, best_doc_arm = pct, a

    parts = []
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
        f'<text x="{pad_left}" y="10" class="chart-title" font-size="11">{esc(metric_label)}</text>'
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
            f'font-size="9" text-anchor="middle">{fmt_num(tv)}</text>'
        )

    by_arm = {a: [] for a in ARM_ORDER}
    for (arm, trial, v) in rows:
        by_arm.setdefault(arm, []).append((trial, v))

    for i, arm in enumerate(ARM_ORDER):
        cy = pad_top + row_h * i + row_h / 2
        parts.append(
            f'<text x="{pad_left - 10}" y="{cy + 3:.1f}" text-anchor="end" '
            f'class="row-label" font-size="10">{esc(ARM_LABELS[arm])}</text>'
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
        f'<text x="0" y="12" class="chart-title" font-size="11">Token composition per run</text>'
    )
    # legend (sequential ramp swatches), on its own row below the title
    lx = 0
    ly = 32
    for k in keys:
        parts_html.append(f'<rect x="{lx}" y="{ly - 8}" width="10" height="10" fill="{COMPOSITION_LIGHT[k]}" class="legend-swatch" data-key="{k}" />')
        parts_html.append(f'<text x="{lx + 14}" y="{ly}" class="legend-label" font-size="9">{esc(key_labels[k])}</text>')
        lx += 14 + len(key_labels[k]) * 6 + 16

    y = pad_top + 8
    for (run_id, arm, trial, comp) in ordered:
        cy = y
        color = f'var(--arm-{arm})'
        parts_html.append(
            f'<rect x="{pad_left - 178}" y="{cy - 9}" width="9" height="9" fill="{color}" rx="2" />'
        )
        parts_html.append(
            f'<text x="{pad_left - 165}" y="{cy}" class="row-label" font-size="9.5">'
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
            f'font-size="9">{fmt_num(total)}</text>'
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
    parts.append(f'<text x="0" y="12" class="chart-title" font-size="11">Acceptance pass rate per run (0-100%)</text>')

    y = pad_top + 8
    for r in ordered:
        cy = y
        color = f'var(--arm-{r["arm"]})'
        parts.append(f'<text x="{pad_left - 8}" y="{cy}" text-anchor="end" class="row-label" font-size="9.5">{esc(ARM_LABELS.get(r["arm"], r["arm"]))} t{esc(r["trial"])}</text>')
        w = xscale(r["pct"])
        parts.append(
            f'<rect x="{pad_left}" y="{cy - row_h + 4:.1f}" width="{max(w, 0):.1f}" height="{row_h - 8}" '
            f'fill="{color}" rx="4" class="mark-bar" '
            f'data-tip="{fmt_pct(r["pct"])} ({r["passed"]}/{r["total"]})">'
            f'<title>{esc(ARM_LABELS.get(r["arm"], r["arm"]))} t{esc(r["trial"])}: {fmt_pct(r["pct"])} '
            f'({r["passed"]}/{r["total"]}) regression_ok={r["reg_ok"]}</title></rect>'
        )
        parts.append(f'<text x="{pad_left + w + 6:.1f}" y="{cy - row_h/2 + 4:.1f}" class="tick-label" font-size="9">{fmt_pct(r["pct"])}</text>')
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
    parts.append(f'<text x="0" y="12" class="chart-title" font-size="11">Harness friction per run (hook denials / stop-hook blocks)</text>')
    parts.append(f'<text x="{pad_left}" y="26" class="legend-label" font-size="9">denials</text>')
    parts.append(f'<text x="{pad_left + plot_w/2 + 10:.1f}" y="26" class="legend-label" font-size="9">stop blocks</text>')

    y = pad_top + 10
    for r in ordered:
        cy = y
        color = f'var(--arm-{r["arm"]})'
        parts.append(f'<text x="{pad_left - 8}" y="{cy}" text-anchor="end" class="row-label" font-size="9.5">{esc(ARM_LABELS.get(r["arm"], r["arm"]))} t{esc(r["trial"])}</text>')
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
    parts.append(f'<text x="0" y="12" class="chart-title" font-size="11">Tool mix by arm (top {TOOL_TOP_N} + Other)</text>')

    for i, arm in enumerate(ARM_ORDER):
        cy = pad_top + row_h * i + row_h / 2
        parts.append(f'<text x="{pad_left - 10}" y="{cy + 3:.1f}" text-anchor="end" class="row-label" font-size="10">{esc(ARM_LABELS[arm])}</text>')
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
        parts.append(f'<text x="{lx + 12}" y="{ly}" class="legend-label" font-size="8.5">{esc(label)}</text>')
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
    parts.append('<text x="0" y="12" class="chart-title" font-size="11">Spec vs doc-rule pass % per arm (mean across runs)</text>')
    # legend
    parts.append(f'<rect x="{pad_left - 178}" y="18" width="10" height="10" fill="var(--arm-baseline)" />')
    parts.append(f'<text x="{pad_left - 164}" y="27" class="legend-label" font-size="9">spec</text>')
    parts.append(f'<rect x="{pad_left - 130}" y="18" width="10" height="10" fill="var(--arm-baseline)" opacity="0.45" />')
    parts.append(f'<text x="{pad_left - 116}" y="27" class="legend-label" font-size="9">doc</text>')

    y = pad_top + 6
    for arm in arms_present:
        vals = spec_doc_by_arm[arm]
        color = f'var(--arm-{arm})'
        parts.append(f'<text x="{pad_left - 8}" y="{y + row_h - 4:.1f}" text-anchor="end" class="row-label" font-size="9.5">{esc(ARM_LABELS.get(arm, arm))}</text>')
        for key, opacity, label in (("spec", 1.0, "spec"), ("doc", 0.45, "doc")):
            v = vals.get(key)
            cy = y
            if v is None:
                parts.append(f'<text x="{pad_left}" y="{cy + row_h/2:.1f}" class="tick-label" font-size="9">no {label} tests</text>')
            else:
                w = max(xscale(v), 0)
                parts.append(
                    f'<rect x="{pad_left}" y="{cy:.1f}" width="{w:.1f}" height="{row_h - 4}" '
                    f'fill="{color}" opacity="{opacity}" rx="3" class="mark-bar" '
                    f'data-tip="{esc(ARM_LABELS.get(arm, arm))} {label}: {fmt_pct(v)}">'
                    f'<title>{esc(ARM_LABELS.get(arm, arm))} {label}: {fmt_pct(v)}</title></rect>'
                )
                parts.append(f'<text x="{pad_left + w + 6:.1f}" y="{cy + row_h/2 + 3:.1f}" class="tick-label" font-size="9">{label} {fmt_pct(v)}</text>')
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
    parts.append('<text x="0" y="10" class="chart-title" font-size="11">Doc-rule memory coverage per run (% of task doc_rules memories read)</text>')
    for tv in (0, 25, 50, 75, 100):
        x = xscale(tv)
        parts.append(f'<line x1="{x:.1f}" y1="{pad_top}" x2="{x:.1f}" y2="{height - pad_bottom}" class="grid-line" />')
        parts.append(f'<text x="{x:.1f}" y="{height - pad_bottom + 14}" class="tick-label" font-size="9" text-anchor="middle">{tv}%</text>')

    by_arm = {a: [] for a in arms_present}
    for r in mem_rows:
        if r["arm"] in by_arm:
            by_arm[r["arm"]].append(r)

    for i, arm in enumerate(arms_present):
        cy = pad_top + row_h * i + row_h / 2
        parts.append(f'<text x="{pad_left - 10}" y="{cy + 3:.1f}" text-anchor="end" class="row-label" font-size="10">{esc(ARM_LABELS.get(arm, arm))}</text>')
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

    return (
        f'<td class="scorecard-cell" data-sort="{val if val is not None else ""}">'
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
                f'<td class="scorecard-cell"><div class="scorecard-value muted">not measured</div></td>' for _a in present
            )
        else:
            cells_html = "".join(_scorecard_cell_html(row, a, control_arm) for a in present)
        body_rows.append(f'<tr><th scope="row" class="scorecard-row-label">{esc(row["label"])}</th>{cells_html}</tr>')

    return (
        '<div class="scorecard-wrap"><table class="scorecard-table">'
        f'<thead><tr><th scope="col" class="scorecard-corner"></th>{"".join(head_cells)}</tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody></table></div>'
    )


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

/* Findings cards */
.findings-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr));
  gap: 10px; margin-top: 12px;
}
.finding-card {
  border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px;
  background: var(--surface-1); font-size: 0.88rem; line-height: 1.45; color: var(--text-primary);
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


def render_report(rows, meta, title="Harness A/B Results", notes_html=None, notes_text=None):
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

    verdict = compute_verdict(agg)

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

    doc_use_takeaway = _takeaway_doc_use(agg)
    gates_takeaway = _takeaway_gates(agg)
    cost_takeaway = _takeaway_cost(agg)
    tools_takeaway = _takeaway_tools(rows)

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
        ("scorecard", "Scorecard"),
        ("doc-use", "Documentation use"),
        ("gates", "Gates"),
        ("cost", "Cost"),
        ("tools", "Tools"),
        ("runs", "Runs"),
        ("method", "Method"),
    ]
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
    <p class="verdict">{esc(verdict)}</p>
  </header>

  <nav class="section-nav" aria-label="Report sections">
    <ul>{nav_html}</ul>
  </nav>

<main>
  {legacy_findings_section_html}

  <section class="report-section" id="scorecard">
    <div class="eyebrow">At a glance</div>
    <h2>Scorecard</h2>
    <p class="section-subtitle">One column per arm; delta is vs control (no harness). Best value per row is bold with a "best" tag.</p>
    {scorecard_table_html}
    {findings_section_html}
    <details class="table-fallback"><summary>Data (per-arm KPI cards)</summary>
      <div class="kpi-row">{kpi_html}</div>
    </details>
  </section>

  <section class="report-section" id="doc-use">
    <div class="eyebrow">Documentation use</div>
    <h2>Spec &amp; doc-rule compliance</h2>
    <p class="section-takeaway">{esc(doc_use_takeaway)}</p>
    <div class="chart-grid">
      {spec_doc_card}
      {other_dot_cards}
    </div>
    {doc_rule_card}
  </section>

  <section class="report-section" id="gates">
    <div class="eyebrow">Gates</div>
    <h2>Gate conformance</h2>
    <p class="section-takeaway">{esc(gates_takeaway)}</p>
    <div class="chart-grid">
      {gate_card}
      {mem_coverage_card}
    </div>
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

    doc = render_report(rows, meta, title=args.title, notes_html=notes_html, notes_text=notes_text)

    with open(args.out, "w") as f:
        f.write(doc)

    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
