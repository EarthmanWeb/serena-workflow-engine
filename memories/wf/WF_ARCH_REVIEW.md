# WF_ARCH_REVIEW - Design, Compliance Review & Approval

> **On step WF_ARCH_REVIEW**

---

## Purpose

Single planning gate for all code changes: design, architecture compliance, parallel execution assessment, and user approval.

---

## SPEC Fast-Path

If a `SPEC_*` memory is already loaded (check WM), skip steps 1-4 and reference the SPEC by name. Proceed to step 5 (Parallel Execution Assessment) and then Approval.
If no SPEC loaded, follow steps 1-4 below.

## Gherkin Spec Gate

If WM contains `gherkin_spec_needed: true` (set at WF_CLASSIFY step 2d):

1. **Check for existing specs:** `Glob(pattern="tests/specs/**/*.feature")`
2. **If no specs exist for this feature**, prompt:

```
> This feature has no Gherkin BDD specs. Writing specs before implementation ensures
> testable requirements and enables TDD.
>
> Options:
> - [A] Write specs now with /swe-gherkin-spec (recommended)
> - [B] Skip specs and proceed to implementation
```

3. **If user chooses [A]:** Invoke `/swe-gherkin-spec` with the feature key. On return, the SPEC_* memory will be loaded and the SPEC Fast-Path applies.
4. **If user chooses [B]:** Clear `gherkin_spec_needed` from WM and continue to Step 1.

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

For each layer in the design, read its rules:

```
mcp__plugin_swe_serena__read_memory("sys/SYS_[SYSTEM]")     # System documentation (feature-specific)
mcp__plugin_swe_serena__read_memory("ref/REF_[TOPIC]")      # Reference patterns (codebase-shared)
mcp__plugin_swe_serena__read_memory("dom/DOM_[DOMAIN]")     # Domain-specific context (feature-specific)
```

### 2b. Load Development Standards

Read the standards index, then read each relevant standard for languages/layers this task touches.

```
mcp__plugin_swe_serena__read_memory("feature/FEATURE_DEV_STANDARDS")  # Index of all DEV_* standards
```

| Task involves...       | Read                 |
| ---------------------- | -------------------- |
| PHP classes/functions  | `dev/DEV_PHP`        |
| JavaScript/jQuery      | `dev/DEV_JAVASCRIPT` |
| SCSS/CSS               | `dev/DEV_SCSS`       |
| Blade/templates        | `dev/DEV_BLADEONE`   |
| Tests                  | `dev/DEV_TESTS`      |
| Cross-language patterns| `dev/DEV_PATTERNS`   |

If a `DEV_*` memory doesn't exist for a language, skip it but note the gap.

### 2c. Derive Project Compliance Checklist

From the DEV_*, DOM_*, SYS_*, and FEATURE_[KEY] memories loaded above, extract the concrete rules that apply to this task. Write them as a checklist in WM under `## Compliance Checklist`.

Scan each loaded memory for rules relevant to the files you'll touch: naming conventions, boilerplate, security patterns, registration contracts, integration points, required interfaces, testing commands, and file patterns.

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

This checklist is verified at WF_VERIFY.

### 3. Design With Explicit File Paths

Define which files/components are affected:

- Files to modify (with what changes)
- Files to create (with justification and naming convention source from DEV_*)
- Data flow between components
- Integration points (registration/wiring for new components)
- Test coverage plan

### 4. Architecture Compliance Check

Answer the generic layer questions:

- [ ] Which layer OWNS this logic?
- [ ] Am I putting logic in the correct layer?
- [ ] Am I following the project's documented data flow pattern?

Verify the compliance checklist (from Step 2c) is consistent with the design.

## STOP CONDITIONS

If any of these apply, revise the design:

### General Layer Violations

- Business logic in presentation layer (views/templates should only display data)
- Presentation layer calling data layer directly (should go through business logic)
- Data access layer containing business rules (should be in service/business layer)
- Cross-cutting concerns scattered instead of centralized

### Presentation Layer

- View contains complex logic beyond simple conditionals
- View has data transformations that belong in business layer
- View imports services/functions directly instead of using provided context

### Project-Specific Violations

- Any item in the compliance checklist (Step 2c) that the design would violate
- New files that don't follow naming conventions from DEV_* memories
- Missing integration points (registration, enqueuing, discovery)

Read REF_* memories for correct patterns.

---

### 5. Parallel Execution Assessment

If the task affects 6+ files OR 3+ layers, consider parallel agents:
- Use Claude Code `Agent` tool with `run_in_background: true`
- Use `isolation: "worktree"` when agents may edit overlapping files
- Use `model: "sonnet"` for implementation, `"haiku"` for read-only
- Note `parallel_agents: true` in WM

For cognitive-only coordination (consensus, reasoning without file access):
- Route to WF_SWARM_ORCHESTRATE for Ruflo setup (niche use case)

If thresholds not met, proceed as single-agent implementation.

---

## Approval

### Template Check (For New Files)

Before proposing new files, check existing patterns in similar files, read relevant SYS_*/REF_* memory for the file type, and follow established feature conventions from FEATURE_[KEY].

### Present Plan

Present your plan including:

- Files to modify/create table
- Key architectural constraints applied
- Data flow description
- Test coverage plan
- Parallel execution recommendation (if applicable)

### Auto-Approve Bypass Check

Check WM for `auto_approve: true` (set at WF_CLASSIFY step 2b).

If `auto_approve: true`: the plan has been presented above. Skip the `AskUserQuestion` gate and go directly to `WF_EXECUTE` (or `WF_SWARM_ORCHESTRATE` if parallel agents planned).

If `auto_approve` is not set or false: continue to the approval gate below.

### Get Approval

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

| User Selection      | Action                                                          |
| ------------------- | --------------------------------------------------------------- |
| "Yes, proceed"      | Read `WF_EXECUTE` (or `WF_SWARM_ORCHESTRATE` if parallel planned) |
| "No, let's discuss" | Read `WF_CLARIFY`                                               |
| "Modify approach"   | Re-run `WF_ARCH_REVIEW` with modified design                    |
| Custom text (Other) | Parse feedback, go to `WF_CLARIFY`                              |

---

## Routing

| Condition                             | Next Step              |
| ------------------------------------- | ---------------------- |
| Auto-approve bypass (simple)          | `WF_EXECUTE`           |
| Auto-approve bypass (parallel needed) | `WF_SWARM_ORCHESTRATE` |
| User approves (simple implementation) | `WF_EXECUTE`           |
| User approves (parallel needed)       | `WF_SWARM_ORCHESTRATE` |
| Needs redesign / user modifies        | `WF_ARCH_REVIEW`       |
| User declines / needs clarification   | `WF_CLARIFY`           |

Update WM via `/swe-wm-update --from WF_ARCH_REVIEW` before transitioning.
