---
name: cleanup
description: Archive completed memories and specs
argument-hint: [all|memories|specs]
---

# /cleanup [target]

Archive completed work to `.serena/archive-*` directories.

## Options

- `/cleanup` - Scan and prompt for confirmation
- `/cleanup memories` - Archive WORKING_MEMORY_* files with status: Completed
- `/cleanup specs` - Archive SPEC_* files (requires confirmation)
- `/cleanup all` - Archive both

## Archivable Criteria

### Working Memories
- Status field contains "Completed"
- Task marked as done

### Specs
- User confirmation required
- Typically after implementation complete

## Archive Locations

- `.serena/archive-memories/` - Completed working memories
- `.serena/archive-specs/` - Completed specifications

## Implementation

1. Scan for archivable files
2. Display list with confirmation prompt
3. Move files with timestamp prefix
4. Update indexes
