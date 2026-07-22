---
name: v4 FSM Redesign
description: Four v4 workflow-engine invariants — preserve them when editing hooks, states.json, or wf/ memories.
metadata:
  type: feedback
---

# v4 FSM Redesign

**Why:** v3 had four structural defects: the FSM advanced without work, double-prompted the user, and blocked legitimate edits. v4 fixes them.

**How to apply:** When editing hooks, states.json, or wf/ memories, preserve every invariant below.

## The Four Fixes

1. **Reads NEVER transition.** `swe_post_read_state.py` does NOT call `transition_to` on a WF_* read. Reading a workflow memory is a PURE read (logs "ON STEP" + continuation for the CURRENT state). Transitions happen ONLY via explicit `set_state` (tool / prompt-intent hook). Root cause fixed: reading WF_* files to analyze them marched the FSM through states with zero work (drove a research session CLASSIFY→…→WF_DONE by reads alone).
2. **WF_START removed.** Init chain = `WF_INIT → CLAUDE_OBLIGATIONS → WF_CLASSIFY`. WF_CLASSIFY is the first post-init state. WM file + init sentinel are created in `swe_user_prompt_workflow.py` (`create_wm_and_sentinel`) on first entry to WF_CLASSIFY.
3. **WF_VERIFY edits in place.** WF_VERIFY is in `EDIT_ALLOWED` (`swe_pre_edit_validate.py`) and `allowEdit/allowWrite: true` in states.json. Verify fixes minor violations without bouncing to WF_EXECUTE. If a fix grows >5 files / new module / 3+ layers, route `WF_VERIFY → WF_CLASSIFY` for re-scoping.
4. **Single question + consent gate; complexity-gated arch review.** All design/approach/blocker questions asked ONCE at WF_ARCH_REVIEW in a single AskUserQuestion call whose FINAL question is "validate the plan or continue through completion?" Answering = consent. Skip when the initial prompt already consented ("get it done", "don't stop", "no questions"). WF_CLASSIFY no longer early-routes approach questions to WF_CLARIFY; WF_CLARIFY stays the subroutine for non-design blockers only. WF_ARCH_REVIEW is NOT entered for every code change — WF_CLASSIFY Step 3b: minor patch + ≤5 files + no open questions → WF_EXECUTE (`arch_review_skipped: true`); new feature / major module / >5 files / 3+ layers → WF_ARCH_REVIEW.

## Invariants to Preserve

- NEVER reintroduce read→transition coupling in any post-read hook.
- `set_state` (+ prompt-intent hook) is the SOLE transition driver.
- states.json version is the source of truth for the matrix; `state_manager.load_transition_matrix` reads it. Keep node `transitions` and `transitionMatrix` in sync.
- WM/sentinel creation lives in the prompt hook, NOT the read hook.
- Canonical docs: `mem:dom/DOM_SWE_STATE_MACHINE`, `mem:dom/DOM_SWE_HOOKS`.
