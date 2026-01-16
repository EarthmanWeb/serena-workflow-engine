# WF_EXECUTE - Do The Work

> **On step WF_EXECUTE**

OUTPUT THE ABOVE LINE IMMEDIATELY. Do not read further until you have reported your step to the user.

---

## ⚠️ MANDATORY: WORKING_MEMORY

**Before starting any work, verify WORKING_MEMORY exists and is current.**

If WORKING_MEMORY is stale or doesn't reflect current task:
```
mcp__serena__write_memory("WORKING_MEMORY_<timestamp>_<descriptor>", "<content>")
```

Echo to chat: `Working Memory: WORKING_MEMORY_<filename>`

**WORKING_MEMORY must be updated:**
- Before starting significant work
- After completing each subtask
- When task state changes
- Before transitioning to another WF_* step

---

## BEFORE ANY WORK - Architecture Check

**Is this multi-layer work?** (touches >1 architectural layer as defined in FEATURE_[KEY])

If YES, you MUST first:
```
mcp__serena__read_memory("ARCH_INDEX")
```
Then for EACH layer involved, read:
```
# Feature-specific (from FEATURE_[KEY]):
mcp__serena__read_memory("SYS_[SYSTEM]")     # For system components

# Codebase-shared:
mcp__serena__read_memory("REF_[PATTERN]")    # For patterns/standards
mcp__serena__read_memory("REF_DEV_STANDARDS") # For coding standards
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
1. `mcp__serena__find_symbol` - locate code
2. `mcp__serena__get_symbols_overview` - file structure
3. `Edit` / `mcp__serena__replace_symbol_body` - make changes

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

- **Track agent IDs** in WORKING_MEMORY
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
2. **UPDATE WORKING_MEMORY** with current progress
3. Read that WF_* memory NOW
4. Report the new step to user

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**
**SKIPPING WORKING_MEMORY UPDATE = WORKFLOW VIOLATION**

[CRITICAL: Did you update WORKING_MEMORY? Are you on a WF_* workflow step? Did you report on it?]
