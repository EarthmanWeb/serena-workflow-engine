#!/usr/bin/env python3
"""Analyze harness A/B results: aggregate runs.jsonl per arm, print a
markdown table, optionally write CSVs, always write summary.json.
"""
import argparse
import csv
import json
import os
import sys

def _est_cost_usd(r):
    """`est_cost_usd` is the current field name; older runs.jsonl rows (written
    before the rename) used `total_cost_usd`. Read either, preferring the new
    name. Both values are Claude Code's notional cost estimate, never an
    actual charge — the harness runs on a claude.ai Max subscription."""
    m = r.get("metrics") or {}
    if "est_cost_usd" in m:
        return m.get("est_cost_usd")
    return m.get("total_cost_usd")


def _tool_calls(r):
    """`total_tool_calls` is the current field name; a small number of very
    old runs.jsonl rows (written before parse_transcript computed it) only
    have the ambiguous `tool_calls` key. Read either, preferring the new
    name."""
    m = r.get("metrics") or {}
    if "total_tool_calls" in m:
        return m.get("total_tool_calls")
    return m.get("tool_calls")


METRIC_FIELDS = [
    # assistant_turns_incl_subagents is the PRIMARY "turns" metric: total
    # assistant-message events across the main agent + every subagent
    # combined. num_turns (the stream-json result event's own counter) is
    # main-agent-only and can be misleadingly low on a run that fanned out
    # into subagents (see run.parse_transcript's docstring) — kept as a
    # secondary/diagnostic field, never used alone for cross-arm comparison.
    ("assistant_turns_incl_subagents", lambda r: (r.get("metrics") or {}).get("assistant_turns_incl_subagents")),
    ("num_turns", lambda r: (r.get("metrics") or {}).get("num_turns")),
    # total_tokens == all_model_tokens: the authoritative total summed over
    # the result event's modelUsage (camelCase per-model dict), which
    # includes subagent token spend the main-agent-only `usage` block
    # misses entirely. See run.parse_transcript's docstring.
    ("total_tokens", lambda r: (r.get("metrics") or {}).get("total_tokens")),
    ("main_tokens", lambda r: (r.get("metrics") or {}).get("main_tokens")),
    ("output_tokens", lambda r: (r.get("metrics") or {}).get("usage", {}).get("output_tokens")),
    ("cache_read_tokens", lambda r: (r.get("metrics") or {}).get("usage", {}).get("cache_read_input_tokens")),
    ("est_cost_usd", _est_cost_usd),
    ("wall_s", lambda r: r.get("wall_s")),
    ("tool_calls", _tool_calls),
    ("memory_file_reads", lambda r: (r.get("metrics") or {}).get("memory_file_reads")),
    ("subagent_launches", lambda r: (r.get("metrics") or {}).get("subagent_launches")),
    ("subagent_messages", lambda r: (r.get("metrics") or {}).get("subagent_messages")),
    ("hook_denials", lambda r: (r.get("metrics") or {}).get("hook_denials")),
    ("stop_hook_blocks", lambda r: (r.get("metrics") or {}).get("stop_hook_blocks")),
]

METRIC_LABELS = {
    "est_cost_usd": "est. cost (notional)",
    "total_tokens": "total tokens (all models, incl. subagents)",
    "main_tokens": "main-agent tokens only",
    "assistant_turns_incl_subagents": "turns (all agents)",
    "num_turns": "main-agent turns",
}


def _acceptance_category_pct(r, category):
    """Pass % (0-100) for one acceptance category ('spec'/'doc'/'other') on
    one run row, or None when that category has no tests recorded (older
    rows predating the category breakdown, or a task with none of that
    category)."""
    acc = r.get("acceptance") or {}
    cat = acc.get(category) or {}
    total = cat.get("total") or 0
    if not total:
        return None
    return 100.0 * (cat.get("passed") or 0) / total


def _gate_bool(r, key):
    gates = r.get("gates") or {}
    val = gates.get(key)
    return val if isinstance(val, bool) else None


def _gate_int(r, key):
    gates = r.get("gates") or {}
    val = gates.get(key)
    return val if isinstance(val, (int, float)) else None


def _doc_rule_coverage(r):
    gates = r.get("gates") or {}
    val = gates.get("doc_rule_memories_coverage")
    return val if isinstance(val, (int, float)) else None


def spec_doc_pass_stats(rows):
    """Per-arm spec/doc pass % (mean across runs that had tests in that
    category). Returns {arm: {"spec_pass_pct_mean": float|None,
    "doc_pass_pct_mean": float|None}}. Pure."""
    by_arm = {}
    for r in rows:
        by_arm.setdefault(r.get("arm"), []).append(r)
    out = {}
    for arm, arm_rows in by_arm.items():
        spec_vals = [v for v in (_acceptance_category_pct(r, "spec") for r in arm_rows) if v is not None]
        doc_vals = [v for v in (_acceptance_category_pct(r, "doc") for r in arm_rows) if v is not None]
        out[arm] = {
            "spec_pass_pct_mean": mean(spec_vals),
            "doc_pass_pct_mean": mean(doc_vals),
        }
    return out


def gate_conformance_stats(rows):
    """Per-arm gate-conformance rollup: init_chain_complete rate,
    sweep_verified rate, mean edits_before_sweep, mean
    doc_rule_memories_coverage. Returns {arm: {...}}. Pure. A run with no
    "gates" field at all (pre-conformance-feature row) is excluded from the
    rate/mean denominators for that row's arm rather than counted as a
    failure, so an un-reparsed old stamp doesn't silently read as 0%
    conformant."""
    by_arm = {}
    for r in rows:
        by_arm.setdefault(r.get("arm"), []).append(r)
    out = {}
    for arm, arm_rows in by_arm.items():
        with_gates = [r for r in arm_rows if isinstance(r.get("gates"), dict)]
        n = len(with_gates)
        init_vals = [_gate_bool(r, "init_chain_complete") for r in with_gates]
        init_vals = [v for v in init_vals if v is not None]
        sweep_vals = [_gate_bool(r, "sweep_verified") for r in with_gates]
        sweep_vals = [v for v in sweep_vals if v is not None]
        edits_vals = [v for v in (_gate_int(r, "edits_before_sweep") for r in with_gates) if v is not None]
        coverage_vals = [v for v in (_doc_rule_coverage(r) for r in with_gates) if v is not None]

        out[arm] = {
            "n_with_gates": n,
            "init_chain_complete_rate": (sum(1 for v in init_vals if v) / len(init_vals)) if init_vals else None,
            "sweep_verified_rate": (sum(1 for v in sweep_vals if v) / len(sweep_vals)) if sweep_vals else None,
            "edits_before_sweep_mean": mean(edits_vals),
            "doc_rule_memories_coverage_mean": mean(coverage_vals),
        }
    return out


def _has_phases(r):
    """True iff this row is a two-phase (pivot) run — carries a `phases`
    dict with both task1 and pivot keys. A single-phase row (including one
    from a task with no pivot/) has no `phases` field at all."""
    phases = r.get("phases")
    return isinstance(phases, dict) and "task1" in phases and "pivot" in phases


def _benchmark_pct(benchmark, category):
    """Pass % (0-100) for one acceptance category on a phases.<phase>.
    benchmark dict (score_hidden_tests_dir()'s return shape) — same idea as
    _acceptance_category_pct but reading a benchmark sub-dict directly
    instead of a top-level row's "acceptance" field."""
    if not isinstance(benchmark, dict):
        return None
    cat = benchmark.get(category) or {}
    total = cat.get("total") or 0
    if not total:
        return None
    return 100.0 * (cat.get("passed") or 0) / total


def _benchmark_success(benchmark):
    """A benchmark counts as a success iff it ran at least one test and all
    of them passed (100% of that benchmark, per the spec: success = 100% of
    that benchmark). None (not measured) when no tests ran at all."""
    if not isinstance(benchmark, dict):
        return None
    total = benchmark.get("total") or 0
    if not total:
        return None
    return bool(benchmark.get("ok"))


def pivot_benchmark_stats(rows):
    """Per-arm Benchmark 1 / Benchmark 2 stats for two-phase rows only.
    Returns {arm: {"b1": {...}, "b2": {...}, "task1_retention": {...},
    "n_pivot": n}}. Non-pivot rows (single-phase, or a pivot-less task) are
    excluded entirely rather than counted as zero -- an arm with no pivot
    rows at all gets an empty per-arm entry (n_pivot == 0), so callers can
    tell "no pivot data" from "0% success on pivot data". Pure."""
    by_arm = {}
    for r in rows:
        if _has_phases(r):
            by_arm.setdefault(r.get("arm"), []).append(r)

    out = {}
    for arm, arm_rows in by_arm.items():
        b1_bench = [r["phases"]["task1"].get("benchmark") for r in arm_rows]
        b2_bench = [r["phases"]["pivot"].get("benchmark") for r in arm_rows]

        b1_spec = [v for v in (_benchmark_pct(b, "spec") for b in b1_bench) if v is not None]
        b1_doc = [v for v in (_benchmark_pct(b, "doc") for b in b1_bench) if v is not None]
        b1_success = [v for v in (_benchmark_success(b) for b in b1_bench) if v is not None]

        b2_spec = [v for v in (_benchmark_pct(b, "spec") for b in b2_bench) if v is not None]
        b2_doc = [v for v in (_benchmark_pct(b, "doc") for b in b2_bench) if v is not None]
        b2_success = [v for v in (_benchmark_success(b) for b in b2_bench) if v is not None]

        retentions = [r["phases"]["pivot"].get("task1_retention") for r in arm_rows]
        retentions = [t for t in retentions if isinstance(t, dict)]
        retention_rates = []
        total_regressions = 0
        for t in retentions:
            total = t.get("total") or 0
            if total:
                retention_rates.append(100.0 * (t.get("passed") or 0) / total)
            total_regressions += len(t.get("regressions") or [])

        task1_medians = _phase_metric_medians(r["phases"]["task1"].get("metrics") for r in arm_rows)
        pivot_medians = _phase_metric_medians(r["phases"]["pivot"].get("metrics") for r in arm_rows)

        out[arm] = {
            "n_pivot": len(arm_rows),
            "b1": {
                "spec_pass_pct_mean": mean(b1_spec),
                "doc_pass_pct_mean": mean(b1_doc),
                "success_rate": mean([1.0 if v else 0.0 for v in b1_success]) if b1_success else None,
            },
            "b2": {
                "spec_pass_pct_mean": mean(b2_spec),
                "doc_pass_pct_mean": mean(b2_doc),
                "success_rate": mean([1.0 if v else 0.0 for v in b2_success]) if b2_success else None,
            },
            "task1_retention": {
                "rate_mean": mean(retention_rates),
                "total_regressions": total_regressions,
            },
            "phase_medians": {
                "task1": task1_medians,
                "pivot": pivot_medians,
            },
        }
    return out


_PHASE_METRIC_KEYS = ("total_tokens", "assistant_turns_incl_subagents",
                       "num_turns", "total_tool_calls", "est_cost_usd")


def _phase_metric_medians(metrics_iter):
    """Per-phase median of a fixed set of metrics (tokens/turns/tool_calls/
    est_cost) across a set of phases.<phase>.metrics dicts. Pure."""
    vals_by_key = {k: [] for k in _PHASE_METRIC_KEYS}
    for m in metrics_iter:
        if not isinstance(m, dict):
            continue
        for k in _PHASE_METRIC_KEYS:
            v = m.get(k)
            if isinstance(v, (int, float)):
                vals_by_key[k].append(v)
    return {k: median(v) for k, v in vals_by_key.items()}


def pivot_gate_stats(rows):
    """Per-arm pivot-gate conformance rollup: pivot_reclassified (attempted/
    succeeded rates), pivot_resweep_verified rate, mean
    pivot_edits_before_sweep, mean pivot_doc_rule_memories_coverage. Reads
    phases.pivot.gates on two-phase rows only. Pure."""
    by_arm = {}
    for r in rows:
        if _has_phases(r):
            by_arm.setdefault(r.get("arm"), []).append(r)

    out = {}
    for arm, arm_rows in by_arm.items():
        pivot_gates = [r["phases"]["pivot"].get("gates") for r in arm_rows]
        pivot_gates = [g for g in pivot_gates if isinstance(g, dict)]
        n = len(pivot_gates)

        reclass = [g.get("pivot_reclassified") for g in pivot_gates]
        reclass = [rc for rc in reclass if isinstance(rc, dict)]
        attempted_vals = [rc.get("attempted") for rc in reclass]
        succeeded_vals = [rc.get("succeeded") for rc in reclass]

        resweep_vals = [g.get("pivot_resweep_verified") for g in pivot_gates]
        resweep_vals = [v for v in resweep_vals if isinstance(v, bool)]

        edits_vals = [g.get("pivot_edits_before_sweep") for g in pivot_gates]
        edits_vals = [v for v in edits_vals if isinstance(v, (int, float))]

        coverage_vals = [g.get("pivot_doc_rule_memories_coverage") for g in pivot_gates]
        coverage_vals = [v for v in coverage_vals if isinstance(v, (int, float))]

        out[arm] = {
            "n_with_pivot_gates": n,
            "pivot_reclassified_attempted_rate":
                (sum(1 for v in attempted_vals if v) / len(attempted_vals)) if attempted_vals else None,
            "pivot_reclassified_succeeded_rate":
                (sum(1 for v in succeeded_vals if v) / len(succeeded_vals)) if succeeded_vals else None,
            "pivot_resweep_verified_rate":
                (sum(1 for v in resweep_vals if v) / len(resweep_vals)) if resweep_vals else None,
            "pivot_edits_before_sweep_mean": mean(edits_vals),
            "pivot_doc_rule_memories_coverage_mean": mean(coverage_vals),
        }
    return out


def doc_rule_pass_matrix(rows):
    """arm x rule pass matrix from each row's acceptance["doc_rules"] (see
    acceptance.doc_rule_pass_matrix). Returns
    {arm: {rule_id: {"passed": n, "total": n, "ok": bool|None,
                      "memory": str}}} aggregated (summed) across every run
    of that arm. A rule absent from a given row (task has no doc_rules, or
    an old row predating this field) contributes nothing for that row.
    Pure."""
    matrix = {}
    for r in rows:
        arm = r.get("arm")
        acc = r.get("acceptance") or {}
        rules = acc.get("doc_rules") or {}
        if not isinstance(rules, dict):
            continue
        arm_matrix = matrix.setdefault(arm, {})
        for rule_id, rule_result in rules.items():
            if not isinstance(rule_result, dict):
                continue
            entry = arm_matrix.setdefault(rule_id, {"passed": 0, "total": 0, "memory": rule_result.get("memory")})
            entry["passed"] += rule_result.get("passed") or 0
            entry["total"] += rule_result.get("total") or 0
            entry["memory"] = entry["memory"] or rule_result.get("memory")
    for arm_matrix in matrix.values():
        for entry in arm_matrix.values():
            entry["ok"] = (entry["passed"] == entry["total"]) if entry["total"] > 0 else None
    return matrix


def _swe_gate_count(r):
    """Count of `gated` events in this run's SWE stream (internal
    init/docs/edit gate firings recorded by the plugin itself), from
    stream_metrics.stream_event_counts."""
    sm = r.get("stream_metrics") or {}
    counts = sm.get("stream_event_counts") or {}
    return counts.get("gated")


def _swe_top_event_types(rows, top_n=8):
    """Aggregate stream_event_counts across rows -> [(type, total_count)],
    sorted descending, top_n entries."""
    totals = {}
    for r in rows:
        sm = r.get("stream_metrics") or {}
        for k, v in (sm.get("stream_event_counts") or {}).items():
            if isinstance(v, (int, float)):
                totals[k] = totals.get(k, 0) + v
    return sorted(totals.items(), key=lambda kv: -kv[1])[:top_n]


def median(values):
    values = sorted(v for v in values if v is not None)
    n = len(values)
    if n == 0:
        return None
    mid = n // 2
    if n % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def mean(values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    return sum(values) / len(values)


def load_runs(stamp_dir):
    path = os.path.join(stamp_dir, "runs.jsonl")
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def aggregate(rows):
    """Pure aggregation: rows -> per-arm summary dict.

    rows: list of run dicts as written by run.py to runs.jsonl.
    Returns {"arms": {arm_name: {...}}, "arm_order": [...]}.
    """
    by_arm = {}
    for r in rows:
        by_arm.setdefault(r["arm"], []).append(r)

    arm_order = list(by_arm.keys())
    summary = {}

    for arm, arm_rows in by_arm.items():
        n = len(arm_rows)
        acc_oks = [r.get("acceptance", {}).get("ok") for r in arm_rows]
        success_rate = sum(1 for x in acc_oks if x) / n if n else None

        acc_pcts = []
        for r in arm_rows:
            acc = r.get("acceptance", {})
            total = acc.get("total") or 0
            if total:
                acc_pcts.append(100.0 * acc.get("passed", 0) / total)
        acc_pass_pct_mean = mean(acc_pcts)

        reg_oks = [r.get("regression", {}).get("ok") for r in arm_rows]
        regression_ok_rate = sum(1 for x in reg_oks if x) / n if n else None

        timeouts = sum(1 for r in arm_rows if r.get("timed_out"))
        timeout_rate = timeouts / n if n else None

        stats = {}
        for field, getter in METRIC_FIELDS:
            vals = [getter(r) for r in arm_rows]
            stats[field] = {
                "median": median(vals),
                "mean": mean(vals),
                "min": min([v for v in vals if v is not None], default=None),
                "max": max([v for v in vals if v is not None], default=None),
            }

        swe_gate_counts = [_swe_gate_count(r) for r in arm_rows]
        swe_gate_counts = [v for v in swe_gate_counts if v is not None]

        spec_vals = [v for v in (_acceptance_category_pct(r, "spec") for r in arm_rows) if v is not None]
        doc_vals = [v for v in (_acceptance_category_pct(r, "doc") for r in arm_rows) if v is not None]

        with_gates = [r for r in arm_rows if isinstance(r.get("gates"), dict)]
        init_vals = [v for v in (_gate_bool(r, "init_chain_complete") for r in with_gates) if v is not None]
        sweep_vals = [v for v in (_gate_bool(r, "sweep_verified") for r in with_gates) if v is not None]
        edits_before_sweep_vals = [v for v in (_gate_int(r, "edits_before_sweep") for r in with_gates) if v is not None]
        coverage_vals = [v for v in (_doc_rule_coverage(r) for r in with_gates) if v is not None]

        summary[arm] = {
            "n": n,
            "success_rate": success_rate,
            "acceptance_pass_pct_mean": acc_pass_pct_mean,
            "spec_pass_pct_mean": mean(spec_vals),
            "doc_pass_pct_mean": mean(doc_vals),
            "regression_ok_rate": regression_ok_rate,
            "timeouts": timeouts,
            "timeout_rate": timeout_rate,
            "stats": stats,
            "swe_gated_events_total": sum(swe_gate_counts) if swe_gate_counts else 0,
            "swe_top_event_types": _swe_top_event_types(arm_rows),
            "gate_conformance": {
                "n_with_gates": len(with_gates),
                "init_chain_complete_rate": (sum(1 for v in init_vals if v) / len(init_vals)) if init_vals else None,
                "sweep_verified_rate": (sum(1 for v in sweep_vals if v) / len(sweep_vals)) if sweep_vals else None,
                "edits_before_sweep_mean": mean(edits_before_sweep_vals),
                "doc_rule_memories_coverage_mean": mean(coverage_vals),
            },
        }

    # vs-baseline deltas (% change of medians), for every arm except baseline
    if "baseline" in summary:
        base_stats = summary["baseline"]["stats"]
        for arm, s in summary.items():
            if arm == "baseline":
                continue
            deltas = {}
            for field, _ in METRIC_FIELDS:
                base_med = base_stats[field]["median"]
                arm_med = s["stats"][field]["median"]
                if base_med in (None, 0) or arm_med is None:
                    deltas[field] = None
                else:
                    deltas[field] = 100.0 * (arm_med - base_med) / base_med
            s["vs_baseline_pct"] = deltas

    return {
        "arms": summary,
        "arm_order": arm_order,
        "doc_rule_matrix": doc_rule_pass_matrix(rows),
        "pivot_benchmarks": pivot_benchmark_stats(rows),
        "pivot_gates": pivot_gate_stats(rows),
    }


def format_markdown(agg):
    lines = []
    arms = agg["arms"]
    arm_names = sorted(arms.keys(), key=lambda a: (a != "baseline", a))

    lines.append("| arm | n | success_rate | acceptance_pass% | spec_pass% | doc_pass% | regression_ok_rate | timeouts |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for arm in arm_names:
        s = arms[arm]
        lines.append(
            f"| {arm} | {s['n']} | "
            f"{_fmt_pct(s['success_rate'])} | "
            f"{_fmt(s['acceptance_pass_pct_mean'])} | "
            f"{_fmt(s.get('spec_pass_pct_mean'))} | "
            f"{_fmt(s.get('doc_pass_pct_mean'))} | "
            f"{_fmt_pct(s['regression_ok_rate'])} | "
            f"{s['timeouts']} |"
        )

    lines.append("")
    lines.append("| arm | n w/ gates | init_chain_complete% | sweep_verified% | edits_before_sweep (mean) | doc_rule_coverage (mean) |")
    lines.append("|---|---|---|---|---|---|")
    for arm in arm_names:
        gc = arms[arm].get("gate_conformance") or {}
        lines.append(
            f"| {arm} | {gc.get('n_with_gates', 0)} | "
            f"{_fmt_pct(gc.get('init_chain_complete_rate'))} | "
            f"{_fmt_pct(gc.get('sweep_verified_rate'))} | "
            f"{_fmt(gc.get('edits_before_sweep_mean'))} | "
            f"{_fmt_pct(gc.get('doc_rule_memories_coverage_mean'))} |"
        )

    doc_matrix = agg.get("doc_rule_matrix") or {}
    if doc_matrix:
        rule_ids = sorted({rid for arm_matrix in doc_matrix.values() for rid in arm_matrix})
        if rule_ids:
            lines.append("")
            lines.append("| arm | " + " | ".join(rule_ids) + " |")
            lines.append("|---|" + "---|" * len(rule_ids))
            for arm in arm_names:
                arm_matrix = doc_matrix.get(arm, {})
                cells = []
                for rid in rule_ids:
                    entry = arm_matrix.get(rid)
                    if not entry:
                        cells.append("-")
                    else:
                        mark = "OK" if entry.get("ok") else ("FAIL" if entry.get("ok") is False else "-")
                        cells.append(f"{mark} ({entry['passed']}/{entry['total']})")
                lines.append(f"| {arm} | " + " | ".join(cells) + " |")

    lines.append("")
    lines.append("| arm | metric | median | mean | min | max | vs baseline % |")
    lines.append("|---|---|---|---|---|---|---|")
    for arm in arm_names:
        s = arms[arm]
        deltas = s.get("vs_baseline_pct", {})
        for field, _ in METRIC_FIELDS:
            st = s["stats"][field]
            delta = deltas.get(field) if deltas else None
            label = METRIC_LABELS.get(field, field)
            lines.append(
                f"| {arm} | {label} | {_fmt(st['median'])} | {_fmt(st['mean'])} | "
                f"{_fmt(st['min'])} | {_fmt(st['max'])} | {_fmt(delta)} |"
            )

    lines.append("")
    lines.append("| arm | SWE `gated` events (total) | top stream event types (type: total count) |")
    lines.append("|---|---|---|")
    for arm in arm_names:
        s = arms[arm]
        top = ", ".join(f"{k}: {v}" for k, v in s.get("swe_top_event_types", []))
        lines.append(f"| {arm} | {s.get('swe_gated_events_total', 0)} | {top or '-'} |")

    pivot_bench = agg.get("pivot_benchmarks") or {}
    pivot_gates = agg.get("pivot_gates") or {}
    pivot_arms = [a for a in arm_names if (pivot_bench.get(a) or {}).get("n_pivot")]
    if pivot_arms:
        lines.append("")
        lines.append("## Benchmark 1 — after task 1")
        lines.append("")
        lines.append("| arm | n | success_rate (100% of B1) | spec_pass% | doc_pass% |")
        lines.append("|---|---|---|---|---|")
        for arm in pivot_arms:
            pb = pivot_bench[arm]
            b1 = pb["b1"]
            lines.append(
                f"| {arm} | {pb['n_pivot']} | {_fmt_pct(b1['success_rate'])} | "
                f"{_fmt(b1['spec_pass_pct_mean'])} | {_fmt(b1['doc_pass_pct_mean'])} |"
            )

        lines.append("")
        lines.append("## Benchmark 2 — after pivot")
        lines.append("")
        lines.append("| arm | n | success_rate (100% of B2) | spec_pass% | doc_pass% | "
                      "task1_retention% | task1 regressions (total) |")
        lines.append("|---|---|---|---|---|---|---|")
        for arm in pivot_arms:
            pb = pivot_bench[arm]
            b2 = pb["b2"]
            ret = pb["task1_retention"]
            lines.append(
                f"| {arm} | {pb['n_pivot']} | {_fmt_pct(b2['success_rate'])} | "
                f"{_fmt(b2['spec_pass_pct_mean'])} | {_fmt(b2['doc_pass_pct_mean'])} | "
                f"{_fmt(ret['rate_mean'])} | {ret['total_regressions']} |"
            )

        lines.append("")
        lines.append("| arm | task1 tokens (median) | task1 turns (median) | "
                      "pivot tokens (median) | pivot turns (median) |")
        lines.append("|---|---|---|---|---|")
        for arm in pivot_arms:
            pm = pivot_bench[arm]["phase_medians"]
            t1, pv = pm["task1"], pm["pivot"]
            lines.append(
                f"| {arm} | {_fmt(t1.get('total_tokens'))} | "
                f"{_fmt(t1.get('assistant_turns_incl_subagents'))} | "
                f"{_fmt(pv.get('total_tokens'))} | "
                f"{_fmt(pv.get('assistant_turns_incl_subagents'))} |"
            )

        lines.append("")
        lines.append("| arm | n | pivot_reclassified attempted% | pivot_reclassified succeeded% | "
                      "pivot_resweep_verified% | pivot_edits_before_sweep (mean) | "
                      "pivot_doc_rule_coverage (mean) |")
        lines.append("|---|---|---|---|---|---|---|")
        for arm in pivot_arms:
            pg = pivot_gates.get(arm) or {}
            lines.append(
                f"| {arm} | {pg.get('n_with_pivot_gates', 0)} | "
                f"{_fmt_pct(pg.get('pivot_reclassified_attempted_rate'))} | "
                f"{_fmt_pct(pg.get('pivot_reclassified_succeeded_rate'))} | "
                f"{_fmt_pct(pg.get('pivot_resweep_verified_rate'))} | "
                f"{_fmt(pg.get('pivot_edits_before_sweep_mean'))} | "
                f"{_fmt_pct(pg.get('pivot_doc_rule_memories_coverage_mean'))} |"
            )

    return "\n".join(lines)


def _fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def _fmt_pct(v):
    if v is None:
        return "-"
    return f"{100 * v:.0f}%"


def per_run_lines(rows):
    lines = []
    for r in rows:
        m = r.get("metrics") or {}
        acc = r.get("acceptance") or {}
        lines.append(
            f"{r['arm']}\tt{r['trial']}\t"
            f"success={acc.get('ok')}\t"
            f"turns(all/main)={m.get('assistant_turns_incl_subagents')}/{m.get('num_turns')}\t"
            f"tokens(all/main)={m.get('total_tokens')}/{m.get('main_tokens')}\t"
            f"tool_calls={_tool_calls(r)}\t"
            f"memory_reads={m.get('memory_file_reads')}\t"
            f"subagents={m.get('subagent_launches')}\t"
            f"est_cost={_est_cost_usd(r)}\t"
            f"wall_s={r.get('wall_s')}\t"
            f"hook_denials={m.get('hook_denials')}\t"
            f"stop_hook_blocks={m.get('stop_hook_blocks')}\t"
            f"swe_gated={_swe_gate_count(r)}"
        )
    return lines


def write_csv(rows, agg, out_dir):
    runs_csv = os.path.join(out_dir, "runs.csv")
    fieldnames = ["run_id", "arm", "trial", "seed", "model", "exit_code", "timed_out",
                  "wall_s", "num_turns", "total_tokens", "main_tokens", "output_tokens",
                  "cache_read_tokens", "est_cost_usd", "tool_calls", "memory_file_reads",
                  "subagent_launches", "subagent_messages",
                  "assistant_turns_incl_subagents", "hook_denials",
                  "stop_hook_blocks", "swe_gated_events", "acceptance_ok",
                  "acceptance_passed", "acceptance_total", "regression_ok"]
    with open(runs_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            m = r.get("metrics") or {}
            acc = r.get("acceptance") or {}
            reg = r.get("regression") or {}
            w.writerow({
                "run_id": r.get("run_id"),
                "arm": r.get("arm"),
                "trial": r.get("trial"),
                "seed": r.get("seed"),
                "model": r.get("model"),
                "exit_code": r.get("exit_code"),
                "timed_out": r.get("timed_out"),
                "wall_s": r.get("wall_s"),
                "num_turns": m.get("num_turns"),
                "total_tokens": m.get("total_tokens"),
                "main_tokens": m.get("main_tokens"),
                "output_tokens": m.get("usage", {}).get("output_tokens"),
                "cache_read_tokens": m.get("usage", {}).get("cache_read_input_tokens"),
                "est_cost_usd": _est_cost_usd(r),
                "tool_calls": _tool_calls(r),
                "memory_file_reads": m.get("memory_file_reads"),
                "subagent_launches": m.get("subagent_launches"),
                "subagent_messages": m.get("subagent_messages"),
                "assistant_turns_incl_subagents": m.get("assistant_turns_incl_subagents"),
                "hook_denials": m.get("hook_denials"),
                "stop_hook_blocks": m.get("stop_hook_blocks"),
                "swe_gated_events": _swe_gate_count(r),
                "acceptance_ok": acc.get("ok"),
                "acceptance_passed": acc.get("passed"),
                "acceptance_total": acc.get("total"),
                "regression_ok": reg.get("ok"),
            })

    summary_csv = os.path.join(out_dir, "summary.csv")
    with open(summary_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "n", "success_rate", "acceptance_pass_pct_mean",
                    "regression_ok_rate", "timeouts"] +
                   [f"{field}_median" for field, _ in METRIC_FIELDS])
        for arm, s in agg["arms"].items():
            w.writerow([arm, s["n"], s["success_rate"], s["acceptance_pass_pct_mean"],
                        s["regression_ok_rate"], s["timeouts"]] +
                       [s["stats"][field]["median"] for field, _ in METRIC_FIELDS])


def main(argv=None):
    p = argparse.ArgumentParser(description="Analyze harness A/B results")
    p.add_argument("stamp_dir")
    p.add_argument("--csv", action="store_true")
    p.add_argument("--md", action="store_true")
    args = p.parse_args(argv)

    rows = load_runs(args.stamp_dir)
    agg = aggregate(rows)

    md = format_markdown(agg)
    print(md)
    print()
    print("per-run:")
    for line in per_run_lines(rows):
        print(line)

    summary_json = os.path.join(args.stamp_dir, "summary.json")
    with open(summary_json, "w") as f:
        json.dump(agg, f, indent=2)

    if args.csv:
        write_csv(rows, agg, args.stamp_dir)

    if args.md:
        md_path = os.path.join(args.stamp_dir, "summary.md")
        with open(md_path, "w") as f:
            f.write(md)

    return 0


if __name__ == "__main__":
    sys.exit(main())
