"""Effectiveness measurement: does each harness mechanism change agent behavior?
All metrics computed from transcript events only."""
import json,glob,os,collections,hashlib,statistics as st
ROOT=os.path.expanduser("~/.claude/projects")
PRE_END="2026-09-30T07:57"; POST_START="2026-10-01T00:15"
def ctext(c):
    if isinstance(c,str): return c
    if isinstance(c,list): return "".join((x.get("text","") if x.get("type")=="text" else ctext(x.get("content"))) for x in c if isinstance(x,dict))
    return ""
def era(ts): return "PRE" if ts<PRE_END else ("POST" if ts>=POST_START else "MID")
def scan(p):
    seq=[]  # (tool, inp_hash, is_err, deny_kind, text_head)
    uses={}; first_ts=None; drift_adv=0; drift_hard=0; seen=set(); api=0
    atts=[]
    order=[]  # tool_use ids in call order
    for l in open(p):
        try:o=json.loads(l)
        except:continue
        ts=o.get("timestamp")
        if ts and not first_ts: first_ts=ts
        t=o.get("type")
        if t=="assistant":
            m=o["message"]
            if m.get("id") not in seen: seen.add(m.get("id")); api+=1
            for c in m.get("content",[]):
                if c.get("type")=="tool_use":
                    uses[c["id"]]=(c["name"],json.dumps(c.get("input",{}),sort_keys=True))
        elif t=="user":
            c=o["message"].get("content")
            if isinstance(c,list):
                for x in c:
                    if isinstance(x,dict) and x.get("type")=="tool_result" and x["tool_use_id"] in uses:
                        name,inp=uses[x["tool_use_id"]]; txt=ctext(x.get("content")); err=bool(x.get("is_error"))
                        deny=None
                        if err and "hook error" in txt[:200]:
                            if "scope-gate" in txt[:300]: deny="scope"
                            elif "DOCS FIRST" in txt[:300]: deny="docs"
                            elif "BASH POLICY" in txt[:300]: deny="bashpol"
                            elif "memory-fs" in txt[:300]: deny="memfs"
                            elif "doc-gate" in txt[:300]: deny="docgate"
                            elif "FOREGROUND" in txt[:300]: deny="fg"
                            else: deny="other"
                        seq.append((name,hashlib.md5((name+inp).encode()).hexdigest()[:10],err,deny,txt[:80]))
        elif t=="attachment":
            a=o.get("attachment",{})
            if a.get("type")=="hook_additional_context":
                txt="".join(a.get("content") or []) if isinstance(a.get("content"),list) else str(a.get("content",""))
                if "Orchestrator drift" in txt:
                    if "hard threshold" in txt or ">= hard" in txt: drift_hard+=1
                    else: drift_adv+=1
    return first_ts,api,seq,drift_adv,drift_hard
def group(name):
    s=name.split("__")[-1]
    if name=="Bash": return "Bash"
    if s=="search_for_pattern": return "serena-search"
    if name in("Grep","Glob"): return "GrepGlob"
    return name if not name.startswith("mcp__") else s
M=collections.defaultdict(lambda: collections.Counter())
denyfollow=collections.defaultdict(lambda: collections.Counter())
flails=collections.defaultdict(list)
driftstats=collections.defaultdict(lambda: collections.Counter())
searchmix=collections.defaultdict(lambda: collections.Counter())
subfail=collections.defaultdict(list)
repeats=collections.defaultdict(lambda: collections.Counter())
for d in glob.glob(ROOT+"/*"):
    if "experiments" in d or "private-var" in d or d.endswith("-Users-webdev"): continue
    for p in glob.glob(d+"/*.jsonl"):
        ts,api,seq,da,dh=scan(p)
        if not ts or ts<"2026-09-20" or api<3: continue
        e=era(ts)
        kinds=[("main",ts,api,seq,da,dh)]
        for sp in glob.glob(p[:-6]+"/subagents/*.jsonl"):
            ts2,api2,seq2,_,_=scan(sp)
            if api2>0: kinds.append(("sub",ts,api2,seq2,0,0))
        for kind,tss,ap,sq,dav,dhv in kinds:
            k=(e,kind); M[k]["transcripts"]+=1; M[k]["api"]+=ap; M[k]["calls"]+=len(sq)
            M[k]["errs"]+=sum(1 for x in sq if x[2])
            for x in sq:
                if x[3]: M[k]["deny_"+x[3]]+=1
            # deny -> next action
            for i,x in enumerate(sq):
                if x[3] and i+1<len(sq):
                    nxt=sq[i+1]
                    same=nxt[0]==x[0]
                    denyfollow[(e,x[3])]["n"]+=1
                    denyfollow[(e,x[3])]["retry_same_tool"]+=same
                    denyfollow[(e,x[3])]["next_err"]+=nxt[2]
            # flail: >=3 consecutive errors
            runl=0
            for x in sq:
                runl=runl+1 if x[2] else 0
                if runl==3: M[k]["flail3"]+=1
            # exact-repeat calls (same tool+input >=3 times)
            cc=collections.Counter(h for _,h,_,_,_ in sq)
            M[k]["repeat3plus"]+=sum(1 for v in cc.values() if v>=3)
            M[k]["repeat_wasted"]+=sum(v-1 for v in cc.values() if v>=2)
            # search mix
            for x in sq:
                g=group(x[0])
                if g=="Bash" : pass
                searchmix[k][g if g in("serena-search","GrepGlob","find_symbol","get_symbols_overview") else ("Bash" if g=="Bash" else None)]+=0
            for x in sq:
                g=group(x[0])
                if g in("serena-search","GrepGlob"): searchmix[k][g]+=1
                if x[0]=="Bash" and any(w in x[4][:0] for w in()): pass
            if kind=="sub":
                subfail[e].append((ap,sum(1 for x in sq if x[2]),sum(1 for x in sq if x[3]=="scope")))
            if kind=="main":
                driftstats[e]["adv"]+=dav; driftstats[e]["hard"]+=dhv
                if dav+dhv:
                    # delegation after drift? count Agent calls present
                    driftstats[e]["sessions_with_drift"]+=1
                    driftstats[e]["agent_calls_in_drift_sessions"]+=sum(1 for x in sq if x[0] in("Agent","Task"))
for k in sorted(M):
    m=M[k]
    print(k, f"transcripts={m['transcripts']} api={m['api']:,} tool_calls={m['calls']:,} err%={m['errs']/max(1,m['calls']):.1%} flail3={m['flail3']} repeat_wasted_calls={m['repeat_wasted']}",
          "denies:",{d.replace('deny_',''):v for d,v in m.items() if d.startswith('deny_')})
print("\n== deny -> next action (same-era):")
for k,v in sorted(denyfollow.items()):
    print(k, f"n={v['n']} retried_same_tool={v['retry_same_tool']} ({v['retry_same_tool']/max(1,v['n']):.0%}) next_call_err={v['next_err']} ({v['next_err']/max(1,v['n']):.0%})")
print("\n== drift advisories/hard in main sessions; Agent calls in those sessions:")
for e,v in driftstats.items(): print(e,dict(v))
print("\n== search tool mix (calls):")
for k,v in sorted(searchmix.items()): print(k,dict(v))
print("\n== subagent failure profile per era: median api, err calls, scope exhaustions")
for e,rows in subfail.items():
    if rows: print(e,"n",len(rows),"median_api",st.median(r[0] for r in rows),"err_total",sum(r[1] for r in rows),"scope_exhaust_events",sum(r[2] for r in rows),"subs_hitting_scope",sum(1 for r in rows if r[2]))
