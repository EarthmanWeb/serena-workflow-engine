---
name: swe-migrate
description: Migrate legacy WF_* files and CLAUDE.md to plugin-based workflow
---

# /swe-migrate

Migrate existing project from legacy WF_* memories and CLAUDE.md-based workflow to plugin-based workflow.

## When to Use

- Projects with existing `.serena/memories/WF_*.md` files (legacy format)
- Migrating from CLAUDE.md-based workflow instructions
- After installing serena-workflow-engine plugin
- When legacy WF_* files don't match plugin's states.json

## Process (5 Steps)

### Step 1: Backup Existing Files

```bash
# Backup legacy WF_* memories
mkdir -p .serena/archive-memories/
cp .serena/memories/WF_*.md .serena/archive-memories/

# Backup CLAUDE.md
cp CLAUDE.md CLAUDE.md.bak
```

### Step 2: Audit Legacy WF_* Files

For each existing WF_*.md, verify against `states.json`:

| Check | Action if Missing |
|-------|-------------------|
| `requiredActions` complete? | Add missing from states.json |
| Transitions correct? | Update to match `transitionMatrix` |
| `planMode` documented? | Add from states.json |
| RLVR signal present? | Add `signalType` and `rewardImpact` |
| Permissions stated? | Add `allowEdit`/`allowWrite` |
| ≤100 lines? | Condense, move detail to cross-refs |
| Icon correct? | Use icon from states.json |

### Step 3: Clean CLAUDE.md

Remove workflow sections from CLAUDE.md:
- Entry point instructions ("BEFORE responding to ANY user message...")
- Step reporting enforcement
- Workflow state transition rules
- WF_* reading requirements

Keep in CLAUDE.md:
- Project-specific instructions
- Coding standards
- Non-workflow guidance

### Step 4: Verify Plugin Hooks

Ensure hooks are configured in `.claude/settings.local.json`

### Step 5: Test Workflow

Run a simple test to verify workflow functions:
1. Start new session
2. Verify WF_START is read
3. Verify step reporting works

## Output

```
================================================================================
WORKFLOW MIGRATION
================================================================================
Backup:
  [x] Legacy WF_* → .serena/archive-memories/ ([count] files)
  [x] CLAUDE.md → CLAUDE.md.bak

Migration:
  [x] Legacy WF_* files archived (now provided via plugin hooks)
  [x] CLAUDE.md cleaned

Verification:
  [x] Plugin hooks configured
  [x] Workflow functions correctly

Migration Status: SUCCESS
================================================================================
```

## Rollback

If migration fails:

```bash
# Restore legacy WF_* files
cp .serena/archive-memories/WF_*.md .serena/memories/

# Restore CLAUDE.md
mv CLAUDE.md.bak CLAUDE.md
```

## Differences: Legacy vs Plugin Format

| Aspect | Legacy | Plugin |
|--------|--------|--------|
| Location | .serena/memories/ | Plugin instructions/ → injected via hooks |
| Format | Variable | Standardized ≤100 lines |
| RLVR | Missing | Required per state |
| planMode | Often missing | Required per state |
| Permissions | Implicit | Explicit allowEdit/allowWrite |
| Icons | Ad-hoc emoji | states.json defined |
