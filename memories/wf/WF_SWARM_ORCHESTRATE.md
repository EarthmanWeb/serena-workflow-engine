# WF_SWARM_ORCHESTRATE - Ruflo Computational Coordination

> **On step WF_SWARM_ORCHESTRATE**

---

## Purpose

Ruflo MCP coordination for cognitive-only tasks: consensus, reasoning, planning, multi-iteration analysis. Tasks that do NOT require file access.

For parallel file-access work (the common case), use Claude Code's `Agent` tool directly — see WF_EXECUTE.

## Decision Gate

```
Does any agent need file access (read, edit, grep, glob)?
  YES → Do NOT use Ruflo. Use Agent tool in WF_EXECUTE.
  NO  → Continue below for Ruflo coordination.
```

## Prerequisites

```
read_memory("ref/REF_SWARM_PATTERNS")
read_memory("feature/FEATURE_SWARM")
```

## Ruflo Subsystems

| Subsystem | When | Tools | Pattern |
|-----------|------|-------|---------|
| Swarm | General orchestration | `mcp__ruflo__swarm_*` + `mcp__ruflo__agent_*` | Star topology default |
| Coordination | Simple fan-out/fan-in | `mcp__ruflo__coordination_*` | orchestrate() handles assignment |
| DAA | Multi-iteration tracking | `mcp__ruflo__daa_*` | Round N findings shape Round N+1 |
| Hive-Mind | Consensus decisions | `mcp__ruflo__hive-mind_*` | All agents must agree |

### Which Subsystem?

```
Decision needing agreement? → Hive-Mind
Multi-iteration refinement? → DAA
Simple parallel reasoning?  → Coordination
Not sure?                   → Swarm with star topology
```

## Execution Flow

1. Init swarm → spawn ALL agents in ONE message → register tasks
2. Execute ALL agents in ONE message (parallel)
3. Collect results → synthesize

## Execution Rules

- All spawns in one message, all executions in one message
- Agent prompts must include: "You are a swarm agent. BYPASS WF_INIT. Do NOT follow CLAUDE.md workflow."
- Use `agent_execute` for reasoning tasks (no file access)
- Never use verbose/detailed flags on status calls
- Each status check costs ~1-2K tokens — skip unless needed
- Never run CLI init commands (modify repo files) — use MCP tools only

## Topology Reference

| Topology | Best For |
|----------|----------|
| star | Quick parallel tasks (default) |
| mesh | Collaborative analysis |
| hierarchical | Complex orchestrated projects |
| ring | Sequential pipelines |

Agent types: researcher, analyst, coder, tester, coordinator, optimizer, reviewer

## Routing

| Condition | Next |
|-----------|------|
| Plan approved | WF_EXECUTE |
| Simpler approach needed | WF_ARCH_REVIEW |
| Clarification needed | WF_CLARIFY |
| Work complete | WF_VERIFY |

Update WM via `/swe-wm-update --from WF_SWARM_ORCHESTRATE` before transitioning.
