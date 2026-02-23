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

## 🧠 DAA (Dynamic Autonomous Agents) Quick Reference

DAA provides autonomous learning agents that adapt from feedback. Use DAA for analysis-heavy tasks like feature onboarding, codebase exploration, and pattern detection.

**MCP Prefix:** `mcp__plugin_claude-flow_ruv-swarm__`

### DAA Initialization

```javascript
ToolSearch({ query: '+ruv-swarm daa' })  // Load DAA tools first

daa_init({ enableLearning: true, enableCoordination: true, persistenceMode: 'memory' })
```

### DAA Agent Creation

```javascript
daa_agent_create({ id: 'agent-1', cognitivePattern: 'adaptive', enableMemory: true, learningRate: 0.1 })
daa_agent_create({ id: 'agent-2', cognitivePattern: 'critical', enableMemory: true, learningRate: 0.1 })
```

**Cognitive patterns:** `adaptive`, `critical`, `convergent`, `divergent`, `lateral`, `systems`

### DAA Workflow Execution

```javascript
daa_workflow_create({ id: 'wf-1', name: 'Feature Analysis', strategy: 'adaptive', steps: [...] })
daa_workflow_execute({ workflowId: 'wf-1' })
```

### DAA Feedback Loop

```javascript
daa_agent_adapt({ agentId: 'agent-1', feedback: 'description of results', performanceScore: 0.9 })
daa_learning_status({ detailed: true })
```

**⚠️ DAA agents ≠ Swarm agents** — Use `daa_workflow_execute`, NOT `task_orchestrate`. See `CLAUDE_FLOW` for full tool reference.

---

## Related Memories

| Memory               | Content                 |
| -------------------- | ----------------------- |
| WF_SWARM_ORCHESTRATE | Complete swarm workflow |
| REF_SWARM_PATTERNS   | MCP tool reference      |
| CLAUDE_FLOW          | Coordination patterns   |
| REF_AGENTS           | Agent selection guide   |
