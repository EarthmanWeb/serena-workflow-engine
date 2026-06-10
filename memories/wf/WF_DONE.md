# WF_DONE - Task Complete

> **On step WF_DONE**

---

## Final WM Update

**Invoke `/swe-wm-update --from WF_DONE`** — provides the complete checklist and
template for final status. The skill handles reading, validating, and writing WM
comprehensively. Do NOT manually construct WM content or read REF_WM separately.

---

## Checklist Before Finishing

- [ ] WM updated with final status
- [ ] Feature memories updated if needed (DOM_*, SYS_*, INDEX_*)
- [ ] No pending violations
- [ ] User informed of any follow-up items

---

## Summarize To User

- What was done
- Any memories updated
- Any follow-up items (documented in WM)

---

## Learning Checkpoint

If the task produced reusable knowledge (patterns, gotchas, conventions), write or update the relevant memory file before transitioning.

---

## Same-Session New Task Handling

To start a new task in the same session: update WM (increment Task Iteration, move current to Previous Task, reset edit count), then route to WF_CLASSIFY.

## Next Step

| Condition                    | Read Next    |
| ---------------------------- | ------------ |
| Learning/cleanup needed      | `WF_CLEANUP` |
| New task in same session     | `WF_CLASSIFY` |
| Session complete             | End          |
