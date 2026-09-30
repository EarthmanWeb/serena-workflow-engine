---
name: swe-workflow-debug-tdd
version: 1.0.0
description: Test-driven debugging for failing tests or bugs
workflow:
  aware: true
  callable_from:
    - WF_CLASSIFY
  default_return: WF_EXECUTE
  supports_standalone: true
  auto_transition: true
---

# Workflow Debug TDD Skill

Test-driven debugging workflow for rapid iteration.

## Purpose

- Reproduce failing tests/bugs
- Identify root cause
- Implement fix
- Verify fix works

## TDD Cycle

1. **RED** - Confirm test fails / bug reproduces
2. **Analyze** - Identify root cause
3. **GREEN** - Implement minimal fix
4. **Verify** - Confirm test passes / bug fixed
5. **Refactor** - Clean up if needed

## Actions

1. **Run failing test**: use the test command documented in `mcp__plugin_swe_serena__read_memory("feature/FEATURE_TESTS")`, scoped to the failing test only.
2. **Read error output**: inspect the command's stdout/stderr from step 1 (exact failure, line number, actual vs expected).
3. **Trace to source**: `mcp__plugin_swe_serena__find_symbol(name_path_pattern="<symbol>")` / `mcp__plugin_swe_serena__search_for_pattern(substring_pattern="<pattern>")` from the stack trace/error location.
4. **Implement fix**: `Edit` the minimal change at the traced location.
5. **Re-run test**: repeat step 1's exact command. Still failing after 2 consecutive attempts → STOP and report per CLAUDE_OBLIGATIONS Skill Failure Threshold; do not try a different fix approach without re-diagnosing.

## Skill Return Format

```markdown
## Skill Return

- **Skill**: swe-workflow-debug-tdd
- **Status**: [success|needs_clarification|blocked]
- **Findings Summary**: [bug description and fix applied]
- **Artifacts**: [files changed, tests affected]
- **Next Step Hint**: WF_EXECUTE
```

## Exit

`> **Skill /swe-workflow-debug-tdd complete** - bug fixed, returning to WF_EXECUTE`
