# WF_ASK_PERMISSION - Get Approval

> **On step WF_ASK_PERMISSION**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## Template Check (For New Files)

Before proposing new files:
1. Check existing patterns in similar files
2. Read relevant SYS_* or REF_* memory for the file type
3. Follow established feature conventions (from FEATURE_[KEY])

## MANDATORY - Ask User Before Any Code Changes

**Format (must include architecture justification):**
```
I plan to:
- Modify: [file] -> [layer] (following [pattern from SYS_*/REF_*])
- Create: [file] -> [layer] (following [pattern from SYS_*/REF_*])

Data flow: [Layer1] <- [Layer2] <- [Layer3]
          (as defined in ARCH_INDEX)

Proceed? (yes/no)
```

**Example:**
```
I plan to:
- Create: UserService.ts -> Service Layer (per SYS_SERVICES)
- Modify: UserController.ts -> Controller (per REF_CONTROLLERS)

Data flow: Controller <- Service <- Repository

Proceed?
```

## TEST FILE ENFORCEMENT

**For every service, controller, or functional code proposed, you MUST also propose corresponding tests.**

Before finalizing your proposal, check:
- [ ] Each new component has test coverage proposed
- [ ] Integration points have test coverage proposed

## MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before responding to user:

| Condition | MUST Read Next |
|-----------|----------------|
| User says yes | `WF_EXECUTE` |
| User says no | `WF_CLARIFY` |

1. Wait for user response
2. Read that WF_* memory NOW
3. Report the new step to user

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

WORKING_MEMORY: Update if task state changed (see `REF_WORKING_MEMORY`)

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
