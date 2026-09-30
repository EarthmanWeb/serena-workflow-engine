---
name: DOM_SWE_RESPONSE_FORMAT_GATE
description: Config-driven terse-reply-budget gate (swe_stop_response_format.py + swe_prompt_format_reminder.py) — config keys, detail triggers, exemptions, runtime sentinel files.
obligations:
  - Configure the response-format plugin option ONLY in a user/managed scope (`~/.claude.json`), NEVER in the repo — set `response_format_enabled=false` to opt a project out.
metadata:
  type: domain
---

# DOM_SWE_RESPONSE_FORMAT_GATE

`swe_stop_response_format.py` (Stop) enforces a terse reply budget; `swe_prompt_format_reminder.py` (UserPromptSubmit) surfaces the budget the turn after a block. Both ON by default; both skip silently when SWE is bypassed, the project is uninitialized, or the gate is disabled.

## Config — canonical Claude-plugin mechanism

- Declared as a `userConfig` block in `.claude-plugin/plugin.json`. Claude Code exports each key to hook subprocesses as `CLAUDE_PLUGIN_OPTION_<KEY>`.
- Read via `core.config.get_response_format_config()` — env-only, NEVER a project file (project-scoped `.claude/settings.json` is intentionally not trusted for plugin config).
- Keys + defaults: `response_format_enabled` (bool, true) · `response_format_terse_limit` (int, 40) · `response_format_detail_limit` (int, 600).
- Per-project override: set the plugin option in a user/managed scope (`~/.claude.json`), NOT the repo. Opt a project out with `response_format_enabled=false`.

## Detail & Exemption Rules

- Detail is opt-in via the literal `DETAIL:` / `DETAIL -` prompt prefix OR natural-language detail triggers (F1): "review", "report", "explain", "analysis", "summary of", "total", "walk me through", "why" — any match grants the detail budget, no block.
- At most ONE format block per user turn (second overage → WARN attachment, F2).
- WF_DONE turns are NEVER blocked (F3).
- The DIAGNOSIS VERIFICATION block + `candidate — unverified` label are word-budget-exempt (G4).
- Excludes code blocks/tables/path lists from the word count.

## Runtime Files (under `.serena/streams/`)

| File                            | Purpose                                                                    |
| ------------------------------- | -------------------------------------------------------------------------- |
| `.format-gate-block-<session>`  | Sentinel the Stop gate writes on a block; the prompt reminder reads+clears |
| `response-format-offenders.log` | One entry per blocked turn (prompt + offending reply) for regex tuning     |

## Testable Seam

`swe_stop_response_format.evaluate(assistant_msgs, last_user_text, terse_limit, detail_limit, retry)` — pure function (no IO), returns `(reason|None, scanned, words)`. Tests: `tests/test_response_format_gate.py`.
