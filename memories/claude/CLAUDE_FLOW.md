# CLAUDE_FLOW - MCP Swarm Coordination Reference

## ⚠️ VERIFIED MCP TOOL PREFIXES (2026-04-27)

| System          | Actual MCP Prefix              |
| --------------- | ------------------------------ |
| **Claude-Flow** | `mcp__claude-flow__`           |
| **RUV-Swarm**   | `mcp__ruv-swarm__`             |
| **Hive-Mind**   | `mcp__claude-flow__hive-mind_` |

**IMPORTANT:** Use `ToolSearch` to load MCP tools before calling them. Only load what you need (3-5 tools max per session).

---

## ⚠️ CONTEXT BUDGET — READ THIS FIRST

**Swarm sessions fail from context overload.** The coordinator agent shares your context window. Every MCP call, every memory read, every tool schema adds tokens.

**Environment Variables (set BEFORE starting claude):**

```bash
export MAX_MCP_OUTPUT_TOKENS=5000    # Cap MCP responses (default 25K — way too high for swarm)
export ENABLE_TOOL_SEARCH=auto:5     # Defer tools at 5% context threshold (default 10%)
```

**Rules:**

1. Load max 3-5 MCP tools via ONE ToolSearch call
2. NEVER use `verbose: true` or `detailed: true` flags
3. NEVER call `memory_stats` (scans 100K entries)
4. Keep `memory_list` to `limit: 5`
5. Task agents have SEPARATE context — delegate all file work to them
6. Load ALL needed memories BEFORE starting swarm (not during)
7. Batch ALL MCP calls into as few messages as possible (init+spawn+task in ONE message)
8. Skip `swarm_status` / `task_status` checks unless actually needed — each adds ~1-2K tokens

---

## 🎯 MCP vs Task Tool Division

| MCP Tools (Coordination Layer)       | Task Tool (Execution Layer)       |
| ------------------------------------ | --------------------------------- |
| `swarm_init` - topology setup        | Spawn agents for actual file work |
| `agent_spawn` - register agent types | Read/Write/Edit files             |
| `task_create` - register tasks       | Run tests, build commands         |
| `memory_store` - state persistence   | Code generation                   |

**Rule:** MCP coordinates strategy → Task tool executes work → TaskOutput collects results

---

## 🚀 Claude-Flow (Primary System)

**Prefix:** `mcp__claude-flow__`
**Version:** 3.5.81 (third-party by ruvnet)
**Tools:** ~257 across 29 categories (deferred-loaded, only load what you need)

### Minimal Orchestration Pattern

```javascript
// 1. Load tools (ONE call)
ToolSearch({ query: "+claude-flow swarm agent task" })

// 2. Init + spawn + task in ONE message
mcp__claude-flow__swarm_init({ topology: "star", maxAgents: 5 })
mcp__claude-flow__agent_spawn({ agentType: "coder", agentId: "agent-1" })
mcp__claude-flow__task_create({ type: "implement", description: "...", assignToAgent: "agent-1", priority: 8 })

// 3. Launch work via Task tool (separate context window)
Task({ subagent_type: "general-purpose", run_in_background: true, prompt: "..." })

// 4. Collect results
TaskOutput({ task_id: "...", block: true })
```

### Key Tools (Only load what you need)

| Tool              | Purpose                             |
| ----------------- | ----------------------------------- |
| `swarm_init`      | Initialize swarm with topology      |
| `swarm_status`    | Check health (NO verbose flag)      |
| `agent_spawn`     | Create coordination agent           |
| `task_create`     | Register task with agent assignment |
| `task_status`     | Check progress                      |
| `memory_store`    | Persist state                       |
| `memory_retrieve` | Recall state                        |

---

## 🚀 RUV-SWARM Task Orchestration

**Prefix:** `mcp__ruv-swarm__`
**Version:** 1.0.20
**Tools:** 25 total (9 core + 10 DAA + 6 utility)

### Minimal Pattern

```javascript
ToolSearch({ query: "+ruv-swarm agent task" })
mcp__ruv-swarm__swarm_init({ topology: "mesh", strategy: "balanced", maxAgents: 5 })
mcp__ruv-swarm__agent_spawn({ type: "researcher", name: "r1" })
mcp__ruv-swarm__agent_spawn({ type: "coder", name: "c1" })
mcp__ruv-swarm__task_orchestrate({ task: "...", strategy: "parallel", priority: "high" })
```

**Agent types:** `researcher`, `analyst`, `coder`, `optimizer`, `coordinator`

**⚠️ Swarm agents ≠ DAA agents — do NOT mix pools**

---

## 🧠 RUV-SWARM DAA (Autonomous Learning)

**Prefix:** `mcp__ruv-swarm__`

### Minimal Pattern

```javascript
ToolSearch({ query: "+ruv-swarm daa" })
mcp__ruv-swarm__daa_init({ enableLearning: true, enableCoordination: true })
mcp__ruv-swarm__daa_agent_create({ id: "daa-1", cognitivePattern: "adaptive", enableMemory: true })
mcp__ruv-swarm__daa_workflow_create({ id: "wf-1", name: "Analysis", strategy: "adaptive" })
mcp__ruv-swarm__daa_workflow_execute({ workflowId: "wf-1" })
```

**Cognitive patterns:** `adaptive`, `critical`, `convergent`, `divergent`, `lateral`, `systems`

---

## 🐝 HIVE-MIND (Collective Intelligence)

**Prefix:** `mcp__claude-flow__hive-mind_`
**State file:** `.claude-flow/hive-mind/state.json` (file-backed, shared by all processes)

### Minimal Pattern (Coordinator)

```javascript
// Coordinator: init + spawn + store context
ToolSearch({ query: "+claude-flow hive-mind" })
mcp__claude-flow__hive-mind_init({ topology: "mesh", queenId: "queen-1" })
mcp__claude-flow__hive-mind_spawn({ count: 3, role: "worker", agentType: "analyst" })
mcp__claude-flow__hive-mind_memory({ action: "set", key: "task-context", value: {...} })

// Launch agents — each MUST use hive-mind tools (see below)
Agent({ run_in_background: true, prompt: "...includes hive-mind tool instructions..." })

// After agents complete: read findings + run consensus
mcp__claude-flow__hive-mind_memory({ action: "get", key: "findings-agent-1" })
mcp__claude-flow__hive-mind_consensus({ action: "propose", type: "decision", strategy: "quorum", value: {...} })
```

### ⛔ CRITICAL: Agent Prompt Requirements

**Agent subagents will NOT use hive-mind tools unless explicitly told to.** Every agent prompt MUST include:

1. `ToolSearch({ query: "select:mcp__claude-flow__hive-mind_memory", max_results: 1 })` — load the tool
2. `hive-mind_memory get` — read shared context stored by coordinator
3. Do analysis work
4. `hive-mind_memory set` — write findings back to shared memory
5. (Optional) `hive-mind_memory get` — read other agents' findings for cross-referencing

**Without this, you just have parallel agents — not a hive-mind.** See `WF_SWARM_HIVE_MIND` for the full agent prompt template.

---

## ⚡ GOLDEN RULES

1. **Batch operations** — All related MCP calls in ONE message
2. **Init before spawn** — Always initialize swarm/hive first
3. **ToolSearch first** — Load MCP tools before calling (ONE batch call)
4. **MCP = coordination, Task = execution** — Never do file work in coordinator
5. **Never run CLI init** — Use MCP tools, not `npx claude-flow init`
6. **Star topology by default** — Least coordination overhead
7. **3-5 tools max** — Don't load tools you won't use
8. **No verbose flags** — Keep responses small

---

## 📊 When to Use Each System

| Scenario                | System        | Topology     |
| ----------------------- | ------------- | ------------ |
| Quick parallel tasks    | Claude-Flow   | star         |
| Parallel file analysis  | RUV-Swarm     | mesh         |
| Coordinated refactoring | Claude-Flow   | hierarchical |
| Learning from patterns  | RUV-Swarm DAA | adaptive     |
| Consensus decisions     | Hive-Mind     | mesh         |

---

## 🔧 Loading Tools

```javascript
// Load claude-flow tools (batch)
ToolSearch({ query: "+claude-flow swarm agent task" })

// Load ruv-swarm tools (batch)
ToolSearch({ query: "+ruv-swarm agent task" })

// Load hive-mind tools
ToolSearch({ query: "+claude-flow hive-mind" })

// Select one specific tool
ToolSearch({ query: "select:mcp__claude-flow__swarm_init" })
```

---

## 🛡️ "Prompt is too long" Prevention

The #1 failure mode for swarm sessions. This is a **hard context limit** — once hit, the session is permanently broken.

**Root cause:** MCP tool responses accumulate in the coordinator's context window. Each response is pretty-printed JSON (~2x size). After 10-15 MCP calls, context overflows.

**Prevention strategy:**

| Strategy              | How                                                                 | Token Impact                                       |
| --------------------- | ------------------------------------------------------------------- | -------------------------------------------------- |
| Cap MCP output        | `MAX_MCP_OUTPUT_TOKENS=5000`                                        | Prevents any single response from being >5K tokens |
| Aggressive ToolSearch | `ENABLE_TOOL_SEARCH=auto:5`                                         | Defers tool schemas until needed                   |
| Minimal MCP calls     | Init+spawn+task in ONE message, skip status checks                  | -50% MCP call volume                               |
| Task agent delegation | ALL file reads/writes in Task agents (separate context)             | Offloads 80%+ of work tokens                       |
| No verbose flags      | Never `verbose: true`, `detailed: true`, `includeMetrics: true`     | -2x per response                                   |
| Fire-and-forget       | Don't call `task_results` — use `TaskOutput` on Task agents instead | Skip MCP result retrieval entirely                 |

**If you hit "Prompt is too long":**

1. Session is dead — start a new one
2. Lower `MAX_MCP_OUTPUT_TOKENS` further (try 3000)
3. Reduce total MCP calls (combine init+spawn+task into single message)

---

## Known Issues (2026-04-27)

| Issue                                           | Mitigation                                        |
| ----------------------------------------------- | ------------------------------------------------- |
| claude-flow is third-party software             | Use simple patterns only                          |
| 257 tools cause context bloat                   | Deferred loading + load 3-5 max                   |
| Pretty-printed JSON doubles response size       | `MAX_MCP_OUTPUT_TOKENS=5000` + keep calls minimal |
| memory_stats scans all entries                  | NEVER call it                                     |
| Wrong prefixes in old docs caused 100% failures | Use prefixes from THIS doc                        |
| ruv-swarm WAL file grows unbounded              | Clear npx cache periodically                      |
| "Prompt is too long" kills session permanently  | Prevention only — see section above               |

Remember: **MCP coordinates, Task tool executes!**
