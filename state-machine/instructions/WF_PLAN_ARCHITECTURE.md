# WF_PLAN_ARCHITECTURE

> **🏗️ On step WF_PLAN_ARCHITECTURE**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

Design implementation approach for medium+ complexity tasks.

## Entry

- **From**: WF_CLASSIFY
- **Triggers**: complexity_medium_plus, new_feature, cross_cutting_change

## On Entry

1. Call `EnterPlanMode` tool
2. Write plan to plan file
3. Present architecture options to user

## Required Actions

1. `analyze_codebase_structure` - Understand existing architecture
2. `identify_affected_components` - List all impacted areas
3. `design_implementation_approach` - Create step-by-step plan
4. `document_trade_offs` - Pros/cons of approach
5. `request_user_approval` - Get explicit sign-off

## Permissions

- **Edit**: false | **Write**: false
- **Plan Mode**: always
  - Reason: Architecture decisions require user approval

## Transitions

| Condition | Next State |
|-----------|------------|
| approved | WF_SWARM_ORCHESTRATE |
| simple_enough | WF_DETECT_REQ |
| needs_revision | WF_PLAN_ARCHITECTURE |
| needs_clarification | WF_CLARIFY |

## RLVR Signal

- **Type**: architecture_plan | **Impact**: neutral

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| Plan approved | `WF_SWARM_ORCHESTRATE` |
| Simpler than expected | `WF_DETECT_REQ` |
| Needs revision | `WF_PLAN_ARCHITECTURE` |
| Unclear requirements | `WF_CLARIFY` |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
