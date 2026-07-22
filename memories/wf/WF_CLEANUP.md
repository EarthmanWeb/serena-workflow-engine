---
name: WF_CLEANUP
description: Terminal workflow state — archive completed Working Memory and temp files, update indexes.
metadata:
  type: workflow
---

# WF_CLEANUP

> **On step WF_CLEANUP**

Terminal state. Archive completed work.

## Entry

- Enter from `WF_DONE`.
- Triggers: `learning_complete` OR `user_confirms_complete`.

## Required Actions

1. `identify_archivable_files` — Find WM and temp files.
2. `confirm_with_user` — STOP. Ask before proceeding. NEVER archive without confirmation.
3. `move_to_archive` — Archive completed WM.
4. `update_indexes` — Remove from active index; add to archive index.

## Archive Commands

```bash
mv .serena/swe/wm/WM_*.md .serena/archive-memories/
rm -f .ruflo/workflow-state.json
```

## Exit

- Terminal state. No transition target.
- Next task starts a new `WF_CLASSIFY`.
