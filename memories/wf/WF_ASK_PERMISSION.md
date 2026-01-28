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

**Use the `AskUserQuestion` tool for interactive approval:**

```javascript
AskUserQuestion({
  questions: [
    {
      question: "I plan to make the following changes. May I proceed?",
      header: "Approval",
      options: [
        {
          label: "Yes, proceed",
          description: "Approve the proposed changes and continue to implementation"
        },
        {
          label: "No, let's discuss",
          description: "Stop and clarify requirements before making changes"
        },
        {
          label: "Modify approach",
          description: "I want to suggest a different approach"
        }
      ],
      multiSelect: false
    }
  ]
})
```

**Before calling AskUserQuestion, present your plan clearly:**

```markdown
## Proposed Changes

### Files to Modify
| File | Layer | Pattern |
|------|-------|---------|
| UserService.ts | Service | per SYS_SERVICES |
| UserController.ts | Controller | per REF_CONTROLLERS |

### Files to Create
| File | Layer | Pattern |
|------|-------|---------|
| UserRepository.ts | Repository | per SYS_REPOSITORIES |

### Data Flow
```
Controller <- Service <- Repository
(as defined in ARCH_INDEX)
```

### Test Coverage
- [ ] UserService.test.ts
- [ ] UserController.test.ts
- [ ] UserRepository.test.ts
```

## AskUserQuestion Tool Reference

The `AskUserQuestion` tool provides interactive UI in VS Code extension:

| Parameter | Description |
|-----------|-------------|
| `questions` | Array of 1-4 questions |
| `question` | Full question text to display |
| `header` | Short label (max 12 chars) |
| `options` | Array of 2-4 choices with `label` and `description` |
| `multiSelect` | If `true`, allows multiple selections |

**Users can always select "Other" for custom text input.**

## TEST FILE ENFORCEMENT

**For every service, controller, or functional code proposed, you MUST also propose corresponding tests.**

Before finalizing your proposal, check:
- [ ] Each new component has test coverage proposed
- [ ] Integration points have test coverage proposed

## Handle User Response

After `AskUserQuestion` returns:

| User Selection | Action |
|----------------|--------|
| "Yes, proceed" | Read `WF_EXECUTE` |
| "No, let's discuss" | Read `WF_CLARIFY` |
| "Modify approach" | Read `WF_CLARIFY` |
| Custom text (Other) | Parse feedback, go to `WF_CLARIFY` |

## MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** After receiving user response:

| Condition | MUST Read Next |
|-----------|----------------|
| User approves | `WF_EXECUTE` |
| User declines or wants changes | `WF_CLARIFY` |

1. Call `AskUserQuestion` with your proposal
2. Wait for user response
3. Read the appropriate WF_* memory NOW
4. Report the new step to user

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

WM: Update if task state changed (see `REF_WM`)

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
