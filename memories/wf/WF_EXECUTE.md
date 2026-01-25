# WF_EXECUTE - Do The Work

> **On step WF_EXECUTE**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## 🛑 BLOCKING: Feature Memory Verification

**BEFORE ANY WORK, you MUST verify feature memories were loaded.**

### 1. Check WM for Feature Key(s)

Look at your WM's `Feature Key(s)` field (e.g., `- **Feature Key(s)**: [KEY1], [KEY2]`)

### 2. Verify FEATURE_[KEY] Was Read for EACH

**Ask yourself:** "Did I read `FEATURE_[KEY]` for every key listed in my WM?"

| If... | Then... |
|-------|---------|
| You read all feature memories | ✅ Continue to WM section |
| You skipped feature loading | ❌ **STOP - Read them NOW** |
| WM has no Feature Key(s) | ❌ **STOP - Go to WF_START** |

### 3. If Features Not Loaded - DO THIS NOW

```
# First, get the feature registry
mcp__plugin_swe_serena__read_memory("INDEX_FEATURES")

# Then, for EACH feature key in WM:
mcp__plugin_swe_serena__read_memory("FEATURE_[KEY1]")
mcp__plugin_swe_serena__read_memory("FEATURE_[KEY2]")
# ... continue for ALL features in WM
```

**Only proceed after ALL feature memories are loaded.**

**⛔ EXECUTING WITHOUT FEATURE MEMORIES = WORKFLOW VIOLATION**

You CANNOT understand the architecture, file locations, testing patterns, or coding standards without the feature memory. Skipping this leads to:
- Writing code in wrong locations
- Missing architectural patterns
- Ignoring feature-specific requirements
- Creating inconsistent implementations

---

## ⚠️ MANDATORY: WM

**Before starting any work, verify WM exists and is current.**

**BEFORE any WM update, you MUST read:**
```
mcp__plugin_swe_serena__read_memory("REF_WM")
```

If WM is stale or doesn't reflect current task:
```
mcp__plugin_swe_serena__write_memory("WM_<timestamp>_<descriptor>", "<content>")
```

Echo to chat: `📋 Working Memory: WM_<filename>`

**WM must be updated:**
- Before starting significant work
- After completing each subtask
- When task state changes
- Before transitioning to another WF_* step

**⛔ NEVER do single-field state edits. See REF_WM for anti-patterns.**

---

## BEFORE ANY WORK - Architecture Check

**Is this multi-layer work?** (touches >1 architectural layer as defined in FEATURE_[KEY])

If YES, you MUST first:
```
mcp__plugin_swe_serena__read_memory("ARCH_INDEX")
```
Then for EACH layer involved, read:
```
# Feature-specific (from FEATURE_[KEY]):
mcp__plugin_swe_serena__read_memory("SYS_[SYSTEM]")     # For system components

# Codebase-shared:
mcp__plugin_swe_serena__read_memory("REF_[PATTERN]")    # For patterns/standards
mcp__plugin_swe_serena__read_memory("REF_DEV_STANDARDS") # For coding standards
```

**DO NOT write code until you have read the relevant memories.**

---

## For Multi-Layer Work

### Step 1: Read Architecture Documentation
- Read ARCH_INDEX
- Read relevant SYS_* memories for system understanding
- Read relevant DOM_* memories for domain understanding
- Understand the data flow pattern from ARCH_INDEX

### Step 2: Implementation
For each layer, follow patterns from relevant SYS_* and REF_* memories.

### Step 3: Testing
- Read REF_TESTING for testing patterns
- Implement tests for functional code
- Run tests and verify (commands from FEATURE_[KEY] or REF_DEV_STANDARDS)

---

## For Single-Layer Work

Use Serena tools directly:
1. `mcp__plugin_swe_serena__find_symbol` - locate code
2. `mcp__plugin_swe_serena__get_symbols_overview` - file structure
3. `Edit` / `mcp__plugin_swe_serena__replace_symbol_body` - make changes

---

## For Swarm-Coordinated Work

**If swarm was initialized at WF_SWARM_ORCHESTRATE:**

### Execute with Parallel Agents

```javascript
// Launch work agents via Claude Code Task tool (ALL in ONE message)
Task({ subagent_type: "Explore", run_in_background: true, prompt: "..." })
Task({ subagent_type: "general-purpose", run_in_background: true, prompt: "..." })

// Monitor swarm status (non-blocking)
mcp__claude-flow__swarm_status({})

// Store progress to memory
mcp__claude-flow__memory_usage({ action: "store", namespace: "swarm", key: "progress", value: "..." })

// Collect results (blocking)
TaskOutput({ task_id: "...", block: true })
```

### Swarm Coordination During Execution

- **Track agent IDs** in WM
- **Update swarm memory** after each completed subtask
- **Monitor for failures** and reassign if needed
- **Synchronize findings** between agents via memory

**⛔ NEVER run CLI init commands** - use MCP tools only. See `WF_SWARM_ORCHESTRATE`.

**Read `REF_SWARM_PATTERNS` for detailed patterns.**

---

## Rules

- Only make approved changes
- Do not expand scope without asking
- Tests are required for functional code
- Integration tests are required for components that interact with external systems

## MANDATORY NEXT STEP

**YOU ARE NOT FINISHED.** After each significant action:

| Condition | MUST Read Next |
|-----------|----------------|
| Created/modified file | `WF_CHECKPOINT` |
| Completed a phase | `WF_CHECKPOINT` |
| All work done (including tests) | `WF_VERIFY` |

1. Determine which condition applies
2. **UPDATE WM** with current progress
3. Read that WF_* memory NOW
4. Report the new step to user

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**
**SKIPPING WM UPDATE = WORKFLOW VIOLATION**

[CRITICAL: Did you load FEATURE memories? Did you update WM? Are you on a WF_* workflow step? Did you report on it?]
