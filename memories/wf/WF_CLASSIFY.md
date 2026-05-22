# WF_CLASSIFY - Classify, Detect Requirements, Load Features & Route

> **On step WF_CLASSIFY**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## 🚫 ANTI-SKIP BLOCK - THIS STEP IS MANDATORY

**YOU CANNOT GO TO WF_EXECUTE WITHOUT COMPLETING THIS STEP.**

If you are thinking of skipping to WF_EXECUTE because:

- ❌ "The task is simple" - **Complexity doesn't matter. ALL tasks go through WF_CLASSIFY.**
- ❌ "I already know what to do" - **You still need to load features and verify.**
- ❌ "WM already has the feature" - **Having the key != having loaded the memory.**
- ❌ "I'll load features later" - **NO. Features are loaded HERE, in this step.**

**The ONLY valid paths to WF_EXECUTE are:**

1. WF_CLASSIFY → WF_ARCH_REVIEW → WF_EXECUTE (code changes)
2. WF_CLASSIFY → WF_ARCH_REVIEW → WF_SWARM_ORCHESTRATE → WF_EXECUTE (swarm)
3. WF_CLASSIFY → WF_EXECUTE (operational tasks only)

**There is NO direct path from WF_CLASSIFY to WF_EXECUTE for code changes.**

---

## Execute These Steps

### 1. Is the request clear?

- No → go to WF_CLARIFY
- Yes → continue

### 2. Detect Requirements (inline)

Scan user message for behavioral/UX requirements:

- "should", "must", "needs to", "has to"
- "users want", "behavior should be"
- "always do X", "never do Y"
- Corrections to current behavior
- UX preferences or constraints

**If requirements detected:** Note them in WM for validation at Step 5 (where they'll be checked against DOM_* memories).

**If no requirements:** Pure implementation task — continue.

### 2b. Auto-Approve Detection

**Scan user's initial message for intent to skip the WF_ARCH_REVIEW approval gate.**

Fuzzy-match for phrases indicating the user wants uninterrupted execution:

- "complete without stopping" / "finish without stopping"
- "don't stop for anything" / "do not stop"
- "don't ask for approval" / "do not ask for approval"
- "no approval needed" / "skip approval"
- "just do it" / "just execute" / "just implement"
- "proceed without asking" / "don't ask me"
- "run unattended" / "autonomous mode"
- "without interruption" / "no interruptions"

**Match loosely** — the user may phrase it differently. The intent is: "I trust you to proceed through the entire workflow without blocking for my approval at WF_ARCH_REVIEW."

**If detected:** Note `auto_approve: true` in WM. The plan will still be **presented** at WF_ARCH_REVIEW for transparency, but the `AskUserQuestion` approval gate will be skipped.

**If not detected:** Normal flow — approval will be required at WF_ARCH_REVIEW.

### 2c. Command & Skill Identification

**Before planning manual implementation, check if an existing command or skill already handles this task. Commands and skills encode tested procedures — always prefer them over ad-hoc work.**

#### How Claude Code's Skill System Works

Claude Code uses **description-based LLM matching**: each skill has a `description` and optional `when_to_use` field in its YAML frontmatter. At runtime, Claude receives all skill descriptions in an `<available_skills>` listing embedded in the Skill tool and uses natural language understanding to match user intent. There is no keyword index or classifier — it's pure LLM reasoning over descriptions.

#### What to Scan

**1. System-reminder skills list** (already in context)

The system-reminder at conversation start contains a section:
> "The following skills are available for use with the Skill tool:"

This lists ALL skills from all installed plugins with their descriptions. Scan this list against the user's request. Skills are namespaced as `plugin:skill-name` (e.g., `swe:swe-workflow-research`).

**2. Project-level commands** (may not be in the skills list)

Projects can define their own slash commands that are NOT plugin skills:

```
.claude/commands/*.md      — Project-level commands
~/.claude/commands/*.md    — User-level commands
.claude/skills/*/SKILL.md  — Project-level skills
~/.claude/skills/*/SKILL.md — User-level skills
```

If the user's request doesn't match any plugin skill, scan these directories for project-specific commands. Read the file's frontmatter `description` field to understand purpose.

**3. Plugin commands** (from installed plugin `commands/` directories)

Plugin commands are invoked via `/command-name` and expand into prompt templates. They may handle operational tasks like status checks, resets, or scaffolding.

#### How to Match

1. **Scan the skills list in context** — match user intent against skill descriptions using natural language understanding (same mechanism Claude Code uses natively)
2. **Check project commands** — if no skill matches, scan project command directories for `.md` files with matching purposes
3. **Fuzzy intent matching** — "debug the tests" → `debug-tdd` skill; "review architecture" → `arch-review` skill; "check status" → a status command
4. **Respect `disable-model-invocation`** — skills with this flag are user-only; do not auto-invoke them

#### Record & Route

1. **If match found** — note in WM: `matched_skill: plugin:skill-name` or `matched_command: /command-name`
2. **Invoke matched skill** — `Skill({ skill: "plugin:skill-name", args: "..." })` — commands/skills may handle routing themselves
3. **If NO match** — continue to Step 3 (task type assessment) for manual routing

**Always prefer an existing command/skill over manual implementation.** They encode best practices, handle edge cases, and are maintained with the project.

### 3. Assess task type and complexity:

#### Research Tasks (Skill-Based)

- Questions about how code works
- Exploring patterns or architecture
- Finding files or symbols
- No code changes needed
  → **WF_RESEARCH**

#### Debugging Tasks (Skill-Based)

- Tests failing on one environment but passing on another
- Behavior differences between environments
- Test-driven debugging needed
  → **WF_DEBUG_TDD**

#### Operational Tasks (No Code Changes)

- Send test HTTP request / curl to an endpoint
- Run WP-CLI or shell commands
- Check database state or config values
- Test a webhook with sample data
- Run existing test suites
- Verify deployment or environment state

These tasks need **feature context** (endpoints, config keys, data formats) but do **not modify source code**. They skip arch review.
→ Mark task as `operational` in WM, route to **WF_EXECUTE** after feature loading (Step 4)

#### Simple Tasks (Code Changes, 1-2 files)

- Bug fix in one file
- Small code change
- Documentation update
- Single function modification
  → **WF_ARCH_REVIEW** (after feature loading in Step 4)

#### Medium Tasks (Code Changes, 2-5 files)

**⚠️ MANDATORY: Development Standards**

**For tasks involving code changes**, read dev standards:

```
mcp__plugin_swe_serena__read_memory("feature/FEATURE_DEV_STANDARDS")
```

**⚠️ MANDATORY RESEARCH BEFORE ROUTING:**

```
mcp__plugin_swe_serena__read_memory("_INDEX")  # Full navigation hub
```

- Read ALL relevant: `INDEX_*`, `ARCH_*`, `SYS_*`, `DOM_*`, `REF_*`, `SPEC_*`
- Check skills: `/research`, `/arch-review`, test skills for helpers
- Use `mcp__plugin_swe_serena__find_symbol()` to verify existing implementations

**NO IMAGINATION. NO INFERENCE. NO GUESSING. EVERYTHING IS DOCUMENTED.**

- New feature spanning 2-5 files
- Refactoring existing code structure
- Multi-layer design changes
  → **WF_ARCH_REVIEW** (swarm assessment happens there)

#### Large Tasks — Parallel Agents (File-Access Work)

When the task involves file reads/edits at scale, use Claude Code's built-in `Agent` tool — NOT Ruflo:

- **Scale**: 6+ files affected OR 3+ architectural layers
- **Parallel Work**: Independent subtasks that can run concurrently (e.g., update multiple modules, research multiple areas)
- **All agents need file access**: grep, read, edit, glob, Serena tools

Note `parallel_agents: true` in WM. These tasks use Claude Code `Agent` tool with `run_in_background: true` and optionally `isolation: "worktree"` for edit conflicts. No Ruflo ceremony needed.

→ **WF_ARCH_REVIEW** (parallel agent plan defined there)

#### Large Tasks — Swarm (Cognitive-Only / Consensus)

When the task involves reasoning, planning, or consensus that does NOT need file access:

- **Reasoning-only**: Spec writing, framework comparison, architecture evaluation
- **Multi-iteration**: Round 1 findings shape Round 2 prompts (DAA tracking)
- **Consensus**: Architecture decisions requiring agreement (Hive-Mind)
- **Keywords**: "swarm", "hive-mind", "ruflo", "DAA", "consensus"

Note `swarm_candidate: true` in WM.

**⚠️ MANDATORY: Load FEATURE_SWARM:**

```
mcp__plugin_swe_serena__read_memory("feature/FEATURE_SWARM")
```

→ **WF_ARCH_REVIEW** (swarm routing confirmed there after feature context is loaded)

---

## 🛑 BLOCKING GATE: Feature Loading (STEP 4)

**⛔ YOU CANNOT PROCEED TO ANY NEXT STEP WITHOUT COMPLETING THIS SECTION.**

### 4a. Read Feature Registry

```
mcp__plugin_swe_serena__read_memory("index/INDEX_FEATURES")
```

### 4b. Identify ALL Affected Features

Scan request for feature indicators:

- Explicit feature names (e.g., "blocks and context providers")
- File paths spanning multiple feature directories
- Cross-cutting concerns (e.g., "theme templates that use blocks")
- Domain terminology from multiple features

### 4c. 🛑 MANDATORY: Load FEATURE_[KEY] for EACH Feature

**For EVERY feature identified, you MUST call:**

```
mcp__plugin_swe_serena__read_memory("feature/FEATURE_[KEY]")
```

**⛔ SKIPPING FEATURE MEMORY LOAD = WORKFLOW VIOLATION**

### 4d. Load Supporting Memories

**Read the Related Memories / Domains / Systems table inside each FEATURE_[KEY] you loaded.** These tables list the specific DOM_*, SYS_*, ARCH_*, and INDEX_* memories that are relevant to that feature. Follow those links — don't guess which memories to load.

| Memory Type                         | When to Read                               | How to Find                              |
| ----------------------------------- | ------------------------------------------ | ---------------------------------------- |
| `dom/DOM_[KEY]_*`                   | Always - contains domain-specific patterns | Listed in FEATURE_[KEY] "Domains" table  |
| `sys/SYS_[SYSTEM]`                  | For system/infrastructure work             | Listed in FEATURE_[KEY] "Systems" table  |
| `arch/ARCH_INDEX` or `arch/ARCH_*`  | For multi-layer architecture work          | Listed in FEATURE_[KEY] or INDEX_FEATURES|
| `index/INDEX_[KEY]_*`              | For locating specific files/classes        | Listed in FEATURE_[KEY] "Indexes" table  |
| `ref/REF_[TOPIC]`                   | For coding standards and patterns          | Codebase-shared, check INDEX_FEATURES    |

### 4e. Update WM with Features

```markdown
## Affected Features

- **Primary**: [KEY1] - [reason]
- **Secondary**: [KEY2] - [reason]
```

---

## Step 5: Validate Requirements Against Domain Memories

**If Step 2 detected requirements** (noted in WM), compare them to loaded domain memories:

1. **Check for existing domain memory:**
   Look for `DOM_*` memories that relate to the detected requirements.

2. **Compare requirement to domain knowledge:**
   - **NEW requirement**: Note it — will be added to domain memory after implementation
   - **CONFLICTING requirement**: Route to `WF_CLARIFY` — ask user before overriding existing domain rules
   - **EXISTING requirement**: Acknowledge — the domain already documents this behavior

3. **If no requirements were detected at Step 2**: Skip this — pure implementation task.

---

## Step 6: Note Key Information for Implementation

From the feature memories, record in your understanding:

- Key file paths and directories
- Important class/function names for Serena lookups
- Testing commands
- Architecture patterns to follow

---

## Feature Loading Verification Checklist

**Before proceeding to ANY next step, confirm ALL boxes:**

- [ ] Read INDEX_FEATURES
- [ ] Identified ALL features for this task
- [ ] Called `read_memory("feature/FEATURE_[KEY]")` for EACH feature
- [ ] Loaded relevant DOM_*, SYS_*, REF_*, ARCH_*, INDEX_* memories
- [ ] Updated WM with feature information
- [ ] Requirements validated against domain memories (or "none — pure implementation")

**If ANY box is unchecked: STOP and complete it NOW.**

---

## Skill Invocation Protocol

When routing to a workflow-aware skill (e.g., `/research`):

### 1. Set Workflow Context in WM

```markdown
## Workflow Context

- **Calling Step**: WF_CLASSIFY
- **Feature Key**: [from INDEX_FEATURES or detected]
- **Session ID**: [from WM filename]
- **Return Step**: WF_CLASSIFY
- **Invocation Mode**: workflow
```

### 2. Inform User

```
> Routing to /research skill for exploration. Will return to WF_CLASSIFY on completion.
```

### 3. Handle Skill Return

| Status                              | Action                    |
| ----------------------------------- | ------------------------- |
| `success` / `success_with_findings` | Continue to `return_step` |
| `needs_clarification`               | Go to `WF_CLARIFY`        |
| `blocked`                           | Go to `WF_CLARIFY`        |

---

## ⛔ MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before transitioning:

### Pre-Transition Verification

**Answer these questions:**

1. Did you load INDEX_FEATURES? (YES/NO)
2. Did you call `read_memory("feature/FEATURE_[KEY]")` for EACH feature? (YES/NO)
3. Did you update WM with features? (YES/NO)
4. Did you detect requirements (or note "none")? (YES/NO)
5. Did you validate requirements against domain memories? (YES/NO)

**If ANY answer is NO: STOP and do it NOW.**

### Routing Table

| Condition                | MUST Read Next   |
| ------------------------ | ---------------- |
| Request unclear          | `WF_CLARIFY`     |
| Test debugging needed    | `WF_DEBUG_TDD`   |
| Research only            | `WF_RESEARCH`    |
| Conflicting requirement  | `WF_CLARIFY`     |
| **Operational tasks**    | `WF_EXECUTE`     |
| **All code change tasks**| `WF_ARCH_REVIEW` |

Swarm assessment happens at WF_ARCH_REVIEW where feature context is available.

1. Determine which condition applies
2. Read that WF_* memory NOW
3. Report the new step to user

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**
**SKIPPING FEATURE LOADING = WORKFLOW VIOLATION**
**GOING DIRECTLY TO WF_EXECUTE FOR CODE CHANGES = WORKFLOW VIOLATION**

## ⚠️ MANDATORY: WM UPDATE

**Before transitioning, invoke `/swe-wm-update --from WF_CLASSIFY`** — provides the
step-specific checklist ensuring no fields are missed. Do NOT manually update WM
without it.

**SKIPPING WM UPDATE = WORKFLOW VIOLATION**

[CRITICAL: Did you load ALL FEATURE_[KEY] memories? Are you on a WF_* workflow step? Did you report on it?]
