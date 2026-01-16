# WF_START

> **🚀 On step WF_START**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

Mandatory entry point - read context, determine path.

## Entry

- **From**: SessionStart, WF_INITIAL_SETUP, WF_ONBOARD
- **Triggers**: session_start, workflow_reset

## Required Actions

1. `read_index_features` - Load INDEX_FEATURES, identify relevant feature(s)
2. `check_working_memory` - Find or create WORKING_MEMORY file
3. `determine_task_type` - Classify as new task, continuation, or research

**WORKING_MEMORY is MANDATORY** - Cannot proceed without it.

## Permissions

- **Edit**: false | **Write**: false
- **Plan Mode**: never

## Transitions

| Condition | Next State |
|-----------|------------|
| new_task | WF_CLASSIFY |
| continue_task | WF_CONTINUE |
| research_only | WF_RESEARCH |
| onboard_needed | WF_ONBOARD |

## RLVR Signal

- **Type**: trajectory_init | **Impact**: baseline

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| No features registered | `WF_ONBOARD` |
| WORKING_MEMORY missing | **CREATE IT NOW** |
| Continue previous work | `WF_CONTINUE` |
| Research/question only | `WF_RESEARCH` |
| Code change/feature/bug | `WF_CLASSIFY` |

**PROCEEDING WITHOUT WORKING_MEMORY = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
