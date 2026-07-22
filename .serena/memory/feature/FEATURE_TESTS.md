---
name: Test Suite
description: Verification approach for this repo (no formal test suite) + task-completion checklist + test-gate mechanics.
metadata:
  type: feature
---

# FEATURE_TESTS — Test Suite

| Property | Value |
| --- | --- |
| Key | TESTS |
| Type | infrastructure |
| Language | Python |
| Formal test suite | None |

## Verification (no automated suite exists)

Run from project root:

- Format: `npm run fmt` (dprint: markdown + JSON)
- Format check: `npm run fmt:check`
- Hook syntax: `python3 -c "import py_compile; py_compile.compile('<path>.py')"` for every modified hook script.
- Manual: exercise the change through the Claude Code plugin system.

## Task-Completion Checklist

Run in order when a task is done:

1. `npm run fmt` — format markdown + JSON.
2. `npm run fmt:check` — confirm zero formatting issues.
3. If releasing: `bash scripts/bump-version.sh`.
4. If hooks modified: `py_compile` every changed script (command above).
5. Commit staged changes with a descriptive message.

## Test Gate

`swe_pre_bash_test_gate.py` BLOCKS direct test-runner Bash commands until this memory is read in the current session.

1. The hook intercepts Bash commands matching test patterns.
2. It checks for sentinel `.serena/streams/.test_feature_{session_id}`.
3. Sentinel missing → BLOCK with instruction to read FEATURE_TESTS.
4. Reading FEATURE_TESTS → `swe_post_read_state.py` calls `create_feature_sentinel(session_id, 'test')`.
5. Sentinel present → test commands pass (existence check).
