---
name: DOM_SWE_HOOKS_SENTINELS
description: Sentinel Pattern detail — stream-counted PostToolUse nudges (edit checkpoint, orchestrator drift), shared mechanism, and how to add a new sentinel.
obligations:
  - Sentinels NEVER block (PostToolUse cannot deny) and always exit 0 — nudges only.
metadata:
  type: domain
---

# DOM_SWE_HOOKS_SENTINELS — Sentinel Pattern Detail

Hub: `mem:dom/DOM_SWE_HOOKS`. Parent: `mem:dom/DOM_SWE_HOOKS_POST`.

Sentinels are non-blocking PostToolUse nudges driven by the append-only JSONL stream (`core/stream.py`). Each fires when a threshold count of same-type events accumulates since a resetting marker. They NEVER block (PostToolUse cannot deny) and always exit 0.

## Sentinels

- Edit checkpoint (`swe_post_edit_checkpoint.py`): counts `edit` events; threshold 10 (`CHECKPOINT_THRESHOLD`); reset markers `state`, `checkpoint`; reminder: update Working Memory progress.
- Orchestrator drift (`swe_post_orchestrator_drift.py`): counts `task_work` events; threshold 6 nudge / 12 mandate+edit-block (`DRIFT_THRESHOLD` / `DRIFT_HARD_THRESHOLD`); reset markers `state`, `checkpoint`, `delegation`; reminder: split remaining work into parallel subagents (12+: `swe_pre_edit_validate.py` denies main-agent edits until delegation or `single-agent: <reason>` in WM Context).

## Mechanism (shared)

1. On the matched tool, append a typed event: `append_event(stream, '<type>', …)`.
2. Count since the last resetting marker: `count_events_since_last(stream, marker_types=(…), count_type='<type>')` (thin wrapper `count_edits_since_checkpoint`).
3. At threshold, emit a `HookOutput` message; under threshold, emit a concise `output_status`.

## Adding a New Sentinel

1. Create `hooks/post/swe_post_{name}.py` — append the event, count since markers, nudge at threshold. Model on `swe_post_edit_checkpoint.py`. Always exit 0.
2. If a new reset marker is needed, append that event type from the appropriate hook (e.g. `docread` from `swe_post_read_state.py`).
3. Add a thin counter wrapper in `core/stream.py` if the marker set is reused.
4. Register the PostToolUse matcher in `hooks/hooks.json` with `${CLAUDE_PLUGIN_ROOT}` + a short timeout.
5. Document the sentinel in the list above and in `mem:feature/FEATURE_SWE`.
