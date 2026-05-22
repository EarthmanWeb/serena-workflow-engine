# WF_SWARM_RUFLO - Ruflo Swarm Methodology

**System:** Ruflo (Recommended for general orchestration)
**MCP Prefix:** `mcp__ruflo__`

---

## ⚠️ Verified MCP Tool Prefix

| System | Actual Prefix |
|--------|---------------|
| **Ruflo** | `mcp__ruflo__` |

---

## When To Use

| Scenario | Topology |
|----------|----------|
| Quick parallel tasks | star |
| Multi-file analysis | mesh |
| Code refactoring | hierarchical |
| Sequential pipelines | ring |

---

## Phase 1: Load Tools + Initialize Swarm + Spawn Agents

```javascript
// 1. Load needed ruflo tools (ONE ToolSearch call)
ToolSearch({ query: "+ruflo swarm agent task" })
// If you need memory tools too:
ToolSearch({ query: "select:mcp__ruflo__memory_store,mcp__ruflo__memory_retrieve" })

// 2. Init swarm with topology
mcp__ruflo__swarm_init({ topology: "star", maxAgents: 5 })
// Topologies: "star" (default, least overhead), "mesh", "hierarchical", "ring"

// 3. Spawn ALL agents in ONE message
mcp__ruflo__agent_spawn({ agentType: "researcher", agentId: "researcher-1" })
mcp__ruflo__agent_spawn({ agentType: "coder", agentId: "coder-1" })
mcp__ruflo__agent_spawn({ agentType: "analyst", agentId: "analyst-1" })
// Agent types: researcher, analyst, coder, tester, coordinator, optimizer, reviewer
```

---

## Phase 2: Create Tasks + Set Dependencies

```javascript
// 4. Register ALL tasks with agent assignments — batch in ONE message
mcp__ruflo__task_create({
  type: "research",
  description: "Analyze component architecture",
  assignToAgent: "researcher-1",
  priority: 8  // 1-10, higher = more urgent
})
mcp__ruflo__task_create({
  type: "implement",
  description: "Implement changes to module X",
  assignToAgent: "coder-1",
  priority: 7
})

// 5. Set dependencies if tasks must run sequentially
// (skip if all tasks are independent/parallel)
```

---

## Phase 3: Launch Task Agents for File Work

```javascript
// 6. Launch background Agent tools for ACTUAL file reads/writes (separate context)
Agent({ description: "Research task", run_in_background: true, prompt: "..." })
Agent({ description: "Coding task", run_in_background: true, prompt: "..." })
// One Agent per ruflo agent — MCP coordinates, Agent tool executes
```

---

## Phase 4: Monitor + Collect + Store State

```javascript
// 7. Monitor progress (only when needed — each call adds ~1-2K tokens)
mcp__ruflo__task_status({ taskId: "task-id" })
mcp__ruflo__swarm_status({})  // NO verbose flag

// 8. After Task agents complete, update task status
mcp__ruflo__task_complete({ taskId: "task-id" })

// 9. Store coordination state for cross-agent visibility
mcp__ruflo__memory_store({
  key: "results-summary",
  value: "findings from completed work"
})

// 10. Retrieve stored state
mcp__ruflo__memory_retrieve({ key: "results-summary" })
```

---

## Essential Tools Reference

Only load what you need (max 3-5 per session):

| Tool | Full Name | Purpose |
|------|-----------|---------|
| `swarm_init` | `mcp__ruflo__swarm_init` | Initialize swarm with topology |
| `swarm_status` | `mcp__ruflo__swarm_status` | Check health (NO verbose flag) |
| `agent_spawn` | `mcp__ruflo__agent_spawn` | Create coordination agent |
| `agent_list` | `mcp__ruflo__agent_list` | List active agents |
| `task_create` | `mcp__ruflo__task_create` | Register task with agent assignment |
| `task_status` | `mcp__ruflo__task_status` | Check task progress |
| `task_complete` | `mcp__ruflo__task_complete` | Mark task done |
| `memory_store` | `mcp__ruflo__memory_store` | Persist state |
| `memory_retrieve` | `mcp__ruflo__memory_retrieve` | Recall state |

---

## Ruflo-Specific Rules

- **Max 3-5 tools loaded** per session via ToolSearch — never load all tools
- **NEVER use `verbose: true`** or `detailed: true` flags on status/metrics calls
- **NEVER call `memory_stats`** — it scans up to 100K entries internally
- **Limit `memory_list` to `limit: 5`** (defaults to 50)
- **Batch init+spawn+task** into as few messages as possible
- **Star topology by default** — least coordination overhead
- **Fire-and-forget MCP tasks** — collect results via Agent tool output, not MCP call
- **Skip `swarm_status` checks** unless actually needed — each adds ~1-2K tokens

---

## Context Budget Warning

| Budget Item | Token Estimate | Rule |
|-------------|----------------|------|
| Each MCP tool schema (ToolSearch) | ~500-1K | Only load tools you'll USE |
| Each MCP tool response | ~200-2K | Avoid verbose/detailed flags |
| Each status check | ~1-2K | Skip unless needed |
| Task agent prompt | ~2-5K | Keep focused |

**If you hit "Prompt is too long":** Session is dead — start a new one with lower `MAX_MCP_OUTPUT_TOKENS`.
