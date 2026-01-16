---
name: swe-migrate
description: Convert project from CLAUDE.md-based to plugin-based workflow
---

# /swe-migrate

Convert project from CLAUDE.md-based workflow instructions to plugin-based workflow.

## When to Use

- Migrating existing projects using CLAUDE.md workflow instructions
- Transitioning to plugin-based hooks and state machine
- After installing the serena-workflow-engine plugin

## Process

### Step 1: Backup

```bash
cp CLAUDE.md CLAUDE.md.bak
```

### Step 2: Verify Prerequisites

Check for:
- [ ] `.serena/memories/WF_START.md` exists
- [ ] `.serena/memories/INDEX_FEATURES.md` exists
- [ ] At least one `FEATURE_*.md` memory exists
- [ ] Plugin hooks configured in `.claude/settings.local.json`

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

Ensure `.claude/settings.local.json` contains:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [".claude/plugins/serena-workflow-engine/hooks/pre-tool-use.sh"]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [".claude/plugins/serena-workflow-engine/hooks/post-tool-use.sh"]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "*",
        "hooks": [".claude/plugins/serena-workflow-engine/hooks/user-prompt-submit.sh"]
      }
    ]
  }
}
```

### Step 5: Verify State Machine

Confirm `state-machine/states.json` is present and configured.

## Output

```
================================================================================
WORKFLOW MIGRATION
================================================================================
Backup:        CLAUDE.md.bak created
Prerequisites: [status]

Checklist:
  [x] WF_START memory exists
  [x] INDEX_FEATURES exists
  [x] FEATURE_* memories found: [count]
  [x] Plugin hooks configured
  [x] State machine configured

CLAUDE.md Changes:
  - Removed: Workflow entry point (24 lines)
  - Removed: Step reporting enforcement (16 lines)
  - Kept: Project-specific instructions

Migration Status: SUCCESS

The workflow is now plugin-driven. Hooks will automatically:
  - Enforce WF_START reading
  - Track state transitions
  - Manage WORKING_MEMORY
  - Enforce checkpoints
================================================================================
```

## Rollback

If migration fails:

```bash
mv CLAUDE.md.bak CLAUDE.md
```
