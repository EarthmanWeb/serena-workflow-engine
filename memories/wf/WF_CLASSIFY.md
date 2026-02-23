# WF_CLASSIFY - Classify, Detect Requirements & Load Features

> **On step WF_CLASSIFY**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## 🚫 ANTI-SKIP BLOCK - THIS STEP IS MANDATORY

**YOU CANNOT GO TO WF_EXECUTE WITHOUT COMPLETING THIS STEP.**

If you are thinking of skipping to WF_EXECUTE because:

- ❌ "The task is simple" - **Complexity doesn't matter. ALL tasks go through WF_CLASSIFY.**
- ❌ "I already know what to do" - **You still need to load features and verify.**
- ❌ "WM already has the feature" - **Having the key != having loaded the memory.**
- ❌ "I'll load features later" - **NO. Features are loaded HERE, at the END of this step.**

**The ONLY valid paths to WF_EXECUTE are:**

1. WF_CLASSIFY → WF_LOAD_FEATURE → WF_ARCH_REVIEW → WF_EXECUTE (code changes)
2. WF_CLASSIFY → WF_LOAD_FEATURE → WF_ARCH_REVIEW → WF_SWARM_ORCHESTRATE → WF_EXECUTE (swarm)
3. WF_CLASSIFY → WF_LOAD_FEATURE → WF_EXECUTE (operational tasks only)

**There is NO direct path from WF_CLASSIFY to WF_EXECUTE.**

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

**If requirements detected:** Note them in WM for validation at WF_LOAD_FEATURE (where they'll be checked against DOM_* memories).

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

These tasks need **feature context** (endpoints, config keys, data formats) but do **not modify source code**. They skip arch review at WF_LOAD_FEATURE.
→ **WF_LOAD_FEATURE** (mark task as `operational` in WM)

#### Simple Tasks (Code Changes, 1-2 files)

- Bug fix in one file
- Small code change
- Documentation update
- Single function modification
  → **WF_LOAD_FEATURE**

#### Medium Tasks (Code Changes, 2-5 files)

**⚠️ MANDATORY: Development Standards**

**For tasks involving code changes**, read dev standards:

```
mcp__plugin_swe_serena__read_memory("REF_DEV_STANDARDS")
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
  → **WF_LOAD_FEATURE** (swarm assessment happens at WF_ARCH_REVIEW)

#### Large Tasks (Potential Swarm)

When ANY of these apply, note `swarm_candidate: true` in WM:

- **Scale**: 6+ files affected OR 3+ architectural layers
- **Parallel Work**: Independent subtasks that can run concurrently
- **Research-Heavy**: Requires analyzing multiple areas simultaneously
- **Complexity**: Multi-domain coordination needed
- **Keywords**: "swarm", "parallel agents", "multi-agent", "hive-mind", "ruv-swarm", "DAA"

**⚠️ MANDATORY: Load FEATURE_SWARM:**

```
mcp__plugin_swe_serena__read_memory("FEATURE_SWARM")
```

→ **WF_LOAD_FEATURE** (swarm routing confirmed at WF_ARCH_REVIEW after feature context is loaded)

---

## 🛑 BLOCKING GATE: Feature Loading (STEP 4)

**⛔ YOU CANNOT PROCEED TO ANY NEXT STEP WITHOUT COMPLETING THIS SECTION.**

### 4a. Read Feature Registry

```
mcp__plugin_swe_serena__read_memory("INDEX_FEATURES")
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
mcp__plugin_swe_serena__read_memory("FEATURE_[KEY]")
```

**⛔ SKIPPING FEATURE MEMORY LOAD = WORKFLOW VIOLATION**

### 4d. Load Supporting Memories

From each FEATURE_[KEY], load relevant:

| Memory Type                     | Purpose                 |
| ------------------------------- | ----------------------- |
| `DOM_[KEY]`                     | Domain-specific context |
| `ARCH_[KEY]` or shared `ARCH_*` | Architecture patterns   |
| `INDEX_[KEY]_*`                 | File/symbol indexes     |

### 4e. Update WM with Features

```markdown
## Affected Features

- **Primary**: [KEY1] - [reason]
- **Secondary**: [KEY2] - [reason]
```

---

## Feature Loading Verification Checklist

**Before proceeding to ANY next step, confirm ALL boxes:**

- [ ] Read INDEX_FEATURES
- [ ] Identified ALL features for this task
- [ ] Called `read_memory("FEATURE_[KEY]")` for EACH feature
- [ ] Loaded relevant DOM_*, ARCH_*, INDEX_* memories
- [ ] Updated WM with feature information
- [ ] Requirements noted (or "none — pure implementation")

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
- **Return Step**: WF_LOAD_FEATURE
- **Invocation Mode**: workflow
```

### 2. Inform User

```
> Routing to /research skill for exploration. Will return to WF_LOAD_FEATURE on completion.
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
2. Did you call `read_memory("FEATURE_[KEY]")` for EACH feature? (YES/NO)
3. Did you update WM with features? (YES/NO)
4. Did you detect requirements (or note "none")? (YES/NO)

**If ANY answer is NO: STOP and do it NOW.**

### Routing Table

| Condition             | MUST Read Next   |
| --------------------- | ---------------- |
| Request unclear       | `WF_CLARIFY`     |
| Test debugging needed | `WF_DEBUG_TDD`   |
| Research only         | `WF_RESEARCH`    |
| **All other tasks**   | `WF_LOAD_FEATURE` |

**ALL implementation tasks (simple, medium, large, operational) go to WF_LOAD_FEATURE.**
Swarm assessment happens later at WF_ARCH_REVIEW where feature context is available.

1. Determine which condition applies
2. Read that WF_* memory NOW
3. Report the new step to user

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**
**SKIPPING FEATURE LOADING = WORKFLOW VIOLATION**
**GOING DIRECTLY TO WF_EXECUTE = WORKFLOW VIOLATION**

## ⚠️ MANDATORY: WM UPDATE

**Before transitioning, invoke `/swe-wm-update --from WF_CLASSIFY`** — provides the
step-specific checklist ensuring no fields are missed. Do NOT manually update WM
without it.

**SKIPPING WM UPDATE = WORKFLOW VIOLATION**

[CRITICAL: Did you load ALL FEATURE_[KEY] memories? Are you on a WF_* workflow step? Did you report on it?]
