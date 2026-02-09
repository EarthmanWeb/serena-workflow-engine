---
name: swe-cleanup
description: Archive completed memories and specs
argument-hint: [all|memories|specs]
---

# /swe-cleanup [target]

Archive completed work to `.serena/archive-*` directories.

## Options

- `/swe-cleanup` - Scan and prompt for confirmation
- `/swe-cleanup memories` - Archive WM_* files with status: Completed
- `/swe-cleanup specs` - Archive SPEC_* files (requires confirmation)
- `/swe-cleanup all` - Archive both

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
2. Display list of found files
3. Use AskUserQuestion for confirmation:

```javascript
AskUserQuestion({
  questions: [
    {
      question: "Found [N] files to archive. Proceed with cleanup?",
      header: "Cleanup",
      options: [
        {
          label: "Archive all",
          description: "Move all listed files to archive directories",
        },
        {
          label: "Archive memories only",
          description: "Only archive completed WORKING_MEMORY files",
        },
        {
          label: "Archive specs only",
          description: "Only archive SPEC_* files",
        },
        {
          label: "Cancel",
          description: "Don't archive anything",
        },
      ],
      multiSelect: false,
    },
  ],
});
```

4. Move files with timestamp prefix based on selection
5. Update indexes
6. Report archived files count
