# FEEDBACK_V4_FSM_REDESIGN — Workflow Engine v4 Architecture

**Why:** v3 had four structural defects that made the FSM advance without work, double-prompt the user, and block legitimate edits. v4 fixes them. Engine-dev sessions MUST follow these rules when touching the state machine.

**How to apply:** when editing hooks, states.json, or wf/ memories, preserve these invariants.

## The four fixes

1. **Reads never transition.** `swe_post_read_state.py` no longer calls `transition_to` on a WF_* read. Reading a workflow memory is a PURE read (logs "ON STEP" + continuation directive for the CURRENT state). Transitions happen ONLY via explicit `set_state` (the tool / prompt-intent hook). Root cause of the old bug: reading WF_* files to analyze them marched the FSM through states with zero work — a research session was driven CLASSIFY→…→WF_DONE just by reading.

2. **WF_START removed.** Init chain is `WF_INIT → CLAUDE_OBLIGATIONS → WF_CLASSIFY`. WF_CLASSIFY is the first post-init state. The WM file + init sentinel are now created in `swe_user_prompt_workflow.py` (`create_wm_and_sentinel`) on first entry to WF_CLASSIFY — relocated from the deleted WF_START read-transition block.

3. **WF_VERIFY edits in place.** `WF_VERIFY` is in `EDIT_ALLOWED` (`swe_pre_edit_validate.py`) and `allowEdit/allowWrite: true` in states.json. Verify fixes minor violations without bouncing to WF_EXECUTE. If a fix grows large (>5 files / new module / 3+ layers) it routes to WF_CLASSIFY for re-scoping (`WF_VERIFY → WF_CLASSIFY` matrix edge added).

4. **Single question + consent gate; complexity-gated arch review.**
   - All design/approach/blocker questions are asked ONCE at WF_ARCH_REVIEW in a single AskUserQuestion call, whose FINAL question is "validate the plan or continue through completion?" Answering = consent. Skipped when the initial prompt already consented ("get it done", "don't stop", "no questions"). WF_CLASSIFY no longer early-routes approach questions to WF_CLARIFY; WF_CLARIFY remains the reusable subroutine for non-design blockers.
   - WF_ARCH_REVIEW is NOT entered for every code change. WF_CLASSIFY Step 3b: minor patch to existing functionality + ≤5 files + no open questions → straight to WF_EXECUTE (`arch_review_skipped: true`). New feature / major module addition / >5 files / 3+ layers → WF_ARCH_REVIEW.

## Invariants to preserve

- Never reintroduce read→transition coupling in any post-read hook.
- `set_state` (+ prompt-intent hook) is the sole transition driver.
- states.json version is the source of truth for the matrix; `state_manager.load_transition_matrix` reads it. Keep node `transitions` and `transitionMatrix` in sync.
- WM/sentinel creation lives in the prompt hook, not the read hook.
- See canonical docs: `memories/dom/DOM_SWE_STATE_MACHINE.md`, `memories/dom/DOM_SWE_HOOKS.md` (shipped to consumers).
