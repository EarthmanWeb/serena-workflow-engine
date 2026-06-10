---
name: FEEDBACK_PLUGIN_SOURCE_LOCATION
description: This repo IS the SWE plugin source - never write to the plugin cache
type: feedback
---

**NEVER write to the plugin cache directory** (`~/.claude/plugins/cache/EarthmanWeb/swe/*/`).

This repository (`/Users/webdev/LocalSites/projects/serena-workflow-engine`) IS the source code for the SWE plugin. The cache is a copy — changes there are ephemeral and will be overwritten on next plugin update.

**Why:** User correction — changes were written to the cache instead of the repo, making them non-persistent and invisible to git.

**How to apply:**
- All hook scripts live at `<repo-root>/hooks/{session,prompt,pre,post,stop}/*.py`
- Core modules at `<repo-root>/hooks/swe_hooks/core/*.py`
- Hook config at `<repo-root>/hooks/hooks.json`
- Plugin config at `<repo-root>/.claude-plugin/plugin.json`
- The cache path `~/.claude/plugins/cache/EarthmanWeb/swe/*` is READ-ONLY for reference
- When editing plugin files, write to the REPO, not the cache
- Use Bash+Python for writes (Claude Code's .claude/ protection doesn't apply here since this isn't inside .claude/)
