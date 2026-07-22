---
name: FEATURE_SWARM
description: Multi-agent parallel processing — Claude Code Agent tool is default; Ruflo only for file-free reasoning/consensus/cross-round state.
metadata:
  type: feature
---

# FEATURE_SWARM — Multi-Agent Parallel Processing

- Key: SWARM
- Purpose: Parallel task orchestration via Claude Code's built-in `Agent` tool.

## Core Principle

- Claude Code's built-in `Agent` tool is the PRIMARY mechanism for ALL parallel work involving file access.
- Use external swarm frameworks (Ruflo, DAA, Hive-Mind) ONLY for file-free cognitive tasks (reasoning, planning, consensus).
- If the agent touches files → use Claude Code `Agent` tool. NEVER route file-access work through Ruflo.

| Task type | Tool |
| --------- | ---- |
| File reads, edits, grep, glob | Claude Code `Agent` tool |
| Research across codebase | Claude Code `Agent` (Explore subagent) |
| Multi-file implementation | Claude Code `Agent` (general-purpose) |
| Reasoning/planning without files | Ruflo `agent_execute` |
| Multi-iteration tracking | Ruflo DAA `knowledge_share` |
| Consensus decisions | Ruflo Hive-Mind |

## Claude Code Agent Capabilities

- Launch multiple `Agent` tool calls in ONE message → run concurrently with separate context windows.
- Set `isolation: "worktree"` to give each agent its own git worktree when agents edit overlapping files.

### Subagent Types

| Type | Model | Tools | Use for |
| ---- | ----- | ----- | ------- |
| Explore | Haiku | Read-only (Glob, Grep, Read) | Fast codebase search, file discovery |
| Plan | Inherits parent | Read-only | Architecture planning, design |
| general-purpose | Inherits parent | All tools | Complex multi-step tasks |

### Model Selection

| Model | Use for |
| ----- | ------- |
| haiku | Read-only exploration, simple searches |
| sonnet | Implementation, code review |
| opus | Complex architecture, multi-step reasoning |

### Background vs Foreground

- Foreground (default): results needed before next step; permission prompts visible.
- Background (`run_in_background: true`): fire-and-forget; auto-denies permission prompts; notification on completion; auto-gets a worktree for file isolation.

### Tooling

- `claude agents` — terminal dashboard for dispatching/monitoring background sessions.
- `/batch` — repo-wide mechanical changes (rename, migration, pattern replacement); splits into 5–30 worktree-isolated subagents, each opening a PR.

## Mandatory Reading (only when Ruflo needed — see decision gate)

| Step | Memory | Purpose |
| ---- | ------ | ------- |
| 1 | `WF_SWARM_ORCHESTRATE` | Primary swarm workflow |
| 2 | `REF_SWARM_PATTERNS` | MCP tool patterns |

## Verified MCP Tool Prefix (2026-05-06)

| System | MCP prefix |
| ------ | ---------- |
| Ruflo (unified) | `mcp__ruflo__` |
| Hive-Mind (subsystem) | `mcp__ruflo__hive-mind_` |
| DAA (subsystem) | `mcp__ruflo__daa_*` |

## Context Budget — Prevent Overload

Prior swarm sessions failed from context overload (loading 12+ memory files ~30-50K tokens, loading too many MCP tools, verbose flags, coordinator doing file reads).

- Delegate ALL file work to Claude Code `Agent` tools (separate context windows).
- Load MAX 3–5 MCP tools per session (if using Ruflo).
- NEVER use verbose/detailed flags on MCP responses.
- Load memories BEFORE agent launch, NEVER during.
- Batch agent launches into ONE message.
- Skip status checks unless actually needed.

## Post-Load Directive

> 🐝 SWARM DETECTED — Assess whether Ruflo is needed (decision gate below). Default to Claude Code `Agent` tool for all file-access work. After completing WF_CLASSIFY feature loading, go to **WF_SWARM_ORCHESTRATE**.

## Trigger Conditions

Route to SWARM when ANY apply:

| Condition | Threshold |
| --------- | --------- |
| File scale | 6+ files affected |
| Layer scale | 3+ architectural layers |
| Parallel work | Independent subtasks can run concurrently |
| Multi-domain | Coordination across domains required |
| User request | Explicit swarm/parallel agents request |

Keyword triggers: `swarm`, `parallel agents`, `multi-agent`, `hive-mind`, `ruflo swarm`, `DAA`, `orchestrate agents`.

## Decision Gate: Do You Need Ruflo?

Default answer is NO. Ruflo adds ~10–15 MCP calls of overhead.

### Use Ruflo when

| Scenario | Why |
| -------- | --- |
| Reasoning-only parallel tasks (no file access) | `agent_execute` calls Anthropic API directly |
| Multi-iteration workflows (Round 1 → Round 2) | `daa_knowledge_share` stores cross-round state |
| Consensus decisions | Hive-Mind has no built-in alternative |
| User explicitly requests Ruflo/DAA | Respect request, explain trade-offs |

### Skip Ruflo when

| Scenario | Why |
| -------- | --- |
| Any task needing file access | `agent_execute` can't read files — use Claude Code `Agent` tool |
| Single-pass parallel work | Claude Code `Agent` tools already run in parallel |
| Simple fan-out/fan-in | Launch N `Agent` tools in one message |
| No cross-iteration state needed | DAA adds ~10 MCP calls for zero benefit |

When Ruflo isn't needed: launch Claude Code `Agent` tools in parallel directly. NEVER call `swarm_init` or `agent_spawn`.

## Quick Start — Claude Code Agent Tool (DEFAULT)

- Launch ALL agents in ONE message (parallel execution).
- EVERY agent prompt MUST include the swarm bypass instruction: "You are a swarm agent. BYPASS WF_INIT entirely. Do NOT read CLAUDE.md workflow. Follow ONLY these instructions: [task]".
- Use `isolation: "worktree"` when agents edit overlapping files.
- Use `model: "haiku"` for read-only exploration, `model: "sonnet"` for implementation.

## Quick Start — Ruflo-Native (Reasoning Only, NO File Access)

Use ONLY when agents don't need file access:

```javascript
mcp__ruflo__swarm_init({ topology: "star", maxAgents: 5 })
mcp__ruflo__agent_spawn({ agentType: "researcher", agentId: "r1", model: "sonnet" })
mcp__ruflo__agent_execute({ agentId: "r1", prompt: "...", maxTokens: 4096 })
```

## Anti-Patterns

| Anti-pattern | Fix |
| ------------ | --- |
| Using Ruflo for file-access tasks | Skip Ruflo, use `Agent` tool directly |
| Spawning Ruflo agents then ignoring them | Either `agent_execute` or don't spawn |
| Launching only 1 of N agents | Execute ALL agents in ONE message |
| Agent re-runs WF_INIT | Include swarm bypass in EVERY prompt |
| Loading Ruflo for simple parallel work | Launch `Agent` tools directly |

## Related Memories

| Memory | Content |
| ------ | ------- |
| `WF_SWARM_ORCHESTRATE` | Swarm workflow (when Ruflo needed) |
| `REF_SWARM_PATTERNS` | MCP tool reference + patterns |
