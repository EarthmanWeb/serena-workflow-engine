# WF_CHECKPOINT - Optional Progress Check

> **On step WF_CHECKPOINT**

---

## This State Is Optional

WF_CHECKPOINT is a self-check, not a mandatory gate. The edit counter provides
an informational nudge at 10 edits — it never blocks. Use this state when you
want to pause and update progress, not because a hook forced you.

State is automatically persisted to the JSON state file at message boundaries
(Stop hook) and state transitions (post-read hook). Manual WM updates are only
needed when you want to record progress notes for cross-message recovery.

---

## When to Use

- You've completed a significant phase and want to record it
- You're about to switch to a different area of the codebase
- You want to update the task description or feature keys

## How to Update

Update progress via swe-wm MCP (does not trigger edit hooks):
```
swe_wm_update_section(section="Progress", content="...")
```

Or invoke the skill for a comprehensive update:
```
/swe-wm-update --from WF_CHECKPOINT
```

## Next Step

| Condition         | Read Next    |
| ----------------- | ------------ |
| More work remains | `WF_EXECUTE` |
| All work complete | `WF_VERIFY`  |
