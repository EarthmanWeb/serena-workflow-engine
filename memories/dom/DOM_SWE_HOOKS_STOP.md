---
name: DOM_SWE_HOOKS_STOP
description: Stop-event hooks — continue-working enforcement and the terse-format response gate (word budget, detail triggers, exemptions).
obligations:
  - swe_stop_continue_working.py and swe_stop_response_format.py both allow the stop BEFORE any blocking logic when stop_hook_active is set or when turn_signals.user_spoke_mid_turn(transcript_path) is true (queued_command human attachment or queue-operation enqueue after the last genuine user prompt).
  - swe_stop_continue_working.py also allows the stop when the last assistant message ends with a question (turn_signals.ends_with_question).
  - swe_stop_response_format.py in the default "advise" mode NEVER emits decision:block — it marks the sentinel + logs the offender so swe_prompt_format_reminder.py still surfaces the budget next turn; set response_format_mode=block for the legacy blocking behavior.
  - At most ONE format block per user turn in "block" mode; a second overage in the same turn emits a WARN attachment, never a second block.
metadata:
  type: domain
---

# DOM_SWE_HOOKS_STOP — Stop Hooks

Hub: `mem:dom/DOM_SWE_HOOKS`.

| Hook                           | Event | Purpose                                   |
| ------------------------------ | ----- | ----------------------------------------- |
| `swe_stop_continue_working.py` | Stop  | Block unnecessary stops, continue-working |
| `swe_stop_response_format.py`  | Stop  | Terse-format gate — see below             |

## Shared mid-turn detection (`core/turn_signals.py`)

Both Stop hooks import `hooks/swe_hooks/core/turn_signals.py` — pure helpers, no IO except reading the transcript file:

- `text_of(content)` / `is_genuine_user(rec)` — CANONICAL implementations (moved from `swe_stop_response_format.py`, which re-exports them as module attributes for compat: `gate.text_of`, `gate.is_genuine_user`). `is_genuine_user` also excludes a `"Stop hook feedback:"`-prefixed record.
- `ends_with_question(text)` — true when the final non-blank paragraph ends with `?` (ignoring trailing closing punctuation/quotes/markdown emphasis). Moved from `swe_stop_response_format.py`, re-exported there too.
- `queued_command_prompt_text(rec)` — returns the prompt text of a `type: "attachment"` record whose `attachment.type == "queued_command"` and is human-originated (`humanTurn is True` or `origin.kind == "human"`); else `None`.
- `user_spoke_mid_turn(transcript_path)` — true when, AFTER the last genuine user prompt record, the transcript contains a human queued_command attachment or a `type: "queue-operation", operation: "enqueue"` record — i.e. the user already typed a follow-up before this Stop event fired. Missing/unreadable transcript → `False` (fail safe, never suppresses a gate's normal behavior).

## `swe_stop_continue_working.py` detail

Allow the stop BEFORE any blocking logic, in order: `stop_hook_active` set → `user_spoke_mid_turn(transcript_path)` → last assistant text `ends_with_question`. Each case persists state and returns `output_empty()` immediately — none of the continue-working logic below it runs.

## `swe_stop_response_format.py` detail

Block (or advise — see mode) replies over the word budget or emitting recap/summary/self-congratulation scaffolding.

- **F1**: natural-language detail triggers (review/report/explain/analysis/"summary of"/total/"walk me through"/why) grant the detail budget alongside the literal `DETAIL:` prefix.
- **F2**: in "block" mode, at most ONE block per user turn (sentinel stores turn fingerprint + count; second overage emits a WARN attachment, never a block). "advise" mode never blocks at all, so F2 does not apply.
- **F3**: never blocks when workflow state is WF_DONE.
- **G4**: `strip_diagnosis_verification()` exempts the DIAGNOSIS VERIFICATION block + `candidate — unverified` label from the word count.
- ON by default; config from `CLAUDE_PLUGIN_OPTION_RESPONSE_FORMAT_*` env (`core.config.get_response_format_config`, `mem:dom/DOM_SWE_RESPONSE_FORMAT_GATE`). Silent when SWE bypassed / project uninitialized / disabled.
- Skips silently (before any word-count logic) on `user_spoke_mid_turn(transcript_path)` — forcing a block/rewrite after the user already typed a follow-up produces a wasted turn.
- NEVER blocks when `stop_hook_active` is set (at most 1 forced rewrite per turn — no infinite rewrite loop).
- **Mode** (`response_format_mode`, default `advise`): `advise` never emits `decision:block` — an overage still calls `mark_blocked()` (sentinel) and `log_offender()`, then exits 0 silently, so `swe_prompt_format_reminder.py` surfaces the budget on the NEXT prompt. `block` is the legacy behavior — emits `decision:block`, subject to the F2 once-per-turn cap.
- `read_transcript()` treats a queued_command human attachment as a turn boundary the same way a genuine user record does — resets `assistant_since_user` and `last_user_text` — so prose written BEFORE a mid-turn follow-up is never counted toward the current turn's word budget.
- Excludes code blocks, tables, and path lists from the word count.
- Writes a per-session `.format-gate-block-<session>` sentinel (read by `swe_prompt_format_reminder.py`) + a `response-format-offenders.log`, both under `.serena/streams/` — written in BOTH modes.
  </content>
