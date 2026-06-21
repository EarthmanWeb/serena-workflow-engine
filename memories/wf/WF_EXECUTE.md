# WF_EXECUTE - Do The Work

> **On step WF_EXECUTE**

---

## Feature Memory Verification

Before starting work, confirm feature memories are loaded.

Check WM for `Feature Key(s)`. For each key, verify you have read `FEATURE_[KEY]`.

| If...                         | Then...                     |
| ----------------------------- | --------------------------- |
| All feature memories loaded   | Continue below               |
| Feature memories not loaded   | Read them now (see below)   |
| WM has no Feature Key(s)      | Go to WF_CLASSIFY           |

```
mcp__plugin_swe_serena__read_memory("index/INDEX_FEATURES")
mcp__plugin_swe_serena__read_memory("feature/FEATURE_[KEY1]")
mcp__plugin_swe_serena__read_memory("feature/FEATURE_[KEY2]")
```

Proceed only after all feature memories are loaded.

---

## WM Check

Verify WM exists and reflects the current task before starting work.

If WM is stale or missing, invoke `/swe-wm-update --from WF_EXECUTE`.

Update WM (via the skill):
- Before starting significant work
- After completing each subtask
- When task state changes
- Before transitioning to another WF_* step

---

## Before Starting Work

If multi-layer (touches >1 architectural layer):

```
mcp__plugin_swe_serena__read_memory("arch/ARCH_INDEX")
```

For each layer, load context:

```
mcp__plugin_swe_serena__read_memory("sys/SYS_[SYSTEM]")      # System docs
mcp__plugin_swe_serena__read_memory("ref/REF_[PATTERN]")     # Coding patterns
mcp__plugin_swe_serena__read_memory("dom/DOM_[DOMAIN]")      # Domain behavior
mcp__plugin_swe_serena__read_memory("feature/FEATURE_DEV_STANDARDS")  # Dev standards index
```

Then load language-specific DEV_* for affected languages:

```
mcp__plugin_swe_serena__read_memory("dev/DEV_PHP")           # If touching PHP
mcp__plugin_swe_serena__read_memory("dev/DEV_JAVASCRIPT")    # If touching JS
```

Do not write code until relevant memories are loaded.

---

## Multi-Layer Implementation

1. Read architecture docs (ARCH_INDEX, SYS_*, DOM_*)
2. Understand data flow from ARCH_INDEX
3. Implement each layer following patterns from SYS_* and REF_*
4. Read REF_TESTING, implement tests, run and verify

---

## Single-Layer Implementation

Use Serena tools directly:

1. `mcp__plugin_swe_serena__find_symbol` - locate code
2. `mcp__plugin_swe_serena__get_symbols_overview` - file structure
3. `Edit` / `mcp__plugin_swe_serena__replace_symbol_body` - make changes

---

## Parallel Execution

For tasks with independent subtasks, use Claude Code Agent tool:

```javascript
Agent({ description: "Task A", run_in_background: true, model: "sonnet",
  isolation: "worktree",
  prompt: "You are a swarm agent. BYPASS WF_INIT. [task]..." })
```

- Launch ALL agents in ONE message for parallel execution
- Use `isolation: "worktree"` when agents edit overlapping files
- Use `model: "haiku"` for read-only tasks, `"sonnet"` for implementation
- Collect results from background task notifications, then synthesize

---

## Rules

- Only make approved changes
- Do not expand scope without asking
- Tests are required for functional code
- Integration tests are required for components that interact with external systems

### New File Creation

When creating new files:

1. Check naming conventions from the relevant `DEV_*` memory
2. Include required boilerplate from `DEV_*` (file headers, guards, defaults)
3. Register/wire the new file per `FEATURE_[KEY]` or `DOM_*` patterns
4. Verify any compliance checklist items in WM

Registration is the most common cause of "code is correct but doesn't work" failures.

---

## Next Step

After each significant action:

| Condition                       | Read Next       |
| ------------------------------- | --------------- |
| Created/modified file           | `WF_CHECKPOINT` |
| Completed a phase               | `WF_CHECKPOINT` |
| All work done (including tests) | `WF_VERIFY`     |

1. Determine which condition applies
2. Update WM with current progress
3. Read that WF_* memory
4. Report the new step to user

Update WM via /swe-wm-update before transitioning.
