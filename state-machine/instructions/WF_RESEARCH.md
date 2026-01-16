# WF_RESEARCH

> **🔬 On step WF_RESEARCH**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

Code exploration without changes - read-only investigation.

## Entry

- **From**: WF_START, WF_CLASSIFY
- **Triggers**: research_needed, exploration_request

## Required Actions

1. `explore_codebase` - Use Serena tools to navigate code
2. `analyze_patterns` - Identify existing patterns and conventions
3. `document_findings` - Update WORKING_MEMORY with discoveries

**NO EDITS ALLOWED** - This is read-only exploration.

## Permissions

- **Edit**: false | **Write**: false
- **Plan Mode**: never

## Research Guidelines

- Use `find_symbol`, `get_symbols_overview`, `search_for_pattern`
- Document all findings in WORKING_MEMORY
- Identify patterns before proposing changes

## Transitions

| Condition | Next State |
|-----------|------------|
| complete | WF_DETECT_REQ |

## RLVR Signal

- **Type**: research_step | **Impact**: neutral

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| Research complete | `WF_DETECT_REQ` |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
