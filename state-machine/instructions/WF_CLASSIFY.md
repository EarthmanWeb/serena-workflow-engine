# WF_CLASSIFY

> **🔍 On step WF_CLASSIFY**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

Classify task complexity and route appropriately.

## Entry

- **From**: WF_START, WF_CONTINUE
- **Triggers**: new_task, reclassify

## Required Actions

1. `analyze_task_scope` - Understand what user is asking
2. `count_affected_files` - Estimate files to be modified
3. `identify_layers` - Determine architectural layers involved
4. `determine_complexity` - Simple (1-2 files), Medium (2-5), Large (6+)

## Permissions

- **Edit**: false | **Write**: false
- **Plan Mode**: conditional
  - Trigger: `complexity >= 'medium' OR task_type == 'new_feature'`

## Complexity Thresholds

| Level | Files | Layers | Expected Transitions |
|-------|-------|--------|---------------------|
| Simple | 1-2 | 1 | 8 |
| Medium | 2-5 | 2-3 | 12 |
| Large | 6+ | 3+ | 18 |

## Transitions

| Condition | Next State |
|-----------|------------|
| simple | WF_DETECT_REQ |
| medium | WF_PLAN_ARCHITECTURE |
| large | WF_SWARM_ORCHESTRATE |
| research_needed | WF_RESEARCH |
| debug_needed | WF_DEBUG_TDD |
| needs_clarification | WF_CLARIFY |

## RLVR Signal

- **Type**: routing_decision | **Impact**: neutral

## MANDATORY NEXT STEP

Route based on complexity determination above.

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
