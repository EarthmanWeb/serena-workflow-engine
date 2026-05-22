# RUFLO - MCP Swarm Coordination Reference

## ⚠️ VERIFIED MCP TOOL PREFIX (2026-05-06)

| System | Actual MCP Prefix |
| ------ | ----------------- |
| **Ruflo** (unified) | `mcp__ruflo__` |
| **Hive-Mind** (subsystem) | `mcp__ruflo__hive-mind_` |
| **DAA** (subsystem) | `mcp__ruflo__daa_*` |
| **Coordination** (subsystem) | `mcp__ruflo__coordination_*` |

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

## 🚀 Ruflo Swarm Orchestration

**Prefix:** `mcp__ruflo__`

### Minimal Orchestration Pattern

```javascript
// 1. Load tools (ONE call)
ToolSearch({ query: "+ruflo swarm agent task" })

// 2. Init + spawn + task in ONE message
mcp__ruflo__swarm_init({ topology: "star", maxAgents: 5 })
mcp__ruflo__agent_spawn({ agentType: "coder", agentId: "agent-1" })
mcp__ruflo__task_create({ type: "implement", description: "...", assignToAgent: "agent-1", priority: 8 })

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

## 🚀 Ruflo Task Orchestration (Coordination Tools)

**Prefix:** `mcp__ruflo__coordination_*`

### Minimal Pattern

```javascript
ToolSearch({ query: "+ruflo agent coordination" })
mcp__ruflo__swarm_init({ topology: "mesh", strategy: "balanced", maxAgents: 5 })
mcp__ruflo__agent_spawn({ type: "researcher", name: "r1" })
mcp__ruflo__agent_spawn({ type: "coder", name: "c1" })
mcp__ruflo__coordination_orchestrate({ task: "...", strategy: "parallel", priority: "high" })
```

**Agent types:** `researcher`, `analyst`, `coder`, `optimizer`, `coordinator`

**⚠️ Swarm agents ≠ DAA agents — do NOT mix pools**

---

## 🧠 Ruflo DAA (Iterative Coordination & Tracking)

**Prefix:** `mcp__ruflo__daa_*`

**⚠️ DAA is a metadata/tracking layer, NOT an execution engine.** `daa_workflow_execute` returns empty arrays. All metrics are simulated. Only use DAA for **multi-iteration workflows** where cross-iteration state tracking adds value. For single-pass parallel work, use Ruflo swarm orchestration.

### How DAA Actually Works

1. `daa_agent_create` → Creates JSON record (cognitive pattern label, capabilities). No process spawned.
2. `daa_workflow_create` → Registers workflow steps as metadata. No execution logic.
3. **Agent tool** → Does ALL actual work in separate context. Cognitive pattern MUST be injected into prompt.
4. `daa_knowledge_share` → Stores Agent findings in JSON registry for next iteration.
5. Repeat: Read stored knowledge → shape next Agent prompt → launch next round.

### Minimal Pattern

```javascript
ToolSearch({ query: "+ruflo daa" })
mcp__ruflo__daa_agent_create({ id: "daa-1", cognitivePattern: "critical", enableMemory: true })
mcp__ruflo__daa_workflow_create({ id: "wf-1", name: "Analysis", strategy: "adaptive" })
// ⚠️ Skip daa_workflow_execute (returns empty arrays) — launch Agent tools directly
// Inject cognitive pattern into Agent prompt to influence actual behavior
Agent({ prompt: "You are daa-1 (cognitive: critical). Analyze critically, find flaws..." })
// After Agent completes, store ACTUAL findings for next iteration:
mcp__ruflo__daa_knowledge_share({ sourceAgentId: "daa-1", ..., knowledgeContent: { findings: "REAL results" } })
```

**Cognitive patterns:** `adaptive`, `critical`, `convergent`, `divergent`, `lateral`, `systems`

**Skip these tools** (return simulated/random data): `daa_learning_status`, `daa_performance_metrics`

---

## 🐝 HIVE-MIND (Collective Intelligence)

**Prefix:** `mcp__ruflo__hive-mind_`

### Minimal Pattern (Coordinator)

```javascript
// Coordinator: init + spawn + store context
ToolSearch({ query: "+ruflo hive-mind" })
mcp__ruflo__hive-mind_init({ topology: "mesh", queenId: "queen-1" })
mcp__ruflo__hive-mind_spawn({ count: 3, role: "worker", agentType: "analyst" })
mcp__ruflo__hive-mind_memory({ action: "set", key: "task-context", value: {...} })

// Launch agents — each MUST use hive-mind tools (see below)
Agent({ run_in_background: true, prompt: "...includes hive-mind tool instructions..." })

// After agents complete: read findings + run consensus
mcp__ruflo__hive-mind_memory({ action: "get", key: "findings-agent-1" })
mcp__ruflo__hive-mind_consensus({ action: "propose", type: "decision", strategy: "quorum", value: {...} })
```

### ⛔ CRITICAL: Agent Prompt Requirements

**Agent subagents will NOT use hive-mind tools unless explicitly told to.** Every agent prompt MUST include:

1. `ToolSearch({ query: "select:mcp__ruflo__hive-mind_memory", max_results: 1 })` — load the tool
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
5. **Never run CLI init** — Use MCP tools only
6. **Star topology by default** — Least coordination overhead
7. **3-5 tools max** — Don't load tools you won't use
8. **No verbose flags** — Keep responses small

---

## 📊 When to Use Each Subsystem

| Scenario                 | Subsystem              | Topology     |
| ------------------------ | ---------------------- | ------------ |
| Quick parallel tasks     | Ruflo swarm            | star         |
| Parallel file analysis   | Ruflo coordination     | mesh         |
| Coordinated refactoring  | Ruflo swarm            | hierarchical |
| Multi-iteration tracking | Ruflo DAA              | adaptive     |
| Consensus decisions      | Ruflo Hive-Mind        | mesh         |

---

## 🔧 Loading Tools

```javascript
// Load ruflo swarm tools (batch)
ToolSearch({ query: "+ruflo swarm agent task" })

// Load ruflo DAA tools (batch)
ToolSearch({ query: "+ruflo daa" })

// Load hive-mind tools
ToolSearch({ query: "+ruflo hive-mind" })

// Select one specific tool
ToolSearch({ query: "select:mcp__ruflo__swarm_init" })
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

## Known Issues (2026-05-06)

| Issue                                           | Mitigation                                        |
| ----------------------------------------------- | ------------------------------------------------- |
| Pretty-printed JSON doubles response size       | `MAX_MCP_OUTPUT_TOKENS=5000` + keep calls minimal |
| memory_stats scans all entries                  | NEVER call it                                     |
| Wrong prefixes in old docs caused 100% failures | Use prefixes from THIS doc                        |
| "Prompt is too long" kills session permanently  | Prevention only — see section above               |

Remember: **MCP coordinates, Task tool executes!**
