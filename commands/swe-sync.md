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

## ⛔ CRITICAL SAFETY RULES

**This command ONLY copies plugin files to local. It NEVER touches local-only files.**

### What it does:
- Copies files from `.claude/plugins/serena-workflow-engine/memories/` TO `.serena/memories/`
- Updates existing files if plugin version is newer
- Preserves ALL local-only files (memories created by user, WM_* files, stats/, etc.)

### What it NEVER does:
- Delete ANY files in destination
- Remove local-only memories
- Touch WM_* working memory files
- Modify stats/ directory

**ONLY USE THIS PATTERN:**
```bash
# Copy plugin memories to local, preserve everything else
cp -n .claude/plugins/serena-workflow-engine/memories/**/*.md .serena/memories/
# Or for specific files:
cp .claude/plugins/serena-workflow-engine/memories/wf/WF_CLASSIFY.md .serena/memories/wf/
```

**⛔ FORBIDDEN COMMANDS - NEVER USE:**
```bash
rsync --delete  # ⛔ DELETES USER DATA
rm -rf          # ⛔ DELETES USER DATA
mv              # ⛔ CAN LOSE DATA
```

## Implementation

See: `skills/swe-sync/SKILL.md`
