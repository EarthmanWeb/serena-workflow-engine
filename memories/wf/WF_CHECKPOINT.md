# WF_CHECKPOINT - Update Progress

> **On step WF_CHECKPOINT**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## ⚠️ CRITICAL: UPDATE WM NOW

**This step exists specifically to update WM. You MUST do this.**

**Invoke `/swe-wm-update --from WF_CHECKPOINT`** — provides the complete checklist and
template. The skill handles reading, validating, and writing WM comprehensively.

Do NOT manually construct WM content or read REF_WM separately — the skill
contains everything needed.

---

## Triggers for this state

- Created/deleted a file
- Modified multiple symbols
- Completed a phase
- ~5 minutes elapsed since last update

## MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before responding to user:

| Condition         | MUST Read Next |
| ----------------- | -------------- |
| More work remains | `WF_EXECUTE`   |
| All work complete | `WF_VERIFY`    |

1. **VERIFY** you updated WM
2. Determine which condition applies
3. Read that WF_* memory NOW
4. Report the new step to user

**SKIPPING WM UPDATE = WORKFLOW VIOLATION**
**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Did you update WM? Are you on a WF_* workflow step? Did you report on it?]
