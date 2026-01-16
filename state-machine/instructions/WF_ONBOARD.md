# WF_ONBOARD

> **📝 On step WF_ONBOARD**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

Feature onboarding wizard - collect info and create feature memories.

## Entry

- **From**: WF_START
- **Triggers**: onboard_feature_command, new_feature_detected

## Required Actions

1. `collect_feature_info` - Gather feature name, path, language, framework
2. `analyze_codebase` - Scan for patterns, architecture, test commands
3. `create_memories` - Generate FEATURE_[KEY], DOM_*, SYS_* memories
4. `update_index` - Add feature to INDEX_FEATURES registry

## Permissions

- **Edit**: true | **Write**: true
- **Plan Mode**: never

## Transitions

| Condition | Next State |
|-----------|------------|
| complete | WF_START |

## RLVR Signal

- **Type**: onboard | **Impact**: neutral

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| Onboarding complete | `WF_START` |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
