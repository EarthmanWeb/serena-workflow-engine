# WF_DONE

> **✅ On step WF_DONE**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

Task complete - execute RLVR learning pipeline.

## Entry

- **From**: WF_VERIFY
- **Requires**: WF_VERIFY passed

## Required Actions

1. `execute_rlvr_pipeline` - Run learning sequence
2. `mark_learning_complete` - Set learning flag
3. `update_working_memory` - Final status update
4. `final_summary` - Present completion summary to user

## RLVR Pipeline (MANDATORY)

```
trajectory_end → sona_learn → pattern_store → agent_adapt → knowledge_share
```

**This pipeline BLOCKS completion until executed.**

## Permissions

- **Edit**: false | **Write**: false
- **Plan Mode**: never

## Completion Summary Format

```markdown
## Task Complete ✅

### What Was Done
- [Summary of changes]

### Files Modified
- [List of files]

### Tests
- [Test results]

### Learning
- RLVR pipeline: [complete/incomplete]
```

## Transitions

| Condition | Next State |
|-----------|------------|
| learning_complete | WF_CLEANUP |
| learning_incomplete | BLOCKED |

## RLVR Signal

- **Type**: learning_checkpoint | **Impact**: mandatory (blocks completion)

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| RLVR complete | `WF_CLEANUP` |
| RLVR incomplete | **BLOCKED - Complete RLVR first** |

**SKIPPING RLVR = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
