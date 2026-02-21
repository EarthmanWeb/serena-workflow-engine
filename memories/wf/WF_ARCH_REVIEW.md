# WF_ARCH_REVIEW - Architecture Compliance Check & Approval

> **On step WF_ARCH_REVIEW**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## Execute These Steps

1. **Get feature architecture:**
   ```
   mcp__plugin_swe_serena__read_memory("INDEX_FEATURES")   # Get active feature
   mcp__plugin_swe_serena__read_memory("FEATURE_[KEY]")    # Get feature config with layers
   ```

2. **Identify layers touched** by proposed change:
   - Check which architectural layers from FEATURE_[KEY] are affected

3. **For each layer, read its documentation:**
   ```
   # Read relevant SYS_* (feature-specific) and REF_* (codebase-shared) memories
   mcp__plugin_swe_serena__read_memory("SYS_[SYSTEM]")     # System documentation (feature-specific)
   mcp__plugin_swe_serena__read_memory("REF_[TOPIC]")      # Reference patterns (codebase-shared)
   mcp__plugin_swe_serena__read_memory("REF_DEV_STANDARDS") # Coding standards (codebase-shared)
   ```

4. **Answer these questions:**
   - [ ] Which layer OWNS this logic?
   - [ ] Am I putting logic in the correct layer?
   - [ ] Am I following the project's documented data flow pattern?

## STOP CONDITIONS

**If any of these are true, REDESIGN before proceeding:**

### General Layer Violations
- Business logic in presentation layer (views/templates should only display data)
- Presentation layer calling data layer directly (should go through business logic)
- Data access layer containing business rules (should be in service/business layer)
- Cross-cutting concerns scattered instead of centralized

### Presentation Layer (check views/templates)
- View contains complex logic beyond simple conditionals
- View has data transformations that belong in business layer
- View imports services/functions directly instead of using provided context
- View is doing more than display/formatting

**Read REF_* memories (codebase-shared) for correct patterns.**

---

## Approval - Ask User Before Code Changes

### Template Check (For New Files)

Before proposing new files:
1. Check existing patterns in similar files
2. Read relevant SYS_* or REF_* memory for the file type
3. Follow established feature conventions (from FEATURE_[KEY])

### MANDATORY - Present Plan and Get Approval

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

**Before calling AskUserQuestion, present your plan clearly** including files to modify/create, data flow, and test coverage.

### Handle User Response

| User Selection | Action |
|----------------|--------|
| "Yes, proceed" | Read `WF_EXECUTE` |
| "No, let's discuss" | Read `WF_CLARIFY` |
| "Modify approach" | Read `WF_PLAN_ARCHITECTURE` |
| Custom text (Other) | Parse feedback, go to `WF_CLARIFY` |

---

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| User approves | `WF_EXECUTE` |
| Needs redesign | `WF_PLAN_ARCHITECTURE` |
| User declines | `WF_CLARIFY` |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

## ⚠️ MANDATORY: WM UPDATE

**Before transitioning, invoke `/swe-wm-update --from WF_ARCH_REVIEW`** — provides the
step-specific checklist ensuring no fields are missed. Do NOT manually update WM
without it.

**SKIPPING WM UPDATE = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
