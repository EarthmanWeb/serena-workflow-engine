---
name: swe-workflow-verify
version: 1.0.0
description: Verify implementation against requirements and standards
workflow:
  aware: true
  callable_from:
    - WF_EXECUTE
    - WF_CHECKPOINT
  default_return: WF_DONE
  supports_standalone: false
  auto_transition: true
---

## ⚠️ WORKFLOW INITIALIZATION

**If starting a new session**, first read workflow initialization:

```
mcp__plugin_swe_serena__read_memory("wf/WF_INIT")
```

Follow WF_INIT instructions before executing this skill.

---

# Workflow Verify Skill

Verify implementation completeness and quality.

## Purpose

- Run test suites
- Check against requirements
- Verify coding standards compliance
- Ensure no regressions

## Actions

1. **Run tests**: use the test command(s) documented in `mcp__plugin_swe_serena__read_memory("feature/FEATURE_TESTS")`, run in full (not a single test).
2. **Check requirements**: `mcp__plugin_swe_serena__read_memory("feature/FEATURE_[KEY]")` (and the task's SPEC_* memory if one exists) — compare each requirement/coverage-map row to the implementation.
3. **Verify standards**: `mcp__plugin_swe_serena__read_memory("claude/CLAUDE_OBLIGATIONS")` and the relevant `dev/DEV_*` memory (`mcp__plugin_swe_serena__list_memories(topic="dev")` to find it) — check the diff against each.
4. **Lint/format check**: the lint/format command documented in `feature/FEATURE_DEV_STANDARDS`, if one is configured there; skip only if that memory documents none.

## Verification Checklist

- [ ] All tests pass
- [ ] Requirements met
- [ ] Coding standards followed
- [ ] No security vulnerabilities introduced
- [ ] Documentation updated if needed

## Skill Return Format

```markdown
## Skill Return

- **Skill**: swe-workflow-verify
- **Status**: [success|success_with_findings|blocked]
- **Findings Summary**: [verification results]
- **Artifacts**: [test results, lint output]
- **Next Step Hint**: [WF_DONE if passed, WF_EXECUTE if failed]
```

## Exit

On success: `> **Skill /swe-workflow-verify complete** - returning to WF_DONE`
On failure: `> **Skill /swe-workflow-verify failed** - returning to WF_EXECUTE for fixes`
