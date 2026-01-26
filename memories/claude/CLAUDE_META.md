# Claude Workflow System - Meta Documentation

This document explains the state machine workflow system used to guide Claude's behavior in this project. Use this to understand, modify, or replicate the approach.

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

- An agent working on templates should NOT read context provider patterns
- An agent working on a block should NOT read function implementation details
- Load ONLY what's needed for the specific task

This applies to:
- **Workflow files** (WF_*) - small, single-responsibility states
- **Domain files** (DOM_*) - site-specific requirements only
- **Architecture files** (ARCH_*) - layer-specific rules for agents

### Agent Spawning Pattern

When work spans multiple layers:
```
WF_PLAN_ARCHITECTURE:
  1. Read ARCH_INDEX (overview only)
  2. Propose: "Need: template, provider, block"
  3. User approves
     ↓
WF_EXECUTE:
  Spawn parallel agents:
  ├── Template agent → ARCH_TEMPLATES + REF_BLADEONE
  ├── Provider agent → ARCH_PROVIDERS + SYS_CONTEXT_PROVIDERS
  └── Block agent → ARCH_BLOCKS + SYS_BLOCKS
```

Each agent has minimal, focused context = fewer hallucinations, faster execution.

---

## Step Reporting

Each workflow state includes a reporting line with a distinct icon:

| Step | Report |
|------|--------|
| WF_START | **🚀 On step WF_START** |
| WF_CLASSIFY | **🔍 On step WF_CLASSIFY** |
| WF_PLAN_ARCHITECTURE | **📐 On step WF_PLAN_ARCHITECTURE** |
| WF_DETECT_REQ | **📋 On step WF_DETECT_REQ** |
| WF_REQUIREMENT | **📝 On step WF_REQUIREMENT** |
| WF_UPDATE_MEMORY | **💾 On step WF_UPDATE_MEMORY** |
| WF_CLARIFY | **❓ On step WF_CLARIFY** |
| WF_LOAD_FEATURE | **📂 On step WF_LOAD_FEATURE** |
| WF_ASK_PERMISSION | **🔐 On step WF_ASK_PERMISSION** |
| WF_EXECUTE | **⚡ On step WF_EXECUTE** |
| WF_CHECKPOINT | **✅ On step WF_CHECKPOINT** |
| WF_VERIFY | **🔎 On step WF_VERIFY** |
| WF_CONTINUE | **▶️ On step WF_CONTINUE** |
| WF_RESEARCH | **🔬 On step WF_RESEARCH** |
| WF_DONE | **✨ On step WF_DONE** |

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
├── CLAUDE.md                    # Entry point (~20 lines)
│
├── .serena/WM/            # Serena MCP memory storage
│   ├── CLAUDE_META.md           # This file - system documentation
│   ├── CLAUDE_WORKFLOW.md       # Visual diagram of state machine
│   ├── CLAUDE_OBLIGATIONS.md    # Behavioral constraints
│   │
│   ├── WF_*.md                  # Workflow states (16 files)
│   │
│   ├── ARCH_INDEX.md            # Architecture overview
│   ├── ARCH_TEMPLATES.md        # BladeOne template layer
│   ├── ARCH_PROVIDERS.md        # Context provider layer
│   ├── ARCH_BLOCKS.md           # ACF block layer
│   ├── ARCH_FUNCTIONS.md        # mu-plugin function layer
│   │
│   ├── DOM_DISTRICT.md          # District site domain
│   ├── DOM_SCHOOLS.md           # Schools site domain
│   ├── DOM_REDACTED.md             # App intranet domain
│   ├── DOM_NETWORK.md           # Multisite network domain
│   │
│   ├── SYS_BLOCKS.md            # Block inventory
│   ├── SYS_CONTEXT_PROVIDERS.md # Provider inventory
│   │
│   ├── INDEX_*.md               # Lookup tables
│   ├── REF_*.md                 # Reference documentation
│   ├── MAP_LEGACY_*.md          # Migration mappings
│   │
│   └── _INDEX.md                # Memory navigation
```

---

## Components Explained

### 1. CLAUDE.md (Entry Point)

The only file Claude reads from disk at conversation start. Must be tiny:

```markdown
# Claude Code - Project Reference

## Entry Point

Read `WF_START` memory. Follow the workflow.

## Quick Reference

| Memory | Purpose |
|--------|---------|
| `WF_*` | Workflow states |
| `CLAUDE_OBLIGATIONS` | Hard rules |
| `ARCH_*` | Architecture layers |
| `DOM_*` | Domain requirements |
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
2. **Read WM**
3. **Classify task type:**
   - Continue previous → `WF_CONTINUE`
   - Research only → `WF_RESEARCH`
   - Code change → `WF_CLASSIFY`

## Next State
Based on classification above.
```

### 3. CLAUDE_OBLIGATIONS.md

Behavioral constraints only. Keep short (~20 lines):

```markdown
# Obligations

## NEVER Do
- [ ] Use `as any` type assertions
- [ ] Create files without permission
- [ ] Guess file paths

## ALWAYS Do
- [ ] Ask before modifying files
- [ ] Use Serena tools before Read/Edit
- [ ] Update WM after steps
```

### 4. ARCH_INDEX.md

Architecture overview pointing to layer-specific ARCH_* files:
- `ARCH_TEMPLATES` - BladeOne template rules
- `ARCH_PROVIDERS` - Context provider rules
- `ARCH_BLOCKS` - ACF block rules
- `ARCH_FUNCTIONS` - mu-plugin function rules

### 5. Domain Memories (DOM_*)

Site-specific requirements and patterns:
- `DOM_DISTRICT` - Main site (board meetings, policies, news)
- `DOM_SCHOOLS` - School sites (colors, staff directories)
- `DOM_REDACTED` - Intranet (employee tools, internal forms)
- `DOM_NETWORK` - Multisite admin operations

**DO** (requirement style):
- "District site displays board meeting archives"
- "School sites show school-specific colors"
- "App requires authentication"

**DON'T** (implementation details):
- Function signatures, parameter types
- Specific query implementations

Implementation details belong in ARCH_* memories or are discovered via Serena tools at execution time.

### 6. System Memories (SYS_*)

Inventories of existing components:
- `SYS_BLOCKS` - ACF block registry
- `SYS_CONTEXT_PROVIDERS` - Provider registry with priorities

### 7. Index Memories (INDEX_*)

Lookup tables for finding code:
- `INDEX_TEMPLATES` - Template → file mapping
- `INDEX_FUNCTIONS` - Function → file mapping
- `INDEX_HOOKS` - Hook registration mapping

### 8. Reference Memories (REF_*)

How-to guides and patterns:
- `REF_BLADEONE` - BladeOne syntax
- `REF_DEV_STANDARDS` - Coding standards
- `REF_TESTING` - Test patterns

---

## Workflow Design Principles

### 1. Small States
Each WF_* file should be 10-20 lines max. If it's longer, split it.

### 2. Explicit Transitions
Every state must declare what states it can transition to:
```
## Next State
- Condition A → `WF_FOO`
- Condition B → `WF_BAR`
```

### 3. Mandatory Checkpoints
Key verification points that can't be skipped:
- `WF_VERIFY` - after all code changes
- `WF_CLARIFY` - when uncertain (reachable from multiple states)

### 4. Loop Back on Violations
`WF_VERIFY` checks for violations and loops back to `WF_START` if found. This forces Claude to fix issues rather than ignore them.

### 5. Requirement Detection
`WF_DETECT_REQ` scans every user message for requirement language and routes to `WF_REQUIREMENT` to update domain memories.

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
- Condition → `WF_NEXT`
```

---

## Modifying Existing States

1. Read current state with `mcp__serena__read_memory`
2. Edit with `mcp__serena__edit_memory`
3. Update diagram if transitions changed
4. Test the workflow path

---

## Memory Tool Reference

Using Serena MCP:

```
# List all memories
mcp__serena__list_memories()

# Read a memory
mcp__serena__read_memory("MEMORY_NAME")

# Write a memory
mcp__serena__write_memory("MEMORY_NAME", "content")

# Edit a memory (regex or literal)
mcp__serena__edit_memory("MEMORY_NAME", "old", "new", "literal")
```

---

## Summary

| Component | Purpose | Size |
|-----------|---------|------|
| CLAUDE.md | Entry point | ~20 lines |
| WF_* | Workflow states | 10-20 lines each |
| CLAUDE_OBLIGATIONS | Behavioral rules | ~20 lines |
| ARCH_INDEX | Architecture overview | ~50 lines |
| ARCH_* | Layer architecture | ~50 lines each |
| DOM_* | Domain requirements | Variable |
| SYS_* | System inventories | Variable |
| INDEX_* | Lookup tables | Variable |
| REF_* | Reference guides | Variable |

**Key principles:**
1. Claude can only know its next step by reading the next memory file
2. Every file is small because large files cause drift and hallucination
3. Agents load ONLY the architecture relevant to their layer
