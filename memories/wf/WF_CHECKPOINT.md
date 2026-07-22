---
name: WF_CHECKPOINT
description: Optional progress-check state; self-check, never a mandatory gate.
metadata:
  type: workflow
---

# WF_CHECKPOINT — Optional Progress Check

> **On step WF_CHECKPOINT**

## Nature

- WF_CHECKPOINT is a self-check, NEVER a mandatory gate.
- Edit counter nudges at 10 edits (informational only). It NEVER blocks.
- Enter this state ONLY to pause and record progress. Do NOT enter because a hook forced you — no hook forces it.
- State auto-persists to the JSON state file at message boundaries (Stop hook) and state transitions (post-read hook).
- Update WM manually ONLY to record progress notes for cross-message recovery.

## When to Use

- Completed a significant phase and want to record it.
- About to switch to a different area of the codebase.
- Updating the task description or feature keys.

## How to Update

- Update progress via swe-wm MCP (does NOT trigger edit hooks): `swe_wm_update_section(section="Progress", content="...")`
- For a comprehensive update, invoke the skill: `/swe-wm-update --from WF_CHECKPOINT`

## Next Step

| Condition         | Read Next    |
| ----------------- | ------------ |
| More work remains | `WF_EXECUTE` |
| All work complete | `WF_VERIFY`  |
