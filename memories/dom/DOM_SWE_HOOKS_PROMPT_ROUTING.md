---
name: DOM_SWE_HOOKS_PROMPT_ROUTING
description: swe_user_prompt_workflow.py intent classification, state-aware routing, session-reset rules, and task-boundary stamping for sweep verification.
obligations:
  - Only an unambiguous `new_task` opener or post-completion WF_DONE re-entry auto-transitions from an active state to WF_CLASSIFY — unknown/possible_pivot prompts STAY and defer to the model.
  - Determine intent solely by pattern match + `current_state`; NEVER use message length as a heuristic.
metadata:
  type: domain
---

# DOM_SWE_HOOKS_PROMPT_ROUTING — Prompt Intent Routing

Hub: `mem:dom/DOM_SWE_HOOKS`.

`swe_user_prompt_workflow.py` classifies each user prompt by pattern match, then routes.

## Intent Table

- **continuation**: detected by "yes", "okay, do X", "any other issues?", "let me know if", status checks. Action: stay in current state; brief reminder. The CONTINUE directive is emitted ONLY on an actual state change (`continuation` event) — a same-state continuation prompt gets the brief reminder without re-emitting CONTINUE.
- **addition**: detected by "also", "remove/change/update the", "while you're at it". Action: stay in state; incorporate addition.
- **new_task**: detected by UNAMBIGUOUS openers only — "new task", "switch to", "let's work on", "help me build", "i need you to" (`NEW_TASK_PATTERNS`). Bare imperative verb at start ("fix", "add", "create" — `BARE_VERB_TASK_PATTERNS`) is new_task ONLY when NO task is in flight (state ∈ WF_CLASSIFY/WF_INIT/UNINITIALIZED/WF_DONE/None). Action: transition to WF_CLASSIFY (the one verified-pivot path).
- **possible_pivot**: detected by a bare imperative verb at start WHILE in an active task state. Action: stay in current state; inject `pivot_analysis_note` — model judges pivot vs. feedback from full context, self-runs `/swe-goto WF_CLASSIFY` only on a genuine pivot.
- **unknown**: no pattern match. Action: active state → stay + `pivot_analysis_note`; WF_CLASSIFY/WF_INIT → emit classify instruction.
- **needs_implementation** (WF_RESEARCH only): a change request ("implement", "do it", "do everything", "fix", "add"...) while `current_state == WF_RESEARCH`. Action: emit a `needs_implementation` directive → `WF_CLASSIFY`, instead of the generic "ambiguous, stay" unknown/possible_pivot handling. Take it by reading `wf/WF_CLASSIFY` (declared `readBackward[WF_RESEARCH]` entry — the read itself transitions); on loop-guard "inspecting — no transition", call `mcp__plugin_swe_swe-wm__swe_wm_transition(session_id, target_state="WF_CLASSIFY", reason="needs_implementation")`.

`analyze_prompt(prompt, current_state)` is STATE-AWARE — the same bare-verb prompt is `new_task` before work starts but `possible_pivot` mid-task; in `WF_RESEARCH` a change-request opener is `needs_implementation`, not `possible_pivot`.

⛔ **The deterministic hook does NOT force-decide ambiguous pivots in an active state.** Unknown- and `possible_pivot`-intent prompts in an active state STAY in the current state — the hook emits `pivot_analysis_note` and the MODEL judges pivot-vs-feedback from full conversation context (which a regex cannot), self-transitioning with `/swe-goto WF_CLASSIFY` only on a genuine brand-new task or complete pivot. Ordinary mid-task feedback ("that didn't work", "fix the spacing too", "no, do it differently") therefore keeps working in place. Only two paths auto-`transition_to('WF_CLASSIFY')` from an active state: an unambiguous `new_task` opener, and (post-completion) same-session re-entry from WF_DONE. `NEW_TASK_CUE_RE` ("instead", "now", "new task", "switch to", …) is a HINT surfaced in `pivot_analysis_note`, NEVER the decider. Default is STAY. Rationale: `WF_EXECUTE → WF_CLASSIFY` is not a valid transition-matrix edge, so an active-state re-classification is a forced bypass — reserve it for verified pivots.

## Pattern Rules

- NEVER anchor continuation patterns with `$` — "okay, you should have the latest" must match, not only bare "okay".
- Determine intent solely by pattern match + `current_state`. NEVER use message length as a heuristic. Only unambiguous openers or a no-active-task bare verb may auto-transition; everything else defers to the model.

## Session-Reset Rules

- Compute `should_reset` from WM filename + state-data existence. NEVER parse WM markdown for this.
- WM filename `WM_{session_id}.md` already carries session_id — do NOT parse content to recover it.

## State-Aware Responses

- WF_INIT → emit MANDATORY instruction to read WF_INIT (blocking gate).
- WF_CLASSIFY + continuation → emit MANDATORY instruction to read WF_CLASSIFY.
- Active state + continuation → emit brief "Continue with workflow".
- Active state + unknown/possible_pivot → STAY; emit `pivot_analysis_note` (model decides pivot vs. feedback, self-transitions only on a true pivot).
- WF_RESEARCH + change-request opener → emit `needs_implementation` directive → read `wf/WF_CLASSIFY` (`readBackward` entry advances the read) or call `mcp__plugin_swe_swe-wm__swe_wm_transition(session_id, target_state="WF_CLASSIFY", reason="needs_implementation")` — NEVER the bare `/swe-goto WF_CLASSIFY` advice.
- new_task (unambiguous opener) → transition to WF_CLASSIFY regardless of current state.
- First transition into WF_CLASSIFY with no WM → create WM + sentinel here.
- Valid WM but missing sentinel → recreate sentinel before routing (prevents init-gate deadlock).
- Same-session new_task from WF_DONE → include previous feature keys for fast-path to WF_ARCH_REVIEW.

## Task-Boundary Stamping (Sweep Verification)

- `events_since_task_start()` bounds the current task at the LAST `session_start` event or `state` event with `to_s=WF_CLASSIFY`. Emit those ONLY at genuine task starts.
- `events_since_task_start(since_sweep=True)` ALSO treats the last `sweep` marker as a boundary. `_check_memory_sweep` stamps a `sweep` event on every SUCCESSFUL sweep and accounts docpending links ONLY since that marker — so once a sweep passes, its links are settled and a later sweep in the same session never re-demands them (fixes cross-task docpending accumulation, where continuation/pivot prompts that DON'T re-stamp a task boundary pooled every prior task's links into one window). `docread`/`loaded` verification still uses the full task window.
- Docpending link tokens are sanitized via `is_valid_memory_name()` (core/stream.py): a truncated hook string (e.g. a literal `ref/ref_...`) names no real memory and is dropped before it can be demanded read/defer.
- Genuine new task (new_task intent from an active state, same-session re-entry after WF_DONE) → `append_task_boundary()` (core/stream.py) stamps the boundary after a SUCCESSFUL `transition_to('WF_CLASSIFY')`.
- Continuation / addition / unknown / possible_pivot prompts NEVER stamp — they stay in-state (no transition), so the in-flight task's docreads must keep counting for sweep verification. A boundary is stamped only when the model itself pivots via `/swe-goto WF_CLASSIFY`.
- Slash-command FAST TRACK: `create_wm_and_sentinel(..., stamp_session_start=False)` when the session already has a state file — a mid-task command invocation (e.g. `/swe-wm-update`) re-creates the WM WITHOUT advancing the boundary. ⛔ Re-stamping mid-task drops every prior docread and makes the sweep an unwinnable re-read loop.
- Tests: `tests/test_sweep_gate.py::TestTaskBoundaryStamping`.

## Canonical Sweep Rule

A docpending link surfaced by the PRIMARY feature is satisfied by read, planned (obligations cited as `(mem:<name>)` in the WM Compliance Checklist), or ruled out (with reason); bare deferral is rejected.
