---
name: WF_CONTINUE
description: Resume previous work — refresh knowledge base, check task state, route to resume point.
metadata:
  type: workflow
---

# WF_CONTINUE — Resume Previous Work

> **On step WF_CONTINUE**

## Step 1: Verify Working Memory

- WM exists already (created on entry to WF_CLASSIFY).
- WM missing → recreate per `REF_WM`, then continue.
- Echo to chat: `Working Memory: WM_<timestamp>`

## Step 2: Re-Research Knowledge Base

Refresh context before resuming. Run:

```
list_memories(topic="dom")
list_memories(topic="ref")
list_memories(topic="dev")
```

- Read DOM_* memories for the feature being worked on.
- Read REF_* memories for coding patterns in affected areas.
- Read DEV_* memories for language-specific standards.
- Compare against WM's loaded-memories list. Read any memory added or updated since the previous session.

## Step 3: Check Current Task State

Read WM for: what was in progress, blockers noted, next step.

## Step 4: Determine Resume Point

- Detect layers from WM `Layers:` field or infer from files being modified. Layers are defined in `FEATURE_[KEY]` and `ARCH_INDEX`.
- Route via the table below.

## Routing

| Condition                        | Read Next        |
| -------------------------------- | ---------------- |
| Multi-layer work (>1 arch layer) | `WF_ARCH_REVIEW` |
| Single-layer work                | `WF_EXECUTE`     |
| Blocked/unclear                  | `WF_CLARIFY`     |
| No previous state                | `WF_CLASSIFY`    |

1. Determine which condition applies.
2. Read that WF_* memory now.
3. Report the new step to user.

Update WM via `/swe-wm-update --from WF_CONTINUE` before transitioning.
