---
name: feedback-bypass-and-setup-location
description: Init-gate setup flag must be detected in .serena AND legacy .claude; project bypass is user-only and un-settable by the LLM
metadata:
  type: feedback
---

The WF_INIT skip incident was NOT an allowlist problem. The init gate
(`swe_pre_tool_init_gate.py`) checked setup only at `.serena/swe-setup-complete.json`,
but plugin <=v1.0.x wrote that flag to `.claude/swe-setup-complete.json`. On a
project set up under the old layout, the gate's "no setup => don't block" escape
hatch fired and disabled enforcement entirely — Bash ran pre-WF_INIT.

**Why:** prose ("run WF_INIT") is not enforcement. A silently-inert gate plus
workflow prose is exactly the "prose is not a gate" failure — the LLM rationalized
the skip because nothing stopped it.

**How to apply:**
- Setup detection lives in `config.resolve_setup_state()` — checks canonical
  (`.serena/`) AND legacy (`.claude/`) AND prior-use artifacts (`.serena/swe-state`,
  WM files). Only a project with NONE is pristine/permissive. Legacy hits migrate
  to canonical via `migrate_legacy_setup_file()`.
- Project bypass = `"bypass": true` INSIDE `swe-setup-complete.json` (same file as
  init, not a separate `swe-bypass.json`). SessionStart announces it each session
  (`BYPASS_NOTICE`) instead of exiting silently.
- The bypass is **user-only and un-rationalizable**: only `/swe-bypass`
  (`disable-model-invocation: true`) sets it. A hard guard in BOTH
  `swe_pre_tool_init_gate.py` and `swe_pre_edit_validate.py` denies any
  Edit/Write/Bash that writes `"bypass": true` into the setup file. Intent phrases
  like "skip swe" are NOT triggers — only the explicit command.

When changing where a state/flag file lives, add backward-compatible detection of
the OLD location + a migration, or every project on the old layout silently breaks.