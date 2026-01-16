# WF_ARCH_REVIEW

> **🔎 On step WF_ARCH_REVIEW**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

Review architecture compliance before execution.

## Entry

- **From**: WF_LOAD_FEATURE, WF_CONTINUE
- **Triggers**: feature_loaded, ready_for_review

## Required Actions

1. `verify_against_standards` - Check REF_DEV_STANDARDS compliance
2. `check_pattern_compliance` - Verify follows existing patterns
3. `validate_approach` - Confirm implementation plan is sound

## Permissions

- **Edit**: false | **Write**: false
- **Plan Mode**: always
  - Reason: Design review before execution

## Review Checklist

- [ ] Follows existing code patterns
- [ ] Respects architectural layers
- [ ] No YAGNI violations
- [ ] Tests planned for changes
- [ ] No security concerns

## Transitions

| Condition | Next State |
|-----------|------------|
| approved | WF_ASK_PERMISSION |
| needs_revision | WF_PLAN_ARCHITECTURE |

## RLVR Signal

- **Type**: arch_review | **Impact**: bonus (+0.1)

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| Review passed | `WF_ASK_PERMISSION` |
| Needs revision | `WF_PLAN_ARCHITECTURE` |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
