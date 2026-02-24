# Claude Workflow System - Meta Documentation

This document explains the state machine workflow system used to guide Claude's behavior. Use this to understand, modify, or replicate the approach.

---

## The Problem

Large CLAUDE.md files don't work well:

- Claude skips or forgets instructions buried in long files
- Context fills up, causing drift from instructions
- No enforcement mechanism - rules are suggestions
- Hard to maintain as project evolves

## The Solution: State Machine Workflow

Instead of one large instruction file, we use:

1. **Tiny CLAUDE.md** (~20 lines) - just an entry point
2. **Workflow memories** (WF_*) - small files (~10-15 lines each) that Claude reads one at a time
3. **Each state points to the next** - Claude can't skip ahead because it doesn't know what's next
4. **Verification loops** - violations send Claude back to START

---

## Key Insight

**Claude must read the next instruction file to know what to do next.**

This creates natural enforcement:

- Can't skip steps (doesn't know them yet)
- Can't hallucinate rules (must read from file)
- Must follow the path (each state defines valid transitions)

---

## Core Principle: Context Minimization

**Every file in this system exists because large files cause drift and hallucination.**

- An agent working on one layer should NOT read unrelated layer patterns
- Load ONLY what's needed for the specific task

This applies to:

- **Workflow files** (WF_*) - small, single-responsibility states
- **Domain files** (DOM_*) - domain-specific requirements only
- **Architecture files** (ARCH_*) - layer-specific rules for agents

### Agent Spawning Pattern

When work spans multiple layers:

```
WF_ARCH_REVIEW:
  1. Read ARCH_INDEX (overview only)
  2. Propose which layers are needed
  3. User approves
     |
WF_EXECUTE:
  Spawn parallel agents:
  +-- Layer A agent -> ARCH_LAYER_A + relevant REF_*
  +-- Layer B agent -> ARCH_LAYER_B + relevant REF_*
  +-- Layer C agent -> ARCH_LAYER_C + relevant REF_*
```

Each agent has minimal, focused context = fewer hallucinations, faster execution.

---

## Step Reporting

Each workflow state includes a reporting line with a distinct icon:

| Step                  | Report                         |
| --------------------- | ------------------------------ |
| WF_START              | **On step WF_START**           |
| WF_CLASSIFY           | **On step WF_CLASSIFY**        |
| WF_UPDATE_MEMORY      | **On step WF_UPDATE_MEMORY**   |
| WF_CLARIFY            | **On step WF_CLARIFY**         |
| WF_LOAD_FEATURE       | **On step WF_LOAD_FEATURE**    |
| ~~WF_ASK_PERMISSION~~ | _(merged into WF_ARCH_REVIEW)_ |
| WF_EXECUTE            | **On step WF_EXECUTE**         |
| WF_CHECKPOINT         | **On step WF_CHECKPOINT**      |
| WF_VERIFY             | **On step WF_VERIFY**          |
| WF_CONTINUE           | **On step WF_CONTINUE**        |
| WF_RESEARCH           | **On step WF_RESEARCH**        |
| WF_DONE               | **On step WF_DONE**            |

**Benefits:**

- Visual distinction for each step
- User visibility into workflow progress
- Ensures steps aren't silently skipped
- Creates audit trail for debugging

**Implementation:**

- Each WF_* memory starts with its icon + step name
- Claude outputs this line before executing the step

---

## File Structure

```
project/
+-- CLAUDE.md                    # Entry point (~20 lines)
|
+-- .serena/swe/            # Serena MCP memory storage
    +-- CLAUDE_META.md           # This file - system documentation
    +-- CLAUDE_WORKFLOW.md       # Visual diagram of state machine
    +-- CLAUDE_OBLIGATIONS.md    # Behavioral constraints
    |
    +-- WF_*.md                  # Workflow states
    |
    +-- ARCH_INDEX.md            # Architecture overview
    +-- ARCH_*.md                # Layer-specific architecture
    |
    +-- DOM_*.md                 # Domain-specific requirements
    |
    +-- INDEX_*.md               # Lookup tables
    +-- REF_*.md                 # Reference documentation
    |
    +-- _INDEX.md                # Memory navigation
```

---

## Components Explained

### 1. CLAUDE.md (Entry Point)

The only file Claude reads from disk at conversation start. Must be tiny:

```markdown
# Claude Code - Project Name

## Entry Point

Read `WF_START` memory. Follow the workflow.

## Quick Reference

| Memory               | Purpose             |
| -------------------- | ------------------- |
| `WF_*`               | Workflow states     |
| `CLAUDE_OBLIGATIONS` | Hard rules          |
| `ARCH_*`             | Architecture layers |
| `DOM_*`              | Domain requirements |
```

### 2. Workflow States (WF_*)

Small memory files that define:

- What to do in this state
- What to read/check
- Which state(s) to go to next

Example `WF_START`:

```markdown
# WF_START - Entry Point

**Report: "On step WF_START"**

## Execute These Steps

1. **Read CLAUDE_OBLIGATIONS**
2. **Read WM (Working Memory)**
3. **Classify task type:**
   - Continue previous -> `WF_CONTINUE`
   - Research only -> `WF_RESEARCH`
   - Code change -> `WF_CLASSIFY`

## Next State

Based on classification above.
```

### 3. CLAUDE_OBLIGATIONS.md

Behavioral constraints only. Keep short (~20 lines):

```markdown
# Obligations

## NEVER Do

- [ ] Use unsafe type assertions
- [ ] Create files without permission
- [ ] Guess file paths

## ALWAYS Do

- [ ] Ask before modifying files
- [ ] Use Serena tools before Read/Edit
- [ ] Update WM after steps
```

### 4. Architecture Memories (ARCH_*)

`ARCH_INDEX` provides architecture overview pointing to layer-specific files:

- Each `ARCH_*` file defines rules for one architectural layer
- Agents load only the architecture relevant to their task

### 5. Domain Memories (DOM_*)

Domain-specific requirements and patterns. Define WHAT the system needs to do, not HOW.

**DO** (requirement style):

- "Users must authenticate before accessing dashboard"
- "Reports display date ranges selectable by user"

**DON'T** (implementation details):

- Function signatures, parameter types
- Specific query implementations

Implementation details belong in ARCH_* memories or are discovered via Serena tools at execution time.

### 6. Index Memories (INDEX_*)

Lookup tables for finding code:

- Map logical names to file locations
- Registry of components and their paths

### 7. Reference Memories (REF_*)

How-to guides and patterns:

- Coding standards
- Testing patterns
- Framework-specific syntax

---

## Workflow Design Principles

### 1. Small States

Each WF_* file should be 10-20 lines max. If it's longer, split it.

### 2. Explicit Transitions

Every state must declare what states it can transition to:

```
## Next State
- Condition A -> `WF_FOO`
- Condition B -> `WF_BAR`
```

### 3. Mandatory Checkpoints

Key verification points that can't be skipped:

- `WF_VERIFY` - after all code changes
- `WF_CLARIFY` - when uncertain (reachable from multiple states)

### 4. Loop Back on Violations

`WF_VERIFY` checks for violations and loops back to `WF_START` if found. This forces Claude to fix issues rather than ignore them.

### 5. Requirement Detection

`WF_CLASSIFY` scans every user message for requirement language inline and notes requirements for validation at `WF_LOAD_FEATURE` against domain memories.

---

## Adding New States

1. Create memory file: `WF_NEWSTATE.md`
2. Define: what to do, what to read, next states
3. Update upstream states to route to new state
4. Update `CLAUDE_WORKFLOW` diagram
5. Update `_INDEX` memory list

Example:

```markdown
# WF_NEWSTATE - Description

## Execute These Steps

1. Do something
2. Check something

## Next State

- Condition -> `WF_NEXT`
```

---

## Modifying Existing States

1. Read current state with `read_memory`
2. Edit with `edit_memory`
3. Update diagram if transitions changed
4. Test the workflow path

---

## Memory Tool Reference

Using Serena MCP:

```
# List all memories
list_memories()

# Read a memory
read_memory("MEMORY_NAME")

# Write a memory
write_memory("MEMORY_NAME", "content")

# Edit a memory
edit_memory("MEMORY_NAME", "old", "new")
```

---

## Summary

| Component          | Purpose               | Size             |
| ------------------ | --------------------- | ---------------- |
| CLAUDE.md          | Entry point           | ~20 lines        |
| WF_*               | Workflow states       | 10-20 lines each |
| CLAUDE_OBLIGATIONS | Behavioral rules      | ~20 lines        |
| ARCH_INDEX         | Architecture overview | ~50 lines        |
| ARCH_*             | Layer architecture    | ~50 lines each   |
| DOM_*              | Domain requirements   | Variable         |
| INDEX_*            | Lookup tables         | Variable         |
| REF_*              | Reference guides      | Variable         |

**Key principles:**

1. Claude can only know its next step by reading the next memory file
2. Every file is small because large files cause drift and hallucination
3. Agents load ONLY the architecture relevant to their layer
