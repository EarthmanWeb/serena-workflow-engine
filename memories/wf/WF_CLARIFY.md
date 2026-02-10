# WF_CLARIFY - Ask User

> **On step WF_CLARIFY**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## When To Use

- Request is unclear
- Requirement conflicts with documented behavior
- User declined proposed changes
- Need to choose between approaches

## Ask User with AskUserQuestion Tool

**Use the `AskUserQuestion` tool for interactive clarification:**

### Conflict Resolution
```javascript
AskUserQuestion({
  questions: [
    {
      question: "Your request says X, but the documented behavior (DOM_[DOMAIN]) says Z. Which should I follow?",
      header: "Conflict",
      options: [
        {
          label: "Follow my request",
          description: "Override the documented behavior for this task"
        },
        {
          label: "Follow documentation",
          description: "Use the documented behavior instead"
        },
        {
          label: "Update documentation",
          description: "My request is correct - update the docs"
        }
      ],
      multiSelect: false
    }
  ]
})
```

### Ambiguous Request
```javascript
AskUserQuestion({
  questions: [
    {
      question: "I need clarification on your request. Which approach do you prefer?",
      header: "Clarify",
      options: [
        {
          label: "Option A",
          description: "[Description of first interpretation]"
        },
        {
          label: "Option B",
          description: "[Description of second interpretation]"
        }
      ],
      multiSelect: false
    }
  ]
})
```

### After Declined Changes
```javascript
AskUserQuestion({
  questions: [
    {
      question: "You declined the proposed changes. How should I proceed?",
      header: "Next Step",
      options: [
        {
          label: "Different approach",
          description: "Try a different implementation strategy"
        },
        {
          label: "Modify scope",
          description: "Reduce or change what we're implementing"
        },
        {
          label: "Cancel task",
          description: "Stop working on this task"
        }
      ],
      multiSelect: false
    }
  ]
})
```

## AskUserQuestion Tool Reference

| Parameter | Description |
|-----------|-------------|
| `questions` | Array of 1-4 questions |
| `question` | Full question text to display |
| `header` | Short label (max 12 chars) |
| `options` | Array of 2-4 choices with `label` and `description` |
| `multiSelect` | If `true`, allows multiple selections |

**Users can always select "Other" for custom text input.**

## MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** After user responds:

| Return To | MUST Read Next |
|-----------|----------------|
| From CLASSIFY | `WF_CLASSIFY` |
| From REQUIREMENT | `WF_REQUIREMENTS` |
| From PLAN_ARCHITECTURE | `WF_PLAN_ARCHITECTURE` |
| From ASK_PERMISSION | `WF_ASK_PERMISSION` |

1. Note where you came from
2. After user responds via AskUserQuestion, read that WF_* memory
3. Report the new step to user

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

📋 **WM:** Update if task state changed (see `REF_WM`)

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
