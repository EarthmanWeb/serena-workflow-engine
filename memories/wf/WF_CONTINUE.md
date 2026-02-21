# WF_CONTINUE - Resume Previous Work

> **On step WF_CONTINUE**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## Execute These Steps

1. **VERIFY WM exists** (should have been created at WF_START)
   - If missing: **STOP** - go back and create it per `REF_WM`
   - Echo to chat: `Working Memory: WM_<timestamp>`

2. **Check current task state:**
   - What was in progress?
   - Any blockers noted?
   - What's the next step?

3. **Determine resume point** (see table below)

## MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before responding to user:

| Condition                                           | MUST Read Next   |
| --------------------------------------------------- | ---------------- |
| Was executing (multi-layer: >1 architectural layer) | `WF_ARCH_REVIEW` |
| Was executing (single-layer)                        | `WF_EXECUTE`     |
| Was blocked/unclear                                 | `WF_CLARIFY`     |
| No previous state                                   | `WF_CLASSIFY`    |

**Multi-layer detection:** Check WM "Layers:" field or infer from files being modified. Layers are defined in FEATURE_[KEY] and ARCH_INDEX.

1. Determine which condition applies
2. Read that WF_* memory NOW
3. Report the new step to user

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

## ⚠️ MANDATORY: WM UPDATE

**Before transitioning, invoke `/swe-wm-update --from WF_CONTINUE`** — provides the
step-specific checklist ensuring no fields are missed. Do NOT manually update WM
without it.

**SKIPPING WM UPDATE = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
