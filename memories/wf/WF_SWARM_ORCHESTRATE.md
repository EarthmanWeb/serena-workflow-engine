# WF_SWARM_ORCHESTRATE - Multi-Agent Swarm Coordination

> **🐝 On step WF_SWARM_ORCHESTRATE**

⬆️ OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## When To Use

- Task affects 6+ files OR 3+ architectural layers
- Independent subtasks can run in parallel
- Multi-domain coordination or consensus needed

**Read `REF_SWARM_PATTERNS` for detailed MCP tool reference.**

---

## ⚠️ Explicit Tool Selection Rule

**When user requests a specific swarm system, USE THOSE EXACT MCP TOOLS — never substitute Task/Explore agents.**

| User Says | Use Tools |
|-----------|-----------|
| "ruv-swarm" | `mcp__ruv-swarm__*` |
| "claude-flow swarm" | `mcp__claude-flow__*` |
| "hive-mind" | `mcp__claude-flow__hive-mind_*` |

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

| System | When | Prefix |
|--------|------|--------|
| **Claude-Flow** | General orchestration, parallel tasks | `mcp__claude-flow__*` |
| **RUV-Swarm** | Learning/adaptation, DAA patterns | `mcp__ruv-swarm__*` |
| **Hive-Mind** | Consensus, collective intelligence | `mcp__claude-flow__hive-mind_*` |

| Topology | Best For |
|----------|----------|
| **mesh** | Collaborative analysis, exploration |
| **hierarchical** | Complex projects, orchestrated changes |
| **star** | Quick parallel tasks |
| **ring** | Sequential processing pipelines |

Agent types: `researcher`, `analyst`, `coder`, `tester`, `coordinator`, `optimizer`, `reviewer`

---

## Step 2: Initialize & Execute

### Pattern A: Claude-Flow V3 (Recommended)

```
1. swarm_init({ topology: 'hierarchical-mesh', maxAgents: 15 })
2. agent_spawn (all agents in ONE message, parallel)
3. task_create({ assignToAgent: 'agent-id', priority: 8 }) for each task
4. task_dependencies() for sequential ordering
5. Task tool (run_in_background: true) for actual file work
6. task_status / swarm_status to monitor
7. task_results / TaskOutput to collect
8. memory_store for coordination state
```

**Key V3 tools:** `swarm/init`, `agent/spawn|list|status`, `task/create|assign|status|results|dependencies`, `workflow/create|execute`

### Pattern B1: RUV-Swarm Task Orchestration

⚠️ `task_orchestrate` ONLY works with `agent_spawn` agents, NOT `daa_agent_create`.

```
1. swarm_init({ topology: 'mesh', strategy: 'balanced' })
2. agent_spawn (all agents)
3. task_orchestrate({ strategy: 'parallel', priority: 'high' })
4. task_status / task_results to collect
```

### Pattern B2: RUV-Swarm DAA (Autonomous Learning)

⚠️ DAA agents are SEPARATE from swarm agents. Use `daa_workflow_execute`, NOT `task_orchestrate`.

```
1. daa_init({ enableLearning: true, enableCoordination: true })
2. daa_agent_create (these are NOT swarm agents)
3. daa_workflow_create + daa_workflow_execute({ parallelExecution: true })
4. daa_knowledge_share between agents
5. daa_learning_status to check progress
```

### Pattern B3: Hybrid (Swarm + DAA)

Combine B1 for task orchestration + B2 for learning. Two separate agent pools.

### Pattern C: Hive-Mind

```
1. hive-mind_init({ topology: 'mesh' })
2. hive-mind_spawn({ count: 3, role: 'worker' })
3. hive-mind_consensus({ action: 'propose' })
4. hive-mind_memory / hive-mind_broadcast as needed
```

---

## ⛔ NEVER Run Init CLI Commands

**Never** `npx claude-flow init` or `npx ruv-swarm init` — these modify repo files. Use MCP tools directly (in-memory coordination).

---

## Critical Execution Rules

**DO:** Init swarm first → Spawn all agents in one message → Register tasks with `task_create` + `assignToAgent` before Task tool → Store state to memory → Monitor non-blocking, collect blocking

**DON'T:** Spawn swarm then revert to single-agent → Block on first agent before spawning others → Skip task registration in coordination layer → Mix swarm systems without clear handoff

### Task Registration (CRITICAL)

MCP agents MUST have tasks registered via `task_create({ assignToAgent })` BEFORE launching Task tool work. Without this, the coordination layer has no visibility into agent work.

```
1. agent_spawn → 2. task_create({ assignToAgent }) → 3. Task tool (background) → 4. task_status to monitor
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
