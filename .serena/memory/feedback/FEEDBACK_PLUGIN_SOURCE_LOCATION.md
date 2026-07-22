---
name: Plugin Source Location
description: This repo IS the SWE plugin source — write plugin edits here, NEVER to the plugin cache.
metadata:
  type: feedback
---

# Plugin Source Location

NEVER write to the plugin cache (`~/.claude/plugins/cache/EarthmanWeb/swe/*/`). It is a copy — cache edits are ephemeral, overwritten on next plugin update, invisible to git.

This repo (`serena-workflow-engine`) IS the plugin source. Write ALL plugin edits here.

**Why:** User correction — edits went to the cache, became non-persistent and git-invisible.

**How to apply:**
- Hook scripts: `<repo>/hooks/{session,prompt,pre,post,stop}/*.py`
- Core modules: `<repo>/hooks/swe_hooks/core/*.py`
- Hook config: `<repo>/hooks/hooks.json`
- Plugin config: `<repo>/.claude-plugin/plugin.json`
- Treat `~/.claude/plugins/cache/EarthmanWeb/swe/*` as READ-ONLY reference.
- This repo is NOT inside `.claude/`, so Claude Code's `.claude/` write-protection does not apply — edit normally.
