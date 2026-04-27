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
| **3** | `CLAUDE_FLOW`          | ⛔ REQUIRED - Coordination ref  |

**⛔ SKIPPING = WORKFLOW VIOLATION**

**Note:** FEATURE_AGENTS is a template file — skip it unless customized.

---

## ⚠️ VERIFIED MCP TOOL PREFIXES (2026-04-27)

| System          | Actual MCP Prefix              |
| --------------- | ------------------------------ |
| **Claude-Flow** | `mcp__claude-flow__`           |
| **RUV-Swarm**   | `mcp__ruv-swarm__`             |
| **Hive-Mind**   | `mcp__claude-flow__hive-mind_` |

**⛔ OLD WRONG PREFIXES (never use these):**

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

Trigger on: `swarm`, `parallel agents`, `multi-agent`, `hive-mind`, `ruv-swarm`, `claude-flow swarm`, `DAA`, `orchestrate agents`

---

## Available Systems

| System      | Use Case                           | Tools | Details In         |
| ----------- | ---------------------------------- | ----- | ------------------ |
| Claude-Flow | General orchestration              | ~257  | CLAUDE_FLOW        |
| RUV-Swarm   | Task orchestration, DAA learning   | 25    | REF_SWARM_PATTERNS |
| Hive-Mind   | Consensus, collective intelligence | 9     | CLAUDE_FLOW        |

---

## Quick Start (Context-Optimized)

```javascript
// 1. Load only needed tools
ToolSearch({ query: "+claude-flow swarm agent task" })

// 2. Init + spawn + task (ONE message)
mcp__claude-flow__swarm_init({ topology: "star", maxAgents: 5 })
mcp__claude-flow__agent_spawn({ agentType: "coder", agentId: "agent-1" })
mcp__claude-flow__task_create({ type: "implement", description: "...", assignToAgent: "agent-1" })

// 3. Actual work via Task tool (separate context)
Task({ subagent_type: "general-purpose", run_in_background: true, prompt: "..." })

// 4. Collect results
TaskOutput({ task_id: "...", block: true })
```

---

## Related Memories

| Memory               | Content                       |
| -------------------- | ----------------------------- |
| WF_SWARM_ORCHESTRATE | Complete swarm workflow       |
| REF_SWARM_PATTERNS   | MCP tool reference + patterns |
| CLAUDE_FLOW          | Coordination patterns + rules |
