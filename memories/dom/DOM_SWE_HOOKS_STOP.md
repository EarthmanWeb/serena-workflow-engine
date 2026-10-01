---
name: DOM_SWE_HOOKS_STOP
description: Stop-event hooks — continue-working enforcement and the terse-format response gate (word budget, detail triggers, exemptions).
obligations:
  - turn_signals.py exports unresolved_items(text) — returns [section] labels + sentences ending in ? or matching indirect-ask patterns; final_reply_text(transcript_path) returns assistant prose after last tool_use.
  - swe_stop_continue_working.py and swe_stop_response_format.py both allow stop BEFORE any blocking logic when stop_hook_active is set or when turn_signals.user_spoke_mid_turn(transcript_path) is true (queued_command human attachment or queue-operation enqueue after last genuine user prompt).
  - swe_stop_continue_working.py applies unresolved-items gate in ANY state (incl. WF_DONE/WF_VERIFY): non-empty unresolved_items(final_reply_text()) → decision:block with AskUserQuestion instruction (one question per item, 2-4 options); logs stop_blocked reason unresolved_items. Under blanket consent, reason directs self-resolution with [consent-override] only for destructive actions.
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

## Shared mid-turn detection & prose analysis (`core/turn_signals.py`)

Both Stop hooks import `hooks/swe_hooks/core/turn_signals.py` — pure helpers, no IO except reading the transcript file:

- `text_of(content)` / `is_genuine_user(rec)` — CANONICAL implementations (moved from `swe_stop_response_format.py`, which re-exports them as module attributes for compat: `gate.text_of`, `gate.is_genuine_user`). `is_genuine_user` also excludes a `"Stop hook feedback:"`-prefixed record.
- `ends_with_question(text)` — true when the final non-blank paragraph ends with `?` (ignoring trailing closing punctuation/quotes/markdown emphasis). Moved from `swe_stop_response_format.py`, re-exported there too.
- `queued_command_prompt_text(rec)` — returns the prompt text of a `type: "attachment"` record whose `attachment.type == "queued_command"` and is human-originated (`humanTurn is True` or `origin.kind == "human"`); else `None`.
- `user_spoke_mid_turn(transcript_path)` — true when, AFTER the last genuine user prompt record, the transcript contains a human queued_command attachment or a `type: "queue-operation", operation: "enqueue"` record — i.e. the user already typed a follow-up before this Stop event fired. Missing/unreadable transcript → `False` (fail safe, never suppresses a gate's normal behavior).
- `unresolved_items(text)` — returns list of open questions anywhere in text (word char/quote/paren directly before `?`), indirect asks (tell me/let me know ... if/whether/which; "if you want/like/prefer/need"; "I can/happy to ... also/too/instead"; "want/would you like me to"; "your call"/"up to you"), and short standalone pending-section headings (Before fixing/proceeding…, Open questions, Questions, Pending, Outstanding, Unresolved, Needs your decision/input, Decisions needed, Remaining, Follow-ups, TODO) as "[section] <label>". Ignores fenced/inline code, URLs, blockquotes. Empty list means reply leaves nothing unresolved.
- `final_reply_text(transcript_path)` — returns assistant text AFTER the last tool_use of the current turn (the closing reply user reads); text written before a later tool call is excluded. Missing/unreadable transcript → "" (fail safe).

## `swe_stop_continue_working.py` detail

Order: `stop_hook_active` set → `user_spoke_mid_turn(transcript_path)` allow; THEN unresolved-items gate in ANY state (incl. WF_DONE/WF_VERIFY): non-empty `unresolved_items(final_reply_text())` → `decision: block` with reason from `unresolved_items_reason()` instructing AskUserQuestion (one question per item, 2-4 options, then terse summary with no questions/offers/pending sections); logs `stop_blocked` reason `unresolved_items`. Under WM blanket consent (`session.wm_has_blanket_consent`, MOVED from swe_pre_question_consent_gate.py to core/session.py) the reason instead says resolve each item yourself; destructive only via AskUserQuestion with `[consent-override]`. The old "ends_with_question → allow stop" guard is REMOVED — ends_with_question still used by swe_stop_response_format.py.

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
