"""Browser tool (browser-devtools / claude-in-chrome) token/usage analysis.

Scope: ~/.claude/projects/*/*.jsonl and */subagents/*.jsonl, mtime >= 2026-09-20,
excluding paths containing "experiments" or "private-var".

Per browser tool name: calls, result tokens (chars/4, image blocks counted
separately), error rate + top error strings, carry cost (result_tok * later
API calls in same transcript), wall time (tool_use ts -> tool_result ts),
retries (same tool+similar input called again after an error), calls per
session, which projects used it. Also scans for any claude-in-chrome usage,
and for deferred_tools listing of browser-devtools tool count (schema/listing
overhead).
"""
import json, glob, os, re, collections, datetime

ROOT = os.path.expanduser("~/.claude/projects")
CUTOFF = datetime.datetime(2026, 9, 20).timestamp()
OUTDIR = os.path.dirname(__file__)


def ctext(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        out = []
        for x in c:
            if isinstance(x, dict):
                if x.get("type") == "text":
                    out.append(x.get("text", ""))
                elif x.get("type") == "image":
                    out.append("")  # counted separately
                elif "content" in x:
                    out.append(ctext(x.get("content")))
        return "".join(out)
    return ""


def count_images(content):
    n = 0
    size = 0
    if isinstance(content, list):
        for x in content:
            if isinstance(x, dict) and x.get("type") == "image":
                n += 1
                src = x.get("source", {})
                data = src.get("data", "") if isinstance(src, dict) else ""
                size += len(data)  # base64 chars; *0.75 for bytes
    return n, size


def is_browser_tool(name):
    return name.startswith("mcp__browser-devtools__") or "browser-devtools__" in name


def is_chrome_tool(name):
    return name.startswith("mcp__claude-in-chrome__") or "claude-in-chrome__" in name


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def analyze(path):
    try:
        lines = open(path, errors="ignore").readlines()
    except Exception:
        return None
    tool_uses = {}  # id -> (name, input, api_ordinal, ts)
    results = []  # (id, chars, n_img, img_size, api_ordinal_at_result, is_error, head, ts)
    n_api = 0
    deferred_browser_count = None
    session_id = os.path.basename(path).replace(".jsonl", "")
    project = os.path.basename(os.path.dirname(os.path.dirname(path))) if "/subagents/" in path else os.path.basename(os.path.dirname(path))
    is_sub = "/subagents/" in path

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        t = o.get("type")
        if t == "assistant":
            m = o["message"]
            if m.get("id"):
                n_api += 1
            ts = parse_ts(o.get("timestamp"))
            for c in m.get("content", []):
                if c.get("type") == "tool_use":
                    tool_uses[c["id"]] = (c["name"], c.get("input", {}), n_api, ts)
        elif t == "user":
            c = o["message"].get("content")
            ts = parse_ts(o.get("timestamp"))
            if isinstance(c, list):
                for x in c:
                    if isinstance(x, dict) and x.get("type") == "tool_result":
                        content = x.get("content")
                        txt = ctext(content)
                        n_img, img_size = count_images(content)
                        results.append((x["tool_use_id"], len(txt), n_img, img_size, n_api, bool(x.get("is_error")), txt[:300], ts))
        # look for deferred_tools listing mentioning browser-devtools tool count
        blob = line
        if "deferred_tools" in blob or ("browser-devtools" in blob and "tool" in blob.lower() and "count" in blob.lower()):
            m2 = re.search(r'browser-devtools[^"]*"[^}]*?(\d+)\s*tool', blob)
            if m2:
                deferred_browser_count = m2.group(1)

    rows = collections.defaultdict(lambda: {
        "calls": 0, "chars": 0, "n_img": 0, "img_size": 0, "carry": 0.0,
        "err": 0, "err_msgs": collections.Counter(), "wall_times": [],
        "sessions": set(), "projects": set(),
    })
    chrome_rows = collections.defaultdict(lambda: {"calls": 0, "chars": 0, "sessions": set(), "projects": set()})
    total_api = n_api

    for tid, chars, n_img, img_size, at, err, head, rts in results:
        if tid not in tool_uses:
            continue
        name, inp, call_api, cts = tool_uses[tid]
        if is_browser_tool(name):
            r = rows[name]
            r["calls"] += 1
            r["chars"] += chars
            r["n_img"] += n_img
            r["img_size"] += img_size
            tk = chars / 4
            r["carry"] += tk * max(0, total_api - at)
            r["sessions"].add(session_id)
            r["projects"].add(project)
            if err:
                r["err"] += 1
                r["err_msgs"][head.strip()[:150]] += 1
            if cts and rts:
                r["wall_times"].append(rts - cts)
        elif is_chrome_tool(name):
            r = chrome_rows[name]
            r["calls"] += 1
            r["chars"] += chars
            r["sessions"].add(session_id)
            r["projects"].add(project)

    return dict(path=path, session=session_id, project=project, is_sub=is_sub,
                rows={k: v for k, v in rows.items()},
                chrome_rows={k: v for k, v in chrome_rows.items()},
                deferred_browser_count=deferred_browser_count,
                n_api=n_api)


def main():
    all_files = (glob.glob(f"{ROOT}/*/*.jsonl") +
                 glob.glob(f"{ROOT}/*/*/subagents/*.jsonl"))
    filtered = [f for f in all_files
                if "experiments" not in f and "private-var" not in f
                and os.path.getmtime(f) >= CUTOFF]

    results = []
    for f in filtered:
        r = analyze(f)
        if r and (r["rows"] or r["chrome_rows"] or r["deferred_browser_count"]):
            results.append(r)

    # aggregate per tool name across all transcripts
    agg = collections.defaultdict(lambda: {
        "calls": 0, "chars": 0, "n_img": 0, "img_size": 0, "carry": 0.0,
        "err": 0, "err_msgs": collections.Counter(), "wall_times": [],
        "sessions": set(), "projects": set(),
    })
    chrome_agg = collections.defaultdict(lambda: {"calls": 0, "chars": 0, "sessions": set(), "projects": set()})
    per_session_calls = collections.Counter()
    deferred_counts = collections.Counter()

    for r in results:
        if r["deferred_browser_count"]:
            deferred_counts[r["deferred_browser_count"]] += 1
        for name, v in r["rows"].items():
            a = agg[name]
            a["calls"] += v["calls"]
            a["chars"] += v["chars"]
            a["n_img"] += v["n_img"]
            a["img_size"] += v["img_size"]
            a["carry"] += v["carry"]
            a["err"] += v["err"]
            a["err_msgs"].update(v["err_msgs"])
            a["wall_times"].extend(v["wall_times"])
            a["sessions"] |= v["sessions"]
            a["projects"] |= v["projects"]
            per_session_calls[r["session"]] += v["calls"]
        for name, v in r["chrome_rows"].items():
            a = chrome_agg[name]
            a["calls"] += v["calls"]
            a["chars"] += v["chars"]
            a["sessions"] |= v["sessions"]
            a["projects"] |= v["projects"]

    print(f"\n=== Scanned {len(filtered)} transcripts (mtime>=2026-09-20, excl experiments/private-var)")
    print(f"=== {len(results)} transcripts had browser-devtools or claude-in-chrome tool calls")
    print(f"=== deferred_tools listing mentions of browser-devtools tool count: {dict(deferred_counts)}")

    print("\n--- browser-devtools (Playwright-based) per-tool stats ---")
    print(f"{'tool':45}{'calls':>7}{'res_tok':>10}{'avg_tok':>9}{'imgs':>6}{'img_KB':>8}{'carry_tok':>12}{'err':>5}{'err%':>6}{'avg_wall_s':>11}{'#sess':>7}{'#proj':>7}")
    tot_calls = tot_chars = tot_err = 0
    for name, v in sorted(agg.items(), key=lambda kv: -kv[1]["calls"]):
        avg_tok = int(v["chars"] / 4 / max(1, v["calls"]))
        img_kb = int(v["img_size"] * 0.75 / 1024)
        avg_wall = sum(v["wall_times"]) / len(v["wall_times"]) if v["wall_times"] else 0
        errpct = 100 * v["err"] / max(1, v["calls"])
        print(f"{name:45}{v['calls']:>7}{int(v['chars']/4):>10,}{avg_tok:>9,}{v['n_img']:>6}{img_kb:>8,}{int(v['carry']):>12,}{v['err']:>5}{errpct:>5.1f}%{avg_wall:>10.1f}s{len(v['sessions']):>7}{len(v['projects']):>7}")
        tot_calls += v["calls"]; tot_chars += v["chars"]; tot_err += v["err"]
    print(f"\nTOTAL calls={tot_calls} result_tok={int(tot_chars/4):,} errors={tot_err} ({100*tot_err/max(1,tot_calls):.1f}%)")

    print("\n--- top error strings across all browser-devtools tools ---")
    all_errs = collections.Counter()
    for v in agg.values():
        all_errs.update(v["err_msgs"])
    for msg, n in all_errs.most_common(15):
        print(f"  [{n:>4}] {msg}")

    print("\n--- sessions with browser-devtools calls (per-session call count) ---")
    for sess, n in sorted(per_session_calls.items(), key=lambda kv: -kv[1])[:20]:
        print(f"  {sess}: {n} calls")
    print(f"  ... total distinct sessions with calls: {len(per_session_calls)}")

    print("\n--- projects using browser-devtools ---")
    all_projects = set()
    for v in agg.values():
        all_projects |= v["projects"]
    for p in sorted(all_projects):
        print(f"  {p}")

    print("\n--- claude-in-chrome (mcp__claude-in-chrome__*) usage ---")
    if not chrome_agg:
        print("  NONE FOUND in scanned transcripts")
    else:
        for name, v in sorted(chrome_agg.items(), key=lambda kv: -kv[1]["calls"]):
            print(f"  {name}: calls={v['calls']} tok={int(v['chars']/4):,} sessions={len(v['sessions'])} projects={v['projects']}")

    # dump raw per-transcript json for drill-down
    dump = []
    for r in results:
        dump.append({
            "path": r["path"], "session": r["session"], "project": r["project"], "is_sub": r["is_sub"],
            "rows": {k: {kk: (list(vv) if isinstance(vv, set) else (dict(vv) if isinstance(vv, collections.Counter) else vv)) for kk, vv in v.items()} for k, v in r["rows"].items()},
            "chrome_rows": {k: {kk: (list(vv) if isinstance(vv, set) else vv) for kk, vv in v.items()} for k, v in r["chrome_rows"].items()},
        })
    json.dump(dump, open(os.path.join(OUTDIR, "browser_analysis.json"), "w"), indent=1)
    print(f"\n(raw per-transcript data written to browser_analysis.json, {len(dump)} transcripts)")


if __name__ == "__main__":
    main()
