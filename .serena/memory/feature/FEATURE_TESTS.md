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
| Formal test suite | stdlib `unittest` (14 files, 590 tests) in `tests/` |

## Unit Test Suite (`tests/`)

Stdlib `unittest` only — no third-party deps (matches the plugin's stdlib-only runtime).

- Run all: `python3 -m unittest discover -s tests -p 'test_*.py' -v`
- Run one: `python3 -m unittest tests.test_core_config -v`
- Import hook/core/script modules via `tests/_hookutil.py` loaders: `import_hook` (hooks/), `import_core` (swe_hooks.*), `load_script` (hyphenated scripts), `load_serena_patch` (serena_memory_patch, stubs serena.*), `reset_caches` (clears config._PROJECT_ROOT, state_manager._transition_matrix_cache, wm_validator._validator between tests).
- Coverage: all pure + IO-injectable functions across core/, hooks/{pre,post,prompt,stop,session}/, mcp/wm_server pure handlers, scripts/swe-bootstrap.py, scripts/serena_memory_patch.py. Side-effect-heavy `main()`/stdio-loop/subprocess entrypoints are intentionally NOT unit-tested.
- `.pyc` gotcha: after editing a source module mid-session, clear `__pycache__` if a test loads stale bytecode (`find . -name __pycache__ -type d -not -path './node_modules/*' -exec rm -rf {} +`).

## Verification

Run from project root:

- Format: `npm run fmt` (dprint: markdown + JSON only — does NOT touch Python).
- Format check: `npm run fmt:check`.
- Unit tests: `python3 -m unittest discover -s tests -p 'test_*.py'`.
- Hook syntax: `python3 -c "import py_compile; py_compile.compile('<path>.py')"` for every modified hook script.
- Manual: exercise the change through the Claude Code plugin system.

## Task-Completion Checklist

Run in order when a task is done:

1. `python3 -m unittest discover -s tests -p 'test_*.py'` — unit suite must be green.
2. `npm run fmt` — format markdown + JSON.
3. `npm run fmt:check` — confirm zero formatting issues.
4. If releasing: `bash scripts/bump-version.sh`.
5. If hooks modified: `py_compile` every changed script (command above).
6. Commit staged changes with a descriptive message.

## Test Gate

`swe_pre_bash_test_gate.py` BLOCKS direct test-runner Bash commands until this memory is read in the current session.

1. The hook intercepts Bash commands matching test patterns.
2. It checks for sentinel `.serena/streams/.test_feature_{session_id}`.
3. Sentinel missing → BLOCK with instruction to read FEATURE_TESTS.
4. Reading FEATURE_TESTS → `swe_post_read_state.py` calls `create_feature_sentinel(session_id, 'test')`.
5. Sentinel present → test commands pass (existence check).
