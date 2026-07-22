---
name: Bypass & Setup-Flag Location
description: Init gate must detect setup in .serena AND legacy .claude; project bypass is user-only and un-settable by the LLM.
metadata:
  type: feedback
---

# Bypass & Setup-Flag Location

The WF_INIT skip incident was NOT an allowlist problem. `swe_pre_tool_init_gate.py` checked setup ONLY at `.serena/swe-setup-complete.json`. Plugin ≤v1.0.x wrote that flag to `.claude/swe-setup-complete.json`. On an old-layout project, the gate's "no setup ⇒ don't block" escape hatch fired and disabled enforcement — Bash ran pre-WF_INIT.

**Why:** Prose ("run WF_INIT") is not enforcement. A silently-inert gate + workflow prose = the "prose is not a gate" failure: the LLM rationalized the skip because nothing stopped it.

**How to apply:**
- Setup detection lives in `config.resolve_setup_state()`. It checks canonical (`.serena/`) AND legacy (`.claude/`) AND prior-use artifacts (`.serena/swe-state`, WM files). ONLY a project with NONE is pristine/permissive. Legacy hits migrate to canonical via `migrate_legacy_setup_file()`.
- Project bypass = `"bypass": true` INSIDE `swe-setup-complete.json` (same file as init — NOT a separate `swe-bypass.json`). SessionStart announces it every session (`BYPASS_NOTICE`); NEVER exit silently.
- Bypass is user-only and un-rationalizable: ONLY `/swe-bypass` (`disable-model-invocation: true`) sets it. A hard guard in BOTH `swe_pre_tool_init_gate.py` and `swe_pre_edit_validate.py` DENIES any Edit/Write/Bash that writes `"bypass": true` into the setup file. Intent phrases like "skip swe" are NOT triggers — only the explicit command.
- When moving any state/flag file: ALWAYS add backward-compatible detection of the OLD location + a migration, or every old-layout project silently breaks.
