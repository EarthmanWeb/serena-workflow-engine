---
name: WF_SWARM_ORCHESTRATE
description: Ruflo MCP coordination for cognitive-only tasks (consensus, reasoning, planning, multi-iteration analysis) that require no file access.
metadata:
  type: workflow
---

# WF_SWARM_ORCHESTRATE — Ruflo Computational Coordination

> **On step WF_SWARM_ORCHESTRATE**

## Scope

- Use Ruflo MCP ONLY for cognitive-only tasks: consensus, reasoning, planning, multi-iteration analysis.
- NEVER use Ruflo when any agent needs file access (read, edit, grep, glob).
- For parallel file-access work, use Claude Code's `Agent` tool in `WF_EXECUTE`.

## Decision Gate

| Condition | Action |
|-----------|--------|
| Any agent needs file access (read, edit, grep, glob) | Do NOT use Ruflo. Use `Agent` tool in `WF_EXECUTE`. |
| No agent needs file access | Continue with Ruflo coordination below. |

## Prerequisites

- Read `ref/REF_SWARM_PATTERNS`.
- Read `feature/FEATURE_SWARM`.

## Ruflo Subsystems

| Subsystem | When | Tools | Pattern |
|-----------|------|-------|---------|
| Swarm | General orchestration | `mcp__ruflo__swarm_*` + `mcp__ruflo__agent_*` | Star topology default |
| Coordination | Simple fan-out/fan-in | `mcp__ruflo__coordination_*` | orchestrate() handles assignment |
| DAA | Multi-iteration tracking | `mcp__ruflo__daa_*` | Round N findings shape Round N+1 |
| Hive-Mind | Consensus decisions | `mcp__ruflo__hive-mind_*` | All agents must agree |

## Subsystem Selection

| Condition | Subsystem |
|-----------|-----------|
| Decision needing agreement | Hive-Mind |
| Multi-iteration refinement | DAA |
| Simple parallel reasoning | Coordination |
| Unclear | Swarm with star topology |

## Execution Flow

1. Init swarm → spawn ALL agents in ONE message → register tasks.
2. Execute ALL agents in ONE message (parallel).
3. Collect results → synthesize.

## Execution Rules

- Issue all spawns in one message; issue all executions in one message.
- Include in every agent prompt: "You are a swarm agent. BYPASS WF_INIT. Do NOT follow CLAUDE.md workflow."
- Use `agent_execute` for reasoning tasks (no file access).
- NEVER pass verbose/detailed flags on status calls — each status check costs ~1-2K tokens; skip unless needed.
- NEVER run CLI init commands — they modify repo files. Use MCP tools only.

## Topology Reference

| Topology | Best For |
|----------|----------|
| star | Quick parallel tasks (default) |
| mesh | Collaborative analysis |
| hierarchical | Complex orchestrated projects |
| ring | Sequential pipelines |

Agent types: researcher, analyst, coder, tester, coordinator, optimizer, reviewer.

## Routing

| Condition | Next |
|-----------|------|
| Plan approved | `WF_EXECUTE` |
| Simpler approach needed | `WF_ARCH_REVIEW` |
| Clarification needed | `WF_CLARIFY` |
| Work complete | `WF_VERIFY` |

Run `/swe-wm-update --from WF_SWARM_ORCHESTRATE` before transitioning.
