# WF_CHECKPOINT - Update Progress

> **On step WF_CHECKPOINT**

---

## Update WM Now

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

## Next Step

| Condition         | Read Next    |
| ----------------- | ------------ |
| More work remains | `WF_EXECUTE` |
| All work complete | `WF_VERIFY`  |

Update WM via `/swe-wm-update --from WF_CHECKPOINT` before transitioning.
