"""Token-usage analysis of Claude Code transcripts (main + subagents).

Per transcript:
  - API usage (input / cache_create / cache_read / output) summed per assistant message (dedup by message id)
  - per-tool: calls, result chars, est tokens (chars/4), carry cost = result_tokens * subsequent API calls
  - hook-injected context (hook_additional_context attachments + hook stdout additionalContext) chars
  - Read: full vs windowed; Grep output modes; Serena tool params; empty Serena results
"""
import json, sys, glob, os, re, collections

ROOT = os.path.expanduser("~/.claude/projects")
SESSIONS = sys.argv[1:]


def ctext(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(ctext(x.get("text", "") if isinstance(x, dict) and x.get("type") == "text" else (ctext(x.get("content")) if isinstance(x, dict) else "")) for x in c)
    return ""


def tool_group(name, inp):
    if name.startswith("mcp__plugin_swe_serena__") or name.startswith("mcp__serena__"):
        short = name.split("__")[-1]
        if short in ("read_memory", "list_memories", "write_memory", "edit_memory", "search_memories_by_name",
                     "search_memories_by_front_matter", "delete_memory", "rename_memory"):
            return "serena-memory"
        if short in ("find_symbol", "get_symbols_overview", "find_referencing_symbols", "find_declaration", "find_implementations"):
            return "serena-symbol-read"
        if short == "search_for_pattern":
            return "serena-search"
        return "serena-edit/other"
    if name.startswith("mcp__plugin_swe_swe-wm__"):
        return "swe-wm"
    if name in ("Read",):
        return "Read"
    if name in ("Grep", "Glob"):
        return name
    if name == "Bash":
        cmd = inp.get("command", "")
        first = re.split(r"[|;&\n]", cmd.strip())[0].strip().split()
        w = first[0] if first else ""
        if w in ("cd",) and "&&" in cmd:
            w = re.split(r"&&", cmd)[1].strip().split()[0] if len(re.split(r"&&", cmd)) > 1 and re.split(r"&&", cmd)[1].strip() else w
        if w in ("grep", "rg", "ag", "find", "ls", "fd"):
            return "Bash-search"
        if w in ("cat", "sed", "head", "tail", "awk", "nl", "less", "wc", "jq"):
            return "Bash-read"
        return "Bash-other"
    if name in ("Agent", "Task"):
        return "Agent"
    if name.startswith("mcp__"):
        return "mcp:" + name.split("__")[1]
    return name


def analyze(path):
    msgs = [json.loads(l) for l in open(path) if l.strip()]
    usage, seen = collections.Counter(), set()
    api_idx = []  # ordinal of each api call
    tool_uses = {}  # id -> (name, input, api_ordinal)
    results = []  # (id, chars, api_ordinal_at_result, is_error)
    hook_chars = collections.Counter()
    hook_calls = collections.Counter()
    n_api = 0
    for o in msgs:
        t = o.get("type")
        if t == "assistant":
            m = o["message"]
            mid = m.get("id")
            if mid not in seen:
                seen.add(mid)
                u = m.get("usage", {})
                for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"):
                    usage[k] += u.get(k, 0) or 0
                n_api += 1
            for c in m.get("content", []):
                if c.get("type") == "tool_use":
                    tool_uses[c["id"]] = (c["name"], c.get("input", {}), n_api)
        elif t == "user":
            c = o["message"].get("content")
            if isinstance(c, list):
                for x in c:
                    if isinstance(x, dict) and x.get("type") == "tool_result":
                        results.append((x["tool_use_id"], len(ctext(x.get("content"))), n_api, bool(x.get("is_error")), ctext(x.get("content"))[:200]))
        elif t == "attachment":
            a = o.get("attachment", {})
            if a.get("type") == "hook_additional_context":
                txt = "".join(a.get("content") or []) if isinstance(a.get("content"), list) else str(a.get("content", ""))
                hk = a.get("hookName") or a.get("hookEvent") or "?"
                hook_chars[hk] += len(txt)
                hook_calls[hk] += 1
            elif a.get("type") in ("hook_blocking_error",):
                hook_chars["BLOCK:" + str(a.get("hookName"))] += len(str(a.get("blockingError", "")))
                hook_calls["BLOCK:" + str(a.get("hookName"))] += 1
    total_api = n_api
    tools = collections.defaultdict(lambda: collections.Counter())
    detail = collections.Counter()
    for tid, chars, at, err, head in results:
        if tid not in tool_uses:
            continue
        name, inp, _ = tool_uses[tid]
        g = tool_group(name, inp)
        tk = chars / 4
        carry = tk * max(0, total_api - at)
        tools[g]["calls"] += 1
        tools[g]["chars"] += chars
        tools[g]["carry"] += carry
        tools[g]["err"] += err
        if name == "Read":
            windowed = "offset" in inp or "limit" in inp
            k = "Read-windowed" if windowed else "Read-full"
            detail[k + ":calls"] += 1
            detail[k + ":chars"] += chars
            fp = inp.get("file_path", "")
            ext = os.path.splitext(fp)[1] or "(none)"
            detail["Read-ext:" + ext + ":chars"] += chars
            detail["Read-ext:" + ext + ":calls"] += 1
            if chars > 40000:
                detail["Read-over10k-tok:calls"] += 1
                detail["Read-over10k-tok:chars"] += chars
        if name == "Grep":
            detail["Grep-mode:" + inp.get("output_mode", "files_with_matches") + ":calls"] += 1
            detail["Grep-mode:" + inp.get("output_mode", "files_with_matches") + ":chars"] += chars
        if g.startswith("serena-symbol") or g == "serena-search":
            short = name.split("__")[-1]
            detail["S:" + short + ":calls"] += 1
            detail["S:" + short + ":chars"] += chars
            if short == "find_symbol" and inp.get("include_body"):
                detail["S:find_symbol+body:calls"] += 1
                detail["S:find_symbol+body:chars"] += chars
            if head.strip() in ("[]", "{}", "") or head.startswith("Error") or "No active" in head:
                detail["S:" + short + ":empty_or_err"] += 1
        if err:
            detail["ERR:" + g] += 1
            if "hook" in head.lower() or "denied" in head.lower() or "blocked" in head.lower() or "⛔" in head:
                detail["DENIED:" + g] += 1
    return dict(path=path, api_calls=total_api, usage=dict(usage), tools={k: dict(v) for k, v in tools.items()},
                hooks={k: (hook_calls[k], hook_chars[k]) for k in hook_chars}, detail=dict(detail))


out = {}
for s in SESSIONS:
    main = glob.glob(f"{ROOT}/*/{s}*.jsonl")[0]
    subs = sorted(glob.glob(f"{ROOT}/*/{s}*/subagents/*.jsonl"))
    out[s] = {"main": analyze(main), "subs": [analyze(p) for p in subs]}
json.dump(out, open(os.path.join(os.path.dirname(__file__), "analysis.json"), "w"), indent=1)


def agg(items):
    U, T, H, D = collections.Counter(), collections.defaultdict(collections.Counter), collections.Counter(), collections.Counter()
    hc = collections.Counter()
    api = 0
    for r in items:
        api += r["api_calls"]
        U.update(r["usage"])
        for k, v in r["tools"].items():
            T[k].update(v)
        for k, (c, ch) in r["hooks"].items():
            hc[k] += c; H[k] += ch
        D.update(r["detail"])
    return api, U, T, H, hc, D


def show(title, items):
    api, U, T, H, hc, D = agg(items)
    print(f"\n=== {title}  ({len(items)} transcripts, {api} API calls)")
    tot_in = U["input_tokens"] + U["cache_creation_input_tokens"] + U["cache_read_input_tokens"]
    print(f"usage: in={U['input_tokens']:,} cache_create={U['cache_creation_input_tokens']:,} cache_read={U['cache_read_input_tokens']:,} out={U['output_tokens']:,} | total_in={tot_in:,}")
    print(f"{'group':22}{'calls':>7}{'res_tok':>11}{'avg':>8}{'carry_tok':>14}{'err':>5}")
    for k, v in sorted(T.items(), key=lambda kv: -kv[1]["carry"]):
        print(f"{k:22}{v['calls']:>7}{int(v['chars']/4):>11,}{int(v['chars']/4/max(1,v['calls'])):>8,}{int(v['carry']):>14,}{v['err']:>5}")
    print("hooks (calls, est tok):")
    for k in sorted(H, key=lambda k: -H[k]):
        print(f"  {k:45}{hc[k]:>6}{int(H[k]/4):>10,}")
    print("detail:")
    for k in sorted(D):
        v = D[k]
        print(f"  {k:45}{int(v/4) if k.endswith(':chars') else v:>12,}{' tok' if k.endswith(':chars') else ''}")


allm, alls = [], []
for s, r in out.items():
    show(f"{s} MAIN", [r["main"]])
    if r["subs"]:
        show(f"{s} SUBAGENTS", r["subs"])
    allm.append(r["main"]); alls += r["subs"]
show("ALL MAIN", allm)
show("ALL SUBAGENTS", alls)
show("ALL", allm + alls)
