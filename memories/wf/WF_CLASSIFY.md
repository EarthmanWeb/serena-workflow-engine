# WF_CLASSIFY - Analyze Request

> **On step WF_CLASSIFY**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## 🚫 ANTI-SKIP BLOCK - THIS STEP IS MANDATORY

**YOU CANNOT GO TO WF_EXECUTE WITHOUT COMPLETING THIS STEP.**

If you are thinking of skipping to WF_EXECUTE because:
- ❌ "The task is simple" - **Complexity doesn't matter. ALL code changes go through WF_CLASSIFY.**
- ❌ "I already know what to do" - **You still need to load features and verify.**
- ❌ "WM already has the feature" - **Having the key != having loaded the memory.**
- ❌ "I'll load features later" - **NO. Features are loaded HERE, at the END of this step.**

**The ONLY valid paths to WF_EXECUTE are:**
1. WF_CLASSIFY → WF_DETECT_REQ → WF_LOAD_FEATURE → /arch-review → WF_EXECUTE
2. WF_CLASSIFY → WF_PLAN_ARCHITECTURE → WF_EXECUTE
3. WF_CLASSIFY → WF_SWARM_ORCHESTRATE → WF_EXECUTE

**There is NO direct path from WF_START to WF_EXECUTE.**

---

## Execute These Steps

### 1. Is the request clear?
- No → go to WF_CLARIFY
- Yes → continue

### 2. Assess task complexity:

#### Research Tasks (Skill-Based)
- Questions about how code works
- Exploring patterns or architecture
- Finding files or symbols
- No code changes needed
→ **Invoke `/research` skill** (see Skill Invocation below)

#### Debugging Tasks (Skill-Based)
- Tests failing on one environment but passing on another
- Behavior differences between environments
- Test-driven debugging needed
→ **Invoke `/debug-tdd` skill** (see Skill Invocation below)

#### Simple Tasks (Single Agent)
- Bug fix in one file
- Small code change
- Documentation update
- Single function modification
→ **WF_DETECT_REQ**

#### Medium Tasks (Architecture Required)

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
→ **WF_PLAN_ARCHITECTURE**

#### Large Tasks (Swarm Orchestration Required)

**⚠️ MANDATORY RESEARCH BEFORE ROUTING:**
```
mcp__plugin_swe_serena__read_memory("_INDEX")  # Full navigation hub
```

Use swarms when ANY of these apply:
- **Scale**: 6+ files affected OR 3+ architectural layers
- **Parallel Work**: Independent subtasks that can run concurrently
- **Research-Heavy**: Requires analyzing multiple areas simultaneously
- **Complexity**: Multi-domain coordination needed
→ **WF_SWARM_ORCHESTRATE**

---

## 🛑 BLOCKING GATE: Feature Loading (STEP 3)

**⛔ YOU CANNOT PROCEED TO ANY NEXT STEP WITHOUT COMPLETING THIS SECTION.**

### 3a. Read Feature Registry
```
mcp__plugin_swe_serena__read_memory("INDEX_FEATURES")
```

### 3b. Identify ALL Affected Features

Scan request for feature indicators:
- Explicit feature names (e.g., "blocks and context providers")
- File paths spanning multiple feature directories
- Cross-cutting concerns (e.g., "theme templates that use blocks")
- Domain terminology from multiple features

### 3c. 🛑 MANDATORY: Load FEATURE_[KEY] for EACH Feature

**For EVERY feature identified, you MUST call:**
```
mcp__plugin_swe_serena__read_memory("FEATURE_[KEY]")
```

**Examples (replace [KEY] with actual feature key from INDEX_FEATURES):**
```
# Single feature:
mcp__plugin_swe_serena__read_memory("FEATURE_[KEY]")

# Multiple features:
mcp__plugin_swe_serena__read_memory("FEATURE_[KEY1]")
mcp__plugin_swe_serena__read_memory("FEATURE_[KEY2]")
mcp__plugin_swe_serena__read_memory("FEATURE_[KEY3]")
```

**⛔ SKIPPING FEATURE MEMORY LOAD = WORKFLOW VIOLATION**

### 3d. Load Supporting Memories

From each FEATURE_[KEY], load relevant:
| Memory Type | Purpose |
|-------------|---------|
| `DOM_[KEY]` | Domain-specific context |
| `ARCH_[KEY]` or shared `ARCH_*` | Architecture patterns |
| `INDEX_[KEY]_*` | File/symbol indexes |

### 3e. Update WM with Features

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

**If ANY box is unchecked: STOP and complete it NOW.**

---

## Swarm Type Selection Guide

| Task Type | Recommended Swarm | Topology |
|-----------|-------------------|----------|
| Codebase analysis | Claude-Flow | mesh |
| Feature implementation | Claude-Flow | hierarchical |
| Research + implement | RUV-Swarm DAA | mesh |
| Pattern discovery | RUV-Swarm + neural | adaptive |
| Distributed refactoring | Hive-Mind | hierarchical |
| Consensus-required tasks | Hive-Mind | mesh |

**Read `REF_SWARM_PATTERNS` for detailed swarm usage patterns.**

---

## Skill Invocation Protocol

When routing to a workflow-aware skill (e.g., `/research`):

### 1. Set Workflow Context in WM
```markdown
## Workflow Context
- **Calling Step**: WF_CLASSIFY
- **Feature Key**: [from INDEX_FEATURES or detected]
- **Session ID**: [from WM filename]
- **Return Step**: WF_DETECT_REQ
- **Invocation Mode**: workflow
```

### 2. Inform User
```
> Routing to /research skill for exploration. Will return to WF_DETECT_REQ on completion.
```

### 3. Handle Skill Return

| Status | Action |
|--------|--------|
| `success` / `success_with_findings` | Continue to `return_step` |
| `needs_clarification` | Go to `WF_CLARIFY` |
| `blocked` | Go to `WF_CLARIFY` |
| `escalate_complexity` | Go to `WF_SWARM_ORCHESTRATE` |

---

## 🛑 BLOCKING GATE: WM Rename (STEP 4)

**⛔ YOU CANNOT TRANSITION TO THE NEXT STATE WITH A PLACEHOLDER WM NAME.**

### 4a. Check WM Filename

If your WM still has the `_session` suffix (e.g., `WM_abc12345_session`), you MUST rename it before proceeding.

### 4b. Choose Meaningful Descriptor

Based on the task you've now classified, choose a 2-4 word snake_case descriptor:
- Examples: `auth_fix`, `block_tests`, `theme_refactor`, `api_endpoint`, `cron_debug`
- Should describe WHAT you're working on, not the workflow state

### 4c. Rename WM File

```bash
# Rename from placeholder to task-specific
mv .serena/memories/WM_{session}_session.md .serena/memories/WM_{session}_{descriptor}.md
```

Then update the WM content to reflect the new name:
```python
mcp__plugin_swe_serena__write_memory("WM_{session}_{descriptor}", "<full content with updated header>")
```

### 4d. Confirm Rename

Echo to chat: `📋 Working Memory renamed: WM_{session}_{descriptor}`

**⛔ TRANSITIONING WITH `_session` SUFFIX = WORKFLOW VIOLATION**

---

## ⛔ MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** Before transitioning:

### Pre-Transition Verification

**Answer these questions:**
1. Did you load INDEX_FEATURES? (YES/NO)
2. Did you call `read_memory("FEATURE_[KEY]")` for EACH feature? (YES/NO)
3. Did you update WM with features? (YES/NO)
4. **Is your WM renamed from `_session` to a meaningful descriptor?** (YES/NO)

**If ANY answer is NO: STOP and do it NOW.**

**⛔ WM STILL HAS `_session` SUFFIX? You MUST rename it before transitioning!**

### Routing Table

| Condition | MUST Read Next |
|-----------|----------------|
| Request unclear | `WF_CLARIFY` |
| Test debugging needed | `WF_DEBUG_TDD` |
| Large task (swarm needed) | `WF_SWARM_ORCHESTRATE` |
| Needs architecture | `WF_PLAN_ARCHITECTURE` |
| Simple change | `WF_DETECT_REQ` |

1. Determine which condition applies
2. Read that WF_* memory NOW
3. Report the new step to user

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**
**SKIPPING FEATURE LOADING = WORKFLOW VIOLATION**
**GOING DIRECTLY TO WF_EXECUTE = WORKFLOW VIOLATION**

## ⚠️ MANDATORY: WM UPDATE

**Before transitioning to another state, you MUST:**
1. Update `## Progress` with completed steps
2. Update `## Affected Features` with loaded features
3. Verify `## Workflow Context` is current

**SKIPPING WM UPDATE = WORKFLOW VIOLATION**

[CRITICAL: Did you load ALL FEATURE_[KEY] memories? Are you on a WF_* workflow step? Did you report on it?]
