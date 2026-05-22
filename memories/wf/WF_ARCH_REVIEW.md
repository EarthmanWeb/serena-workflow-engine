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
mcp__plugin_swe_serena__read_memory("dom/DOM_[DOMAIN]")     # Domain-specific context (feature-specific)
```

### 2b. Load Development Standards for Affected Languages/Layers

**Read `FEATURE_DEV_STANDARDS` and follow links to the specific `DEV_*` memories for languages/layers this task touches.**

```
mcp__plugin_swe_serena__read_memory("feature/FEATURE_DEV_STANDARDS")  # Index of all DEV_* standards
```

**Then for EACH language/layer involved in the task, read the relevant standard:**

| Task involves...       | Read                |
| ---------------------- | ------------------- |
| PHP classes/functions  | `dev/DEV_PHP`       |
| JavaScript/jQuery      | `dev/DEV_JAVASCRIPT` |
| SCSS/CSS               | `dev/DEV_SCSS`      |
| Blade/templates        | `dev/DEV_BLADEONE`  |
| Tests                  | `dev/DEV_TESTS`     |
| Cross-language patterns| `dev/DEV_PATTERNS`  |

**If a `DEV_*` memory doesn't exist yet for the language, skip it — but note the gap.**

### 2c. Derive Project Compliance Checklist

**From the DEV_*, DOM_*, SYS_*, and FEATURE_[KEY] memories you just loaded, extract the concrete rules that apply to THIS task.** Write them as a checklist in WM under `## Compliance Checklist`.

**How to derive:**

1. Scan each loaded DEV_* memory for rules relevant to the files you'll touch (naming conventions, boilerplate requirements, security patterns, formatting rules)
2. Scan each loaded DOM_* memory for registration contracts, integration points, required interfaces
3. Scan FEATURE_[KEY] for testing commands, related memory references, common file patterns
4. If creating new files: extract naming patterns, required headers, registration steps

**Example output (written to WM):**

```markdown
## Compliance Checklist

- [ ] PHP file header with @package and @since (DEV_PHP)
- [ ] Handler implements getFieldHTML + initField (DOM_BUILDER_FIELDS)
- [ ] Blade template has variable defaults block at top (DEV_BLADEONE)
- [ ] filemtime() for asset versioning, not hardcoded (DEV_PHP)
- [ ] Handler registered via registerComponentHandler (DOM_BUILDER_FIELDS)
- [ ] New JS/CSS enqueued in builder-assets.php (FEATURE_builder)
- [ ] Nonce verification in any AJAX handler (DEV_PHP)
```

**This checklist will be verified at WF_VERIFY. Do not skip this step.**

⛔ **WRITING CODE WITHOUT A PROJECT COMPLIANCE CHECKLIST = working without guardrails.**

### 3. Design With Explicit File Paths

Define which files/components are affected:

- Files to be modified (with what changes)
- Files to be created (with justification — include naming convention source from DEV_*)
- Data flow between components
- Integration points (what must be registered/wired for new components to work)
- Test coverage plan

### 4. Architecture Compliance Check

**Answer the generic layer questions:**

- [ ] Which layer OWNS this logic?
- [ ] Am I putting logic in the correct layer?
- [ ] Am I following the project's documented data flow pattern?

**Then verify the project compliance checklist (from Step 2c) is consistent with the design.**

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

### Project-Specific Violations

- Any item in the compliance checklist (Step 2c) that the design would violate
- New files that don't follow naming conventions from DEV_* memories
- Missing integration points (registration, enqueuing, discovery)

**Read REF_* memories (codebase-shared) for correct patterns.**

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
