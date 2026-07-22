---
name: CLAUDE_META
description: Meta-reference for the state-machine workflow system — its structure, memory types, step-reporting contract, and rules for adding/modifying states.
metadata:
  type: reference
---

# CLAUDE_META — Workflow System Reference

## Why This System Exists

- Large CLAUDE.md files fail: Claude skips buried instructions, context fills and drifts, rules become suggestions.
- Split into: tiny CLAUDE.md entry point + one-responsibility WF_* state files + verification loops.
- Claude MUST read the next state file to know the next step. This blocks skipping ahead, blocks hallucinated rules, and forces the declared transition path.

## Context Minimization (hard rule)

- Load ONLY memories needed for the current task. NEVER read unrelated layer patterns.
- Applies to WF_* (single-responsibility states), DOM_* (domain requirements only), ARCH_* (one layer per file).

### Agent Spawning

- `WF_ARCH_REVIEW`: read `ARCH_INDEX` (overview only) → propose needed layers → user approves.
- `WF_EXECUTE`: spawn one parallel agent per layer; each agent loads only its `ARCH_LAYER_*` + relevant `REF_*`.

## Step Reporting (contract — do NOT drop)

- Each WF_* memory starts with its step name. Claude MUST output the report line before executing the step. This blocks silent step-skipping and creates the audit trail.

| Step                  | Report                         |
| --------------------- | ------------------------------ |
| WF_CLASSIFY           | **On step WF_CLASSIFY**        |
| WF_UPDATE_MEMORY      | **On step WF_UPDATE_MEMORY**   |
| WF_CLARIFY            | **On step WF_CLARIFY**         |
| ~~WF_LOAD_FEATURE~~   | _(merged into WF_CLASSIFY)_    |
| ~~WF_ASK_PERMISSION~~ | _(merged into WF_ARCH_REVIEW)_ |
| WF_EXECUTE            | **On step WF_EXECUTE**         |
| WF_CHECKPOINT         | **On step WF_CHECKPOINT**      |
| WF_VERIFY             | **On step WF_VERIFY**          |
| WF_CONTINUE           | **On step WF_CONTINUE**        |
| WF_RESEARCH           | **On step WF_RESEARCH**        |
| WF_DONE               | **On step WF_DONE**            |

## File Structure

```
project/
+-- CLAUDE.md                # Entry point (~20 lines)
+-- .serena/swe/             # Serena MCP memory storage
    +-- CLAUDE_META.md       # This file
    +-- CLAUDE_WORKFLOW.md   # State-machine diagram
    +-- CLAUDE_OBLIGATIONS.md# Behavioral constraints
    +-- WF_*.md              # Workflow states
    +-- ARCH_INDEX.md        # Architecture overview
    +-- ARCH_*.md            # Layer-specific architecture
    +-- DOM_*.md             # Domain requirements
    +-- INDEX_*.md           # Lookup tables
    +-- REF_*.md             # Reference docs
    +-- MEMORY.md            # Memory index (auto-loaded)
```

## Memory Types

| Type                 | Contains                                                              | Constraint                                    |
| -------------------- | -------------------------------------------------------------------- | --------------------------------------------- |
| CLAUDE.md            | Entry point only; reads `WF_INIT`                                    | ~20 lines; only file read from disk at start  |
| `WF_*`               | What to do, what to read, next state(s)                              | 10-20 lines each; split if longer             |
| `CLAUDE_OBLIGATIONS` | Behavioral constraints (NEVER/ALWAYS)                               | ~20 lines                                     |
| `ARCH_INDEX`         | Architecture overview pointing to layer files                       | ~50 lines                                     |
| `ARCH_*`             | Rules for ONE architectural layer                                    | ~50 lines each; agents load only their layer  |
| `DOM_*`              | Domain requirements (WHAT, not HOW); NO signatures/queries          | Variable; implementation lives in `ARCH_*`/Serena |
| `INDEX_*`            | Lookup tables mapping logical names → file paths                    | Variable                                      |
| `REF_*`              | How-to guides, coding/testing standards, framework syntax           | Variable                                      |

## Workflow Design Rules

- Keep each WF_* file 10-20 lines max. Split when longer.
- Every state MUST declare its explicit transitions (`condition → WF_TARGET`). NEVER leave next-state implicit.
- `WF_VERIFY` runs after all code changes; on violation it loops back to `WF_CLASSIFY` to force a fix.
- `WF_CLARIFY` is reachable from multiple states when uncertain.
- `WF_CLASSIFY` scans every user message for requirement language inline, and validates requirements against domain memories in Step 5.

## Adding a State

1. Create `WF_NEWSTATE.md`: what to do, what to read, next states.
2. Route upstream states to the new state.
3. Update `CLAUDE_WORKFLOW` diagram.
4. Update `MEMORY.md` index.

## Modifying a State

1. `read_memory` the current state.
2. `edit_memory` to change it.
3. Update `CLAUDE_WORKFLOW` diagram if transitions changed.
4. Test the workflow path.

## Serena Memory Tools

- `list_memories()` — list all memories.
- `read_memory("NAME")` — read one.
- `write_memory("NAME", content)` — write one.
- `edit_memory("NAME", old, new)` — patch one.

## Invariants

- Claude knows its next step ONLY by reading the next memory file.
- Every file stays small because large files cause drift and hallucination.
- Agents load ONLY the architecture relevant to their layer.
