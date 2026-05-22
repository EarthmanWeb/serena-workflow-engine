# REF_SWARM_PATTERNS - Swarm Coordination Reference

Multi-agent patterns for parallel processing and complex task coordination.

---

## ⚡ DEFAULT: Claude Code Built-In Agent Tool

**The Claude Code `Agent` tool is the PRIMARY mechanism for all parallel work involving file access.** Ruflo/DAA/Hive-Mind are secondary — use them ONLY for cognitive load tasks (reasoning, planning, consensus) where no file system access is needed.

### When to Use Claude Code Agent Tool (DEFAULT)

| Scenario | Method |
|----------|--------|
| Parallel file reads/edits | Multiple `Agent` calls in ONE message |
| Codebase exploration | `Agent` with `subagent_type: "Explore"` (Haiku, read-only) |
| Multi-file implementation | `Agent` with `isolation: "worktree"` per agent |
| Research across codebase | `Agent` with `run_in_background: true` |
| Repo-wide mechanical changes | `/batch` command (auto-worktree, auto-PR) |

### Quick Reference: Claude Code Agent Parameters

| Parameter | Values | Purpose |
|-----------|--------|---------|
| `model` | `"haiku"`, `"sonnet"`, `"opus"` | Cost/capability trade-off |
| `run_in_background` | `true/false` | Fire-and-forget vs blocking |
| `isolation` | `"worktree"` | Git worktree per agent (prevents edit conflicts) |
| `subagent_type` | `"Explore"`, `"Plan"`, `"general-purpose"` | Specialized behavior |

### Parallel Execution Pattern

```javascript
// All agents launch simultaneously — no orchestration framework needed
Agent({ description: "Task A", run_in_background: true, model: "sonnet",
  prompt: "You are a swarm agent. BYPASS WF_INIT. [task]..." })
Agent({ description: "Task B", run_in_background: true, model: "sonnet",
  prompt: "You are a swarm agent. BYPASS WF_INIT. [task]..." })
Agent({ description: "Task C", run_in_background: true, model: "haiku",
  subagent_type: "Explore", prompt: "You are a swarm agent. BYPASS WF_INIT. [task]..." })
// Results arrive via background task notifications
```

### When to Escalate to Ruflo

Only when ALL of these are true:
1. Agents do NOT need file system access (reasoning/planning only)
2. Task benefits from cross-iteration state tracking (DAA) OR consensus (Hive-Mind)
3. The overhead of ~10-15 MCP calls is justified by the coordination value

**If any agent needs file access → use Claude Code `Agent` tool directly. Ruflo's `agent_execute` cannot read files.**

---

## ⚠️ VERIFIED MCP TOOL PREFIX (2026-05-06)

**The ACTUAL MCP tool names visible in ToolSearch deferred list:**

| System | MCP Prefix | Example Tool |
| ------ | ---------- | ------------ |
| **Ruflo** (unified) | `mcp__ruflo__` | `mcp__ruflo__swarm_init` |
| **Hive-Mind** | `mcp__ruflo__` | `mcp__ruflo__hive-mind_init` |
| **DAA** | `mcp__ruflo__` | `mcp__ruflo__daa_agent_create` |
| **Coordination** | `mcp__ruflo__` | `mcp__ruflo__coordination_orchestrate` |

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

## ⚠️ TOOL SELECTION HIERARCHY

**Default to Claude Code `Agent` tool. Only use Ruflo when explicitly requested or when cognitive-only tasks need it.**

| User Says | Use | Why |
|-----------|-----|-----|
| "parallel agents" / "do this in parallel" / (no specific framework) | Claude Code `Agent` tool | Default — native file access, parallel execution |
| "launch swarm" / "ruflo swarm" | `mcp__ruflo__swarm_*` + `mcp__ruflo__agent_*` | User explicitly requested Ruflo |
| "use hive-mind" | `mcp__ruflo__hive-mind_*` | Consensus mechanism |
| "use DAA" / "DAA swarm" | `mcp__ruflo__daa_*` | Multi-iteration tracking |
| "coordinate tasks" | `mcp__ruflo__coordination_*` | Task orchestration |

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

| Tool            | Full Name                     | Purpose                                          |
| --------------- | ----------------------------- | ------------------------------------------------ |
| `swarm_init`    | `mcp__ruflo__swarm_init`      | Initialize swarm with topology                   |
| `swarm_status`  | `mcp__ruflo__swarm_status`    | Check swarm health (NO verbose flag)             |
| `agent_spawn`   | `mcp__ruflo__agent_spawn`     | Create Ruflo-tracked executable agent            |
| `agent_execute` | `mcp__ruflo__agent_execute`   | **Run prompt on spawned agent via Anthropic API** |
| `agent_list`    | `mcp__ruflo__agent_list`      | List active agents                               |
| `task_create`   | `mcp__ruflo__task_create`     | Register task in coordination layer              |
| `task_status`   | `mcp__ruflo__task_status`     | Check task progress                              |
| `memory_store`  | `mcp__ruflo__memory_store`    | Persist coordination state                       |

### ⚠️ CRITICAL: Two Agent Creation Tools — Different Purposes

| Tool | Creates | Executable? | Use When |
|------|---------|-------------|----------|
| `agent_spawn` | Ruflo-tracked agent with model, cost tracking, swarm coordination | ✅ YES — use with `agent_execute` | You want Ruflo to EXECUTE work |
| `daa_agent_create` | Metadata record with cognitive pattern label | ❌ NO — just bookkeeping | You only need cross-iteration tracking (DAA) |

**⛔ NEVER create `daa_agent_create` agents and then expect them to execute. They are metadata ONLY.**
**✅ ALWAYS use `agent_spawn` → `agent_execute` for Ruflo-native execution.**

### Three Execution Paths (Ordered by Preference)

| Path | Tools | File Access? | Use When |
|------|-------|-------------|----------|
| **Claude Code Agent (DEFAULT)** | Claude Code `Agent` tool directly | ✅ Yes (full tool access) | **Any task needing file access** — codebase analysis, file edits, grep, symbol lookup. No Ruflo needed. |
| **Ruflo-native** | `agent_spawn` → `agent_execute` | ❌ No (API call only) | Reasoning, planning, spec writing — cognitive tasks not needing project files |
| **Hybrid** | `agent_spawn` (tracking) + Claude Code `Agent` tool (execution) | ✅ Yes (full tool access) | When you need BOTH file access AND Ruflo's cross-iteration tracking |

**Minimal workflow — Ruflo-native (reasoning tasks):**

```javascript
// Step 1: Load tools
ToolSearch({ query: "+ruflo swarm agent" })
ToolSearch({ query: "select:mcp__ruflo__agent_execute" })

// Step 2: Init swarm
mcp__ruflo__swarm_init({ topology: "star", maxAgents: 5 })

// Step 3: Spawn ALL agents in ONE message
mcp__ruflo__agent_spawn({ agentType: "researcher", agentId: "r1", model: "sonnet", task: "Research task" })
mcp__ruflo__agent_spawn({ agentType: "researcher", agentId: "r2", model: "sonnet", task: "Research task" })

// Step 4: Execute on ALL agents in ONE message (parallel)
mcp__ruflo__agent_execute({ agentId: "r1", prompt: "Full task prompt...", maxTokens: 4096 })
mcp__ruflo__agent_execute({ agentId: "r2", prompt: "Full task prompt...", maxTokens: 4096 })

// Step 5: Results come back directly — no TaskOutput needed
```

**Minimal workflow — Hybrid (codebase file access tasks):**

```javascript
// Steps 1-3: Same as above (swarm_init + agent_spawn for tracking)

// Step 4: Launch Claude Code Agent tools for file work (separate context)
Agent({ description: "...", run_in_background: true, prompt: "..." })

// Step 5: Collect results
TaskOutput({ task_id: "...", block: true })

// Step 6: Store results to Ruflo for cross-agent tracking
mcp__ruflo__memory_store({ key: "r1-results", value: { findings: "..." } })
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

`daa_workflow_execute` flips a status flag and returns empty arrays. `daa_agent_create` creates metadata records ONLY — they cannot execute. **For actual execution, use `agent_spawn` + `agent_execute` (Ruflo-native) or `agent_spawn` + Claude Code `Agent` tool (hybrid for file access).**

**Only use DAA for multi-iteration workflows** where you need structured cross-iteration state. For single-pass parallel work, use Ruflo swarm orchestration.

**Minimal Pattern (DAA + Ruflo-native execution):**

```javascript
// Step 1: Load tools
ToolSearch({ query: "+ruflo daa agent" })
ToolSearch({ query: "select:mcp__ruflo__agent_execute,mcp__ruflo__daa_knowledge_share" })

// Step 2: Create DAA metadata agents for tracking + cognitive patterns
mcp__ruflo__daa_agent_create({ id: "daa-1", cognitivePattern: "adaptive", enableMemory: true })
mcp__ruflo__daa_workflow_create({ id: "wf-1", name: "Analysis", strategy: "adaptive" })

// Step 3: ALSO spawn executable Ruflo agents (these actually run)
mcp__ruflo__agent_spawn({ agentType: "researcher", agentId: "r1", model: "sonnet", task: "Analysis task" })

// Step 4: Execute via Ruflo (cognitive pattern from DAA shapes the prompt)
mcp__ruflo__agent_execute({ agentId: "r1", prompt: "You are r1 (cognitive: adaptive). Adjust approach based on findings...", maxTokens: 4096 })

// Step 5: Store findings for next iteration
mcp__ruflo__daa_knowledge_share({ sourceAgentId: "daa-1", targetAgentIds: ["daa-2"], knowledgeDomain: "analysis", knowledgeContent: { findings: "ACTUAL results from agent_execute" } })
```

**Minimal Pattern (DAA + Hybrid execution for file access):**

```javascript
// Steps 1-3: Same as above (daa_agent_create for tracking + agent_spawn for execution)

// Step 4: Use Claude Code Agent tool for file work (has Glob/Grep/Read access)
Agent({ description: "...", run_in_background: true, prompt: "You are r1 (cognitive: adaptive)..." })

// Step 5: Collect results, then store to DAA
mcp__ruflo__daa_knowledge_share({ sourceAgentId: "daa-1", targetAgentIds: ["daa-2"], knowledgeDomain: "analysis", knowledgeContent: { findings: "Results from Agent tool" } })
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
2. Spawn ALL agents (`agent_spawn`) + create ALL tasks in ONE message
3. Execute via `agent_execute` (Ruflo-native) OR Claude Code `Agent` tool (hybrid for file access)
4. **Use `agent_execute` for reasoning/planning tasks** — results come back directly, no Task/Agent overhead
5. **Use Claude Code `Agent` tool ONLY when file system access is needed** (Grep, Read, Glob, etc.)
6. Keep coordinator lean — only orchestrate
7. Batch all ToolSearch loads into ONE call

### DON'T:

1. Load tools you won't use
2. Use verbose/detailed flags on MCP calls
3. Call memory_stats (scans all entries)
4. Read memory docs during swarm execution (load them BEFORE)
5. Block on first agent before spawning others
6. Read files directly in coordinator — agents do that
7. **Use `SendMessage`** — it does NOT exist. The Agent tool output suggests it, but the tool is not available. Agents are fire-and-forget.

---

## ⛔ Agent Communication Constraints (Updated 2026-05-22)

**Standard mode: `SendMessage` does NOT exist.** The Agent tool's completion output suggests it, but the tool is not available in standard sessions.

**Experimental Agent Teams mode:** `SendMessage` IS available when `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is set. This enables peer-to-peer messaging between teammates. However, Agent Teams are experimental — no session resumption, high token cost (~3-7x), no file isolation.

**Standard mode constraints:**

| Need | Solution | Limitation |
|------|----------|------------|
| Send instructions to agent | Include ALL instructions in the initial Agent prompt | Cannot update mid-execution |
| Share data between agents | Use `hive-mind_memory set/get` | Agent must be coded to poll shared memory |
| Refine scope after launch | Update hive-mind memory key BEFORE agent reads it | Race condition — agent may have already read the old value |
| Continue a completed agent | Launch a NEW Agent with the completed agent's output | No context preservation — must re-provide context |

**Rules:**
- All agent instructions must be **complete and self-contained** in the initial prompt
- Treat agents as **fire-and-forget workers** — plan accordingly
- For file isolation between parallel agents, use `isolation: "worktree"` on the Agent tool

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

## ⛔ Mandatory Agent Prompt Template (Hybrid Path)

**When using Claude Code `Agent` tool for swarm agents, EVERY prompt MUST start with this block:**

```
You are a swarm agent spawned by a DAA coordinator.
BYPASS WF_INIT entirely. Do NOT follow CLAUDE.md workflow initialization.
Do NOT read WF_START, WF_CLASSIFY, or any WF_* memories.
Do NOT create a WM file.
Follow ONLY the task instructions below.
```

**Without this, Claude Code Agents will re-run the full workflow init sequence (WF_INIT → CLAUDE_OBLIGATIONS → WF_START → WF_CLASSIFY), consuming their entire context window on workflow overhead instead of their assigned task.**

---

## Known Issues

| Issue                                  | Impact                                 | Mitigation                              |
| -------------------------------------- | -------------------------------------- | --------------------------------------- |
| Pretty-printed JSON responses          | 2x response size                       | Can't control this — keep calls minimal |
| **SendMessage does not exist**         | Cannot communicate with running agents | All instructions in initial prompt; use hive-mind shared memory for data exchange |
| Agent tool claims SendMessage works    | Misleading output on agent completion  | Ignore the suggestion — tool is not available |
| **Spawned agents re-run WF_INIT**      | Agent wastes full context on workflow init | Include swarm bypass instruction in EVERY Agent tool prompt (see template above) |
| **Coordinator spawns N agents, executes 1** | N-1 agents idle, swarm is serial | Execute ALL agents in ONE message — match spawn count to execution count |
| **Coordinator uses Agent tool ignoring spawned Ruflo agents** | Ruflo agents never execute, no tracking | Use `agent_execute` on spawned agents. Only use Agent tool for hybrid (file access) path |
