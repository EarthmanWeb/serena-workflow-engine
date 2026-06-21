# WF_CLEANUP

> **On step WF_CLEANUP**

---

## Purpose

Archive completed work. This is a terminal state.

## Entry

- **From**: WF_DONE
- **Triggers**: learning_complete, user_confirms_complete

## Required Actions

1. `identify_archivable_files` - Find WM and temp files
2. `confirm_with_user` - Ask if cleanup should proceed
3. `move_to_archive` - Archive completed WM
4. `update_indexes` - Remove from active, add to archive index

## Archive Process

```bash
# Move WM to archive
mv .serena/swe/wm/WM_*.md .serena/archive-memories/

# Clean up any temp files
rm -f .ruflo/workflow-state.json
```

Terminal state. Ready for next task (new WF_CLASSIFY).
