---
name: working-memory
description: Manage session WORKING_MEMORY files
argument-hint: "[show|create|update|list|archive]"
---

# /working-memory [action]

Manage WORKING_MEMORY session state files.

## Actions

### show (default)

Display current WORKING_MEMORY contents.

```
/working-memory show
/working-memory
```

Output: Full contents of current WORKING_MEMORY file.

### create [descriptor]

Create new WORKING_MEMORY with timestamp.

```
/working-memory create auth_refactor
/working-memory create bugfix_login
```

Creates: `WORKING_MEMORY_YYYYMMDD_[descriptor].md`

Template:
```markdown
# WORKING_MEMORY - [Descriptor]

Created: [timestamp]
Session: [session_id]

## Current Task
[To be filled]

## Active Feature(s)
- [feature_key]

## Decisions Made
(none yet)

## Blockers
(none)

## Next Steps
1. [pending]
```

### update

Open current WORKING_MEMORY for editing.

```
/working-memory update
```

Reads current file and prompts for updates to:
- Current Task
- Decisions Made
- Blockers
- Next Steps

### list

List all WORKING_MEMORY files.

```
/working-memory list
```

Output:
```
================================================================================
WORKING MEMORY FILES
================================================================================
Current: WORKING_MEMORY_20260115_auth_refactor.md

All Files:
  * WORKING_MEMORY_20260115_auth_refactor.md (active)
    WORKING_MEMORY_20260114_bugfix.md
    WORKING_MEMORY_20260113_feature_x.md
    WORKING_MEMORY_20260110_initial_archived.md

Total: 4 files
================================================================================
```

### archive

Archive current WORKING_MEMORY and start fresh.

```
/working-memory archive
```

Process:
1. Rename current to `[name]_archived_[timestamp].md`
2. Create new WORKING_MEMORY with current date
3. Update `workflow-state.json` reference

## Integration

WORKING_MEMORY is automatically:
- Created at session start (via hooks)
- Updated at state transitions
- Referenced in RLVR trajectory
- Archived at session end

## File Location

All WORKING_MEMORY files stored in `.serena/memories/`
