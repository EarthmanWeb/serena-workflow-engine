# WF_SWARM_ORCHESTRATE - Multi-Agent Swarm Coordination

> **🐝 On step WF_SWARM_ORCHESTRATE**

⬆️ OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## When To Use

- Task affects 6+ files OR 3+ architectural layers
- Independent subtasks can run in parallel
- Multi-domain coordination or consensus needed

---

## ⚠️ Explicit Tool Selection Rule

**When user requests a swarm subsystem, USE THESE EXACT MCP TOOLS — NEVER substitute Task/Explore agents.**

| User Says | Use Tools | Read |
|-----------|-----------|------|
| "ruflo swarm" / "swarm" | `mcp__ruflo__swarm_*` + `mcp__ruflo__agent_*` | `WF_SWARM_RUFLO` |
| "coordinate" / "orchestrate" | `mcp__ruflo__coordination_*` | `WF_SWARM_RUV` (Pattern B1) |
| "DAA" / "DAA swarm" | `mcp__ruflo__daa_*` | `WF_SWARM_RUV` (Pattern B2) |
| "hive-mind" | `mcp__ruflo__hive-mind_*` | `WF_SWARM_HIVE_MIND` |

---

## ⛔ Pre-Swarm Research (MANDATORY)

**BEFORE planning ANY swarm:**

1. `read_memory("_INDEX")` — find all relevant memories
2. Read ALL relevant `INDEX_*`, `ARCH_*`, `SYS_*`, `DOM_*`, `REF_*`, `SPEC_*` memories
3. Use `find_symbol()` to verify nothing similar already exists
4. Check relevant skills (`/research`, `/arch-review`, `/verify`)

**Every swarm agent prompt MUST include:** "Research existing patterns in INDEX_*, ARCH_*, SYS_* memories before implementing. DO NOT create anything that already exists."

---

## Step 1: Select Subsystem & Topology

| Subsystem | When | Prefix | Methodology |
|-----------|------|--------|-------------|
| **Ruflo Swarm** | General orchestration, parallel tasks | `mcp__ruflo__swarm_*` + `mcp__ruflo__agent_*` | `WF_SWARM_RUFLO` |
| **Ruflo Coordination** | Simple parallel task orchestration | `mcp__ruflo__coordination_*` | `WF_SWARM_RUV` (B1) |
| **Ruflo DAA** | Multi-iteration tracking/coordination (metadata only — NOT autonomous) | `mcp__ruflo__daa_*` | `WF_SWARM_RUV` (B2) |
| **Ruflo Hybrid** | Task orchestration + DAA iterative tracking | `mcp__ruflo__*` | `WF_SWARM_RUV` (B3) |
| **Ruflo Hive-Mind** | Consensus, collective intelligence | `mcp__ruflo__hive-mind_*` | `WF_SWARM_HIVE_MIND` |

| Topology | Best For |
|----------|----------|
| **star** | Quick parallel tasks (RECOMMENDED default) |
| **mesh** | Collaborative analysis, exploration |
| **hierarchical** | Complex projects, orchestrated changes |
| **ring** | Sequential processing pipelines |

Agent types: `researcher`, `analyst`, `coder`, `tester`, `coordinator`, `optimizer`, `reviewer`

### Decision Guide: Which Subsystem and Why?

| Subsystem | Choose When | Rationale | Avoid When |
|-----------|------------|-----------|------------|
| **Ruflo Swarm (A)** | General-purpose parallel tasks, multi-file changes, coordinated refactoring | Most flexible. Star topology has minimal overhead. Task registration gives full visibility. Memory store enables cross-agent state sharing. | You need learning/adaptation (use DAA) or consensus (use Hive-Mind) |
| **Ruflo Coordination (B1)** | Simple parallel task execution, quick fan-out/fan-in | `coordination_orchestrate` handles agent assignment automatically. Lower context budget cost. | You need learning, adaptation, or cross-domain knowledge transfer (use B2). |
| **Ruflo DAA (B2)** | Multi-iteration workflows where Round 1 findings shape Round 2 prompts. Iterative audits, progressive refinement. | DAA is a **metadata/tracking layer** — stores agent records, cognitive pattern labels, and knowledge entries. Value comes from: (1) cognitive patterns shaping Agent tool prompts, (2) knowledge_share storing findings for next iteration. | Single-pass parallel work (use B1 or Swarm — DAA adds ~10 MCP calls of overhead with zero benefit). |
| **Ruflo Hybrid (B3)** | Multi-phase projects where Phase 1 findings inform Phase 2 execution | Combines B1's task speed with B2's cross-iteration state tracking. | Single-phase tasks. Simple tasks that don't benefit from two agent pools. |
| **Ruflo Hive-Mind (C)** | Architecture decisions requiring agreement, collective code review, design consensus | Consensus mechanism ensures all agents agree before proceeding. Shared memory provides single source of truth. | Speed-critical tasks (consensus adds latency). Pure execution tasks with no decision-making. |

### Quick Decision Tree

```
Is the task a decision that needs agreement? → Hive-Mind (C)
Is this a multi-iteration workflow where round N findings shape round N+1? → DAA (B2) or Hybrid (B3)
Is it a multi-phase project with progressive refinement? → Hybrid (B3)
Do you need fine-grained task dependencies? → Ruflo Swarm (A)
Is it simple parallel work? → Ruflo Coordination (B1)
Not sure? → Ruflo Swarm (A) with star topology (safe default)
```

---

## Step 2: Read Pattern-Specific Methodology

**MANDATORY: Read the methodology file for your selected subsystem BEFORE executing.**

```
mcp__plugin_swe_serena__read_memory("wf/WF_SWARM_RUFLO")   // Pattern A
mcp__plugin_swe_serena__read_memory("wf/WF_SWARM_RUV")           // Patterns B1, B2, B3
mcp__plugin_swe_serena__read_memory("wf/WF_SWARM_HIVE_MIND")     // Pattern C
```

**Follow the phased methodology in the selected file exactly.**

---

## ⛔ NEVER Run Init CLI Commands

**Never** run CLI init commands — these modify repo files. Use MCP tools directly (in-memory coordination).

---

## Critical Execution Rules (All Subsystems)

**DO:**
- Init swarm FIRST → spawn all agents in ONE message → register tasks BEFORE launching Agent tools
- Use Agent tool (background) for ALL file reads/writes — separate context windows
- Batch MCP calls into as few messages as possible
- Load memories BEFORE swarm init, not during
- Store coordination state to MCP memory

**DON'T:**
- Spawn swarm then revert to single-agent work
- Block on first agent before spawning others
- Skip task registration in coordination layer
- Mix swarm subsystems without clear handoff
- Read files directly in coordinator context — agents do that
- Use verbose/detailed flags on MCP calls
- Call `memory_stats` (scans 100K entries)

### Task Registration (CRITICAL)

MCP agents MUST have tasks registered BEFORE launching Task tool work. Without this, the coordination layer has no visibility into agent work.

```
1. agent_spawn/daa_agent_create → 2. task_create/daa_workflow_create → 3. Agent tool (background) → 4. Collect results
```

---

## MANDATORY NEXT STEP

| Condition | Read Next |
|-----------|-----------|
| User approves swarm plan | `WF_EXECUTE` |
| User wants simpler approach | `WF_ARCH_REVIEW` |
| Need clarification | `WF_CLARIFY` |
| Swarm work complete | `WF_VERIFY` |

**Before transitioning, invoke `/swe-wm-update --from WF_SWARM_ORCHESTRATE`.**

**SKIPPING WM UPDATE = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
