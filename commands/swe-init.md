---
name: swe-init
description: Initialize swe plugin via autonomous agent
---

# /swe-init

First-time setup command for the swe plugin. Launches an autonomous agent to complete all initialization tasks and verify success.

## When to Run

- First time using plugin in a project
- After cloning a repo with the plugin
- When `session-start.sh` reports "INITIAL SETUP REQUIRED"

## Execution

```javascript
Task({
  subagent_type: "general-purpose",
  description: "SWE plugin initialization",
  prompt: `You are the SWE Init Agent.

Read .claude/plugins/serena-workflow-engine/agents/swe-init-agent.md and execute ALL tasks (1-10), then run all 8 verifications.

Only create swe-setup-complete.json after ALL verifications pass.
Output the completion summary at the end.`
})
```

## Agent Definition

See [agents/swe-init-agent.md](../agents/swe-init-agent.md) for tasks, verifications, and troubleshooting.
