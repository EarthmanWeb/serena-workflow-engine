# REF_SWARM_PATTERNS - Swarm Coordination Reference

Multi-agent swarm patterns for parallel processing and complex task coordination.

---

## ⚠️ VERIFIED MCP TOOL PREFIXES (2026-02-23)

**The ACTUAL MCP tool names visible in ToolSearch deferred list:**

| System          | MCP Prefix           | Example Tool                       |
| --------------- | -------------------- | ---------------------------------- |
| **Claude-Flow** | `mcp__claude-flow__` | `mcp__claude-flow__swarm_init`     |
| **RUV-Swarm**   | `mcp__ruv-swarm__`   | `mcp__ruv-swarm__agent_spawn`      |
| **Hive-Mind**   | `mcp__claude-flow__` | `mcp__claude-flow__hive-mind_init` |

**⛔ WRONG prefixes found in previous docs (DO NOT USE):**

- ~~`mcp__plugin_claude-flow_claude-flow__`~~ — WRONG
- ~~`mcp__plugin_claude-flow_ruv-swarm__`~~ — WRONG
- ~~`mcp__plugin_swe_ruv-swarm__`~~ — WRONG

---

## ⚠️ CONTEXT BUDGET RULES (CRITICAL)

**Why swarm sessions fail: context overload.** Every MCP tool call adds request+response tokens. Every memory read adds content. The workflow state machine compounds this.

### Budget Limits

| Budget Item                                  | Token Estimate | Rule                         |
| -------------------------------------------- | -------------- | ---------------------------- |
| Workflow init (WF_INIT → WF_CLASSIFY)        | ~15-25K        | Unavoidable baseline         |
| Each memory read                             | ~1-5K          | Only read what you NEED      |
| Each MCP tool schema (loaded via ToolSearch) | ~500-1K        | Only load tools you'll USE   |
| Each MCP tool response                       | ~200-2K        | Avoid verbose/detailed flags |
| Task agent prompt                            | ~2-5K          | Keep agent prompts focused   |

### Environment Variables (set BEFORE launching claude)

```bash
export MAX_MCP_OUTPUT_TOKENS=5000    # Cap MCP responses (default 25K — causes overflow)
export ENABLE_TOOL_SEARCH=auto:5     # Defer tools at 5% context threshold (default 10%)
```

### Mandatory Minimization Rules

1. **Load max 3-5 MCP tools per swarm session** via ToolSearch
2. **NEVER use `verbose: true` or `detailed: true`** on status/metrics calls
3. **NEVER call `memory_stats`** (scans up to 100K entries internally)
4. **Limit `memory_list` to `limit: 5`** (defaults to 50)
5. **Skip `memory_search`** unless absolutely needed (returns full values)
6. **Use Task agents for ALL file work** — they have separate context windows
7. **Keep coordinator context lean** — it only orchestrates, doesn't read code
8. **Batch MCP calls** — init+spawn+task in ONE message, not separate turns
9. **Skip status checks** unless needed — each `swarm_status`/`task_status` adds ~1-2K tokens
10. **Fire-and-forget MCP tasks** — use `TaskOutput` on Task agents, not `task_results` MCP call

---

## ⚠️ EXPLICIT TOOL SELECTION RULE

**When user explicitly requests a specific swarm system, USE THOSE EXACT MCP TOOLS.**

| User Says                        | YOU MUST USE                    | NOT                 |
| -------------------------------- | ------------------------------- | ------------------- |
| "launch ruv-swarm" / "ruv swarm" | `mcp__ruv-swarm__*` tools       | Task/Explore agents |
| "launch claude-flow swarm"       | `mcp__claude-flow__*` tools     | Task/Explore agents |
| "use hive-mind"                  | `mcp__claude-flow__hive-mind_*` | Task/Explore agents |

---

## ⛔ NEVER RUN CLI INIT COMMANDS

**DO NOT run `npx claude-flow init`, `npx ruv-swarm init`, or similar.**

Use MCP tools directly (in-memory coordination only):

```javascript
// ✅ CORRECT: MCP tool
mcp__claude-flow__swarm_init({ topology: "mesh" })

// ❌ WRONG: CLI init (modifies repo files)
npx claude-flow init
```

---

## Available Swarm Systems

### 1. Claude-Flow (Primary - Recommended for orchestration)

**MCP Prefix:** `mcp__claude-flow__`
**Version:** 3.1.0-alpha.44 (third-party, alpha)
**Tools:** ~241 across 26 categories (deferred-loaded via ToolSearch)
**Memory:** sql.js (WASM SQLite) + HNSW vector index

**Essential Tools (load ONLY what you need):**

| Tool           | Full Name                        | Purpose                              |
| -------------- | -------------------------------- | ------------------------------------ |
| `swarm_init`   | `mcp__claude-flow__swarm_init`   | Initialize swarm with topology       |
| `swarm_status` | `mcp__claude-flow__swarm_status` | Check swarm health (NO verbose flag) |
| `agent_spawn`  | `mcp__claude-flow__agent_spawn`  | Create coordination agent            |
| `agent_list`   | `mcp__claude-flow__agent_list`   | List active agents                   |
| `task_create`  | `mcp__claude-flow__task_create`  | Register task in coordination layer  |
| `task_status`  | `mcp__claude-flow__task_status`  | Check task progress                  |
| `memory_store` | `mcp__claude-flow__memory_store` | Persist coordination state           |

**Minimal workflow (context-optimized):**

```javascript
// Step 1: Load only needed tools (ONE ToolSearch call)
ToolSearch({ query: "+claude-flow swarm agent task" })

// Step 2: Init swarm (small response)
mcp__claude-flow__swarm_init({ topology: "star", maxAgents: 5 })

// Step 3: Spawn agents + create tasks IN ONE MESSAGE
mcp__claude-flow__agent_spawn({ agentType: "coder", agentId: "agent-1" })
mcp__claude-flow__task_create({ type: "implement", description: "...", assignToAgent: "agent-1" })

// Step 4: Launch ACTUAL work via Task tool (separate context)
Task({ subagent_type: "general-purpose", run_in_background: true, prompt: "..." })

// Step 5: Collect results (blocking)
TaskOutput({ task_id: "...", block: true })
```

### 2. RUV-Swarm (Simpler, fewer tools)

**MCP Prefix:** `mcp__ruv-swarm__`
**Version:** 1.0.20
**Tools:** 25 (15 core + 10 DAA)
**Memory:** better-sqlite3 (native SQLite), 256MB mmap, WAL mode

**⚠️ TWO SEPARATE agent systems — DO NOT MIX:**

| System    | Agent Creation     | Execution              | Pool       |
| --------- | ------------------ | ---------------------- | ---------- |
| **Swarm** | `agent_spawn`      | `task_orchestrate`     | Swarm pool |
| **DAA**   | `daa_agent_create` | `daa_workflow_execute` | DAA pool   |

**Essential Tools:**

| Tool               | Full Name                          | Purpose               |
| ------------------ | ---------------------------------- | --------------------- |
| `swarm_init`       | `mcp__ruv-swarm__swarm_init`       | Initialize            |
| `agent_spawn`      | `mcp__ruv-swarm__agent_spawn`      | Create swarm agent    |
| `task_orchestrate` | `mcp__ruv-swarm__task_orchestrate` | Execute across agents |
| `task_status`      | `mcp__ruv-swarm__task_status`      | Check progress        |
| `task_results`     | `mcp__ruv-swarm__task_results`     | Get results           |

**Minimal Pattern A (Task Orchestration):**

```javascript
ToolSearch({ query: "+ruv-swarm agent task" })
mcp__ruv-swarm__swarm_init({ topology: "mesh", strategy: "balanced", maxAgents: 5 })
mcp__ruv-swarm__agent_spawn({ type: "researcher", name: "r1" })
mcp__ruv-swarm__agent_spawn({ type: "coder", name: "c1" })
mcp__ruv-swarm__task_orchestrate({ task: "...", strategy: "parallel", priority: "high" })
// Then use Task tool for actual file work
```

**Minimal Pattern B (DAA Learning):**

```javascript
ToolSearch({ query: "+ruv-swarm daa" })
mcp__ruv-swarm__daa_init({ enableLearning: true, enableCoordination: true })
mcp__ruv-swarm__daa_agent_create({ id: "daa-1", cognitivePattern: "adaptive", enableMemory: true })
mcp__ruv-swarm__daa_workflow_create({ id: "wf-1", name: "Analysis", strategy: "adaptive" })
```

### 3. Hive-Mind (Consensus/Collective Intelligence)

**MCP Prefix:** `mcp__claude-flow__hive-mind_`

**Essential Tools:**

| Tool                  | Full Name                               |
| --------------------- | --------------------------------------- |
| `hive-mind_init`      | `mcp__claude-flow__hive-mind_init`      |
| `hive-mind_spawn`     | `mcp__claude-flow__hive-mind_spawn`     |
| `hive-mind_consensus` | `mcp__claude-flow__hive-mind_consensus` |
| `hive-mind_memory`    | `mcp__claude-flow__hive-mind_memory`    |
| `hive-mind_status`    | `mcp__claude-flow__hive-mind_status`    |

---

## When to Use Each System

| Scenario               | System        | Topology     |
| ---------------------- | ------------- | ------------ |
| Quick parallel tasks   | Claude-Flow   | star         |
| Multi-file analysis    | Claude-Flow   | mesh         |
| Code refactoring       | Claude-Flow   | hierarchical |
| Research with learning | RUV-Swarm DAA | adaptive     |
| Simple parallel tasks  | RUV-Swarm     | mesh         |
| Consensus decisions    | Hive-Mind     | mesh         |

---

## Agent Types

**RUV-Swarm:** `researcher`, `analyst`, `coder`, `optimizer`, `coordinator`
**DAA Patterns:** `adaptive`, `critical`, `convergent`, `divergent`, `lateral`, `systems`

---

## CRITICAL: Execution Rules

### DO:

1. Initialize swarm FIRST
2. Spawn ALL agents + create ALL tasks in ONE message
3. Use Task tool for actual file work (separate context)
4. Keep coordinator lean — only orchestrate
5. Batch all ToolSearch loads into ONE call

### DON'T:

1. Load tools you won't use
2. Use verbose/detailed flags on MCP calls
3. Call memory_stats (scans all entries)
4. Read memory docs during swarm execution (load them BEFORE)
5. Block on first agent before spawning others
6. Read files directly in coordinator — agents do that

---

## Topology Guide

| Topology     | Structure             | Best For                             |
| ------------ | --------------------- | ------------------------------------ |
| star         | Central hub + workers | Quick parallel (RECOMMENDED default) |
| mesh         | All peers connected   | Collaborative analysis               |
| hierarchical | Tree with coordinator | Complex orchestrated changes         |
| ring         | Circular chain        | Sequential pipelines                 |

**Default to `star` topology** — it has the least coordination overhead.

---

## Known Issues

| Issue                                  | Impact                                 | Mitigation                              |
| -------------------------------------- | -------------------------------------- | --------------------------------------- |
| claude-flow is alpha (v3.1.0-alpha.44) | Stability concerns                     | Use simple patterns only                |
| 241 tools cause context bloat          | ToolSearch deferred loading helps      | Only load 3-5 tools max                 |
| Pretty-printed JSON responses          | 2x response size                       | Can't control this — keep calls minimal |
| ruv-swarm WAL file grows unbounded     | DB file accumulation                   | Clear npx cache periodically            |
| GitHub Issue #126: naming confusion    | 100% tool call failure if wrong prefix | Use prefixes from THIS doc              |
