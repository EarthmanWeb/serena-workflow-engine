# WF_DETECT_REQ

> **📋 On step WF_DETECT_REQ**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

Detect implicit requirements from user request.

## Entry

- **From**: WF_CLASSIFY, WF_RESEARCH
- **Triggers**: analysis_complete

## Required Actions

1. `extract_explicit_requirements` - What user directly asked for
2. `infer_implicit_requirements` - What's needed but not stated
3. `identify_edge_cases` - Error handling, validation needs
4. `document_requirements` - Write to WORKING_MEMORY

## Permissions

- **Edit**: false | **Write**: false
- **Plan Mode**: conditional
  - Trigger: `requirement_type == 'architectural'`

## Requirement Categories

| Type | Example |
|------|---------|
| Functional | "Add login button" |
| Behavioral | Error handling, validation |
| Architectural | New service, cross-cutting |
| Testing | Test coverage requirements |

## Transitions

| Condition | Next State |
|-----------|------------|
| requirements_found | WF_REQUIREMENT |
| simple_task | WF_LOAD_FEATURE |

## RLVR Signal

- **Type**: requirement_detection | **Impact**: neutral

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| Requirements detected | `WF_REQUIREMENT` |
| Simple/direct task | `WF_LOAD_FEATURE` |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
