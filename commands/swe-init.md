---
name: swe-init
description: Initialize swe plugin via autonomous agent
---

# /swe-init

First-time setup command for the SWE plugin. Launches an autonomous agent to complete all initialization tasks and verify success.

## When to Run

- First time using plugin in a project
- After cloning a repo with the plugin
- When SessionStart hook reports "Project Not Initialized"

## Execution

```javascript
Task({
  subagent_type: "general-purpose",
  description: "SWE plugin initialization",
  prompt: `You are the SWE Init Agent.

First resolve SWE_PLUGIN_ROOT by checking these paths in order (use the first that contains .claude-plugin/plugin.json):
1. .claude/plugins/serena-workflow-engine (local dev)
2. ~/.claude/plugins/marketplaces/EarthmanWeb (marketplace install)
3. Latest version dir in ~/.claude/plugins/cache/EarthmanWeb/swe/ (cache)

Then read $SWE_PLUGIN_ROOT/agents/swe-init-agent.md and execute ALL tasks (1-9), then run all 6 verifications.

Only create swe-setup-complete.json after ALL verifications pass.
Output the completion summary at the end.`
})
```

## Agent Definition

See [agents/swe-init-agent.md](../agents/swe-init-agent.md) for tasks, verifications, and troubleshooting.
