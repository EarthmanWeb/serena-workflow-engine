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

        summary[arm] = {
            "n": n,
            "success_rate": success_rate,
            "acceptance_pass_pct_mean": acc_pass_pct_mean,
            "regression_ok_rate": regression_ok_rate,
            "timeouts": timeouts,
            "timeout_rate": timeout_rate,
            "stats": stats,
            "swe_gated_events_total": sum(swe_gate_counts) if swe_gate_counts else 0,
            "swe_top_event_types": _swe_top_event_types(arm_rows),
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

    return {"arms": summary, "arm_order": arm_order}


def format_markdown(agg):
    lines = []
    arms = agg["arms"]
    arm_names = sorted(arms.keys(), key=lambda a: (a != "baseline", a))

    lines.append("| arm | n | success_rate | acceptance_pass% | regression_ok_rate | timeouts |")
    lines.append("|---|---|---|---|---|---|")
    for arm in arm_names:
        s = arms[arm]
        lines.append(
            f"| {arm} | {s['n']} | "
            f"{_fmt_pct(s['success_rate'])} | "
            f"{_fmt(s['acceptance_pass_pct_mean'])} | "
            f"{_fmt_pct(s['regression_ok_rate'])} | "
            f"{s['timeouts']} |"
        )

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
