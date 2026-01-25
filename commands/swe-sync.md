---
name: swe-sync
description: Sync plugin memories to local project using ruv-swarm
---

# /swe-sync

Synchronize Serena memories between plugin and local project.

## Usage

```
/swe-sync                           # Sync all memories plugin → local
/swe-sync --dry-run                 # Preview changes without syncing
/swe-sync category=wf               # Sync only WF_ workflow files
/swe-sync category=ref              # Sync only REF_ reference files
/swe-sync direction=local-to-plugin # Sync local changes back to plugin
```

## Process

Uses ruv-swarm for parallel file comparison:
1. Initialize mesh swarm with DAA coordination
2. Spawn analyzer agents for plugin and local directories
3. Compare files by category (wf, ref, or all)
4. Report differences in table format
5. Execute sync if not --dry-run
6. Verify sync completion

## Implementation

See: `skills/swe-sync/SKILL.md`
