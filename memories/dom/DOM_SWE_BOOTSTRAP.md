---
name: DOM_SWE_BOOTSTRAP
description: New-project bootstrap/init three-tier flow, bypass mechanism, swe-bootstrap.py guards, .gitignore additions.
obligations:
  - NEVER set `"bypass": true` in `swe-setup-complete.json` — bypass is user-only, triggered ONLY by the user running `/swe-bypass`; a hard guard in `swe_pre_tool_init_gate.py` and `swe_pre_edit_validate.py` denies any Edit/Write/Bash attempting it.
  - Run the auto-memory symlink step FIRST in init (before any memory is written) so init-time memories land in `.serena/memory/`.
metadata:
  type: domain
---

# DOM_SWE_BOOTSTRAP

When the plugin is installed at user level and a new project is opened, use a three-tier approach — never block the user.

## Tier 1: Prompt to Set Up (new project detected)

SessionStart detects no `swe-setup-complete.json` and prompts (does NOT block):

- Option 1: say "yes" or run `/swe-init` to set up.
- Option 2: run `/swe-bypass` to disable (user-only).

## Tier 2: Project Bypass (user-only command)

- Bypass is a `"bypass": true` field inside `swe-setup-complete.json` (same file used for init — no separate `swe-bypass.json`).
- When set: all three hooks (SessionStart, UserPromptSubmit, PreToolUse init gate) skip enforcement.
- SessionStart announces the bypass each session (`BYPASS_NOTICE`) with removal instructions — NOT silent.
- Re-enable by setting `"bypass": false` (or removing the field) in `.serena/swe-setup-complete.json`.
- Bypass is user-only and un-rationalizable: set ONLY via `/swe-bypass` (`disable-model-invocation: true`). Intent phrases like "skip swe" are NOT triggers.
- Legacy: `.serena/swe-bypass.json` still honored for backward compatibility; new bypasses use the in-file field.

## Tier 3: Full Init (user accepts)

1. User says "yes" → `swe-bootstrap.py` runs inline (via UserPromptSubmit hook).
2. Bootstrap creates: `.serena/`, `.serena/swe/`, `.serena/memories/`, `.serena/.gitignore`, `project.yml`, `memory-paths.conf`, `CLAUDE_PREFIX.md` injection, rendered template memories (`{{placeholders}}` filled from detected project info), `swe-setup-complete.json` with `bootstrapped: true`.
3. Init gate is unblocked (gate checks `complete` field; bootstrapped-but-not-complete passes through).
4. User runs `/swe-init`, which launches the init agent (11 tasks):
   - Detect environment + resolve plugin root.
   - Auto-memory symlink (FIRST) — redirect Claude Code auto-memory into `.serena/memory/` before any memory is written.
   - Run bootstrap (if not already done).
   - Verify MCP servers (Serena, swe-wm).
   - Serena onboarding (+ migrate default memories into SWE templates).
   - Relocate & link the `memory_maintenance` memory into `ref/REF_MEMORY_MAINTENANCE` (sourced from the EarthmanWeb/serena fork — NEVER upstream oraios/serena or the uv cache).
   - Verify and install language servers.
   - Verify SWE plugin is enabled.
   - Review CLAUDE.md for conflicts.
   - Install Serena Log Viewer VSCode extension.
   - Finalize setup (`complete: true`).
5. Full workflow is now active.

## State Flow

```
New Project → No setup file
  → SessionStart prompts (not blocks)
  ├── "yes" → Bootstrap runs → bootstrapped: true → Scaffold → complete: true → Full workflow
  └── user runs /swe-bypass → "bypass": true in swe-setup-complete.json → hooks skip + announce bypass each session
```

## swe-bootstrap.py Guards

| Guard                                                      | Behavior                     |
| ---------------------------------------------------------- | ---------------------------- |
| `.serena/swe-bypass.json` exists                           | Exit: "SWE bypassed"         |
| `.serena/swe-setup-complete.json` has `complete: true`     | Exit: "Already initialized"  |
| `.serena/swe-setup-complete.json` has `bootstrapped: true` | Exit: "Already bootstrapped" |

## .gitignore Additions (via bootstrap)

`.serena/.gitignore` (auto-created inside `.serena/`, only if absent). Default set (paths relative to `.serena/`):

```
/cache
/streams
/memories
/swe-setup-complete
```

`/memories` blanket-ignores the plural session-WM dir (`.serena/memories/`, holds `WM_*.md`). Committed typed feature memories live in the singular `.serena/memory/` and are NOT matched. Source: `ensure_serena_gitignore()` in `scripts/swe-bootstrap.py`.

Project root `.gitignore` (appended by `update_gitignore()`, guarded by the `!.serena/memory/` marker):

```
.serena/swe-bypass.json
.serena/swe-setup-complete.json
.serena/swe-state/

# Override global .serena/* ignore — un-ignore project memories
!.serena/memory/
!.serena/memory/**/*.md
!.serena/memories/
!.serena/memories/**/*.md
.serena/memories/WM_*.md
```
