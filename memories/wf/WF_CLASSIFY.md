---
name: WF_CLASSIFY
description: Classify the task, detect requirements, load the primary feature memory, and route. First workflow state after init. Classification and routing only — no task work.
metadata:
  type: workflow
---

# WF_CLASSIFY — Classify, Detect Requirements, Load Primary Feature, Route

> **On step WF_CLASSIFY**

## Entry & Non-Skippable

- WF_CLASSIFY is the FIRST workflow state after init (`WF_INIT` → `CLAUDE_OBLIGATIONS` → `WF_CLASSIFY`).
- The hook creates the WM file and init sentinel automatically on transition into WF_CLASSIFY. Do NOT create them.
- ALL tasks pass through WF_CLASSIFY. NEVER skip it — it loads feature memories, detects requirements, and routes.
- A feature key in WM is NOT a loaded `FEATURE_[KEY]` memory. Features load HERE (Step 4).

Valid paths to WF_EXECUTE:

- Major code change: `WF_CLASSIFY` → `WF_ARCH_REVIEW` → `WF_EXECUTE`
- Minor code change (Step 3b): `WF_CLASSIFY` → `WF_EXECUTE` (arch review skipped)
- Operational task: `WF_CLASSIFY` → `WF_EXECUTE`

## ⛔ NO Task Work in This State

WF_CLASSIFY is classification and routing ONLY. The edit gate (`swe_pre_edit_validate.py`) HARD-BLOCKS every Edit/Write/Serena-edit call here. Task work now is wasted — you redo it after transition.

Allowed (classification inputs only):

- `read_memory` for `INDEX_FEATURES` and the single primary `FEATURE_[KEY]` (Step 4)
- Read the user request and existing WM context
- Lightweight `list_memories` / `Glob` STRICTLY to detect specs (Step 2d) or the targeted feature

NEVER here — defer ALL to WF_EXECUTE or WF_ARCH_REVIEW:

- Do NOT read the target source/doc file you intend to change
- Do NOT run `find_symbol` / `get_symbols_overview` / `search_for_pattern` to scope the edit
- Do NOT plan the exact change, draft the diff, or decide `needle`/`repl` values
- Do NOT call `Edit`, `Write`, `replace_content`, `replace_symbol_body`, or any edit tool — HARD-BLOCKED here

> Reading the file you are about to edit is task work, not classification. You do NOT need file contents to classify task type or count files touched — the user request and the primary FEATURE memory suffice. If you catch yourself opening the target file or reaching for an edit tool: STOP, finish routing, transition first.

## Steps

### 1. Clarity Check

- Cannot classify AT ALL (hard blocker, e.g. cannot tell which of two features is targeted) → `WF_CLARIFY`
- Otherwise → continue. NEVER resolve approach/design ambiguity or approach conflicts here — defer to the single question gate at `WF_ARCH_REVIEW`.

### 2. Detect Requirements

Scan the user message for behavioral/UX requirements ("should", "must", "needs to", corrections to current behavior, UX preferences). If found, note in WM for Step 5. If none, continue.

### 2b. Auto-Approve Detection

Detect EXPLICIT intent to skip the WF_ARCH_REVIEW approval gate. ONLY these phrases qualify:

- "skip approval" / "skip the approval gate"
- "don't ask for approval" / "don't stop for approval"
- "auto-approve" / "auto approve"

"just do it", "continue through to completion", "run unattended", "go ahead" do NOT qualify — urgency/agreement, not blanket bypass.

- Explicit opt-out detected → note `auto_approve: true` in WM. Plan is still presented at WF_ARCH_REVIEW; approval gate is skipped.
- Not detected (default) → approval required at WF_ARCH_REVIEW.

### 2c. Command & Skill Identification

Before planning manual implementation, check for an existing command or skill that handles the task.

Scan locations:

1. System-reminder skills list (already in context) — match intent against skill descriptions
2. Project/user commands — `.claude/commands/*.md`, `.claude/skills/*/SKILL.md`, `~/.claude/commands/*.md`, `~/.claude/skills/*/SKILL.md`
3. Plugin commands — installed plugin `commands/` directories

- Use fuzzy intent matching. Respect `disable-model-invocation` (user-only skills).
- Match found → note `matched_skill: plugin:skill-name` or `matched_command: /command-name` in WM, then invoke it. Commands/skills may handle routing themselves.
- No match → continue to Step 3.

### 2d. Gherkin Spec Detection

1. Explicit Gherkin request (user asks to write specs, create `.feature` files, or do BDD/TDD from specs):
   - Note `gherkin_spec: true` in WM
   - Route to `/swe-gherkin-spec` (authoring) or `/swe-gherkin-dev` (TDD from existing spec)
2. New feature development (user describes new functionality to build):
   - Check SPEC_* memories for the feature: `list_memories(topic="spec")`
   - No specs exist → note `gherkin_spec_needed: true` in WM (enforced at WF_ARCH_REVIEW)
3. Feature addition to an existing feature with Gherkin specs:
   - Check `.feature` files: `Glob(pattern="tests/specs/*[feature-key]*.feature")`
   - Specs exist → note `gherkin_spec_update: true` in WM (enforced at WF_VERIFY)

### 3. Task Type Assessment

| Task type | Signals | Route |
|-----------|---------|-------|
| Research (no code changes, exploration only) | How code works, exploring patterns, finding files/symbols | `WF_RESEARCH` |
| Debugging (test-driven) | Failing tests, behavior differs between environments, test-driven debugging | `WF_DEBUG_TDD` |
| Operational (no code changes, execution only) | Run shell/WP-CLI, HTTP requests, check DB state, run test suites, verify deployments — needs feature context, modifies no source. Skip arch review | `WF_EXECUTE` (after Step 4) |
| Code change | Bug fix, feature addition, refactor, doc update — modifies source | `WF_ARCH_REVIEW` or `WF_EXECUTE` per Step 3b (after Step 4) |
| Parallel agents (6+ files OR 3+ architectural layers) | Reads/edits at scale with independent concurrent subtasks. Note `parallel_agents: true`; use `Agent` tool with `run_in_background: true` and optionally `isolation: "worktree"` for edit conflicts | `WF_ARCH_REVIEW` |
| Ruflo swarm (cognitive-only, consensus, no file access) | Niche: reasoning, spec writing, arch evaluation, consensus WITHOUT file access. Most tasks use parallel agents instead. Note `swarm_candidate: true`; `read_memory("feature/FEATURE_SWARM")` | `WF_ARCH_REVIEW` (swarm routing confirmed there) |

### 3b. Architecture Review Necessity Check (Code Changes Only)

REQUIRES `WF_ARCH_REVIEW` if ANY is true:

- New feature (net-new functionality, not a change to existing behavior)
- Major module addition to an existing feature (new class/subsystem/integration surface)
- Touches MORE than 5 files
- Touches 3+ architectural layers, OR `parallel_agents` / `swarm_candidate` was noted
- `gherkin_spec_needed: true` noted at Step 2d

MAY SKIP `WF_ARCH_REVIEW` → route directly to `WF_EXECUTE` ONLY if ALL hold:

- Minor patch to EXISTING functionality (bug fix, small refactor, copy/doc tweak, config value, localized behavior change) — NOT a new feature or major module addition
- Touches 5 files or fewer
- All design/approach questions already resolved (request unambiguous, or answers obvious from the loaded primary feature memory) — nothing to ask at a question gate

When skipping arch review:

- Note `arch_review_skipped: true` and the reason in WM
- You MUST still load the relevant DEV_*/DOM_* standards for the touched files (the load WF_ARCH_REVIEW would have done) at the START of WF_EXECUTE, scoped to touched files
- If in WF_EXECUTE the change turns out larger than classified (>5 files or adds a module), STOP and route back to `WF_ARCH_REVIEW`

When in doubt, do NOT skip → route to `WF_ARCH_REVIEW`. Skip is for genuinely small, well-understood changes only.

## Step 4: Feature Loading (Gate)

Complete all substeps before proceeding.

### 4a. Read Feature Registry

`read_memory("index/INDEX_FEATURES")`

### 4b. Identify All Affected Features

Scan request for feature indicators: explicit names, file paths spanning feature directories, cross-cutting concerns, domain terminology.

### 4c. Load ONLY the Primary FEATURE_[KEY]

- `read_memory("feature/FEATURE_[KEY]")` — the single primary feature needed to route.
- Do NOT load secondary features' full memories here. Do NOT read their Related Memories tables yet.

### 4d. Defer the Broad Supporting-Memory Sweep

Do NOT run `list_memories(topic="dom")` / `list_memories(topic="ref")` / `list_memories(topic="dev")` or the "read each related memory" expansion here.

- Code changes → dom/ref/dev sweep and DEV/DOM/SYS compliance-checklist load happens at `WF_ARCH_REVIEW`, scoped to the chosen approach.
- Operational tasks → load only what WF_EXECUTE needs, when it needs it.
- At WF_CLASSIFY load ONLY INDEX_FEATURES (4a) and the single primary FEATURE_[KEY] (4c).

### 4e. Update WM with Features

```markdown
## Affected Features

- **Primary**: [KEY1] - [reason]
- **Secondary**: [KEY2] - [reason]
```

## Step 5: Validate Requirements Against Domain Memories

If Step 2 detected requirements, compare them to loaded domain memories:

1. Check for DOM_* memories relating to the detected requirements.
2. Compare:
   - NEW requirement → note it; added to domain memory after implementation
   - CONFLICTING requirement → note the conflict in WM. Do NOT route to WF_CLARIFY. Approach/design conflicts (including overriding a documented domain rule) are deferred to the single question gate at `WF_ARCH_REVIEW`, asked once alongside all design questions.
   - EXISTING requirement → acknowledge; domain already documents this behavior
3. No requirements detected at Step 2 → skip this step.

## Step 6: Note Key Information for Implementation

From loaded feature memories, record: key file paths, class/function names for Serena lookups, testing commands, architecture patterns to follow.

## Skill Invocation Protocol

When routing to a workflow-aware skill (e.g. `/research`):

1. Set workflow context in WM: calling step, feature key, session ID, return step, invocation mode
2. Inform user: `> Routing to /research skill. Will return to WF_CLASSIFY on completion.`
3. Handle return:

| Status | Action |
|--------|--------|
| `success` / `success_with_findings` | Continue to return step |
| `needs_clarification` | `WF_CLARIFY` |
| `blocked` | `WF_CLARIFY` |

## Routing Table

| Condition | Route To |
|-----------|----------|
| Hard blocker — cannot classify (e.g. which of two features) | `WF_CLARIFY` |
| Research only | `WF_RESEARCH` |
| Test debugging needed | `WF_DEBUG_TDD` |
| Approach/design ambiguity or conflicting requirement | Defer to `WF_ARCH_REVIEW` (single question gate) |
| Operational task (no code changes) | `WF_EXECUTE` |
| Code change — minor patch to existing functionality, ≤5 files, no open questions (Step 3b) | `WF_EXECUTE` (`arch_review_skipped: true`) |
| Code change — new feature, major module addition, >5 files, or 3+ layers (Step 3b) | `WF_ARCH_REVIEW` |
| Gherkin spec authoring (explicit) | `/swe-gherkin-spec` |
| Gherkin TDD from existing spec | `/swe-gherkin-dev` |

1. Determine which condition applies
2. Read that WF_* memory
3. Report the new step to user

Update WM via `/swe-wm-update --from WF_CLASSIFY` before transitioning.
