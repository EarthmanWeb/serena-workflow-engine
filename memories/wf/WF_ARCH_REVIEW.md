# WF_ARCH_REVIEW - Design, Compliance Review & Approval

> **On step WF_ARCH_REVIEW**

---

## Purpose

Single planning gate for **major** code changes: design, architecture compliance, parallel execution assessment, and the single question + consent gate.

## When This State Is Entered

WF_ARCH_REVIEW is NOT entered for every code change. WF_CLASSIFY Step 3b (Architecture Review Necessity Check) routes here only when the task is a **new feature, a major module addition, touches >5 files, or crosses 3+ layers**. Minor patches to existing functionality (≤5 files, no open design questions) skip this state and go straight to WF_EXECUTE with `arch_review_skipped: true`.

If you arrived here for something that is actually a trivial one-file patch, that is a mis-route — note it and proceed; do not pad a small change with ceremony.

---

## SPEC Fast-Path

If a `SPEC_*` memory is already loaded (check WM), skip steps 1-4 and reference the SPEC by name. Proceed to step 5 (Parallel Execution Assessment) and then the Single Question + Consent Gate.
If no SPEC loaded, follow steps 1-4 below.

> Note: steps 1, 2, 2b, and 2c describe the heavy memory load + compliance-checklist derivation. This load is DEFERRED from WF_CLASSIFY and now runs AFTER the questions are answered — see "Heavy Memory Load (After Questions Answered)" in the Single Question + Consent Gate section. Use steps 1-2c there for the procedure, scoped to the chosen approach.

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

## Single Question + Consent Gate

This is the ONE question gate in the workflow. There is NO separate "May I proceed?" approval step — answering the questions IS consent.

### Template Check (For New Files)

Before proposing new files, check existing patterns in similar files, read relevant SYS_*/REF_* memory for the file type, and follow established feature conventions from FEATURE_[KEY].

### Consent-Skip Check (Initial Prompt Blanket Consent)

Check whether the INITIAL user prompt already gave blanket consent — phrases like "get it done", "continue to completion", "don't stop till finished", "run to completion", "don't ask me questions", "no questions". (This corresponds to the `auto_approve` / `no_questions` flags noted at WF_CLASSIFY.)

- **If blanket consent was given:** SKIP the final validate-or-continue question. If "no questions" was requested, also derive the most logical choices for any design/approach questions yourself and proceed on that initial-prompt consent — do NOT call `AskUserQuestion`. Go directly to `WF_EXECUTE` (or `WF_SWARM_ORCHESTRATE` if parallel agents planned).
- **Otherwise:** assemble and ask the single question call below.

### Assemble & Ask ONE Question Call

Gather every design/approach/blocker question this task raises into a SINGLE `AskUserQuestion` call. The FINAL question in that call MUST be exactly the validate-or-continue question shown below.

```javascript
AskUserQuestion({
  questions: [
    // ...any design / approach / blocker questions for this task, each with options...
    {
      question: 'Would you like me to validate the final plan with you, or shall I continue through completion?',
      header: 'Plan',
      options: [
        {
          label: 'Validate the plan with me first',
          description: 'Present the assembled plan and wait for explicit go-ahead before implementing',
        },
        {
          label: 'Continue through to completion',
          description: 'Proceed straight through implementation without a separate plan review',
        },
      ],
      multiSelect: false,
    },
  ],
});
```

Answering this call IS consent. There is no second approval prompt.

### Heavy Memory Load (After Questions Answered)

Now that the approach is chosen, run the heavy memory load DEFERRED from WF_CLASSIFY — scoped to the chosen approach's files:

1. `read_memory("feature/FEATURE_DEV_STANDARDS")` and the relevant `DEV_*` / `DOM_*` / `SYS_*` memories for the languages/layers the chosen approach touches (steps 2 / 2b above).
2. Derive the `## Compliance Checklist` in WM (step 2c) from those memories.

This load is scoped to the chosen approach — do not sweep memories for approaches that were not selected.

### Handle Final-Question Response

| Selection                          | Action                                                                                                          |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| "Validate the plan with me first"  | Present the assembled plan (files table, constraints, data flow, test plan, parallel rec). Get explicit go-ahead, then read `WF_EXECUTE` (or `WF_SWARM_ORCHESTRATE` if parallel planned). |
| "Continue through to completion"   | Read `WF_EXECUTE` directly (or `WF_SWARM_ORCHESTRATE` if parallel planned).                                     |
| Consent-skip (blanket consent)     | Read `WF_EXECUTE` directly (or `WF_SWARM_ORCHESTRATE` if parallel planned).                                     |

A non-design blocker that surfaces here may still use `WF_CLARIFY` (the reusable ask-user subroutine for non-design blockers only). Design/approach questions are never routed there — they belong in the single question call above.

---

## Routing

| Condition                                       | Next Step              |
| ----------------------------------------------- | ---------------------- |
| Consent-skip (blanket consent, simple)          | `WF_EXECUTE`           |
| Consent-skip (blanket consent, parallel needed) | `WF_SWARM_ORCHESTRATE` |
| "Continue through to completion" (simple)       | `WF_EXECUTE`           |
| "Continue through to completion" (parallel)     | `WF_SWARM_ORCHESTRATE` |
| "Validate the plan" → go-ahead (simple)         | `WF_EXECUTE`           |
| "Validate the plan" → go-ahead (parallel)       | `WF_SWARM_ORCHESTRATE` |
| Non-design blocker                              | `WF_CLARIFY`           |

Update WM via `/swe-wm-update --from WF_ARCH_REVIEW` before transitioning.
