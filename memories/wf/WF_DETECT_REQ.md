# WF_DETECT_REQ - Requirement Detection

> **🔍 On step WF_DETECT_REQ**

⬆️ OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## Scan User Message For

- "should", "must", "needs to", "has to"
- "users want", "behavior should be"
- "always do X", "never do Y"
- Corrections to current behavior
- UX preferences or constraints

## Decision

**Requirement found?**

- Yes → contains behavioral/UX requirement
- No → pure implementation task

## ⛔ MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before responding to user:

| Condition         | MUST Read Next    |
| ----------------- | ----------------- |
| Requirement found | `WF_REQUIREMENTS` |
| No requirement    | `WF_LOAD_FEATURE` |

1. Determine which condition applies
2. Read that WF_* memory NOW
3. Report the new step to user

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

## ⚠️ MANDATORY: WM UPDATE

**Before transitioning, invoke `/swe-wm-update --from WF_DETECT_REQ`** — provides the
step-specific checklist ensuring no fields are missed. Do NOT manually update WM
without it.

**SKIPPING WM UPDATE = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
