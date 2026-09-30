---
name: DOM_SWE_HOOKS_STOP
description: Stop-event hooks — continue-working enforcement and the terse-format response gate (word budget, detail triggers, exemptions).
obligations:
  - swe_stop_response_format.py NEVER blocks when WF_DONE, when stop_hook_active is set, or on a reply ending with a question.
  - At most ONE format block per user turn; a second overage in the same turn emits a WARN attachment, never a second block.
metadata:
  type: domain
---

# DOM_SWE_HOOKS_STOP — Stop Hooks

Hub: `mem:dom/DOM_SWE_HOOKS`.

| Hook                           | Event | Purpose                                   |
| ------------------------------ | ----- | ----------------------------------------- |
| `swe_stop_continue_working.py` | Stop  | Block unnecessary stops, continue-working |
| `swe_stop_response_format.py`  | Stop  | Terse-format gate — see below             |

## `swe_stop_response_format.py` detail

Block replies over the word budget or emitting recap/summary/self-congratulation scaffolding.

- **F1**: natural-language detail triggers (review/report/explain/analysis/"summary of"/total/"walk me through"/why) grant the detail budget alongside the literal `DETAIL:` prefix.
- **F2**: at most ONE block per user turn (sentinel stores turn fingerprint + count; second overage emits a WARN attachment, never a block).
- **F3**: never blocks when workflow state is WF_DONE.
- **G4**: `strip_diagnosis_verification()` exempts the DIAGNOSIS VERIFICATION block + `candidate — unverified` label from the word count.
- ON by default; config from `CLAUDE_PLUGIN_OPTION_RESPONSE_FORMAT_*` env (`core.config.get_response_format_config`). Silent when SWE bypassed / project uninitialized / disabled.
- NEVER blocks when `stop_hook_active` is set (at most 1 forced rewrite per turn — no infinite rewrite loop) and NEVER blocks a reply ending with a question.
- Excludes code blocks, tables, and path lists from the word count.
- Writes a per-session `.format-gate-block-<session>` sentinel (read by `swe_prompt_format_reminder.py`) + a `response-format-offenders.log`, both under `.serena/streams/`.
