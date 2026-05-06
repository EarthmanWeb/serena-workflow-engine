# REF_SWARM_PATTERNS - Swarm Coordination Reference

Multi-agent swarm patterns for parallel processing and complex task coordination.

---

## ⚠️ VERIFIED MCP TOOL PREFIX (2026-05-06)

**The ACTUAL MCP tool names visible in ToolSearch deferred list:**

| System | MCP Prefix | Example Tool |
| ------ | ---------- | ------------ |
| **Ruflo** (unified) | `mcp__ruflo__` | `mcp__ruflo__swarm_init` |
| **Hive-Mind** | `mcp__ruflo__` | `mcp__ruflo__hive-mind_init` |
| **DAA** | `mcp__ruflo__` | `mcp__ruflo__daa_agent_create` |
| **Coordination** | `mcp__ruflo__` | `mcp__ruflo__coordination_orchestrate` |

**⛔ OLD WRONG PREFIXES (DO NOT USE):**

- ~~`mcp__claude-flow__`~~ — OLD
- ~~`mcp__ruv-swarm__`~~ — OLD
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

**When user explicitly requests a specific swarm subsystem, USE THOSE EXACT MCP TOOLS.**

| User Says | YOU MUST USE | NOT |
| --------- | ------------ | --- |
| "launch swarm" / "ruflo swarm" | `mcp__ruflo__swarm_*` + `mcp__ruflo__agent_*` tools | Task/Explore agents |
| "use hive-mind" | `mcp__ruflo__hive-mind_*` | Task/Explore agents |
| "use DAA" / "DAA swarm" | `mcp__ruflo__daa_*` | Task/Explore agents |
| "coordinate tasks" | `mcp__ruflo__coordination_*` | Task/Explore agents |

---

## ⛔ NEVER RUN CLI INIT COMMANDS

Use MCP tools directly (in-memory coordination only):

```javascript
// ✅ CORRECT: MCP tool
mcp__ruflo__swarm_init({ topology: "mesh" })

// ❌ WRONG: CLI init (modifies repo files)
npx ruflo init
```

---

## Available Swarm Subsystems

### 1. Ruflo Swarm (Primary - Recommended for orchestration)

**MCP Prefix:** `mcp__ruflo__`

**Essential Tools (load ONLY what you need):**

| Tool           | Full Name                    | Purpose                              |
| -------------- | ---------------------------- | ------------------------------------ |
| `swarm_init`   | `mcp__ruflo__swarm_init`     | Initialize swarm with topology       |
| `swarm_status` | `mcp__ruflo__swarm_status`   | Check swarm health (NO verbose flag) |
| `agent_spawn`  | `mcp__ruflo__agent_spawn`    | Create coordination agent            |
| `agent_list`   | `mcp__ruflo__agent_list`     | List active agents                   |
| `task_create`  | `mcp__ruflo__task_create`    | Register task in coordination layer  |
| `task_status`  | `mcp__ruflo__task_status`    | Check task progress                  |
| `memory_store` | `mcp__ruflo__memory_store`   | Persist coordination state           |

**Minimal workflow (context-optimized):**

```javascript
// Step 1: Load only needed tools (ONE ToolSearch call)
ToolSearch({ query: "+ruflo swarm agent task" })

// Step 2: Init swarm (small response)
mcp__ruflo__swarm_init({ topology: "star", maxAgents: 5 })

// Step 3: Spawn agents + create tasks IN ONE MESSAGE
mcp__ruflo__agent_spawn({ agentType: "coder", agentId: "agent-1" })
mcp__ruflo__task_create({ type: "implement", description: "...", assignToAgent: "agent-1" })

// Step 4: Launch ACTUAL work via Task tool (separate context)
Task({ subagent_type: "general-purpose", run_in_background: true, prompt: "..." })

// Step 5: Collect results (blocking)
TaskOutput({ task_id: "...", block: true })
```

### 2. Ruflo Coordination (Task Orchestration)

**MCP Prefix:** `mcp__ruflo__coordination_*`

**⚠️ TWO SEPARATE agent systems — DO NOT MIX:**

| System    | Agent Creation     | Execution                    | Pool       |
| --------- | ------------------ | ---------------------------- | ---------- |
| **Swarm** | `agent_spawn`      | `coordination_orchestrate`   | Swarm pool |
| **DAA**   | `daa_agent_create` | `daa_workflow_execute`       | DAA pool   |

**Essential Tools:**

| Tool                      | Full Name                               | Purpose                     |
| ------------------------- | --------------------------------------- | --------------------------- |
| `swarm_init`              | `mcp__ruflo__swarm_init`                | Initialize                  |
| `agent_spawn`             | `mcp__ruflo__agent_spawn`               | Create swarm agent          |
| `coordination_orchestrate`| `mcp__ruflo__coordination_orchestrate`  | Execute across agents       |
| `task_status`             | `mcp__ruflo__task_status`               | Check progress              |
| `task_summary`            | `mcp__ruflo__task_summary`              | Get results                 |

**Minimal Pattern (Task Orchestration):**

```javascript
ToolSearch({ query: "+ruflo agent coordination" })
mcp__ruflo__swarm_init({ topology: "mesh", strategy: "balanced", maxAgents: 5 })
mcp__ruflo__agent_spawn({ type: "researcher", name: "r1" })
mcp__ruflo__agent_spawn({ type: "coder", name: "c1" })
mcp__ruflo__coordination_orchestrate({ task: "...", strategy: "parallel", priority: "high" })
// Then use Task tool for actual file work
```

**⚠️ DAA REALITY: DAA is a metadata/tracking layer, NOT an execution engine.**

`daa_workflow_execute` flips a status flag and returns empty arrays. All actual work is done by the Agent tool. **Only use DAA for multi-iteration workflows** where you need structured cross-iteration state. For single-pass parallel work, use Ruflo swarm orchestration.

**Minimal Pattern (DAA Iterative Tracking):**

```javascript
ToolSearch({ query: "+ruflo daa" })
mcp__ruflo__daa_agent_create({ id: "daa-1", cognitivePattern: "adaptive", enableMemory: true })
// Register workflow for tracking (NOT execution)
mcp__ruflo__daa_workflow_create({ id: "wf-1", name: "Analysis", strategy: "adaptive" })
// DO NOT expect daa_workflow_execute to produce results — launch Agent tools instead
// Use cognitive pattern to SHAPE the Agent tool prompt
Agent({ prompt: "You are daa-1 (cognitive: adaptive). Adjust approach based on findings..." })
// After Agent completes, store findings for next iteration:
mcp__ruflo__daa_knowledge_share({ sourceAgentId: "daa-1", ..., knowledgeContent: { findings: "ACTUAL results" } })
```

### 3. Hive-Mind (Consensus/Collective Intelligence)

**MCP Prefix:** `mcp__ruflo__hive-mind_`

**Essential Tools:**

| Tool                  | Full Name                           |
| --------------------- | ----------------------------------- |
| `hive-mind_init`      | `mcp__ruflo__hive-mind_init`        |
| `hive-mind_spawn`     | `mcp__ruflo__hive-mind_spawn`       |
| `hive-mind_consensus` | `mcp__ruflo__hive-mind_consensus`   |
| `hive-mind_memory`    | `mcp__ruflo__hive-mind_memory`      |
| `hive-mind_status`    | `mcp__ruflo__hive-mind_status`      |

**⛔ CRITICAL: Agent subagents MUST be explicitly instructed to use hive-mind tools.**
Without explicit `ToolSearch` + `hive-mind_memory` instructions in agent prompts, agents run as plain parallel workers — not hive-mind participants. See `WF_SWARM_HIVE_MIND` Phase 4 for the required agent prompt template.

---

## When to Use Each Subsystem

| Scenario               | Subsystem            | Topology     |
| ---------------------- | -------------------- | ------------ |
| Quick parallel tasks   | Ruflo swarm          | star         |
| Multi-file analysis    | Ruflo swarm          | mesh         |
| Code refactoring       | Ruflo swarm          | hierarchical |
| Multi-iteration tracking | Ruflo DAA          | adaptive     |
| Simple parallel tasks  | Ruflo coordination   | mesh         |
| Consensus decisions    | Ruflo Hive-Mind      | mesh         |

---

## Agent Types

**Swarm:** `researcher`, `analyst`, `coder`, `optimizer`, `coordinator`
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
7. **Use `SendMessage`** — it does NOT exist. The Agent tool output suggests it, but the tool is not available. Agents are fire-and-forget.

---

## ⛔ Agent Communication Constraints (Verified 2026-04-27)

**`SendMessage` does NOT exist.** The Agent tool's completion output says "Use SendMessage with to: 'agentId' to continue this agent" — this is misleading. The tool is not available.

**What this means:**

| Need | Solution | Limitation |
|------|----------|------------|
| Send instructions to agent | Include ALL instructions in the initial Agent prompt | Cannot update mid-execution |
| Share data between agents | Use `hive-mind_memory set/get` | Agent must be coded to poll shared memory |
| Refine scope after launch | Update hive-mind memory key BEFORE agent reads it | Race condition — agent may have already read the old value |
| Continue a completed agent | Launch a NEW Agent with the completed agent's output | No context preservation — must re-provide context |

**Rules:**
- All agent instructions must be **complete and self-contained** in the initial prompt
- For scope refinements, update hive-mind shared memory keys and hope the agent hasn't read them yet
- For cross-referencing, agents should read hive-mind memory at the END of their analysis (Step 5), not just at the start
- Treat agents as **fire-and-forget workers** — plan accordingly

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
| Pretty-printed JSON responses          | 2x response size                       | Can't control this — keep calls minimal |
| **SendMessage does not exist**         | Cannot communicate with running agents | All instructions in initial prompt; use hive-mind shared memory for data exchange |
| Agent tool claims SendMessage works    | Misleading output on agent completion  | Ignore the suggestion — tool is not available |
