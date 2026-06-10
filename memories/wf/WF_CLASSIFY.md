# WF_CLASSIFY - Classify, Detect Requirements, Load Features & Route

> **On step WF_CLASSIFY**

---

## This Step Cannot Be Skipped

All tasks go through WF_CLASSIFY — it loads feature memories, detects requirements, and routes correctly. Valid paths to WF_EXECUTE:

- Code changes: WF_CLASSIFY → WF_ARCH_REVIEW → WF_EXECUTE
- Operational tasks only: WF_CLASSIFY → WF_EXECUTE

Having a feature key in WM is not the same as having loaded the FEATURE_[KEY] memory. Features are loaded HERE, in Step 4.

---

## Steps

### 1. Clarity Check

- Request unclear → go to WF_CLARIFY
- Request clear → continue

### 2. Detect Requirements

Scan user message for behavioral/UX requirements ("should", "must", "needs to", corrections to current behavior, UX preferences). If found, note them in WM for validation at Step 5. If none, continue.

### 2b. Auto-Approve Detection

Scan for intent to skip the WF_ARCH_REVIEW approval gate (e.g., "just do it", "don't stop for approval", "run unattended", or similar phrasing).

- **If detected:** Note `auto_approve: true` in WM. The plan is still presented at WF_ARCH_REVIEW but the approval gate is skipped.
- **If not detected:** Normal flow — approval required at WF_ARCH_REVIEW.

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

#### Code Changes (any size)

- Bug fixes, feature additions, refactoring, documentation updates — anything that modifies source files
- Route: **WF_ARCH_REVIEW** (after feature loading in Step 4)

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

## Step 4: Feature Loading (Gate)

Complete all substeps before proceeding.

### 4a. Read Feature Registry

```
read_memory("index/INDEX_FEATURES")
```

### 4b. Identify All Affected Features

Scan request for feature indicators: explicit names, file paths spanning feature directories, cross-cutting concerns, domain terminology.

### 4c. Load FEATURE_[KEY] for Each Feature

For every feature identified, call:

```
read_memory("feature/FEATURE_[KEY]")
```

### 4d. Load Supporting Memories

After loading each FEATURE_[KEY], read its Related Memories table for linked DOM_*/SYS_*/ARCH_*/INDEX_* memories.

Then discover additional relevant memories:

```
list_memories(topic="dom")   # Domain behavior patterns
list_memories(topic="ref")   # Reference documentation
list_memories(topic="dev")   # Development standards
```

For each result related to the task's feature(s) or affected area, call `read_memory()`.

Prioritize:

- DOM_* memories for the feature's domain (behavioral rules, data contracts)
- REF_* memories for coding patterns and tooling
- DEV_* memories for language-specific standards (DEV_PHP, DEV_JAVASCRIPT, etc.)
- ARCH_* for cross-layer architecture

| Memory Type | When to Read | Discovery Method |
|-------------|-------------|-----------------|
| DOM_* | Always — domain patterns | FEATURE_[KEY] table + list_memories(topic="dom") |
| REF_* | Always — coding standards | FEATURE_[KEY] table + list_memories(topic="ref") |
| DEV_* | Code changes — language standards | list_memories(topic="dev") |
| SYS_* | System/infrastructure work | FEATURE_[KEY] table |
| ARCH_* | Multi-layer work | FEATURE_[KEY] table |

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
   - **CONFLICTING requirement** — route to WF_CLARIFY; ask user before overriding domain rules
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
| Request unclear | WF_CLARIFY |
| Research only | WF_RESEARCH |
| Test debugging needed | WF_DEBUG_TDD |
| Conflicting requirement | WF_CLARIFY |
| Operational task (no code changes) | WF_EXECUTE |
| Code changes (any size) | WF_ARCH_REVIEW |
| Gherkin spec authoring (explicit) | `/swe-gherkin-spec` |
| Gherkin TDD from existing spec | `/swe-gherkin-dev` |

1. Determine which condition applies
2. Read that WF_* memory
3. Report the new step to user

Update WM via /swe-wm-update --from WF_CLASSIFY before transitioning.
