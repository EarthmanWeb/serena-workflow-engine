# WF_SWARM_ORCHESTRATE

> **🐝 On step WF_SWARM_ORCHESTRATE**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

Multi-agent swarm coordination for large tasks.

## Entry

- **From**: WF_CLASSIFY, WF_PLAN_ARCHITECTURE
- **Triggers**: large_complexity, architecture_approved

## Required Actions

1. `select_swarm_system` - Choose claude-flow or ruv-swarm
2. `decompose_into_subtasks` - Break down into parallel work units
3. `spawn_agents` - Create specialized agents for subtasks
4. `coordinate_execution` - Manage agent communication
5. `synthesize_results` - Merge agent outputs

## Permissions

- **Edit**: false | **Write**: false
- **Plan Mode**: always
  - Reason: Multi-agent coordination needs planning

## NO IMAGINATION RULE

**NO IMAGINATION. NO INFERENCE. NO GUESSING.**
- ONLY use explicitly documented patterns
- ONLY reference files that exist
- ONLY apply rules from loaded memories

## Swarm Selection

| System | Use When |
|--------|----------|
| claude-flow | Persistent agents, complex coordination |
| ruv-swarm | Quick parallel tasks, DAA features |

## Transitions

| Condition | Next State |
|-----------|------------|
| complete | WF_EXECUTE |

## RLVR Signal

- **Type**: swarm_coordination | **Impact**: neutral

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| Swarm complete | `WF_EXECUTE` |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
