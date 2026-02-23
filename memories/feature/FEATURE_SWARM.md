# FEATURE_SWARM - Multi-Agent Swarm Orchestration

## Overview

| Property    | Value                                                           |
| ----------- | --------------------------------------------------------------- |
| **Key**     | SWARM                                                           |
| **Type**    | Workflow Routing Feature                                        |
| **Purpose** | Mandatory routing target in WF_CLASSIFY for swarm orchestration |

---

## 🛑 STOP - MANDATORY READING BEFORE ANY SWARM WORK

**YOU MUST READ THESE MEMORIES IN ORDER. DO NOT PROCEED WITHOUT COMPLETING ALL
STEPS.**

| Step  | Memory                 | MUST READ                            |
| ----- | ---------------------- | ------------------------------------ |
| **1** | `WF_SWARM_ORCHESTRATE` | ⛔ REQUIRED FIRST - Primary workflow |
| **2** | `REF_SWARM_PATTERNS`   | ⛔ REQUIRED - MCP tool patterns      |
| **3** | `CLAUDE_FLOW`          | ⛔ REQUIRED - Coordination reference |
| **4** | `REF_AGENTS`           | ⛔ REQUIRED - Agent types            |

```
mcp__plugin_swe_serena__read_memory("WF_SWARM_ORCHESTRATE")
mcp__plugin_swe_serena__read_memory("REF_SWARM_PATTERNS")
mcp__plugin_swe_serena__read_memory("CLAUDE_FLOW")
mcp__plugin_swe_serena__read_memory("REF_AGENTS")
```

**⛔ SKIPPING STEPS 1-4 = WORKFLOW VIOLATION** **⛔ PROCEEDING WITHOUT READING =
WORKFLOW VIOLATION**

---

## 🐝 POST-LOAD DIRECTIVE

> 🐝 SWARM DETECTED - You MUST use ruv-swarm or hive-mind swarm orchestration.
> After completing WF_CLASSIFY feature loading, go to **WF_SWARM_ORCHESTRATE**.

This directive activates when FEATURE_SWARM is loaded. It overrides other
routing options in WF_CLASSIFY.

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

Trigger on: `swarm`, `parallel agents`, `multi-agent`, `hive-mind`, `ruv-swarm`,
`claude-flow swarm`, `DAA`, `orchestrate agents`

---

## Available Systems

| System      | Use Case                           | Details In         |
| ----------- | ---------------------------------- | ------------------ |
| Claude-Flow | General orchestration              | CLAUDE_FLOW        |
| RUV-Swarm   | Task orchestration, DAA learning   | REF_SWARM_PATTERNS |
| Hive-Mind   | Consensus, collective intelligence | CLAUDE_FLOW        |

**Tool patterns documented in CLAUDE_FLOW and REF_SWARM_PATTERNS.**

---

## Related Memories

| Memory               | Content                 |
| -------------------- | ----------------------- |
| WF_SWARM_ORCHESTRATE | Complete swarm workflow |
| REF_SWARM_PATTERNS   | MCP tool reference      |
| CLAUDE_FLOW          | Coordination patterns   |
| REF_AGENTS           | Agent selection guide   |
