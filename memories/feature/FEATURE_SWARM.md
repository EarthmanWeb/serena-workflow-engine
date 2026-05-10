# FEATURE_SWARM - Multi-Agent Swarm Orchestration

## Overview

| Property    | Value                                                           |
| ----------- | --------------------------------------------------------------- |
| **Key**     | SWARM                                                           |
| **Type**    | Workflow Routing Feature                                        |
| **Purpose** | Mandatory routing target in WF_CLASSIFY for swarm orchestration |

---

## 🛑 STOP - MANDATORY READING BEFORE ANY SWARM WORK

**Read these memories IN ORDER before swarm work:**

| Step  | Memory                 | Purpose                         |
| ----- | ---------------------- | ------------------------------- |
| **1** | `WF_SWARM_ORCHESTRATE` | ⛔ REQUIRED - Primary workflow  |
| **2** | `REF_SWARM_PATTERNS`   | ⛔ REQUIRED - MCP tool patterns |
| **3** | `REF_RUFLO_MCP_TOOLS`  | ⛔ REQUIRED - Tool schemas & execution flows |
| **4** | `RUFLO`                | ⛔ REQUIRED - Coordination ref  |

**⛔ SKIPPING = WORKFLOW VIOLATION**

**Note:** FEATURE_AGENTS is a template file — skip it unless customized.

---

## ⚠️ VERIFIED MCP TOOL PREFIX (2026-05-06)

| System | Actual MCP Prefix |
| ------ | ----------------- |
| **Ruflo** (unified) | `mcp__ruflo__` |
| **Hive-Mind** (subsystem) | `mcp__ruflo__hive-mind_` |
| **DAA** (subsystem) | `mcp__ruflo__daa_*` |

**⛔ OLD WRONG PREFIXES (never use):**

- ~~`mcp__claude-flow__`~~
- ~~`mcp__ruv-swarm__`~~
- ~~`mcp__plugin_claude-flow_claude-flow__`~~
- ~~`mcp__plugin_claude-flow_ruv-swarm__`~~
- ~~`mcp__plugin_swe_ruv-swarm__`~~

---

## ⚠️ CONTEXT BUDGET WARNING

**Previous swarm sessions failed from context overload.** Root causes:

1. Loading 12+ memory files before work starts (~30-50K tokens)
2. Loading too many MCP tools via ToolSearch
3. Using verbose/detailed flags on MCP responses
4. MCP coordinator doing file reads instead of delegating to Task agents

**Environment Variables (set BEFORE launching claude):**

```bash
export MAX_MCP_OUTPUT_TOKENS=5000    # Cap responses (default 25K causes overflow)
export ENABLE_TOOL_SEARCH=auto:5     # Aggressive tool deferral
```

**Rules to prevent overload:**

- Load max 3-5 MCP tools per session
- NEVER use verbose/detailed flags
- NEVER call memory_stats
- Delegate ALL file work to Task agents (separate context)
- Load memories BEFORE swarm init, not during
- Batch init+spawn+task into ONE message
- Skip status checks unless actually needed

---

## 🐝 POST-LOAD DIRECTIVE

> 🐝 SWARM DETECTED - Use MCP swarm orchestration.
> After completing WF_CLASSIFY feature loading, go to **WF_SWARM_ORCHESTRATE**.

---

## Trigger Conditions

Route to SWARM when ANY apply:

| Condition     | Threshold                                 |
| ------------- | ----------------------------------------- |
| File Scale    | 6+ files affected                         |
| Layer Scale   | 3+ architectural layers                   |
| Parallel Work | Independent subtasks can run concurrently |
| Multi-Domain  | Coordination across domains required      |
| User Request  | Explicit swarm/parallel agents request    |

### Keyword Detection

Trigger on: `swarm`, `parallel agents`, `multi-agent`, `hive-mind`, `ruflo swarm`, `DAA`, `orchestrate agents`

---

## ⚠️ MANDATORY FIRST QUESTION: Do You Actually Need Ruflo?

**Ruflo is a coordination layer, not an execution engine (except for `agent_execute` which is API-only, no file access).** Before spinning up Ruflo, decide if it adds value:

| Task Profile | Use Ruflo? | Why |
|-------------|-----------|-----|
| Reasoning-only parallel tasks (no file access) | **YES** — `agent_execute` IS the execution engine | Ruflo is the only way to run these |
| Multi-iteration (Round 1 findings → Round 2) | **YES** — `daa_knowledge_share` stores cross-round state | Real value from DAA tracking |
| Consensus decisions | **YES** — Hive-mind has no alternative | Only Ruflo provides this |
| Single-pass parallel tasks needing file access | **NO** — just launch Claude Code `Agent` tools directly | Ruflo agents sit "idle" in hybrid mode. They track but don't execute. It's overhead. |
| User explicitly requests Ruflo/DAA | **YES** — respect the request | But explain trade-offs |

**If Ruflo isn't needed:** Skip straight to launching Claude Code `Agent` tools in parallel (all in ONE message, with swarm bypass prompts). No `swarm_init`, no `agent_spawn`, no ceremony.

**⚠️ In hybrid mode (Ruflo + Claude Code Agent), Ruflo agents show `status: "idle"` in `agent_list`.** This is expected — they're tracking-only. The Claude Code Agent tools do the actual work. Communicate this to the user BEFORE launching to avoid confusion.

---

## Available Subsystems (all under Ruflo)

| Subsystem   | Use Case                                       | Details In         |
| ----------- | ---------------------------------------------- | ------------------ |
| Swarm       | General orchestration                          | RUFLO              |
| DAA         | Task orchestration, DAA iterative tracking     | REF_SWARM_PATTERNS |
| Hive-Mind   | Consensus, collective intelligence             | RUFLO              |
| Coordination | Task orchestration across agents              | REF_SWARM_PATTERNS |

---

## ⛔ EXECUTION PATH DECISION GATE (MANDATORY)

**After spawning agents, you MUST explicitly choose an execution path for EACH agent. This is a blocking gate — you cannot proceed without deciding.**

| Question | If YES → | If NO → |
|----------|----------|---------|
| Does the agent need to read/write files from the codebase? | **Hybrid path**: `agent_spawn` (tracking) + Claude Code `Agent` tool (execution) | **Ruflo-native path**: `agent_spawn` → `agent_execute` |

**⛔ ANTI-PATTERNS THAT TRIGGERED THIS GATE:**

| Anti-Pattern | What Goes Wrong | Fix |
|-------------|----------------|-----|
| Spawn Ruflo agents → launch Claude Code `Agent` tool ignoring spawned agents | Ruflo agents sit idle, no tracking, no coordination | Use `agent_execute` on spawned agents |
| Launch only 1 of N agents | 80% of swarm does nothing | Execute ALL agents in ONE message (parallel) |
| Claude Code Agent re-runs WF_INIT | Agent gets stuck in workflow init instead of doing task | Include "You are a swarm agent. BYPASS WF_INIT. Follow ONLY these instructions:" in prompt |

**Rules:**
1. **Every `agent_spawn` MUST have a corresponding `agent_execute` OR Claude Code `Agent` launch**
2. **ALL agents MUST be executed in ONE message** — never launch 1 of 5
3. **Claude Code `Agent` prompts MUST include swarm bypass instruction** (see WF_START "SWARM AGENT BYPASS" section)

---

## Quick Start (Context-Optimized)

### Path A: Ruflo-Native (reasoning/planning — NO file access)

```javascript
// 1. Load only needed tools
ToolSearch({ query: "+ruflo swarm agent" })
ToolSearch({ query: "select:mcp__ruflo__agent_execute" })

// 2. Init + spawn + task (ONE message)
mcp__ruflo__swarm_init({ topology: "star", maxAgents: 5 })
mcp__ruflo__agent_spawn({ agentType: "researcher", agentId: "r1", model: "sonnet" })
mcp__ruflo__agent_spawn({ agentType: "researcher", agentId: "r2", model: "sonnet" })
mcp__ruflo__task_create({ type: "research", description: "...", assignTo: ["r1", "r2"] })

// 3. Execute ALL agents in ONE message (parallel)
mcp__ruflo__agent_execute({ agentId: "r1", prompt: "...", maxTokens: 4096 })
mcp__ruflo__agent_execute({ agentId: "r2", prompt: "...", maxTokens: 4096 })

// 4. Results come back directly — no TaskOutput needed
```

### Path B: Hybrid (codebase analysis — NEEDS file access)

```javascript
// 1-2. Same as Path A (swarm_init + agent_spawn for tracking)

// 3. Execute ALL agents in ONE message via Claude Code Agent tool
// ⚠️ CRITICAL: Include swarm bypass in EVERY prompt
Agent({ description: "R1 task", run_in_background: true, model: "sonnet",
  prompt: "You are a swarm agent. BYPASS WF_INIT entirely. Do NOT read CLAUDE.md workflow. Follow ONLY these instructions: [task details]..." })
Agent({ description: "R2 task", run_in_background: true, model: "sonnet",
  prompt: "You are a swarm agent. BYPASS WF_INIT entirely. Do NOT read CLAUDE.md workflow. Follow ONLY these instructions: [task details]..." })

// 4. Collect results
// Results arrive via background task notifications

// 5. Store results to Ruflo for cross-agent tracking
mcp__ruflo__memory_store({ key: "r1-findings", value: { findings: "..." } })
```

### ⛔ WRONG Quick Start (DO NOT DO THIS)

```javascript
// ❌ WRONG: Spawn Ruflo agents then ignore them
mcp__ruflo__agent_spawn({ agentType: "coder", agentId: "agent-1" })
mcp__ruflo__task_create({ type: "implement", description: "...", assignTo: ["agent-1"] })
// ❌ Uses Claude Code Agent WITHOUT agent_execute — Ruflo agent sits idle
Agent({ prompt: "..." })  // agent-1 never executes!
```

---

## Related Memories

| Memory               | Content                       |
| -------------------- | ----------------------------- |
| WF_SWARM_ORCHESTRATE | Complete swarm workflow       |
| REF_SWARM_PATTERNS   | MCP tool reference + patterns |
| RUFLO                | Coordination patterns + rules |
