# WF_CONTINUE - Resume Previous Work

> **On step WF_CONTINUE**

---

## Step 1: Verify Working Memory

WM should already exist (created when the session entered WF_CLASSIFY). If missing, go back and create it per `REF_WM`.

Echo to chat: `Working Memory: WM_<timestamp>`

## Step 2: Re-Research Knowledge Base

Before resuming work, refresh context by discovering new or updated memories:

```
list_memories(topic="dom")   # Domain behavior patterns
list_memories(topic="ref")   # Reference documentation
list_memories(topic="dev")   # Development standards
```

For each result relevant to the task:
- Read any DOM_* memories related to the feature being worked on
- Read any REF_* memories for coding patterns in affected areas
- Read any DEV_* memories for language-specific standards
- Check for memories added since the last session that may affect the task

Compare loaded memories against what was loaded in the previous session (check WM's loaded memories list). Load any new ones.

This ensures the agent operates with current knowledge, especially if domain docs, reference patterns, or dev standards were updated between sessions.

## Step 3: Check Current Task State

Review WM for:
- What was in progress?
- Any blockers noted?
- What is the next step?

## Step 4: Determine Resume Point

Use the routing table below.

**Multi-layer detection:** Check WM "Layers:" field or infer from files being modified. Layers are defined in FEATURE_[KEY] and ARCH_INDEX.

## Routing

| Condition                  | Read Next        |
| -------------------------- | ---------------- |
| Multi-layer work (>1 arch layer) | `WF_ARCH_REVIEW` |
| Single-layer work          | `WF_EXECUTE`     |
| Blocked/unclear            | `WF_CLARIFY`     |
| No previous state          | `WF_CLASSIFY`    |

1. Determine which condition applies
2. Read that WF_* memory now
3. Report the new step to user

Update WM via `/swe-wm-update --from WF_CONTINUE` before transitioning.
