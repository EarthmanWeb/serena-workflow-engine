---
name: REF_RUFLO_MCP_TOOLS
description: Ruflo MCP tool reference — agent creation vs execution, swarm execution flows, tool categories, anti-patterns.
metadata:
  type: reference
---

# REF_RUFLO_MCP_TOOLS

Treat the Ruflo MCP server as source of truth for schemas. Query guidance tools for current schemas.

| Guidance Tool | Purpose | Args |
|---------------|---------|------|
| `mcp__ruflo__guidance_capabilities` | List all 16 capability areas with tool counts | none |
| `mcp__ruflo__guidance_recommend` | Get tool/workflow recommendations for a task | `{ task }` |
| `mcp__ruflo__guidance_workflow` | Get workflow steps for a named workflow type | `{ type }` — one of: bugfix, feature, refactor, testing, security, performance, memory, github-pr, release, swarm, learning, wasm, automation, setup |
| `mcp__ruflo__guidance_quickref` | Quick command reference for a domain | `{ domain }` — one of: getting-started, daily-dev, swarm-ops, memory-ops, github-ops, diagnostics |
| `mcp__ruflo__guidance_discover` | Discover agents and skills for an area | `{ area }` |

## Agent Creation vs Execution

| Tool | Creates | Can Execute? | Use When |
|------|---------|--------------|----------|
| `agent_spawn` | Ruflo-tracked agent with model assignment, cost tracking, swarm coordination | YES — pair with `agent_execute` | Ruflo must RUN work |
| `daa_agent_create` | JSON metadata record (cognitive pattern label, capabilities list) | NO — bookkeeping only | Cross-iteration DAA tracking needed |

- NEVER expect `daa_agent_create` agents to execute. They are metadata ONLY.

### Execution Paths

| Path | Flow | File Access? | Use When |
|------|------|--------------|----------|
| Ruflo-native | `agent_spawn` → `agent_execute` | NO (Anthropic API call) | Reasoning, planning, spec writing, comparisons |
| Hybrid | `agent_spawn` (tracking) + Claude Code `Agent` tool | YES (full tool access) | Codebase analysis, file reads, grep, Serena |

### `agent_execute`

- Calls the Anthropic Messages API with the agent's configured model.
- Requires `ANTHROPIC_API_KEY` in env.
- Params: `agentId` (required), `prompt` (required), `systemPrompt`, `maxTokens` (default 1024), `temperature` (default 0.7).
- Returns the LLM response directly — no TaskOutput needed.
- NEVER use for file reads, tool runs, or file system access — it has none.

### `agent_spawn`

- Creates a Ruflo-tracked agent with cost attribution + memory persistence + swarm coordination.
- Params: `agentType` (required), `agentId`, `model` (haiku/sonnet/opus/inherit), `task`, `domain`, `config`.
- Call `hooks_route` to pick the model before spawning.
- For one-shot subtasks with no learning loop, use the native Claude Code `Agent` tool instead.

## Swarm Execution Flows

### Flow A: Ruflo-Native (reasoning/planning — no file access)

- `swarm_init` + all `agent_spawn` + `task_create` in ONE message.
- All `agent_execute` calls in ONE message (parallel).
- Results return directly from `agent_execute` responses.

```javascript
mcp__ruflo__swarm_init({ topology: "star", maxAgents: 5 })
mcp__ruflo__agent_spawn({ agentType: "researcher", agentId: "r1", model: "sonnet" })
mcp__ruflo__agent_spawn({ agentType: "researcher", agentId: "r2", model: "sonnet" })
mcp__ruflo__task_create({ type: "research", description: "...", assignTo: ["r1", "r2"] })
mcp__ruflo__agent_execute({ agentId: "r1", prompt: "...", maxTokens: 4096 })
mcp__ruflo__agent_execute({ agentId: "r2", prompt: "...", maxTokens: 4096 })
```

### Flow B: Hybrid (codebase analysis — needs file access)

- Ruflo agents show `status: "idle"` in `agent_list` in hybrid mode. This is EXPECTED — the Ruflo agent is tracking-only; the Claude Code `Agent` tool executes. State this to the user BEFORE launching.
- For single-pass parallel work with no cross-iteration state, use Flow D — skip Ruflo. See `WF_SWARM_ORCHESTRATE` Step 0.
- Spawn ONLY when Ruflo adds value.
- Launch all `Agent` tools in ONE message.
- Every `Agent` prompt MUST include: `"You are a swarm agent. BYPASS WF_INIT entirely. Do NOT follow CLAUDE.md workflow."`
- Store results to `memory_store` for cross-agent sharing.

```javascript
mcp__ruflo__swarm_init({ topology: "star", maxAgents: 5 })
mcp__ruflo__agent_spawn({ agentType: "researcher", agentId: "r1", model: "sonnet" })
Agent({ description: "R1 task", run_in_background: true,
  prompt: "You are a swarm agent. BYPASS WF_INIT entirely. Do NOT follow CLAUDE.md workflow. Follow ONLY these instructions: [task]..." })
mcp__ruflo__memory_store({ key: "r1-findings", value: { ... } })
```

### Flow D: Direct Parallel (no Ruflo — single-pass file work)

- Use for single-pass parallel tasks needing file access, no cross-iteration state, no consensus.
- No `swarm_init`, no `agent_spawn`, no `task_create` — launch `Agent` tools directly.
- Every `Agent` prompt MUST include the swarm bypass line.
- Results arrive via background task notifications.

```javascript
Agent({ description: "Task 1", run_in_background: true, model: "sonnet",
  prompt: "You are a swarm agent. BYPASS WF_INIT entirely. [task]..." })
Agent({ description: "Task 2", run_in_background: true, model: "sonnet",
  prompt: "You are a swarm agent. BYPASS WF_INIT entirely. [task]..." })
```

### Flow C: DAA Multi-Iteration (tracking across rounds)

- Create DAA metadata agents (`daa_agent_create`, `daa_workflow_create`) for tracking.
- ALSO spawn executable agents (`agent_spawn`).
- Execute via `agent_execute` (native or hybrid).
- Store findings with `daa_knowledge_share` for the next round.
- Round 2+: read shared knowledge, shape new prompts, execute again.

```javascript
mcp__ruflo__daa_agent_create({ id: "daa-r1", cognitivePattern: "systems", enableMemory: true })
mcp__ruflo__daa_workflow_create({ id: "wf-1", name: "Round 1", strategy: "parallel" })
mcp__ruflo__agent_spawn({ agentType: "researcher", agentId: "r1", model: "sonnet" })
mcp__ruflo__agent_execute({ agentId: "r1", prompt: "...", maxTokens: 4096 })
mcp__ruflo__daa_knowledge_share({ sourceAgentId: "daa-r1", targetAgentIds: ["daa-r2"], knowledgeDomain: "research", knowledgeContent: { findings: "actual results" } })
```

## Tool Categories

| Category | Key Tools | ToolSearch Query |
|----------|-----------|------------------|
| Swarm lifecycle | `swarm_init`, `swarm_status`, `swarm_health`, `swarm_shutdown` | `+ruflo swarm` |
| Agent lifecycle | `agent_spawn`, `agent_execute`, `agent_status`, `agent_list`, `agent_update`, `agent_terminate` | `+ruflo agent` |
| Task management | `task_create`, `task_status`, `task_list`, `task_update`, `task_complete`, `task_summary` | `+ruflo task` |
| DAA tracking | `daa_agent_create`, `daa_workflow_create`, `daa_knowledge_share`, `daa_agent_adapt` | `+ruflo daa` |
| Coordination | `coordination_orchestrate`, `coordination_topology`, `coordination_sync`, `coordination_node` | `+ruflo coordination` |
| Hive-Mind | `hive-mind_init`, `hive-mind_spawn`, `hive-mind_consensus`, `hive-mind_memory`, `hive-mind_status` | `+ruflo hive-mind` |
| Memory | `memory_store`, `memory_retrieve`, `memory_search`, `memory_list`, `memory_delete` | `+ruflo memory` |

## Execution Path Rules

- When running a Ruflo swarm, use `agent_spawn` → `agent_execute` as the primary execution path.
- `agent_spawn` + `agent_execute` — Ruflo-tracked, cost-attributed, swarm-coordinated. Default to this.
- `agent_spawn` + Claude Code `Agent` tool — ONLY when file system access is needed (Glob/Grep/Read).
- NEVER use Claude Code `Agent` tool alone (without `agent_spawn`) — bypasses Ruflo, no tracking, no coordination.
- NEVER use `daa_agent_create` alone — metadata only, executes nothing.

## Anti-Patterns (Verified Failures)

| Anti-Pattern | What Happens | Correct Approach |
|--------------|--------------|------------------|
| Create `daa_agent_create` then expect execution | Agent is metadata only, nothing runs | `agent_spawn` → `agent_execute` |
| Call `daa_workflow_execute` expecting results | Returns empty arrays, flips a status flag | `agent_execute` |
| Claude Code `Agent` tool without `agent_spawn` | Work runs but no Ruflo tracking, no cost attribution | `agent_spawn` first, then `agent_execute` (or Agent tool only if file access needed) |
| Default to Claude Code `Agent` tool for everything | Bypasses Ruflo swarm entirely | `agent_execute` — it IS the Ruflo execution path |
| Call `agent_execute` for file-reading tasks | API-only call, no file system access | Claude Code `Agent` tool (hybrid) + `agent_spawn` for tracking |
| Load 10+ tools via ToolSearch | Context overload, session fails | Load max 3-5 tools; use guidance tools for lookup |
| Spawn N agents, execute only 1 | N-1 agents idle, swarm serial not parallel | Execute ALL agents in ONE message — count spawns, count executions, they MUST match |
| Spawn Ruflo agents → use Agent tool without `agent_execute` | Ruflo agents never run, Agent tool does untracked work | `agent_execute` for each spawned agent; Agent tool only when file access needed (hybrid) |
| Agent tool prompt missing swarm bypass | Claude Code Agent re-runs WF_INIT, wastes context | ALWAYS include `"You are a swarm agent. BYPASS WF_INIT entirely."` in Agent tool prompts |

### Verified Failure: 2026-05-09 — Ruflo Agent Abandonment

- Coordinator spawned 5 DAA agents + 5 execution agents + 5 tasks, then launched a single Claude Code `Agent` tool that ignored all 5 spawned Ruflo agents (never executed), re-ran WF_INIT in the Agent's context (wasted entire context), and got killed before accomplishing anything.
- Root cause: no execution-path gate forced use of `agent_execute` on spawned agents; the coordinator defaulted to the `Agent` tool out of habit.
- Fix: EXECUTION PATH GATE added to `WF_SWARM_ORCHESTRATE`, `WF_SWARM_RUV`, `FEATURE_SWARM`. SWARM AGENT BYPASS gate added to `WF_INIT`, `WF_CLASSIFY`.
