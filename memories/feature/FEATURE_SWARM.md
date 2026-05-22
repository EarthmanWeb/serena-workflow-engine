# FEATURE_SWARM - Multi-Agent Parallel Processing

## Overview

| Property    | Value                                                           |
| ----------- | --------------------------------------------------------------- |
| **Key**     | SWARM                                                           |
| **Type**    | Workflow Routing Feature                                        |
| **Purpose** | Parallel task orchestration via Claude Code's built-in agents   |

---

## ⚡ CORE PRINCIPLE: Claude Code Agent Tool Is the Default

**Claude Code's built-in `Agent` tool is the PRIMARY mechanism for all parallel work involving file access.** External swarm frameworks (Ruflo, DAA, Hive-Mind) are ONLY for cognitive load tasks — reasoning, planning, consensus — where no file system access is needed.

| Task Type | Tool | Why |
|-----------|------|-----|
| **File reads, edits, grep, glob** | Claude Code `Agent` tool | Native file access, worktree isolation, parallel execution |
| **Research across codebase** | Claude Code `Agent` (Explore subagent) | Read-only, fast, Haiku model |
| **Multi-file implementation** | Claude Code `Agent` (general-purpose) | Full tool access, worktree isolation |
| **Reasoning/planning without files** | Ruflo `agent_execute` | API-only, no file access needed |
| **Multi-iteration tracking** | Ruflo DAA `knowledge_share` | Cross-round state persistence |
| **Consensus decisions** | Ruflo Hive-Mind | No built-in alternative |

**Rule: If the agent needs to touch files → use Claude Code `Agent` tool. Period.**

---

## ⚡ Claude Code Built-In Agent Capabilities

### Parallel Execution

Launch multiple `Agent` tool calls in a **single message** — they run concurrently with separate context windows.

```javascript
// All three launch in parallel — no orchestration framework needed
Agent({ description: "Analyze auth module", run_in_background: true, model: "sonnet",
  prompt: "You are a swarm agent. BYPASS WF_INIT. [task]..." })
Agent({ description: "Analyze API layer", run_in_background: true, model: "sonnet",
  prompt: "You are a swarm agent. BYPASS WF_INIT. [task]..." })
Agent({ description: "Analyze database layer", run_in_background: true, model: "sonnet",
  prompt: "You are a swarm agent. BYPASS WF_INIT. [task]..." })
```

### Subagent Types

| Type | Model | Tools | Best For |
|------|-------|-------|----------|
| **Explore** | Haiku | Read-only (Glob, Grep, Read) | Fast codebase search, file discovery |
| **Plan** | Inherits parent | Read-only | Architecture planning, design |
| **general-purpose** | Inherits parent | All tools | Complex multi-step tasks |

### File Isolation with Worktrees

Set `isolation: "worktree"` to give each agent its own git worktree — prevents parallel edit conflicts.

```javascript
Agent({ description: "Refactor module A", isolation: "worktree", model: "sonnet",
  prompt: "..." })
```

### Model Selection

| Model | Use For | Cost |
|-------|---------|------|
| **haiku** | Exploration, simple searches | Lowest |
| **sonnet** | Implementation, code review | Balanced |
| **opus** | Complex architecture, multi-step reasoning | Highest |

### Background vs Foreground

- **Foreground** (default): Results needed before next step. Permission prompts visible.
- **Background** (`run_in_background: true`): Fire-and-forget. Auto-denies permission prompts. Notification on completion.

### Agent View Dashboard

`claude agents` — terminal dashboard for dispatching and monitoring multiple background sessions. Every background session auto-gets a worktree for file isolation.

### /batch Command

For repo-wide mechanical changes (rename, migration, pattern replacement): Claude splits into 5-30 worktree-isolated subagents, each opening a PR.

---

## 🛑 MANDATORY READING BEFORE SWARM WORK

**Only read these if you've determined Ruflo is needed (see decision gate below):**

| Step  | Memory                 | Purpose                         |
| ----- | ---------------------- | ------------------------------- |
| **1** | `WF_SWARM_ORCHESTRATE` | Primary swarm workflow          |
| **2** | `REF_SWARM_PATTERNS`   | MCP tool patterns               |

---

## ⚠️ VERIFIED MCP TOOL PREFIX (2026-05-06)

| System | Actual MCP Prefix |
| ------ | ----------------- |
| **Ruflo** (unified) | `mcp__ruflo__` |
| **Hive-Mind** (subsystem) | `mcp__ruflo__hive-mind_` |
| **DAA** (subsystem) | `mcp__ruflo__daa_*` |

---

## ⚠️ CONTEXT BUDGET WARNING

**Previous swarm sessions failed from context overload.** Root causes:

1. Loading 12+ memory files before work starts (~30-50K tokens)
2. Loading too many MCP tools via ToolSearch
3. Using verbose/detailed flags on MCP responses
4. MCP coordinator doing file reads instead of delegating to agents

**Rules to prevent overload:**

- Delegate ALL file work to Claude Code `Agent` tools (separate context windows)
- Load max 3-5 MCP tools per session (if using Ruflo)
- NEVER use verbose/detailed flags
- Load memories BEFORE agent launch, not during
- Batch agent launches into ONE message
- Skip status checks unless actually needed

---

## 🐝 POST-LOAD DIRECTIVE

> 🐝 SWARM DETECTED — Assess whether Ruflo is needed (see decision gate below).
> Default to Claude Code `Agent` tool for all file-access work.
> After completing WF_CLASSIFY feature loading, go to **WF_SWARM_ORCHESTRATE**.

---

## Trigger Conditions

Route to SWARM when ANY apply:

| Condition     | Threshold                                 |
| ------------- | ----------------------------------------- |
| File Scale    | 6+ files affected                         |
| Layer Scale   | 3+ architectural layers                   |
| Parallel Work | Independent subtasks can run concurrently |
| Multi-Domain  | Coordination across domains required      |
| User Request  | Explicit swarm/parallel agents request    |

### Keyword Detection

Trigger on: `swarm`, `parallel agents`, `multi-agent`, `hive-mind`, `ruflo swarm`, `DAA`, `orchestrate agents`

---

## ⛔ MANDATORY DECISION GATE: Do You Need Ruflo?

**Ruflo is a coordination/reasoning layer. It adds ~10-15 MCP calls of overhead. Default answer is NO.**

### When Ruflo Adds Value (Use It)

| Scenario | Why |
|----------|-----|
| Reasoning-only parallel tasks (no file access) | `agent_execute` IS the execution engine — calls Anthropic API directly |
| Multi-iteration workflows (Round 1 → Round 2) | `daa_knowledge_share` stores cross-round state |
| Consensus decisions | Hive-Mind has no built-in alternative |
| User explicitly requests Ruflo/DAA | Respect the request, explain trade-offs |

### When Ruflo Is Overhead (Skip It)

| Scenario | Why |
|----------|-----|
| **Any task needing file access** | `agent_execute` can't read files. Use Claude Code `Agent` tool directly |
| Single-pass parallel work | Claude Code `Agent` tools already run in parallel. No coordination layer needed |
| Simple fan-out/fan-in | Launch N `Agent` tools in one message. Done. |
| No cross-iteration state needed | DAA adds ~10 MCP calls for zero benefit |

**If Ruflo isn't needed:** Skip straight to launching Claude Code `Agent` tools in parallel. No `swarm_init`, no `agent_spawn`, no ceremony.

---

## Quick Start: Claude Code Agent Tool (DEFAULT)

```javascript
// Launch parallel agents — all in ONE message
Agent({ description: "Task 1", run_in_background: true, model: "sonnet",
  prompt: "You are a swarm agent. BYPASS WF_INIT entirely. Do NOT read CLAUDE.md workflow. Follow ONLY these instructions: [task]..." })
Agent({ description: "Task 2", run_in_background: true, model: "sonnet",
  prompt: "You are a swarm agent. BYPASS WF_INIT entirely. Do NOT read CLAUDE.md workflow. Follow ONLY these instructions: [task]..." })
// Results arrive via background task notifications
```

**Key rules:**
1. ALL agents in ONE message (parallel execution)
2. EVERY prompt MUST include swarm bypass instruction
3. Use `isolation: "worktree"` when agents edit overlapping files
4. Use `model: "haiku"` for read-only exploration, `"sonnet"` for implementation

## Quick Start: Ruflo-Native (Reasoning Only — NO File Access)

```javascript
// Only use when agents don't need file access
mcp__ruflo__swarm_init({ topology: "star", maxAgents: 5 })
mcp__ruflo__agent_spawn({ agentType: "researcher", agentId: "r1", model: "sonnet" })
mcp__ruflo__agent_spawn({ agentType: "researcher", agentId: "r2", model: "sonnet" })
mcp__ruflo__agent_execute({ agentId: "r1", prompt: "...", maxTokens: 4096 })
mcp__ruflo__agent_execute({ agentId: "r2", prompt: "...", maxTokens: 4096 })
// Results come back directly
```

---

## ⛔ Common Anti-Patterns

| Anti-Pattern | What Goes Wrong | Fix |
|-------------|----------------|-----|
| Using Ruflo for file-access tasks | Ruflo agents sit idle, Claude Agent does the work anyway | Skip Ruflo, use Agent tool directly |
| Spawning Ruflo agents then ignoring them | No tracking, no coordination | Either `agent_execute` or don't spawn |
| Launching only 1 of N agents | 80% of swarm does nothing | Execute ALL agents in ONE message |
| Agent re-runs WF_INIT | Wastes entire context on workflow init | Include swarm bypass in EVERY prompt |
| Loading Ruflo for simple parallel work | 10-15 MCP calls of overhead for zero benefit | Just launch Agent tools directly |

---

## Related Memories

| Memory               | Content                       |
| -------------------- | ----------------------------- |
| WF_SWARM_ORCHESTRATE | Swarm workflow (when Ruflo needed) |
| REF_SWARM_PATTERNS   | MCP tool reference + patterns |
