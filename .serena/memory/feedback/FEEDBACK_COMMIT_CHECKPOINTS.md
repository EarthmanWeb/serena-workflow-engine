---
name: Commit at checkpoints
description: Commit each verified unit of work immediately; never leave the work tree dirty between stages.
metadata:
  type: feedback
---

# Commit at Checkpoints

- Commit each verified stage (tests green) before starting the next stage or waiting on agents.
- Never end a turn with uncommitted task work in the tree.
- Subagents do not commit; the orchestrator commits right after verifying their output.

**Why:** User correction (2026-09-29): "make commits, stop leaving the work tree so dirty."

**How to apply:** After every verification pass → `git add` the task files → commit on the current feature branch. Never push without asking.
