# WF_SWARM_ORCHESTRATE - Multi-Agent Swarm Coordination

> **🐝 On step WF_SWARM_ORCHESTRATE**

⬆️ OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## When To Use

- Task affects 6+ files OR 3+ architectural layers
- Independent subtasks can run in parallel
- Multi-domain coordination or consensus needed

---

## ⚡ Step 0: Choose Execution Strategy (MANDATORY)

**Claude Code's built-in `Agent` tool is the DEFAULT for all parallel work involving file access.** Only use Ruflo for cognitive-only tasks (reasoning, planning, consensus).

### Decision Gate

```
Does ANY agent need file access (read, edit, grep, glob)?
  YES → Use Claude Code Agent tool directly. Skip Ruflo.
  NO  → Does the task need cross-iteration state or consensus?
    YES → Use Ruflo (agent_execute for reasoning, DAA for iterations, Hive-Mind for consensus)
    NO  → Use Claude Code Agent tool. It's simpler.
Did the user explicitly request Ruflo/DAA/swarm?
  YES → Use Ruflo. Respect the request, explain trade-offs.
```

### Path A: Claude Code Agent Tool (DEFAULT — File Access Tasks)

```javascript
// Launch ALL agents in ONE message — they run in parallel
Agent({ description: "Task 1", run_in_background: true, model: "sonnet",
  isolation: "worktree",  // prevents edit conflicts
  prompt: "You are a swarm agent. BYPASS WF_INIT. [task]..." })
Agent({ description: "Task 2", run_in_background: true, model: "sonnet",
  isolation: "worktree",
  prompt: "You are a swarm agent. BYPASS WF_INIT. [task]..." })
// Results arrive via background task notifications — synthesize after all complete
```

**Key rules:**
- ALL agents in ONE message (parallel execution)
- EVERY prompt includes swarm bypass instruction
- Use `isolation: "worktree"` when agents edit overlapping files
- Use `model: "haiku"` for read-only exploration, `"sonnet"` for implementation
- Use `subagent_type: "Explore"` for fast codebase search

**If using Claude Code Agent tool:** Skip to the MANDATORY NEXT STEP section. No Ruflo init needed.

### Path B: Ruflo (Cognitive-Only Tasks)

**Only when agents DON'T need file access.** Continue to Step 1 below.

---

## ⚠️ Tool Selection (When User Requests Specific Subsystem)

| User Says | Use Tools | Read |
|-----------|-----------|------|
| "parallel agents" / (no specific framework) | Claude Code `Agent` tool | (no additional reading needed) |
| "ruflo swarm" / "swarm" | `mcp__ruflo__swarm_*` + `mcp__ruflo__agent_*` | `WF_SWARM_RUFLO` |
| "coordinate" / "orchestrate" | `mcp__ruflo__coordination_*` | `WF_SWARM_RUV` (Pattern B1) |
| "DAA" / "DAA swarm" | `mcp__ruflo__daa_*` | `WF_SWARM_RUV` (Pattern B2) |
| "hive-mind" | `mcp__ruflo__hive-mind_*` | `WF_SWARM_HIVE_MIND` |

---

## ⛔ BLOCKING GATE: Read Swarm Reference (If Using Ruflo)

**If you chose Ruflo in Step 0, you MUST read REF_SWARM_PATTERNS before execution.**

```
mcp__plugin_swe_serena__read_memory("ref/REF_SWARM_PATTERNS")
```

**Skip this if using Claude Code Agent tool directly.**

---

## ⛔ Pre-Swarm Research (MANDATORY for All Paths)

**BEFORE planning ANY parallel work:**

1. Read ALL relevant `INDEX_*`, `ARCH_*`, `SYS_*`, `DOM_*`, `REF_*` memories
2. Use `find_symbol()` to verify nothing similar already exists
3. Check relevant skills (`/research`, `/arch-review`, `/verify`)

**Every agent prompt MUST include:** "Research existing patterns before implementing. DO NOT create anything that already exists."

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

## ⛔ MANDATORY EXECUTION PATH GATE (Step 3)

**After spawning agents and registering tasks, you MUST complete this gate BEFORE any execution.**

### 3a. Choose Execution Path Per Agent

For EACH spawned agent, decide:

| Agent Needs File Access? | Execution Path | Tool |
|--------------------------|---------------|------|
| **NO** (reasoning, planning, spec writing, comparison) | Ruflo-native | `agent_execute(agentId, prompt)` |
| **YES** (file reads, grep, glob, Serena tools) | Hybrid | Claude Code `Agent` tool |

### 3b. Verify Execution Coverage

**⛔ BLOCKING CHECK: Count your spawned agents. Count your execution calls. They MUST match.**

```
Spawned agents: [r1, r2, r3, r4, r5]  → 5 agents
Execution calls: [agent_execute(r1), agent_execute(r2), ...]  → MUST be 5 calls
```

**If counts don't match, you are violating the swarm. STOP and fix.**

### 3c. Swarm Agent Prompts

**When using Claude Code `Agent` tool (hybrid path), EVERY prompt MUST include:**

```
You are a swarm agent spawned by a DAA coordinator.
BYPASS WF_INIT entirely. Do NOT follow CLAUDE.md workflow initialization.
Follow ONLY the task instructions below.
```

**Without this, agents will re-run WF_INIT and waste their entire context on workflow init.**

### 3d. Execute ALL Agents in ONE Message

**⛔ NEVER launch agents one at a time.** All `agent_execute` calls OR all `Agent` tool calls MUST be in a single message for parallel execution.

---

## Critical Execution Rules

### Claude Code Agent Tool (Default Path)

**DO:**
- **Launch ALL agents in ONE message** — they run in parallel automatically
- Include swarm bypass instruction in EVERY agent prompt
- Use `isolation: "worktree"` when agents may edit overlapping files
- Use `model: "haiku"` for read-only tasks, `"sonnet"` for implementation
- Load memories BEFORE launching agents, not during

**DON'T:**
- ❌ Launch only 1 of N agents — violates parallel execution
- ❌ Launch Agent tool without swarm bypass instruction in prompt
- ❌ Read files directly in coordinator context — agents do that
- ❌ Use Ruflo when agents need file access — it adds overhead without value

### Ruflo Subsystems (Cognitive-Only Path)

**DO:**
- Init swarm FIRST → spawn all agents in ONE message → register tasks BEFORE execution
- **Execute ALL agents in ONE message** — never 1 of N
- Use `agent_execute` for reasoning tasks (no file access)
- Batch MCP calls into as few messages as possible
- Store coordination state to MCP memory

**DON'T:**
- ❌ Spawn Ruflo agents then use Agent tool without `agent_execute` — agents sit idle
- ❌ Use Ruflo for tasks that need file access — `agent_execute` can't read files
- ❌ Block on first agent before spawning others
- ❌ Skip task registration in coordination layer
- ❌ Use verbose/detailed flags on MCP calls
- ❌ Call `memory_stats` (scans 100K entries)

### Task Registration (CRITICAL)

MCP agents MUST have tasks registered BEFORE launching execution. Without this, the coordination layer has no visibility into agent work.

```
1. agent_spawn/daa_agent_create → 2. task_create/daa_workflow_create → 3. EXECUTION PATH GATE → 4. Execute ALL agents (ONE message) → 5. Collect results
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
