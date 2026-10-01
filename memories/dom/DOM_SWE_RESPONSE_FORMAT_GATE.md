---
name: DOM_SWE_RESPONSE_FORMAT_GATE
description: Config-driven terse-reply-budget gate (swe_stop_response_format.py + swe_prompt_format_reminder.py) — config keys, modes, detail triggers, exemptions, runtime sentinel files.
obligations:
  - Configure the response-format plugin option ONLY in a user/managed scope (`~/.claude.json`), NEVER in the repo — set `response_format_enabled=false` to opt a project out.
  - Default mode is "advise": an overage never emits decision:block, only marks the sentinel + logs the offender for the next-prompt reminder. Set `response_format_mode=block` for the legacy blocking behavior.
metadata:
  type: domain
---

# DOM_SWE_RESPONSE_FORMAT_GATE

`swe_stop_response_format.py` (Stop) enforces a terse reply budget; `swe_prompt_format_reminder.py` (UserPromptSubmit) surfaces the budget the turn after a block/advise. Both ON by default; both skip silently when SWE is bypassed, the project is uninitialized, or the gate is disabled.

## Config — canonical Claude-plugin mechanism

- Declared as a `userConfig` block in `.claude-plugin/plugin.json`. Claude Code exports each key to hook subprocesses as `CLAUDE_PLUGIN_OPTION_<KEY>`.
- Read via `core.config.get_response_format_config()` — env-only, NEVER a project file (project-scoped `.claude/settings.json` is intentionally not trusted for plugin config).
- Keys + defaults: `response_format_enabled` (bool, true) · `response_format_terse_limit` (int, 40) · `response_format_detail_limit` (int, 600) · `response_format_mode` (`advise`|`block`, default `advise`; any other/malformed value falls back to `advise`).
- Per-project override: set the plugin option in a user/managed scope (`~/.claude.json`), NOT the repo. Opt a project out with `response_format_enabled=false`.

## Mode

- `advise` (default): an overage NEVER emits `decision:block` — the Stop event is allowed through silently. It still marks the per-session `.format-gate-block-<session>` sentinel and logs the offender, so `swe_prompt_format_reminder.py` surfaces the budget on the next UserPromptSubmit.
- `block` (legacy): emits `decision:block`, subject to the once-per-turn cap (F2) — a second overage in the same turn WARNs instead of blocking again.
- `swe_prompt_format_reminder.py` reads the current mode and picks mode-aware wording: "exceeded the response-format budget" (advise) vs "was BLOCKED by the response-format gate" (block).

## Mid-Turn Skip

`swe_stop_response_format.py` skips silently, before any word-count logic, when `turn_signals.user_spoke_mid_turn(transcript_path)` is true — the user already typed a follow-up (queued_command human attachment, or a queue-operation enqueue) before this Stop event fired, so forcing a block/advise now produces a wasted rewrite the user never sees. `read_transcript()` also treats a queued_command human attachment as a turn boundary, resetting `assistant_since_user`/`last_user_text` the same way a genuine user record does — prose written before the mid-turn follow-up is never counted toward the CURRENT turn's word budget. See `mem:dom/DOM_SWE_HOOKS_STOP` for the shared `core/turn_signals.py` helpers.

## Detail & Exemption Rules

- Detail is opt-in via the literal `DETAIL:` / `DETAIL -` prompt prefix OR natural-language detail triggers (F1): "review", "report", "explain", "analysis", "summary of", "total", "walk me through", "why" — any match grants the detail budget, no block.
- At most ONE format block per user turn in `block` mode (second overage → WARN attachment, F2); `advise` mode never blocks so F2 does not apply.
- WF_DONE turns are NEVER blocked (F3).
- `stop_hook_active` set NEVER blocks (at most 1 forced rewrite per turn).
- The DIAGNOSIS VERIFICATION block + `candidate — unverified` label are word-budget-exempt (G4).
- Excludes code blocks/tables/path lists from the word count.

## Runtime Files (under `.serena/streams/`)

| File                            | Purpose                                                                                    |
| ------------------------------- | ------------------------------------------------------------------------------------------ |
| `.format-gate-block-<session>`  | Sentinel the Stop gate writes on an overage (both modes); the prompt reminder reads+clears |
| `response-format-offenders.log` | One entry per overage turn (prompt + offending reply) for regex tuning, both modes         |

## Testable Seam

`swe_stop_response_format.evaluate(assistant_msgs, last_user_text, terse_limit, detail_limit, retry)` — pure function (no IO), returns `(reason|None, scanned, words)`. Tests: `tests/test_response_format_gate.py`, `tests/test_turn_signals.py`.
</content>
