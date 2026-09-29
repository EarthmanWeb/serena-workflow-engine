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


def compute_verdict(agg):
    """Plain-language one-sentence verdict from aggregate() output. Pure."""
    arms = agg.get("arms", {})
    present = [a for a in ARM_ORDER if a in arms]
    if not present:
        return "No runs to report."

    best_arm, best_rate = None, -1
    for a in present:
        rate = arms[a].get("success_rate")
        if rate is not None and rate > best_rate:
            best_rate, best_arm = rate, a

    parts = []
    if best_arm is not None:
        parts.append(
            f"{ARM_LABELS.get(best_arm, best_arm)} had the highest acceptance success rate "
            f"({best_rate * 100:.0f}%)."
        )
    else:
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
}
body { padding: 16px; }
main { max-width: 1100px; margin: 0 auto; min-width: 0; }
h1, h2, h3 { font-weight: 600; }
h1 { font-size: 1.5rem; margin: 0 0 4px; }
h2 { font-size: 1.1rem; margin: 28px 0 10px; border-bottom: 1px solid var(--border); padding-bottom: 6px; }
p { line-height: 1.5; color: var(--text-secondary); }
.muted { color: var(--text-muted); }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); }

header.report-header {
  border-bottom: 1px solid var(--border);
  padding-bottom: 14px;
  margin-bottom: 12px;
}
.meta-line { font-size: 0.85rem; color: var(--text-muted); }
.verdict { font-size: 0.95rem; color: var(--text-primary); margin-top: 8px; }

.kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr));
  gap: 10px;
  margin: 14px 0;
}
.kpi-card {
  border: 1px solid var(--border);
  border-left: 3px solid var(--arm-accent);
  border-radius: 6px;
  padding: 10px 12px;
  background: var(--surface-1);
}
.kpi-arm { font-weight: 600; font-size: 0.9rem; display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.chip { display: inline-block; width: 10px; height: 10px; border-radius: 2px; }
.kpi-list { margin: 0; display: grid; gap: 3px; }
.kpi-list > div { display: flex; justify-content: space-between; gap: 8px; font-size: 0.82rem; }
.kpi-list dt { color: var(--text-muted); }
.kpi-list dd { margin: 0; font-variant-numeric: tabular-nums; font-weight: 600; }

.chart-section { margin-bottom: 22px; }
.small-multiples { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(320px, 100%), 1fr)); gap: 8px 16px; min-width: 0; }
.small-multiples > .chart-card { min-width: 0; }
.chart-svg { display: block; background: var(--surface-1); border: 1px solid var(--border); border-radius: 6px; max-width: 100%; height: auto; }
.chart-title { fill: var(--text-primary); font-weight: 600; }
.tick-label, .legend-label { fill: var(--text-muted); }
.row-label { fill: var(--text-secondary); }
.grid-line { stroke: var(--gridline); stroke-width: 1; }
.mark-dot, .mark-bar, .comp-seg, .tool-seg { cursor: pointer; }
.mark-dot:hover, .mark-bar:hover, .comp-seg:hover, .tool-seg:hover { opacity: 0.8; }

details.table-fallback { margin-top: 6px; font-size: 0.82rem; }
details.table-fallback summary { cursor: pointer; color: var(--text-secondary); }
.fallback-table-wrap { overflow-x: auto; }
.fallback-table { border-collapse: collapse; width: 100%; margin-top: 6px; font-variant-numeric: tabular-nums; font-size: 0.8rem; }
.fallback-table th, .fallback-table td { text-align: left; padding: 3px 8px; border-bottom: 1px solid var(--border); }

.heatmap-table { border-collapse: collapse; font-size: 0.82rem; font-variant-numeric: tabular-nums; }
.heatmap-table th, .heatmap-table td { padding: 4px 10px; text-align: right; border-bottom: 1px solid var(--border); }
.heatmap-table th:first-child, .heatmap-table td:first-child { text-align: left; }
.heat-cell { background: color-mix(in oklab, var(--arm-baseline) calc(var(--heat-t) * 70%), var(--surface-1)); }

.table-wrap { overflow-x: auto; }
table.run-table { border-collapse: collapse; width: 100%; font-size: 0.82rem; font-variant-numeric: tabular-nums; min-width: 900px; }
table.run-table th, table.run-table td { padding: 5px 9px; border-bottom: 1px solid var(--border); text-align: right; white-space: nowrap; }
table.run-table th:first-child, table.run-table td:first-child { text-align: left; }
table.run-table thead th { cursor: pointer; color: var(--text-secondary); font-weight: 600; user-select: none; position: sticky; top: 0; background: var(--surface-1); }
table.run-table thead th:hover { color: var(--text-primary); }
.sort-indicator::after { content: ""; }
.sort-indicator.asc::after { content: " \\2191"; }
.sort-indicator.desc::after { content: " \\2193"; }
.success-yes { color: var(--success-good); font-weight: 600; }
.success-no { color: var(--status-critical); font-weight: 600; }

.method-section ul { padding-left: 18px; color: var(--text-secondary); font-size: 0.88rem; line-height: 1.5; }

/* Tooltip */
#viz-tooltip {
  position: fixed; pointer-events: none; z-index: 50;
  background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 4px; padding: 4px 8px; font-size: 0.78rem;
  color: var(--text-primary); box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  display: none; white-space: nowrap;
}

@media (max-width: 480px) {
  h1 { font-size: 1.2rem; }
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


def render_report(rows, meta, title="Harness A/B Results", notes_html=None):
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

    # --- KPI row ---
    kpi_html = kpi_row(agg)

    # --- dot/strip small multiples ---
    dot_charts = []
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
        dot_charts.append(f"""
        <div class="chart-card">
          {svg}
          <details class="table-fallback"><summary>Data table</summary>{fallback}</details>
        </div>""")

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

    # --- acceptance ---
    acc_rows = acceptance_rows(rows)
    acc_svg, _acc_h = acceptance_bar_chart(acc_rows)
    acc_fallback = build_fallback_table(
        [(ARM_LABELS.get(r["arm"], r["arm"]), r["trial"], f'{r["passed"]}/{r["total"]}', fmt_pct(r["pct"]), r["reg_ok"]) for r in sorted(acc_rows, key=lambda r: (ARM_ORDER.index(r["arm"]) if r["arm"] in ARM_ORDER else 99, r["trial"] or 0))],
        ["arm", "trial", "passed/total", "pct", "regression ok"]
    )

    # --- friction ---
    fric_rows = friction_rows(rows)
    fric_svg, _fric_h = friction_chart(fric_rows)
    fric_fallback = build_fallback_table(
        [(ARM_LABELS.get(r["arm"], r["arm"]), r["trial"], r["hook_denials"], r["stop_hook_blocks"]) for r in sorted(fric_rows, key=lambda r: (ARM_ORDER.index(r["arm"]) if r["arm"] in ARM_ORDER else 99, r["trial"] or 0))],
        ["arm", "trial", "hook denials", "stop-hook blocks"]
    )
    stream_table_html = stream_event_heatmap(stream_event_table(rows))

    # --- tool mix ---
    tool_order, per_arm_tools = tool_mix_rows(rows)
    tool_svg = tool_mix_chart(tool_order, per_arm_tools)
    tool_fallback_rows = []
    for arm in ARM_ORDER:
        row = per_arm_tools.get(arm, {})
        tool_fallback_rows.append([ARM_LABELS.get(arm, arm)] + [fmt_num(row.get(t, 0)) for t in tool_order])
    tool_fallback = build_fallback_table(tool_fallback_rows, ["arm"] + tool_order)

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

    method_html = f"""
    <ul>
      {''.join(arm_method_items) if arm_method_items else '<li>Arm metadata not recorded in meta.json.</li>'}
      <li>Isolation: each plugin arm runs from a full <code>git clone --no-hardlinks</code> (never a worktree) with <code>origin</code> removed; runs use <code>--setting-sources project,local</code> so operator user settings never load; the subprocess environment is scrubbed of <code>CLAUDE*</code>/<code>SWE_*</code>/<code>ANTHROPIC_*</code> vars.</li>
      <li>Auth: subscription (<code>claude.ai</code>) auth is required before any run; recorded auth mode for this experiment: <strong>{esc(auth_mode)}</strong>.</li>
      <li>n is small ({esc(trials_str) or 'see KPI row'}) &mdash; treat deltas as directional hypotheses, not statistically powered conclusions.</li>
      <li>The <code>control</code> arm has no SWE plugin or MCP servers loaded, but can still read <code>.serena/memory/</code> files as plain text if present in the fixture &mdash; &quot;no plugin&quot; is not the same guarantee as &quot;no visible workflow artifacts.&quot;</li>
      <li>Cost figures are Claude Code's own <strong>notional</strong> cost estimate on a subscription plan, not an actual charge.</li>
    </ul>
    """

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
<main>
  <header class="report-header">
    <h1>{esc(title)}</h1>
    <div class="meta-line">{esc(date_str)} &middot; model {esc(model)} &middot; trials/arm: {esc(trials_str) if trials_str else esc(str(trials))} &middot; claude {esc(claude_version)} &middot; auth: {esc(auth_mode)}</div>
    <p class="verdict">{esc(verdict)}</p>
  </header>

  {f'<section class="chart-section findings-section"><h2>Findings</h2>{notes_html}</section>' if notes_html else ''}

  <section class="kpi-row">
    {kpi_html}
  </section>

  <section class="chart-section">
    <h2>Run metrics (dot/strip plots, per arm, with median tick)</h2>
    <div class="small-multiples">
      {''.join(dot_charts)}
    </div>
  </section>

  <section class="chart-section">
    <h2>Token composition per run</h2>
    {comp_svg}
    <details class="table-fallback"><summary>Data table</summary>{comp_fallback}</details>
  </section>

  <section class="chart-section">
    <h2>Acceptance pass rate</h2>
    {acc_svg}
    <details class="table-fallback"><summary>Data table</summary>{acc_fallback}</details>
  </section>

  <section class="chart-section">
    <h2>Harness friction</h2>
    {fric_svg}
    <details class="table-fallback"><summary>Data table</summary>{fric_fallback}</details>
    <h3>Top stream event types by arm (plugin arms only)</h3>
    {stream_table_html}
  </section>

  <section class="chart-section">
    <h2>Tool mix</h2>
    {tool_svg}
    <details class="table-fallback"><summary>Data table</summary>{tool_fallback}</details>
  </section>

  <section class="chart-section">
    <h2>Per-run detail</h2>
    <div class="table-wrap">
      {run_table_html}
    </div>
  </section>

  <section class="method-section">
    <h2>Method &amp; caveats</h2>
    {method_html}
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
    p.add_argument("--notes", default=None, metavar="FILE.html",
                    help="path to a trusted HTML fragment injected verbatim as a "
                         "'Findings' section right after the header, before the "
                         "KPI row. Not escaped — the file's content is the "
                         "author's own write-up, not untrusted data.")
    args = p.parse_args(argv)

    rows = load_rows(args.stamp_dir)
    meta = load_meta(args.stamp_dir)

    notes_html = None
    if args.notes:
        with open(args.notes) as f:
            notes_html = f.read()

    doc = render_report(rows, meta, title=args.title, notes_html=notes_html)

    with open(args.out, "w") as f:
        f.write(doc)

    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
