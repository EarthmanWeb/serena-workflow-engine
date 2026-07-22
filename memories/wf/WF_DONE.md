---
name: WF_DONE
description: Task-complete state — final WM update, completion checklist, learning checkpoint, and same-session new-task routing.
metadata:
  type: workflow
---

# WF_DONE — Task Complete

> **On step WF_DONE**

## Final WM Update

- Invoke `/swe-wm-update --from WF_DONE` for the final status write. It reads, validates, and writes WM completely.
- Do NOT hand-construct WM content.
- Do NOT read `REF_WM` separately — the skill covers it.

## Completion Checklist (all required before finishing)

- [ ] WM updated with final status
- [ ] Feature memories updated when changed (`DOM_*`, `SYS_*`, `INDEX_*`)
- [ ] No pending violations
- [ ] User informed of follow-up items

## Summarize To User

- What was done.
- Memories updated.
- Follow-up items (recorded in WM).

## Learning Checkpoint

- When the task produced reusable knowledge (patterns, gotchas, conventions), write or update the relevant memory file BEFORE transitioning.

## Same-Session New Task

- To start a new task in the same session: update WM (increment Task Iteration, move current to Previous Task, reset edit count), then route to `WF_CLASSIFY`.

## Next Step

| Condition                | Next          |
| ------------------------ | ------------- |
| New task in same session | `WF_CLASSIFY` |
| Session complete         | End           |
