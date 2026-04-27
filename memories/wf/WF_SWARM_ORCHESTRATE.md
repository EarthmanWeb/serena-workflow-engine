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

**When user requests a swarm system, USE THESE EXACT MCP TOOLS — NEVER substitute Task/Explore agents.**

| User Says | Use Tools | Read |
|-----------|-----------|------|
| "claude-flow swarm" | `mcp__claude-flow__*` | `WF_SWARM_CLAUDE_FLOW` |
| "ruv-swarm" | `mcp__ruv-swarm__*` | `WF_SWARM_RUV` |
| "DAA" / "DAA swarm" | `mcp__ruv-swarm__daa_*` | `WF_SWARM_RUV` (Pattern B2) |
| "hive-mind" | `mcp__claude-flow__hive-mind_*` | `WF_SWARM_HIVE_MIND` |

---

## ⛔ Pre-Swarm Research (MANDATORY)

**BEFORE planning ANY swarm:**

1. `read_memory("_INDEX")` — find all relevant memories
2. Read ALL relevant `INDEX_*`, `ARCH_*`, `SYS_*`, `DOM_*`, `REF_*`, `SPEC_*` memories
3. Use `find_symbol()` to verify nothing similar already exists
4. Check relevant skills (`/research`, `/arch-review`, `/verify`)

**Every swarm agent prompt MUST include:** "Research existing patterns in INDEX_*, ARCH_*, SYS_* memories before implementing. DO NOT create anything that already exists."

---

## Step 1: Select System & Topology

| System | When | Prefix | Methodology |
|--------|------|--------|-------------|
| **Claude-Flow** | General orchestration, parallel tasks | `mcp__claude-flow__*` | `WF_SWARM_CLAUDE_FLOW` |
| **RUV-Swarm Task** | Simple parallel task orchestration | `mcp__ruv-swarm__*` | `WF_SWARM_RUV` (B1) |
| **RUV-Swarm DAA** | Learning/adaptation, autonomous agents | `mcp__ruv-swarm__daa_*` | `WF_SWARM_RUV` (B2) |
| **RUV-Swarm Hybrid** | Task orchestration + DAA learning | `mcp__ruv-swarm__*` | `WF_SWARM_RUV` (B3) |
| **Hive-Mind** | Consensus, collective intelligence | `mcp__claude-flow__hive-mind_*` | `WF_SWARM_HIVE_MIND` |

| Topology | Best For |
|----------|----------|
| **star** | Quick parallel tasks (RECOMMENDED default) |
| **mesh** | Collaborative analysis, exploration |
| **hierarchical** | Complex projects, orchestrated changes |
| **ring** | Sequential processing pipelines |

Agent types: `researcher`, `analyst`, `coder`, `tester`, `coordinator`, `optimizer`, `reviewer`

### Decision Guide: Which System and Why?

| System | Choose When | Rationale | Avoid When |
|--------|------------|-----------|------------|
| **Claude-Flow (A)** | General-purpose parallel tasks, multi-file changes, coordinated refactoring | Most flexible system. Star topology has minimal overhead. Task registration gives full visibility. Memory store enables cross-agent state sharing. Best balance of power and simplicity. | You need learning/adaptation (use DAA) or consensus (use Hive-Mind) |
| **RUV-Swarm Task (B1)** | Simple parallel task execution, quick fan-out/fan-in | Simpler than Claude-Flow with fewer tools (25 vs 241). `task_orchestrate` handles agent assignment automatically. Lower context budget cost. | You need learning, adaptation, or cross-domain knowledge transfer (use B2). You need fine-grained task dependencies (use Claude-Flow). |
| **RUV-Swarm DAA (B2)** | Research/audit tasks, code reviews, architecture analysis, tasks requiring learning from findings | DAA agents have cognitive patterns (critical, systems, adaptive) that shape analysis approach. Meta-learning transfers knowledge across domains. Knowledge sharing cross-pollinates findings between agents. Agent adaptation improves performance over iterations. | Simple parallel execution where learning adds no value (use B1). Tasks where consensus matters more than analysis (use Hive-Mind). |
| **RUV-Swarm Hybrid (B3)** | Multi-phase projects where Phase 1 findings inform Phase 2 execution | Combines B1's task speed with B2's learning. Swarm agents do immediate work; DAA agents learn from results and inform next iteration. | Single-phase tasks. Simple tasks that don't benefit from two agent pools. |
| **Hive-Mind (C)** | Architecture decisions requiring agreement, collective code review, design consensus | Consensus mechanism ensures all agents agree before proceeding. Shared memory provides single source of truth. Broadcast ensures all agents get same instructions. Best for quality-critical decisions. | Speed-critical tasks (consensus adds latency). Tasks where one agent's opinion suffices. Pure execution tasks with no decision-making. |

### Quick Decision Tree

```
Is the task a decision that needs agreement? → Hive-Mind (C)
Does the task benefit from learning/adaptation? → DAA (B2) or Hybrid (B3)
Is it a multi-phase project? → Hybrid (B3)
Do you need fine-grained task dependencies? → Claude-Flow (A)
Is it simple parallel work? → RUV-Swarm Task (B1)
Not sure? → Claude-Flow (A) with star topology (safe default)
```

---

## Step 2: Read Pattern-Specific Methodology

**MANDATORY: Read the methodology file for your selected system BEFORE executing.**

```
mcp__plugin_swe_serena__read_memory("wf/WF_SWARM_CLAUDE_FLOW")   // Pattern A
mcp__plugin_swe_serena__read_memory("wf/WF_SWARM_RUV")           // Patterns B1, B2, B3
mcp__plugin_swe_serena__read_memory("wf/WF_SWARM_HIVE_MIND")     // Pattern C
```

**Follow the phased methodology in the selected file exactly.**

---

## ⛔ NEVER Run Init CLI Commands

**Never** `npx claude-flow init` or `npx ruv-swarm init` — these modify repo files. Use MCP tools directly (in-memory coordination).

---

## Critical Execution Rules (All Systems)

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
- Mix swarm systems without clear handoff
- Read files directly in coordinator context — agents do that
- Use verbose/detailed flags on MCP calls
- Call `memory_stats` (scans 100K entries)

### Task Registration (CRITICAL)

MCP agents MUST have tasks registered BEFORE launching Task tool work. Without this, the coordination layer has no visibility into agent work.

```
1. agent_spawn/daa_agent_create → 2. task_create/daa_workflow_create → 3. Agent tool (background) → 4. Collect results
```

---

## Coordination Hooks

| Phase | Command |
|-------|---------|
| Before | `npx claude-flow@alpha hooks pre-task --description "[task]"` |
| During | `npx claude-flow@alpha hooks post-edit --file "[file]"` |
| After | `npx claude-flow@alpha hooks post-task --task-id "[task]"` |

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
