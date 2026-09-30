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

- `WF_ARCH_REVIEW`: read `mem:arch/ARCH_SWE` (overview only) → propose needed layers → user approves.
- `WF_EXECUTE`: spawn one parallel agent per layer; each agent loads only its layer's `arch/ARCH_*` + relevant `ref/REF_*`.

## Step Reporting (contract — do NOT drop)

- Each WF_* memory starts with its step name. Claude MUST output the report line before executing the step. This blocks silent step-skipping and creates the audit trail.

| Step             | Report                       |
| ---------------- | ---------------------------- |
| WF_CLASSIFY      | **On step WF_CLASSIFY**      |
| WF_UPDATE_MEMORY | **On step WF_UPDATE_MEMORY** |
| WF_CLARIFY       | **On step WF_CLARIFY**       |
| WF_ARCH_REVIEW   | **On step WF_ARCH_REVIEW**   |
| WF_EXECUTE       | **On step WF_EXECUTE**       |
| WF_CHECKPOINT    | **On step WF_CHECKPOINT**    |
| WF_VERIFY        | **On step WF_VERIFY**        |
| WF_CONTINUE      | **On step WF_CONTINUE**      |
| WF_RESEARCH      | **On step WF_RESEARCH**      |
| WF_DONE          | **On step WF_DONE**          |

Feature loading is a step inside `WF_CLASSIFY` (Step 4), not a separate state. Approval/consent is a step inside `WF_ARCH_REVIEW` (the Single Question + Consent Gate), not a separate state.

## File Structure

```
project/
+-- CLAUDE.md                # Entry point (~20 lines)
+-- .serena/memory/          # Serena MCP memory storage
    +-- claude/CLAUDE_META.md        # This file
    +-- claude/CLAUDE_OBLIGATIONS.md # Behavioral constraints
    +-- wf/WF_*.md                   # Workflow states
    +-- arch/ARCH_*.md               # Architecture documentation
    +-- dom/DOM_*.md                 # Domain requirements
    +-- index/INDEX_*.md             # Lookup tables
    +-- ref/REF_*.md                 # Reference docs
    +-- MEMORY.md                    # Memory index (auto-loaded)
```

## Memory Types

| Type                 | Contains                                                   | Constraint                                        |
| -------------------- | ---------------------------------------------------------- | ------------------------------------------------- |
| CLAUDE.md            | Entry point only; reads `WF_INIT`                          | ~20 lines; only file read from disk at start      |
| `WF_*`               | What to do, what to read, next state(s)                    | Size Budget; hub ≤12,000 chars                    |
| `CLAUDE_OBLIGATIONS` | Behavioral constraints (NEVER/ALWAYS)                      | Size Budget                                       |
| `ARCH_*`             | Architecture documentation (system overview or one layer)  | Size Budget; agents load only their layer         |
| `DOM_*`              | Domain requirements (WHAT, not HOW); NO signatures/queries | Variable; implementation lives in `ARCH_*`/Serena |
| `INDEX_*`            | Lookup tables mapping logical names → file paths           | Variable                                          |
| `REF_*`              | How-to guides, coding/testing standards, framework syntax  | Variable                                          |

## Workflow Design Rules

- Keep every memory within the Size Budget (`mem:ref/REF_MEMORY_STYLE`: ≤8,000 chars target, >16,000 must split, ≥50,000 unreadable — measured). WF_* are read every task: hub ≤12,000; move conditional detail to `ref/REF_WF_<STATE>_<TOPIC>` children. Audit with `/swe-memory-size-audit`.
- Every state MUST declare its explicit transitions in a `## Routing` table (`condition → WF_[NEXT]`). NEVER leave next-state implicit.
- `WF_VERIFY` runs after all code changes; on a large violation it loops back to `WF_CLASSIFY` to re-evaluate scope (see `mem:wf/WF_VERIFY` Re-Scope Check); a minor violation is fixed in place.
- `WF_CLARIFY` is reachable from multiple states when uncertain.
- `WF_CLASSIFY` scans every user message for requirement language inline, and validates requirements against domain memories in Step 5.

## Adding a State

1. Create `wf/WF_[NEWSTATE].md`: what to do, what to read, `## Routing` table.
2. Route upstream states to the new state (update their `## Routing` tables).
3. Add the state to `state-machine/states.json` (definition, `transitionMatrix`, `rank`).
4. Update `dom/DOM_SWE_STATE_MACHINE` and `MEMORY.md` index.
5. Run `python3 scripts/validate-graph.py` and `python3 skills/swe-memory-size-audit/scripts/validate-memory-graph.py --extra-root memories` (conf roots + plugin source tree in ONE run — never validate trees separately).

## Modifying a State

1. `read_memory` the current state.
2. `edit_memory` to change it.
3. Update the state's `## Routing` table and `state-machine/states.json` if transitions changed.
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
