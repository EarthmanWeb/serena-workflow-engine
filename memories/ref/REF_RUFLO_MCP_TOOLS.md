# REF_RUFLO_MCP_TOOLS - Ruflo MCP Tool Reference

**Source of truth:** The Ruflo MCP server itself. Use these guidance tools for up-to-date schemas:

| Guidance Tool | Purpose | Example |
|---------------|---------|---------|
| `mcp__ruflo__guidance_capabilities` | List all 16 capability areas with tool counts | No params needed |
| `mcp__ruflo__guidance_recommend` | Get tool/workflow recommendations for a task | `{ task: "parallel research agents" }` |
| `mcp__ruflo__guidance_workflow` | Get workflow steps for a named workflow type | `{ type: "swarm" }` — available: bugfix, feature, refactor, testing, security, performance, memory, github-pr, release, swarm, learning, wasm, automation, setup |
| `mcp__ruflo__guidance_quickref` | Quick command reference for a domain | `{ domain: "swarm-ops" }` — available: getting-started, daily-dev, swarm-ops, memory-ops, github-ops, diagnostics |
| `mcp__ruflo__guidance_discover` | Discover agents and skills for an area | `{ area: "swarm-orchestration" }` |

---

## ⚠️ CRITICAL: Agent Creation vs Execution

### Two Agent Creation Tools — Different Purposes

| Tool | What It Creates | Can Execute? | Use When |
|------|----------------|--------------|----------|
| `agent_spawn` | Ruflo-tracked agent with model assignment, cost tracking, swarm coordination | ✅ YES — pair with `agent_execute` | You want Ruflo to RUN work |
| `daa_agent_create` | JSON metadata record (cognitive pattern label, capabilities list) | ❌ NO — bookkeeping only | You need cross-iteration DAA tracking |

**⛔ `daa_agent_create` agents CANNOT execute. They are metadata ONLY.**

### Two Execution Paths

| Path | Flow | File Access? | Use When |
|------|------|--------------|----------|
| **Ruflo-native** | `agent_spawn` → `agent_execute` | ❌ No (Anthropic API call) | Reasoning, planning, spec writing, comparisons |
| **Hybrid** | `agent_spawn` (tracking) + Claude Code `Agent` tool | ✅ Yes (full tool access) | Codebase analysis, file reads, grep, Serena |

### `agent_execute` — Key Details

- Calls the Anthropic Messages API with the agent's configured model
- **Requires `ANTHROPIC_API_KEY` in env**
- Parameters: `agentId` (required), `prompt` (required), `systemPrompt`, `maxTokens` (default 1024), `temperature` (default 0.7)
- Returns the LLM response directly — no TaskOutput needed
- Cannot read files, run tools, or access the file system

### `agent_spawn` — Key Details

- Creates a Ruflo-tracked agent with cost attribution + memory persistence + swarm coordination
- Parameters: `agentType` (required), `agentId`, `model` (haiku/sonnet/opus/inherit), `task`, `domain`, `config`
- Use `hooks_route` to pick the right model before spawning
- For one-shot subtasks with no learning loop, native Claude Code `Agent` tool is fine instead

---

## Correct Swarm Execution Flows

### Flow A: Ruflo-Native (reasoning/planning — no file access needed)

```javascript
// 1. Init + spawn in ONE message
mcp__ruflo__swarm_init({ topology: "star", maxAgents: 5 })
mcp__ruflo__agent_spawn({ agentType: "researcher", agentId: "r1", model: "sonnet" })
mcp__ruflo__agent_spawn({ agentType: "researcher", agentId: "r2", model: "sonnet" })
mcp__ruflo__task_create({ type: "research", description: "...", assignTo: ["r1", "r2"] })

// 2. Execute ALL in ONE message (parallel)
mcp__ruflo__agent_execute({ agentId: "r1", prompt: "...", maxTokens: 4096 })
mcp__ruflo__agent_execute({ agentId: "r2", prompt: "...", maxTokens: 4096 })

// 3. Results come back directly from agent_execute responses
```

### Flow B: Hybrid (codebase analysis — needs file access)

```javascript
// 1. Init + spawn for tracking
mcp__ruflo__swarm_init({ topology: "star", maxAgents: 5 })
mcp__ruflo__agent_spawn({ agentType: "researcher", agentId: "r1", model: "sonnet" })

// 2. Launch Claude Code Agent tools (have file access via Glob/Grep/Read)
Agent({ description: "R1 task", run_in_background: true, prompt: "..." })

// 3. Store results to Ruflo memory for cross-agent sharing
mcp__ruflo__memory_store({ key: "r1-findings", value: { ... } })
```

### Flow C: DAA Multi-Iteration (tracking across rounds)

```javascript
// Round 1:
// 1. Create DAA metadata agents for tracking
mcp__ruflo__daa_agent_create({ id: "daa-r1", cognitivePattern: "systems", enableMemory: true })
mcp__ruflo__daa_workflow_create({ id: "wf-1", name: "Round 1", strategy: "parallel" })

// 2. ALSO spawn executable agents
mcp__ruflo__agent_spawn({ agentType: "researcher", agentId: "r1", model: "sonnet" })

// 3. Execute (native or hybrid)
mcp__ruflo__agent_execute({ agentId: "r1", prompt: "...", maxTokens: 4096 })

// 4. Store findings for next round
mcp__ruflo__daa_knowledge_share({ sourceAgentId: "daa-r1", targetAgentIds: ["daa-r2"], knowledgeDomain: "research", knowledgeContent: { findings: "actual results" } })

// Round 2: Read knowledge, shape new prompts, execute again
```

---

## Tool Categories Quick Reference

| Category | Key Tools | ToolSearch Query |
|----------|-----------|------------------|
| **Swarm lifecycle** | `swarm_init`, `swarm_status`, `swarm_health`, `swarm_shutdown` | `+ruflo swarm` |
| **Agent lifecycle** | `agent_spawn`, `agent_execute`, `agent_status`, `agent_list`, `agent_update`, `agent_terminate` | `+ruflo agent` |
| **Task management** | `task_create`, `task_status`, `task_list`, `task_update`, `task_complete`, `task_summary` | `+ruflo task` |
| **DAA tracking** | `daa_agent_create`, `daa_workflow_create`, `daa_knowledge_share`, `daa_agent_adapt` | `+ruflo daa` |
| **Coordination** | `coordination_orchestrate`, `coordination_topology`, `coordination_sync`, `coordination_node` | `+ruflo coordination` |
| **Hive-Mind** | `hive-mind_init`, `hive-mind_spawn`, `hive-mind_consensus`, `hive-mind_memory`, `hive-mind_status` | `+ruflo hive-mind` |
| **Memory** | `memory_store`, `memory_retrieve`, `memory_search`, `memory_list`, `memory_delete` | `+ruflo memory` |

---

## ⛔ CRITICAL RULE: Use Ruflo Agents, NOT Default Agent Tool

**When running a Ruflo swarm, ALWAYS use `agent_spawn` → `agent_execute` as the primary execution path.**

- ✅ `agent_spawn` + `agent_execute` — Ruflo-tracked, cost-attributed, swarm-coordinated
- ✅ `agent_spawn` + Claude Code `Agent` tool — ONLY when file system access is needed (Glob/Grep/Read)
- ❌ Claude Code `Agent` tool alone (without `agent_spawn`) — bypasses Ruflo entirely, no tracking, no coordination
- ❌ `daa_agent_create` alone — metadata only, cannot execute anything

**Default to `agent_execute`. Only fall back to Claude Code `Agent` when the task requires reading/writing files from the codebase.**

---

## Anti-Patterns (Verified Failures)

| Anti-Pattern | What Happens | Correct Approach |
|-------------|-------------|------------------|
| Create `daa_agent_create` then expect execution | Agent is metadata only, nothing runs | Use `agent_spawn` → `agent_execute` |
| Call `daa_workflow_execute` expecting results | Returns empty arrays, flips a status flag | Use `agent_execute` |
| Use Claude Code `Agent` tool without `agent_spawn` | Work runs but no Ruflo tracking, no cost attribution | `agent_spawn` first, then `agent_execute` (or Agent tool only if file access needed) |
| Default to Claude Code `Agent` tool for everything | Bypasses Ruflo swarm entirely | Use `agent_execute` — it IS the Ruflo execution path |
| Call `agent_execute` for file-reading tasks | API-only call, no file system access | Use Claude Code `Agent` tool (hybrid path) with `agent_spawn` for tracking |
| Load 10+ tools via ToolSearch | Context overload, session fails | Load max 3-5 tools, use guidance tools for lookup |
