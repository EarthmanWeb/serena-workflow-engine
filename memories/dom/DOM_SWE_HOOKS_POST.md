---
name: DOM_SWE_HOOKS_POST
description: PostToolUse observer/learner hooks (read-state, edit checkpoint, search hints, memory index/style, tool failure, doc-claims, orchestrator drift) and the sentinel nudge pattern they share.
obligations:
  - Sentinels NEVER block (PostToolUse cannot deny) and always exit 0 — nudges only.
  - Orchestrator-drift count feeds the pre-edit gate's HARD BLOCK at 12 (`mem:dom/DOM_SWE_HOOKS_PRE_GATES`) — this hook itself never blocks.
  - Only a BACKGROUND Agent/Task call (`run_in_background: true`) or a Workflow call resets the drift counter; a foreground Agent/Task call counts as `task_work`.
  - `read_state`/`edit_checkpoint`/`write_continue`/`todo_wm_sync`/`search_docs_hint`/`doc_claims` are exempt for spawned agents — no workflow directives (ON STEP/CONTINUE/checkpoint nudges) are injected into a subagent's tool stream; `read_state` still logs `docread` for a subagent but NEVER readAdvances the FSM on its behalf.
metadata:
  type: domain
---

# DOM_SWE_HOOKS_POST — Post-Tool Observers & Sentinels

Hub: `mem:dom/DOM_SWE_HOOKS`.

## Post-Tool Hooks (`post/`)

Spawned-agent exemption: `read_state`, `edit_checkpoint`, `write_continue`, `todo_wm_sync`, `search_docs_hint`, and `doc_claims` are ALL exempt for spawned-agent tool calls — NEVER inject workflow directives (ON STEP/CONTINUE, init denial, checkpoint nudges) into a subagent's stream. A spawned agent's `read_memory`/`list_memories` calls still append a `docread` event (bookkeeping for the parent session's metrics) but NEVER trigger readAdvance for that agent — the FSM transition is orchestrator-only.

- `swe_post_read_state.py` (PostToolUse: read_memory/list_memories/search_memories_by_name/search_memories_by_front_matter): logs "ON STEP" for the resulting state — see readAdvance below. Appends a `docread` event WITH the memory name (resets the wide-search streak, refills the docs-first gate budget, feeds sweep verification). Memory searches get credit ONLY when they surface no unread names; new names → `docsearch` event + instruction to read them first. Reads surface their own `mem:`/`[[…]]` links: unread linked docs → `docpending` event + read-these instruction (wf/claude/spec/report/research/project/templates excluded). Exempt for spawned agents: logs `docread` only, NEVER emits "ON STEP"/"CONTINUE" and NEVER readAdvances.
- `swe_post_edit_checkpoint.py` (PostToolUse: Edit/Write/Serena): edit counting, checkpoint at 10 edits (`CHECKPOINT_THRESHOLD`). Exempt for spawned agents — no checkpoint nudge injected.
- `swe_post_search_docs_hint.py` (PostToolUse: Grep/Glob/search_for_pattern): counts CONSECUTIVE wide searches; at 3 in a row (`SEARCH_HINT_THRESHOLD`) reminds to check memories/docs first. `docread`/`state`/`checkpoint` events reset the streak. Exempt for spawned agents.
- `swe_post_write_continue.py` (PostToolUse: write_memory): post-write continuation. Exempt for spawned agents.
- `swe_post_todo_wm_sync.py` (PostToolUse: TodoWrite): WM sync reminder on todo changes. Exempt for spawned agents.
- `swe_post_memory_index.py` (PostToolUse: write_memory): enforce MEMORY.md index update.
- `swe_post_memory_style.py` (PostToolUse: write_memory/edit_memory): enforce terse-imperative memory style (`mem:ref/REF_MEMORY_STYLE`). Nudges toward adding `obligations:` front-matter on a write/edit of a dom/ref/dev/feature memory missing it — advisory only, covers edits and existing memories the pre-gate's create/overwrite deny does not reach.
- `swe_post_tool_failure.py` (PostToolUseFailure): flailing detection, failure logging. For a spawned agent, logs `agent_fail{kind}` (kind: test/edit/bash) — feeds `[scope-gate]`'s per-kind consecutive-failure streak (`mem:dom/DOM_SWE_HOOKS_PRE_GATES_AGENT`).
- `swe_post_doc_claims.py` (PostToolUse: Bash): C6 substitution detector — on a SUCCESSFUL Bash call whose command near-matches a `## Doc Claims Used` ledger claim (shared ≥4-char token stem, different value), emits "you substituted `<used>` for documented `<claim>` — correct the memory or record why the doc is right"; one emission per (claim,used) pair per session; stat()-cheap no-ledger fast path (`core/doc_claims.py`). Exempt for spawned agents.
- `swe_post_orchestrator_drift.py` (PostToolUse: Edit/Write/NotebookEdit/Bash/Serena edit tools/Agent/Task/Workflow): orchestrator-drift enforcement — see below.

### `swe_post_orchestrator_drift.py` detail

- Counts consecutive main-agent task-work calls since the last BACKGROUND delegation (`task_work` events, reset ONLY by a `delegation` event this same hook appends on Agent/Task calls with `run_in_background: true`, or on any Workflow call).
- A FOREGROUND Agent/Task call (`run_in_background: false` or omitted, even with a valid `[foreground-justified: <reason>]` tag) does NOT append a `delegation` event — it counts as `task_work`, same as an Edit/Write/Bash call.
- At `DRIFT_THRESHOLD` (6): advisory "split remaining work into parallel background subagents" (see `mem:feature/FEATURE_SUBAGENTS`) — SUPPRESSED when a `direct_instruction` event exists since the last `prompt` event (see `mem:dom/DOM_SWE_HOOKS_PROMPT_ROUTING`). `DRIFT_HARD_THRESHOLD` (12) behavior is unchanged by this suppression.
- At `DRIFT_HARD_THRESHOLD` (12): MANDATE, not a suggestion — the count feeds `swe_pre_edit_validate.py`, which DENIES further main-agent edits until a BACKGROUND delegation (or Workflow call) resets the counter or `single-agent: <reason>` is recorded in WM `## Workflow Context` (tight single-file coupled-fix exception only).
- This hook itself never blocks (PostToolUse); enforcement happens on the NEXT edit attempt via the pre-edit gate.
- Exempt for spawned-agent tool calls (subagents are expected to do direct work, not delegate further).
- Exempt for verification Bash (`git diff`/`status`/`log`/`show`/`add`/`commit`, test runners, `py_compile`, `jq`, validate scripts) and `Read` — checking work, not doing it, does not count toward drift. `bash_is_verification(command)` (the exemption's classifier) treats EVERY command group (split on `;`/`&&`/`||`/newline/bare job-control `&`, excluding `2>&1`) as verification when its primary stage matches the build/test regex, OR `scope_guard.is_test_command` (playwright/jest/vitest/phpunit/go test/cargo test), OR a read-only inspection command (`grep`/`rg`/`cat`/`head`/`tail`/`ls`/`wc`/`find`/`sed -n`/`awk`/`git grep`/`file`/`stat`/`diff`) — a single non-matching group disqualifies the WHOLE call. The call is ALSO disqualified outright, regardless of primary-stage match, when it contains output redirection (other than `2>/dev/null`/`2>&1`), `sed -i`, `find -exec`/`-execdir`/`-delete`, `tee`, or `xargs` anywhere — these mutate state even inside a filter pipeline (e.g. `grep -l TODO *.py | xargs sed -i ...`).
- Also logs, for `[scope-gate]` bookkeeping: `agent_spawn{agent,model,budget,expect_red?}` from the orchestrator's own Agent-call result (background delegation) — `expect_red: true` is added when `scope_guard.expects_red_runs(prompt)` finds a literal `[swe-expect-red]` tag or fail-proofing/red-green phrasing in the spawning prompt, which widens the spawned agent's `test` failure-streak limit only (`mem:dom/DOM_SWE_HOOKS_PRE_GATES_AGENT`) — `agent_ok` on a spawned agent's successful Bash/edit call (resets that kind's failure streak), and `scope_extend{agent,budget_add}` when a SendMessage to a spawned agent carries `[scope-extend]`/`[scope-extend: N]`. See `mem:dom/DOM_SUBAGENTS_PROMPT_CONTRACT` for scope limits on failure.

## Read-advance and read-backward, not read-and-stay

`readAdvance` is enabled in `state-machine/states.json`: reading a `WF_*` memory ranked higher than the current state advances the FSM along a valid edge — `swe_post_read_state.py` performs this transition and then logs "ON STEP" for the new state. A LOWER-rank read also transitions when the target is listed in that state's `readBackward` allowlist (`WF_RESEARCH→[WF_CLASSIFY]`, `WF_ARCH_REVIEW→[WF_CLASSIFY]`, `WF_EXECUTE→[WF_CLASSIFY]`, `WF_CHECKPOINT→[WF_CLASSIFY]`, `WF_DEBUG_TDD→[WF_CLASSIFY]`, `WF_VERIFY→[WF_EXECUTE, WF_CLASSIFY]`, `WF_CONTINUE→[WF_CLASSIFY]`; `WF_DONE` has none). Any other backward/same-rank read, reads into `WF_CLARIFY`, reads of a `subflow` (`WF_INIT`, `WF_CLEANUP`, `WF_RESEARCH_LITE`, `WF_UPDATE_MEMORY`), and ANY read by a spawned agent never transition. Explicit `set_state`/`swe_wm_transition` (the dedicated tool or the prompt-intent hook, `swe_user_prompt_workflow.py`) remains the only way to make an undeclared pivot, backward, or subflow move. See `mem:dom/DOM_SWE_STATE_MACHINE` "Transition Model (readAdvance + readBackward)".

### Inspect loop guard

`swe_post_read_state.py` logs "inspecting — no transition" when a `WF_*` read has neither a `readAdvance` nor a `readBackward` edge from the current state (read-only inspection). On the 2nd-or-later such "inspecting — no transition" read of the SAME memory in a session, it escalates to a LOOP GUARD message naming the exact fallback call: `mcp__plugin_swe_swe-wm__swe_wm_transition(session_id, target_state, reason)` (MCP), or the CLI `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/swe_hooks/tools/set_state.py" <session_id> <STATE>`. Prevents a repeated inert read from stalling the FSM silently, e.g. `WF_RESEARCH` unable to reach `WF_CLASSIFY`.

## Sentinel Pattern (stream-counted nudges)

Full detail (mechanism, per-sentinel thresholds, adding a new sentinel): `mem:dom/DOM_SWE_HOOKS_SENTINELS`.
