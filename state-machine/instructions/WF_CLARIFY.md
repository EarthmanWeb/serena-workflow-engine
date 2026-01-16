# WF_CLARIFY - Ask User

> **On step WF_CLARIFY**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## When To Use

- Request is unclear
- Requirement conflicts with documented behavior
- User declined proposed changes
- Need to choose between approaches

## Ask User

Format your question clearly:
- "You said X, but DOM_[DOMAIN] says Z. Which is correct?"
- "I'm not sure what you want. Do you mean A or B?"
- "You declined. What should I do differently?"

## MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** After user responds:

| Return To | MUST Read Next |
|-----------|----------------|
| From CLASSIFY | `WF_CLASSIFY` |
| From REQUIREMENT | `WF_REQUIREMENT` |
| From PLAN_ARCHITECTURE | `WF_PLAN_ARCHITECTURE` |

1. Note where you came from
2. After user responds, read that WF_* memory
3. Report the new step to user

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

📋 **WORKING_MEMORY:** Update if task state changed (see `REF_WORKING_MEMORY`)

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
