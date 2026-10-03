import json,glob,os,collections,re,sys
ROOT=os.path.expanduser("~/.claude/projects")
def ctext(c):
    if isinstance(c,str): return c
    if isinstance(c,list): return "".join((x.get("text","") if x.get("type")=="text" else ctext(x.get("content"))) for x in c if isinstance(x,dict))
    return ""
mem=collections.Counter(); memc=collections.Counter(); memrep=collections.Counter()
first=[]; denies=collections.Counter(); empties=[]; per=[]
bigread=[]; tools_by_kind=collections.Counter()
for s in sys.argv[1:]:
    files=[(glob.glob(f"{ROOT}/*/{s}*.jsonl")[0],"main")]+[(p,"sub") for p in glob.glob(f"{ROOT}/*/{s}*/subagents/*.jsonl")]
    for p,kind in files:
        uses={}; seenmem=collections.Counter(); seen=set(); firstctx=None; n=0; maxctx=0
        for l in open(p):
            o=json.loads(l)
            if o.get("type")=="assistant":
                m=o["message"]; u=m.get("usage",{})
                if m.get("id") not in seen:
                    seen.add(m.get("id")); n+=1
                    ctx=u.get("input_tokens",0)+u.get("cache_creation_input_tokens",0)+u.get("cache_read_input_tokens",0)
                    if firstctx is None: firstctx=ctx
                    maxctx=max(maxctx,ctx)
                for c in m.get("content",[]):
                    if c.get("type")=="tool_use": uses[c["id"]]=(c["name"],c.get("input",{}))
            elif o.get("type")=="user" and isinstance(o["message"].get("content"),list):
                for x in o["message"]["content"]:
                    if isinstance(x,dict) and x.get("type")=="tool_result" and x["tool_use_id"] in uses:
                        name,inp=uses[x["tool_use_id"]]; t=ctext(x.get("content")); short=name.split("__")[-1]
                        if short in("read_memory",):
                            mn=inp.get("memory_name",""); key=mn.split("/")[0] if "/" in mn else mn
                            mem[(kind,mn)]+=len(t); memc[(kind,mn)]+=1
                            seenmem[mn]+=1
                            if seenmem[mn]>1: memrep[kind]+=len(t)
                        if short in ("search_memories_by_front_matter","search_memories_by_name","list_memories"):
                            mem[(kind,"<"+short+">")]+=len(t); memc[(kind,"<"+short+">")]+=1
                        if x.get("is_error"):
                            denies[(kind,name if not name.startswith("mcp__") else short, t[:110].replace("\n"," "))]+=1
                        if short=="search_for_pattern" and (t.strip() in("{}","[]") or "too long" in t):
                            empties.append((kind,t[:80].replace("\n"," "),json.dumps(inp)[:160]))
                        if name=="Read" and len(t)>20000: bigread.append((kind,len(t)//4,inp.get("file_path","")[-70:],"offset" in inp or "limit" in inp))
        first.append((s,kind,os.path.basename(p)[:20],firstctx,maxctx,n))
print("== memory reads by name (kind, calls, est tok) top 40")
for (k,mn),ch in sorted(mem.items(),key=lambda kv:-kv[1])[:40]: print(f"{k:5}{memc[(k,mn)]:>5}{ch//4:>9,}  {mn}")
grp=collections.Counter(); grpc=collections.Counter()
for (k,mn),ch in mem.items():
    g=k+":"+(mn.split("/")[0] if "/" in mn else mn); grp[g]+=ch; grpc[g]+=memc[(k,mn)]
print("== memory by prefix"); [print(f"{g:40}{grpc[g]:>5}{v//4:>9,}") for g,v in sorted(grp.items(),key=lambda kv:-kv[1])]
print("== repeated memory reads (same transcript) est tok:",{k:v//4 for k,v in memrep.items()})
print("== first-call context / max ctx / api calls")
import statistics
for k in("main","sub"):
    f=[x[3] for x in first if x[1]==k and x[3]]; print(k,"n",len(f),"first median",statistics.median(f),"min",min(f),"max",max(f))
for x in first:
    if x[1]=="main": print(x)
print("== big Reads (>5k tok)"); [print(b) for b in sorted(bigread,key=lambda b:-b[1])]
print("== search_for_pattern empty/too-long"); [print(e) for e in empties[:30]]
print("== errors/denials top")
for (k,n,t),c in sorted(denies.items(),key=lambda kv:-kv[1])[:45]: print(f"{c:>3} {k:4} {n:28} {t}")
