# WF_ARCH_REVIEW - Design, Compliance Review & Approval

> **On step WF_ARCH_REVIEW**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## Purpose

This is the **single planning gate** for all code changes. It combines:

1. **Design** — define which files/components are affected, with explicit paths
2. **Architecture compliance** — verify layer boundaries and patterns
3. **Swarm assessment** — determine if multi-agent orchestration is needed
4. **User approval** — present plan and get sign-off before execution

---

## SPEC Fast-Path: Skip Design If SPEC Already Exists

**If a `SPEC_*` memory has already been loaded for this task (check WM):**

The SPEC contains the pre-approved architecture, file paths, data flow, and implementation plan. In this case:

- ✅ **SKIP steps 1–4** (feature architecture, layer docs, design, compliance check) — the SPEC already covers these
- ✅ **Reference the SPEC by name** (e.g., "Plan per SPEC_TICKETS_FRONTEND") — do NOT re-present or reiterate its contents
- ✅ Proceed directly to the **Swarm Assessment** (step 5) and then **Approval** (or auto-approve bypass)
- ❌ Do NOT re-derive file paths, layer assignments, or data flow — use exactly what the SPEC provides

**If no SPEC loaded:** Follow steps 1–4 as normal below.

---

## Execute These Steps

### 1. Get Feature Architecture

If not already loaded at WF_CLASSIFY (check WM):

```
mcp__plugin_swe_serena__read_memory("index/INDEX_FEATURES")   # Get active feature
mcp__plugin_swe_serena__read_memory("feature/FEATURE_[KEY]")    # Get feature config with layers
mcp__plugin_swe_serena__read_memory("arch/ARCH_INDEX")          # Architecture overview (if exists)
```

### 2. Read Layer Documentation

**For EACH layer in the design, read its rules:**

```
mcp__plugin_swe_serena__read_memory("sys/SYS_[SYSTEM]")     # System documentation (feature-specific)
mcp__plugin_swe_serena__read_memory("ref/REF_[TOPIC]")      # Reference patterns (codebase-shared)
mcp__plugin_swe_serena__read_memory("feature/FEATURE_DEV_STANDARDS") # Coding standards (codebase-shared)
mcp__plugin_swe_serena__read_memory("dom/DOM_[DOMAIN]")     # Domain-specific context (feature-specific)
```

### 3. Design With Explicit File Paths

Define which files/components are affected:

- Files to be modified (with what changes)
- Files to be created (with justification)
- Data flow between components
- Test coverage plan

### 4. Architecture Compliance Check

**Answer these questions:**

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

**Read REF** memories (codebase-shared) for correct patterns._*

---

### 5. Swarm Assessment

**Assess whether this task needs multi-agent orchestration:**

| Condition     | Threshold                                 |
| ------------- | ----------------------------------------- |
| File Scale    | 6+ files affected                         |
| Layer Scale   | 3+ architectural layers                   |
| Parallel Work | Independent subtasks can run concurrently |
| Multi-Domain  | Coordination across domains required      |

**If ANY threshold is met AND WM has `swarm_candidate: true` from WF_CLASSIFY:**

- Include swarm recommendation in plan presentation
- Note topology, agent types, parallelization strategy
- Route to `WF_SWARM_ORCHESTRATE` after user approval

**If thresholds NOT met:** Proceed as single-agent implementation.

---

## Approval - Ask User Before Code Changes

### Template Check (For New Files)

Before proposing new files:

1. Check existing patterns in similar files
2. Read relevant SYS_* or REF_* memory for the file type
3. Follow established feature conventions (from FEATURE_[KEY])

### MANDATORY - Present Plan

**Present your plan clearly** including:

- Files to modify/create table
- Key architectural constraints applied
- Data flow description
- Test coverage plan
- **Swarm recommendation** (if applicable): topology, agent types, parallelization strategy

### Auto-Approve Bypass Check

**Check WM for `auto_approve: true`** (set at WF_CLASSIFY step 2b).

**If `auto_approve: true` in WM:**

- ✅ The plan has been presented above (transparency preserved)
- ✅ **SKIP the `AskUserQuestion` approval gate below**
- ✅ Treat as "Yes, proceed" — go directly to `WF_EXECUTE` (or `WF_SWARM_ORCHESTRATE` if swarm planned)
- ℹ️ The user explicitly requested uninterrupted execution in their initial message

**If `auto_approve` is NOT set (or false):** Continue to the approval gate below.

### Get Approval (when auto_approve is NOT set)

**Use the `AskUserQuestion` tool for interactive approval:**

```javascript
AskUserQuestion({
  questions: [
    {
      question: 'I plan to make the following changes. May I proceed?',
      header: 'Approval',
      options: [
        {
          label: 'Yes, proceed',
          description: 'Approve the proposed changes and continue to implementation',
        },
        {
          label: "No, let's discuss",
          description: 'Stop and clarify requirements before making changes',
        },
        {
          label: 'Modify approach',
          description: 'I want to suggest a different approach',
        },
      ],
      multiSelect: false,
    },
  ],
});
```

### Handle User Response

| User Selection      | Action                                                         |
| ------------------- | -------------------------------------------------------------- |
| "Yes, proceed"      | Read `WF_EXECUTE` (or `WF_SWARM_ORCHESTRATE` if swarm planned) |
| "No, let's discuss" | Read `WF_CLARIFY`                                              |
| "Modify approach"   | Re-run this step (`WF_ARCH_REVIEW`) with modified design       |
| Custom text (Other) | Parse feedback, go to `WF_CLARIFY`                             |

---

## MANDATORY NEXT STEP

| Condition                             | MUST Read Next         |
| ------------------------------------- | ---------------------- |
| Auto-approve bypass (simple)          | `WF_EXECUTE`           |
| Auto-approve bypass (swarm needed)    | `WF_SWARM_ORCHESTRATE` |
| User approves (simple implementation) | `WF_EXECUTE`           |
| User approves (swarm needed)          | `WF_SWARM_ORCHESTRATE` |
| Needs redesign / user modifies        | `WF_ARCH_REVIEW`       |
| User declines / needs clarification   | `WF_CLARIFY`           |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

## ⚠️ MANDATORY: WM UPDATE

**Before transitioning, invoke `/swe-wm-update --from WF_ARCH_REVIEW`** — provides the
step-specific checklist ensuring no fields are missed. Do NOT manually update WM
without it.

**SKIPPING WM UPDATE = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
