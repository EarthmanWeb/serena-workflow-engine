# WF_SWARM_HIVE_MIND - Hive-Mind Collective Intelligence Methodology

**System:** Hive-Mind (part of Claude-Flow)
**MCP Prefix:** `mcp__claude-flow__hive-mind_`
**Purpose:** Consensus-based decisions, collective intelligence, shared memory

---

## ⚠️ Verified MCP Tool Prefix

| System | Actual Prefix |
|--------|---------------|
| **Hive-Mind** | `mcp__claude-flow__hive-mind_` |

**Note:** Hive-Mind tools are part of Claude-Flow but use the `hive-mind_` sub-prefix.

---

## When To Use

| Scenario | Topology |
|----------|----------|
| Consensus decisions across agents | mesh |
| Collective code review | mesh |
| Architecture decision-making | mesh |
| Shared knowledge accumulation | mesh |

**Hive-Mind is best for tasks requiring agreement or collective intelligence, not raw parallel execution.** For parallel tasks, use Claude-Flow (Pattern A) or RUV-Swarm (Pattern B1).

---

## Phase 1: Load Tools + Initialize Hive

```javascript
// 1. Load hive-mind tools
ToolSearch({ query: "+claude-flow hive-mind" })

// 2. Init hive with topology and queen
mcp__claude-flow__hive-mind_init({
  topology: "mesh",
  queenId: "queen-1"
})
```

---

## Phase 2: Spawn Workers

```javascript
// 3. Spawn worker agents
mcp__claude-flow__hive-mind_spawn({
  count: 3,
  role: "worker",        // "worker" or "queen"
  agentType: "analyst"   // researcher, analyst, coder, etc.
})
```

---

## Phase 3: Set Shared Memory + Broadcast

```javascript
// 4. Store shared configuration/context in hive memory
mcp__claude-flow__hive-mind_memory({
  action: "set",
  key: "task-config",
  value: { description: "...", scope: "..." }
})

// 5. Broadcast instructions to all workers
mcp__claude-flow__hive-mind_broadcast({
  message: "Analyze the form submission pipeline for gaps",
  priority: "high"
})

// 6. Retrieve shared memory
mcp__claude-flow__hive-mind_memory({
  action: "get",
  key: "task-config"
})
```

---

## Phase 4: Launch Task Agents for File Work

```javascript
// 7. Launch background Agent tools for actual work
Agent({ description: "Worker 1 analysis", run_in_background: true, prompt: "..." })
Agent({ description: "Worker 2 analysis", run_in_background: true, prompt: "..." })
Agent({ description: "Worker 3 analysis", run_in_background: true, prompt: "..." })
```

---

## Phase 5: Consensus + Collect Results

```javascript
// 8. Propose a decision for consensus
mcp__claude-flow__hive-mind_consensus({
  action: "propose",
  type: "decision",
  value: {
    question: "Should we refactor the submission pipeline?",
    options: ["yes-full-refactor", "partial-refactor", "no-change"]
  }
})

// 9. Vote on proposal (each worker votes)
mcp__claude-flow__hive-mind_consensus({
  action: "vote",
  proposalId: "proposal-id",
  vote: "yes-full-refactor"
})

// 10. Check consensus status
mcp__claude-flow__hive-mind_status({})

// 11. Store results in shared memory
mcp__claude-flow__hive-mind_memory({
  action: "set",
  key: "consensus-result",
  value: { decision: "...", rationale: "..." }
})
```

---

## Phase 6: Cleanup

```javascript
// 12. Workers leave hive when done
mcp__claude-flow__hive-mind_leave({ agentId: "worker-1" })

// 13. Shutdown hive when all work complete
mcp__claude-flow__hive-mind_shutdown({})
```

---

## Essential Tools Reference

| Tool | Full Name | Purpose |
|------|-----------|---------|
| `hive-mind_init` | `mcp__claude-flow__hive-mind_init` | Initialize hive |
| `hive-mind_spawn` | `mcp__claude-flow__hive-mind_spawn` | Spawn workers |
| `hive-mind_join` | `mcp__claude-flow__hive-mind_join` | Agent joins hive |
| `hive-mind_leave` | `mcp__claude-flow__hive-mind_leave` | Agent leaves hive |
| `hive-mind_broadcast` | `mcp__claude-flow__hive-mind_broadcast` | Send to all agents |
| `hive-mind_memory` | `mcp__claude-flow__hive-mind_memory` | Shared key-value store |
| `hive-mind_consensus` | `mcp__claude-flow__hive-mind_consensus` | Propose/vote/decide |
| `hive-mind_status` | `mcp__claude-flow__hive-mind_status` | Check hive state |
| `hive-mind_shutdown` | `mcp__claude-flow__hive-mind_shutdown` | Terminate hive |

---

## Hive-Mind Specific Rules

- **Always init before spawn** — hive must exist before workers join
- **Use shared memory** (`hive-mind_memory`) for cross-agent state, not individual agent memory
- **Use broadcast** for instructions that all workers need
- **Use consensus** for decisions that require agreement
- **Cleanup:** `leave` workers → `shutdown` hive when done
- **Mesh topology** is the only practical choice for consensus
- **MCP = coordination, Agent tool = execution** — same rule as all systems
