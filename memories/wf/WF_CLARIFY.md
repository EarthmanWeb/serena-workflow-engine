---
name: WF_CLARIFY
description: Workflow state — ask the user to resolve unclear requests, conflicts, declined changes, or approach choices via AskUserQuestion, then route back.
metadata:
  type: workflow
---

# WF_CLARIFY — Ask User

> **On step WF_CLARIFY**

## When To Enter

Enter WF_CLARIFY when ANY holds:
- Request is unclear.
- Requirement conflicts with documented behavior.
- User declined proposed changes.
- Must choose between approaches.

## Before Asking

- When the clarification involves domain behavior, read the relevant `DOM_*` memory first.
- Reference the specific `DOM_*` memory by name in the question so the user can verify.

## Ask With AskUserQuestion

Use the `AskUserQuestion` tool. Pick the matching scenario.

### Conflict Resolution

```javascript
AskUserQuestion({
  questions: [
    {
      question: 'Your request says X, but the documented behavior (DOM_[DOMAIN]) says Z. Which should I follow?',
      header: 'Conflict',
      options: [
        { label: 'Follow my request', description: 'Override the documented behavior for this task' },
        { label: 'Follow documentation', description: 'Use the documented behavior instead' },
        { label: 'Update documentation', description: 'My request is correct - update the docs' },
      ],
      multiSelect: false,
    },
  ],
});
```

### Ambiguous Request

```javascript
AskUserQuestion({
  questions: [
    {
      question: 'I need clarification on your request. Which approach do you prefer?',
      header: 'Clarify',
      options: [
        { label: 'Option A', description: '[First interpretation]' },
        { label: 'Option B', description: '[Second interpretation]' },
      ],
      multiSelect: false,
    },
  ],
});
```

### After Declined Changes

```javascript
AskUserQuestion({
  questions: [
    {
      question: 'You declined the proposed changes. How should I proceed?',
      header: 'Next Step',
      options: [
        { label: 'Different approach', description: 'Try a different implementation strategy' },
        { label: 'Modify scope', description: 'Reduce or change what we are implementing' },
        { label: 'Cancel task', description: 'Stop working on this task' },
      ],
      multiSelect: false,
    },
  ],
});
```

## AskUserQuestion Parameters

| Parameter     | Rule                                                |
| ------------- | --------------------------------------------------- |
| `questions`   | Array of 1-4 questions                              |
| `question`    | Full question text to display                       |
| `header`      | Short label, max 12 chars                           |
| `options`     | Array of 2-4 choices, each with `label` and `description` |
| `multiSelect` | `true` allows multiple selections                   |

Users can always select "Other" for custom text input.

## After User Responds

1. Note the state you came from.
2. Read the WF_* memory for the state you route back to.
3. Report the new step to the user.

## Routing

| Return From   | Next State        |
| ------------- | ----------------- |
| CLASSIFY      | `WF_CLASSIFY`     |
| ARCH_REVIEW   | `WF_ARCH_REVIEW`  |

Update WM via `/swe-wm-update` before transitioning.
