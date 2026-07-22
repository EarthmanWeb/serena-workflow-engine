---
name: RUFLO
description: MCP swarm coordination reference — Ruflo/Hive-Mind/DAA prefixes, context-budget rules, orchestration patterns.
metadata:
  type: reference
---

# RUFLO — MCP Swarm Coordination

## Verified MCP Tool Prefixes (2026-05-06)

| System | Prefix |
| ------ | ------ |
| Ruflo (unified) | `mcp__ruflo__` |
| Hive-Mind (subsystem) | `mcp__ruflo__hive-mind_` |
| DAA (subsystem) | `mcp__ruflo__daa_*` |
| Coordination (subsystem) | `mcp__ruflo__coordination_*` |

- Load MCP tools via `ToolSearch` before calling. NEVER exceed 3-5 tools per session.
- Use prefixes from THIS doc only. Old-doc prefixes caused 100% failures.

## Context Budget — Apply First

The coordinator shares your context window. Every MCP call, memory read, and tool schema adds tokens. Swarm sessions fail from context overload.

Set BEFORE starting claude:

```bash
export MAX_MCP_OUTPUT_TOKENS=5000    # cap MCP responses (default 25K)
export ENABLE_TOOL_SEARCH=auto:5     # defer tools at 5% context (default 10%)
```

- Load MCP tools with ONE ToolSearch call; 3-5 tools max.
- NEVER pass `verbose: true`, `detailed: true`, or `includeMetrics: true`.
- NEVER call `memory_stats` (scans 100K entries).
- Set `memory_list` to `limit: 5`.
- Delegate ALL file work to Task agents (separate context).
- Load ALL needed memories BEFORE starting swarm, NEVER during.
- Batch init + spawn + task into ONE message.
- Skip `swarm_status` / `task_status` unless needed (~1-2K tokens each).

## MCP vs Task Tool Division

| MCP (Coordination Layer) | Task Tool (Execution Layer) |
| ------------------------ | --------------------------- |
| `swarm_init` — topology setup | Spawn agents for file work |
| `agent_spawn` — register agent types | Read/Write/Edit files |
| `task_create` — register tasks | Run tests, build commands |
| `memory_store` — state persistence | Code generation |

- MCP coordinates strategy. Task tool executes work. TaskOutput collects results.
- NEVER do file work in the coordinator.

## Ruflo Swarm Orchestration

Prefix `mcp__ruflo__`. Load with `ToolSearch({ query: "+ruflo swarm agent task" })`.

Sequence: one ToolSearch call → `swarm_init` + `agent_spawn` + `task_create` in ONE message → launch work via Task tool (background, separate context) → collect with `TaskOutput`.

| Tool | Purpose |
| ---- | ------- |
| `swarm_init` | Initialize swarm with topology |
| `swarm_status` | Check health (NO verbose flag) |
| `agent_spawn` | Create coordination agent |
| `task_create` | Register task with agent assignment |
| `task_status` | Check progress |
| `memory_store` | Persist state |
| `memory_retrieve` | Recall state |

## Ruflo Coordination Tools

Prefix `mcp__ruflo__coordination_*`. Load with `ToolSearch({ query: "+ruflo agent coordination" })`.

Sequence: `swarm_init` → `agent_spawn` (per agent) → `coordination_orchestrate`.

- Agent types: `researcher`, `analyst`, `coder`, `optimizer`, `coordinator`.
- NEVER mix swarm-agent and DAA-agent pools.

## Ruflo DAA (Iterative Coordination & Tracking)

Prefix `mcp__ruflo__daa_*`. Load with `ToolSearch({ query: "+ruflo daa" })`.

- DAA is a metadata/tracking layer, NOT an execution engine. `daa_workflow_execute` returns empty arrays; all metrics are simulated.
- Use DAA ONLY for multi-iteration workflows where cross-iteration state tracking adds value. For single-pass parallel work use Ruflo swarm orchestration.

How DAA works:

1. `daa_agent_create` → creates JSON record (cognitive pattern label, capabilities). No process spawned.
2. `daa_workflow_create` → registers workflow steps as metadata. No execution logic.
3. Agent tool → does ALL actual work in separate context. Inject cognitive pattern into the prompt.
4. `daa_knowledge_share` → stores Agent findings in JSON registry for next iteration.
5. Repeat: read stored knowledge → shape next Agent prompt → launch next round.

Rules:

- Skip `daa_workflow_execute` (returns empty arrays). Launch Agent tools directly.
- Inject the cognitive pattern into the Agent prompt to influence behavior.
- After an Agent completes, store ACTUAL findings via `daa_knowledge_share`.
- Skip `daa_learning_status` and `daa_performance_metrics` (return simulated/random data).
- Cognitive patterns: `adaptive`, `critical`, `convergent`, `divergent`, `lateral`, `systems`.

## Hive-Mind (Collective Intelligence)

Prefix `mcp__ruflo__hive-mind_`. Load with `ToolSearch({ query: "+ruflo hive-mind" })`.

Coordinator sequence: `hive-mind_init` → `hive-mind_spawn` → `hive-mind_memory` (action `set` task context) → launch agents (background) → after agents complete read findings via `hive-mind_memory` (action `get`) → `hive-mind_consensus` (action `propose`).

Every agent prompt MUST include these steps — Agent subagents will NOT use hive-mind tools unless explicitly told to. Without this you have parallel agents, NOT a hive-mind:

1. `ToolSearch({ query: "select:mcp__ruflo__hive-mind_memory", max_results: 1 })` — load the tool.
2. `hive-mind_memory get` — read shared context stored by coordinator.
3. Do analysis work.
4. `hive-mind_memory set` — write findings back to shared memory.
5. (Optional) `hive-mind_memory get` — read other agents' findings for cross-referencing.

See `WF_SWARM_HIVE_MIND` for the full agent prompt template.

## Golden Rules

- Batch all related MCP calls into ONE message.
- Init swarm/hive BEFORE spawn.
- ToolSearch to load MCP tools BEFORE calling (ONE batch call).
- MCP = coordination, Task = execution. NEVER do file work in the coordinator.
- NEVER run CLI init. Use MCP tools only.
- Default to star topology (least coordination overhead).
- 3-5 tools max. Do NOT load tools you won't use.
- NEVER pass verbose flags.

## Subsystem Selection

| Scenario | Subsystem | Topology |
| -------- | --------- | -------- |
| Quick parallel tasks | Ruflo swarm | star |
| Parallel file analysis | Ruflo coordination | mesh |
| Coordinated refactoring | Ruflo swarm | hierarchical |
| Multi-iteration tracking | Ruflo DAA | adaptive |
| Consensus decisions | Ruflo Hive-Mind | mesh |

## Loading Tools

- Swarm: `ToolSearch({ query: "+ruflo swarm agent task" })`
- DAA: `ToolSearch({ query: "+ruflo daa" })`
- Hive-Mind: `ToolSearch({ query: "+ruflo hive-mind" })`
- One specific tool: `ToolSearch({ query: "select:mcp__ruflo__swarm_init" })`

## "Prompt is too long" Prevention

Hard context limit. Once hit, the session is permanently broken. Root cause: MCP tool responses (pretty-printed JSON, ~2x size) accumulate in the coordinator's context; after 10-15 MCP calls context overflows.

| Strategy | How | Impact |
| -------- | --- | ------ |
| Cap MCP output | `MAX_MCP_OUTPUT_TOKENS=5000` | No single response >5K tokens |
| Aggressive ToolSearch | `ENABLE_TOOL_SEARCH=auto:5` | Defers tool schemas until needed |
| Minimal MCP calls | Init+spawn+task in ONE message; skip status checks | -50% MCP call volume |
| Task agent delegation | ALL file reads/writes in Task agents | Offloads 80%+ of work tokens |
| No verbose flags | Never `verbose`/`detailed`/`includeMetrics` | -2x per response |
| Fire-and-forget | Use `TaskOutput` on Task agents; do NOT call `task_results` | Skips MCP result retrieval |

If hit:

1. Session is dead — start a new one.
2. Lower `MAX_MCP_OUTPUT_TOKENS` further (try 3000).
3. Combine init+spawn+task into a single message.

## Known Issues (2026-05-06)

| Issue | Mitigation |
| ----- | ---------- |
| Pretty-printed JSON doubles response size | `MAX_MCP_OUTPUT_TOKENS=5000` + minimal calls |
| `memory_stats` scans all entries | NEVER call it |
| Wrong prefixes in old docs caused 100% failures | Use prefixes from THIS doc |
| "Prompt is too long" kills session permanently | Prevention only — see section above |
