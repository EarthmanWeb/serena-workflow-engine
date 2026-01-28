---
name: swe-reset
description: Reset workflow state (requires confirmation)
---

# /swe-reset

Reset workflow to WF_START state.

## Warning

⚠️ This will:
- Archive current WORKING_MEMORY
- Delete workflow-state.json
- Reset all state tracking

## Confirmation with AskUserQuestion

**Use AskUserQuestion for destructive action confirmation:**

```javascript
AskUserQuestion({
  questions: [
    {
      question: "⚠️ This will reset all workflow state. Are you sure?",
      header: "Reset",
      options: [
        {
          label: "Yes, reset workflow",
          description: "Archive current WM and delete state files"
        },
        {
          label: "No, cancel",
          description: "Keep current workflow state"
        }
      ],
      multiSelect: false
    }
  ]
})
```

## Implementation

1. Show current state and warning
2. Call AskUserQuestion for confirmation
3. If "Yes, reset workflow" selected:
   - Archive current WORKING_MEMORY (append _archived_timestamp)
   - Delete workflow-state.json
   - Delete workflow-layers.json (if exists)
   - Output: "Workflow reset. Read WF_START to begin."
4. If "No, cancel" selected:
   - Output: "Reset cancelled. Workflow state unchanged."
