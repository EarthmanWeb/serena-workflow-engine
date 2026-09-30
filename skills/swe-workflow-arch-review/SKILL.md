---
name: swe-workflow-arch-review
version: 1.0.0
description: Review architecture compliance before execution
workflow:
  aware: true
  callable_from:
    - WF_CLASSIFY
    - WF_CONTINUE
  default_return: WF_EXECUTE
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

# Workflow Architecture Review Skill

Review proposed changes against architecture standards.

## Purpose

- Verify changes align with existing architecture
- Check layer boundaries respected
- Validate naming conventions
- Ensure patterns are followed

## Actions

1. **Read ARCH_INDEX**: `mcp__plugin_swe_serena__read_memory("arch/ARCH_INDEX")`.
2. **Read feature context**: `mcp__plugin_swe_serena__read_memory("feature/FEATURE_[KEY]")` for each affected feature.
3. **Check patterns**: `mcp__plugin_swe_serena__search_for_pattern(substring_pattern="<pattern>", relative_path="<scope>")` against the proposed change's target files, comparing against the patterns documented in the memories read above.
4. **Validate approach** (judgment, output only): assess the implementation plan against Review Criteria below; record pass/fail per criterion in the Skill Return.

## Review Criteria

- [ ] Layer boundaries respected
- [ ] Naming conventions followed
- [ ] Dependencies flow correctly
- [ ] No circular dependencies introduced
- [ ] Consistent with existing patterns

## Skill Return Format

```markdown
## Skill Return

- **Skill**: swe-workflow-arch-review
- **Status**: [success|success_with_findings|blocked]
- **Findings Summary**: [architecture compliance assessment]
- **Artifacts**: [patterns checked, issues found]
- **Next Step Hint**: [WF_EXECUTE if approved, WF_ARCH_REVIEW if revision needed]
```

## Exit

On approval: `> **Skill /swe-workflow-arch-review passed** - returning to WF_EXECUTE`
On revision needed: `> **Skill /swe-workflow-arch-review needs revision** - returning to WF_ARCH_REVIEW`
