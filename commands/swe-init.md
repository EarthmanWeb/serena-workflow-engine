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
  subagent_type: "swe:swe-init-agent",
  description: "SWE plugin initialization",
  prompt: `You are the SWE Init Agent.

First resolve SWE_PLUGIN_ROOT by checking these paths in order (use the first that contains .claude-plugin/plugin.json):
1. .claude/plugins/serena-workflow-engine (local dev)
2. ~/.claude/plugins/marketplaces/EarthmanWeb (marketplace install)
3. Latest version dir in ~/.claude/plugins/cache/EarthmanWeb/swe/ (cache)

Then read $SWE_PLUGIN_ROOT/agents/swe-init-agent.md and execute its tasks in order (two-pass flow — see Task 3.5 below), then run all 7 verifications.

Task 3.5 is a MANDATORY reconnect gate: if this is the FIRST pass (swe-setup-complete.json newly shows bootstrapped:true, complete:false), STOP after bootstrap and RETURN control with the reconnect instruction — do NOT run Tasks 4+ on the first pass. If swe-setup-complete.json already shows bootstrapped:true on entry, this is the RESUME pass (Serena has been reconnected): skip Tasks 2–3.5 and run Tasks 4–11.

Only create swe-setup-complete.json (complete:true) after ALL verifications pass.
Output the completion summary at the end.`
})
```

## Two-Pass Flow (Serena reconnect gate)

`memory-paths.conf` is created by bootstrap **after** this session's Serena MCP server already connected. Serena reads that file only at connection time, so it must reconnect before any memory is written — otherwise memory operations resolve against the default path (split-brain: writes and reads land in different trees).

1. **Pass 1 — `/swe-init`:** runs Tasks 1–3 (symlink, bootstrap → writes `memory-paths.conf`), then STOPS at the Task 3.5 gate and asks the user to reconnect Serena (`/mcp` → `serena` → Reconnect) and re-run `/swe-init`.
2. **Pass 2 — `/swe-init` (resume):** bootstrap is idempotent (guards on `bootstrapped: true`); the agent detects the resume, skips Tasks 2–3.5 (re-verifying the auto-memory symlink from Task 2 is intact before writing memories), and runs Tasks 4–11 with Serena now reading the correct memory paths.

## Agent Definition

See [agents/swe-init-agent.md](../agents/swe-init-agent.md) for tasks, verifications, and troubleshooting. Task 3.5 documents the reconnect gate and resume detection.
