---
name: REF_SWE_DEPLOY
description: How to deploy the Serena Workflow Engine plugin — push source to GitHub, plugin auto-updates next load; cache priming allowed during active dev.
metadata:
  type: reference
  keywords: deploy, push, github, publish, release, plugin auto-update, cache priming
---

# REF_SWE_DEPLOY — Deploying the SWE Plugin

Deploying the Serena Workflow Engine plugin is just **pushing the source repo to
GitHub**. No build, publish, or release step.

- Source repo: `origin` = `EarthmanWeb/serena-workflow-engine`, branch `main`.
- `git push origin main` IS the deploy. Claude Code auto-updates the installed
  plugin from the marketplace on the next session load; the pushed commit is
  live next session.
- **Cache priming is allowed during active development**: copy a changed source
  file over its installed copy (`~/.claude/plugins/marketplaces/EarthmanWeb/…`
  or `cache/EarthmanWeb/swe/<version>/…`) so the CURRENT session picks it up
  without waiting for auto-update. Convenience only — cache edits are
  overwritten on the next update and are never the source of truth. Still push.

Full dev standards + dual-location + hook-sync rules: `REF_SWE_DEVELOPMENT`.
