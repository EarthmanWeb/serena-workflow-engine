# WF_CLASSIFY - Classify, Detect Requirements, Load Features & Route

> **On step WF_CLASSIFY**

---

## First Post-Init Entry State

WF_CLASSIFY is the first workflow state entered after init (WF_INIT → CLAUDE_OBLIGATIONS → WF_CLASSIFY). The WM file and the init sentinel are created automatically by the hook when the session transitions into WF_CLASSIFY — the agent does NOT create them.

---

## This Step Cannot Be Skipped

All tasks go through WF_CLASSIFY — it loads feature memories, detects requirements, and routes correctly. Valid paths to WF_EXECUTE:

- Major code changes: WF_CLASSIFY → WF_ARCH_REVIEW → WF_EXECUTE
- Minor code changes (see Step 3b): WF_CLASSIFY → WF_EXECUTE (arch review skipped)
- Operational tasks only: WF_CLASSIFY → WF_EXECUTE

Having a feature key in WM is not the same as having loaded the FEATURE_[KEY] memory. Features are loaded HERE, in Step 4.

---

## Steps

### 1. Clarity Check

Only a HARD blocker that prevents classification at all routes to WF_CLARIFY here — e.g. the request cannot be classified because you cannot tell which of two features it targets. Approach/design ambiguity and approach-style conflicts are NOT resolved here; they are deferred to the single question gate at WF_ARCH_REVIEW.

- Cannot classify at all (hard blocker) → go to WF_CLARIFY
- Otherwise → continue (defer any approach/design clarification to WF_ARCH_REVIEW)

### 2. Detect Requirements

Scan user message for behavioral/UX requirements ("should", "must", "needs to", corrections to current behavior, UX preferences). If found, note them in WM for validation at Step 5. If none, continue.

### 2b. Auto-Approve Detection

Scan for **explicit** intent to skip the WF_ARCH_REVIEW approval gate. Only these narrow phrases qualify:
- "skip approval" / "skip the approval gate"
- "don't ask for approval" / "don't stop for approval"
- "auto-approve" / "auto approve"

Ambiguous phrases like "just do it", "continue through to completion", "run unattended", or "go ahead" do **NOT** qualify — these express urgency or agreement with a specific action, not blanket approval-gate bypass.

- **If explicit opt-out detected:** Note `auto_approve: true` in WM. The plan is still presented at WF_ARCH_REVIEW but the approval gate is skipped.
- **If not detected (default):** Normal flow — approval required at WF_ARCH_REVIEW.

### 2c. Command & Skill Identification

Before planning manual implementation, check if an existing command or skill handles this task.

**Scan locations:**

1. **System-reminder skills list** (already in context) — match user intent against skill descriptions
2. **Project-level commands** — `.claude/commands/*.md`, `.claude/skills/*/SKILL.md`, `~/.claude/commands/*.md`, `~/.claude/skills/*/SKILL.md`
3. **Plugin commands** — from installed plugin `commands/` directories

**Matching:** Use fuzzy intent matching. Respect `disable-model-invocation` (user-only skills).

**If match found:** Note `matched_skill: plugin:skill-name` or `matched_command: /command-name` in WM, then invoke it. Commands/skills may handle routing themselves.

**If no match:** Continue to Step 3.

### 2d. Gherkin Spec Detection

Check if the task involves new feature development or feature additions that should have Gherkin specs:

1. **Explicit Gherkin request** — user asks to write specs, create `.feature` files, or do BDD/TDD from specs
   - Note `gherkin_spec: true` in WM
   - Route directly to `/swe-gherkin-spec` (spec authoring) or `/swe-gherkin-dev` (TDD from existing spec)

2. **New feature development** — user describes new functionality to build
   - Check if SPEC_* memories exist for the affected feature: `list_memories(topic="spec")`
   - If no specs exist: note `gherkin_spec_needed: true` in WM (enforced at WF_ARCH_REVIEW)

3. **Feature addition** — user adds behavior to an existing feature that has Gherkin specs
   - Check for existing `.feature` files: `Glob(pattern="tests/specs/*[feature-key]*.feature")`
   - If specs exist for this feature: note `gherkin_spec_update: true` in WM (enforced at WF_VERIFY)

### 3. Task Type Assessment

#### Research (no code changes, exploration only)

- Questions about how code works, exploring patterns, finding files/symbols
- Route: **WF_RESEARCH**

#### Debugging (test-driven)

- Failing tests, behavior differences between environments, test-driven debugging
- Route: **WF_DEBUG_TDD**

#### Operational (no code changes, execution only)

- Run shell/WP-CLI commands, send HTTP requests, check database state, run test suites, verify deployments
- These need feature context but do not modify source code. Skip arch review.
- Route: **WF_EXECUTE** (after feature loading in Step 4)

#### Code Changes

- Bug fixes, feature additions, refactoring, documentation updates — anything that modifies source files
- Route depends on the **Architecture Review Necessity Check** (Step 3b): minor patches skip arch review and go straight to **WF_EXECUTE**; new features, major module additions, or >5-file changes go to **WF_ARCH_REVIEW**.
- Route: **WF_ARCH_REVIEW** or **WF_EXECUTE** per Step 3b (after feature loading in Step 4)

#### Parallel Agents (6+ files OR 3+ architectural layers)

When the task involves file reads/edits at scale with independent subtasks that can run concurrently:

- Note `parallel_agents: true` in WM
- These use Claude Code `Agent` tool with `run_in_background: true` and optionally `isolation: "worktree"` for edit conflicts
- Route: **WF_ARCH_REVIEW** (parallel agent plan defined there)

#### Ruflo Swarm (cognitive-only, consensus, no file access)

Niche use case for reasoning, spec writing, architecture evaluation, or consensus decisions that do NOT need file access. Most tasks should use parallel agents instead.

- Note `swarm_candidate: true` in WM
- Load swarm config: `read_memory("feature/FEATURE_SWARM")`
- Route: **WF_ARCH_REVIEW** (swarm routing confirmed there after feature context loaded)

---

## Step 3b: Architecture Review Necessity Check (Code Changes Only)

Not every code change needs a full architecture review. Decide whether this task may skip WF_ARCH_REVIEW and go straight to WF_EXECUTE.

**REQUIRES WF_ARCH_REVIEW if ANY of these is true:**

- New feature (net-new functionality, not a change to existing behavior)
- Major module addition to an existing feature (new class/subsystem/integration surface)
- Touches **more than 5 files**
- Touches **3+ architectural layers**, or `parallel_agents` / `swarm_candidate` was noted
- `gherkin_spec_needed: true` was noted at Step 2d (new feature needing specs)

**MAY SKIP WF_ARCH_REVIEW → route directly to WF_EXECUTE if ALL of these hold:**

- It is a **minor patch to existing functionality** (bug fix, small refactor, copy/doc tweak, config value, localized behavior change) — NOT a new feature or major module addition
- It touches **5 files or fewer**
- Any design/approach questions are already resolved (the request is unambiguous, or the answers are obvious from the loaded primary feature memory) — there is nothing to ask at a question gate

**When skipping arch review:**

- Note `arch_review_skipped: true` and the reason in WM
- You MUST still load the relevant DEV_*/DOM_* standards for the files you will touch (the load that WF_ARCH_REVIEW would have done) before editing — load them at the start of WF_EXECUTE, scoped to the touched files
- If, once in WF_EXECUTE, the change turns out to be larger than classified (e.g. it now spans >5 files or adds a module), STOP and route back to WF_ARCH_REVIEW

**When in doubt, do NOT skip** — route to WF_ARCH_REVIEW. The skip is for genuinely small, well-understood changes only.

---

## Step 4: Feature Loading (Gate)

Complete all substeps before proceeding.

### 4a. Read Feature Registry

```
read_memory("index/INDEX_FEATURES")
```

### 4b. Identify All Affected Features

Scan request for feature indicators: explicit names, file paths spanning feature directories, cross-cutting concerns, domain terminology.

### 4c. Load Only the PRIMARY FEATURE_[KEY]

Load ONLY the single primary `FEATURE_[KEY]` needed to route this task:

```
read_memory("feature/FEATURE_[KEY]")
```

This is enough to classify and route. Do NOT load secondary features' full memories here, and do NOT read their Related Memories tables yet.

### 4d. Defer the Broad Supporting-Memory Sweep

The heavy `list_memories(topic="dom")` / `list_memories(topic="ref")` / `list_memories(topic="dev")` sweep and the "read each related memory" expansion are DEFERRED to keep this early stage light:

- **Code changes** → the dom/ref/dev sweep and DEV/DOM/SYS compliance-checklist load happens at **WF_ARCH_REVIEW**, scoped to the chosen approach.
- **Operational tasks** → load only what WF_EXECUTE needs, when it needs it.

Do NOT run the broad sweep or read "each related memory" here. Only INDEX_FEATURES (4a) and the single primary FEATURE_[KEY] (4c) are loaded at WF_CLASSIFY.

### 4e. Update WM with Features

```markdown
## Affected Features

- **Primary**: [KEY1] - [reason]
- **Secondary**: [KEY2] - [reason]
```

---

## Step 5: Validate Requirements Against Domain Memories

If Step 2 detected requirements, compare them to loaded domain memories:

1. **Check for existing domain memory:** Look for DOM_* memories that relate to detected requirements.
2. **Compare:**
   - **NEW requirement** — note it; will be added to domain memory after implementation
   - **CONFLICTING requirement** — note the conflict in WM; do NOT route to WF_CLARIFY here. Approach/design conflicts (including overriding a documented domain rule) are deferred to the single question gate at WF_ARCH_REVIEW, where they are asked once alongside all other design questions.
   - **EXISTING requirement** — acknowledge; domain already documents this behavior
3. **No requirements detected at Step 2:** Skip this step.

---

## Step 6: Note Key Information for Implementation

From loaded feature memories, record: key file paths, class/function names for Serena lookups, testing commands, architecture patterns to follow.

---

## Skill Invocation Protocol

When routing to a workflow-aware skill (e.g., `/research`):

1. **Set workflow context in WM:** Calling step, feature key, session ID, return step, invocation mode
2. **Inform user:** `> Routing to /research skill. Will return to WF_CLASSIFY on completion.`
3. **Handle return:**

| Status | Action |
|--------|--------|
| `success` / `success_with_findings` | Continue to return step |
| `needs_clarification` | Go to WF_CLARIFY |
| `blocked` | Go to WF_CLARIFY |

---

## Routing Table

| Condition | Route To |
|-----------|----------|
| Hard blocker — cannot classify (e.g. which of two features) | WF_CLARIFY |
| Research only | WF_RESEARCH |
| Test debugging needed | WF_DEBUG_TDD |
| Approach/design ambiguity or conflicting requirement | Defer to WF_ARCH_REVIEW (single question gate) |
| Operational task (no code changes) | WF_EXECUTE |
| Code change — minor patch to existing functionality, ≤5 files, no open questions (Step 3b) | WF_EXECUTE (`arch_review_skipped: true`) |
| Code change — new feature, major module addition, >5 files, or 3+ layers (Step 3b) | WF_ARCH_REVIEW |
| Gherkin spec authoring (explicit) | `/swe-gherkin-spec` |
| Gherkin TDD from existing spec | `/swe-gherkin-dev` |

1. Determine which condition applies
2. Read that WF_* memory
3. Report the new step to user

Update WM via /swe-wm-update --from WF_CLASSIFY before transitioning.
