import json,glob,os,collections,re,statistics as st
ROOT=os.path.expanduser("~/.claude/projects")
PROJ=[d for d in glob.glob(ROOT+"/*") if "experiments" not in d and "private-var" not in d and not d.endswith("-Users-webdev")]
PRE_END="2026-09-30T07:57"; POST_START="2026-10-01T00:15"
def ctext(c):
    if isinstance(c,str): return c
    if isinstance(c,list): return "".join((x.get("text","") if x.get("type")=="text" else ctext(x.get("content"))) for x in c if isinstance(x,dict))
    return ""
def scan(p,is_sub):
    uses={}; seen=set(); r=collections.Counter(); first_ts=None; work=False; prompt=None; listed=[]
    for l in open(p):
        try:o=json.loads(l)
        except:continue
        ts=o.get("timestamp")
        if ts and not first_ts: first_ts=ts
        t=o.get("type")
        if t=="assistant":
            m=o["message"]
            if m.get("id") not in seen:
                seen.add(m.get("id")); u=m.get("usage",{}); r["api"]+=1
                r["input"]+=u.get("input_tokens",0)+u.get("cache_creation_input_tokens",0)+u.get("cache_read_input_tokens",0)
            for c in m.get("content",[]):
                if c.get("type")=="tool_use":
                    uses[c["id"]]=(c["name"],c.get("input",{}))
                    s=c["name"].split("__")[-1]
                    if s not in("read_memory","ToolSearch","search_memories_by_front_matter","search_memories_by_name","list_memories"): work=True
        elif t=="user":
            c=o["message"].get("content")
            if prompt is None and is_sub: prompt=ctext(c)
            if isinstance(c,list):
                for x in c:
                    if isinstance(x,dict) and x.get("type")=="tool_result" and x["tool_use_id"] in uses:
                        name,inp=uses[x["tool_use_id"]]; s=name.split("__")[-1]; n=len(ctext(x.get("content")))
                        r["tool_res"]+=n
                        if s=="read_memory":
                            r["mem_reads"]+=1; r["mem_chars"]+=n
                            if not work: r["upfront_mem"]+=n; r["upfront_reads"]+=1
                            if inp.get("memory_name","").split("/")[0] in("wf","claude"): r["wf_chars"]+=n
                            else: r["task_mem_chars"]+=n; r["task_mem_reads"]+=1
                        if s in("search_memories_by_front_matter",): r["fm_calls"]+=1; r["fm_chars"]+=n
    if is_sub and prompt:
        i=prompt.find("[swe-required-reading]")
        r["has_inject"]=int(i>=0)
        if i>=0: r["inject_chars"]=len(prompt)-i
        r["prompt_chars"]=len(prompt)
        r["obl_lines"]=prompt.count("obligation")
    return first_ts,r
rows=[]
for d in PROJ:
    for p in glob.glob(d+"/*.jsonl"):
        ts,r=scan(p,False)
        if not ts or ts<"2026-09-20": continue
        b="PRE" if ts<PRE_END else ("POST" if ts>=POST_START else "MID")
        subs=[scan(s,True)[1] for s in glob.glob(p[:-6]+"/subagents/*.jsonl")]
        rows.append((b,os.path.basename(d)[-30:],os.path.basename(p)[:8],ts,r,subs))
def summ(b):
    R=[x for x in rows if x[0]==b and x[4]["api"]>5]
    if not R: return
    M=collections.Counter(); S=collections.Counter(); ns=0; up=[]; inj=[]; hasinj=0; persub_mem=[]
    for _,_,_,_,r,subs in R:
        M.update(r)
        for s in subs:
            if s["api"]==0: continue
            ns+=1; S.update(s); up.append(s["upfront_mem"]//4); persub_mem.append(s["mem_chars"]//4)
            hasinj+=s.get("has_inject",0)
            if s.get("has_inject"): inj.append(s["inject_chars"]//4)
    print(f"\n### {b}: {len(R)} main sessions, {ns} subagents")
    print(f" MAIN: api={M['api']:,} mem_reads={M['mem_reads']} mem_tok={M['mem_chars']//4:,} (wf/claude {M['wf_chars']//4:,}, task {M['task_mem_chars']//4:,}) | per session mem_tok={M['mem_chars']//4//len(R):,} | mem tok per api call={M['mem_chars']/4/M['api']:.0f} | avg tok/read={M['mem_chars']/4/max(1,M['mem_reads']):.0f} | task reads/session={M['task_mem_reads']/len(R):.1f} | fm_search calls={M['fm_calls']} tok={M['fm_chars']//4:,} | mem share of tool results={M['mem_chars']/max(1,M['tool_res']):.0%}")
    if ns:
        print(f" SUBS: api={S['api']:,} mem_reads={S['mem_reads']} mem_tok={S['mem_chars']//4:,} | per subagent mem_tok median={st.median(persub_mem):,.0f} mean={st.mean(persub_mem):,.0f} | upfront median={st.median(up):,.0f} mean={st.mean(up):,.0f} | avg tok/read={S['mem_chars']/4/max(1,S['mem_reads']):.0f} | reads/subagent={S['mem_reads']/ns:.1f} | injected digest in {hasinj}/{ns} prompts, digest tok median={st.median(inj) if inj else 0:,.0f} | mem share of tool results={S['mem_chars']/max(1,S['tool_res']):.0%}")
for b in("PRE","MID","POST"): summ(b)
print()
for b,proj,sid,ts,r,subs in sorted(rows,key=lambda x:x[3]):
    if r["api"]>5: print(b,ts[:16],proj,sid,"api",r["api"],"mem_tok",r["mem_chars"]//4,"subs",len(subs),"sub_mem_tok",sum(s["mem_chars"] for s in subs)//4)
