# WF_CLEANUP

> **🧹 On step WF_CLEANUP**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

Archive completed work - terminal state.

## Entry

- **From**: WF_DONE
- **Triggers**: learning_complete, user_confirms_complete

## Required Actions

1. `identify_archivable_files` - Find WM and temp files
2. `confirm_with_user` - Ask if cleanup should proceed
3. `move_to_archive` - Archive completed WM
4. `update_indexes` - Remove from active, add to archive index

## Permissions

- **Edit**: false | **Write**: false
- **Plan Mode**: never

## Archive Process

```bash
# Move WM to archive
mv .serena/memories/wm/WM_*.md .serena/archive-memories/

# Clean up any temp files
rm -f .claude-flow/workflow-state.json
```

## Transitions

| Condition | Next State |
|-----------|------------|
| complete | null (terminal) |

**This is a terminal state - workflow ends here.**

## RLVR Signal

- **Type**: cleanup | **Impact**: neutral

## MANDATORY NEXT STEP

None - this is the terminal state.

Workflow complete. Ready for next task (new WF_START).

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
