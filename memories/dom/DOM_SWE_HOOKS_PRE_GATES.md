---
name: DOM_SWE_HOOKS_PRE_GATES
description: PreToolUse gatekeeper hooks — init gate (incl. two-tier circuit breaker + recovery), edit validation, memory index gate, bash test gate, docs-first search gate, question consent gate, agent model gate.
obligations:
  - Init gate blocks ALL tools until the WF_INIT chain completes; Tier-1/Tier-2 degraded modes never unlock Edit/Write/NotebookEdit/mutating Bash.
  - Docs-first search gate DENIES gated calls once the `GATED_CALL_BUDGET` (15) is spent with no fresh `docread`; spawned agents are always exempt.
metadata:
  type: domain
---

# DOM_SWE_HOOKS_PRE_GATES — Pre-Tool Gatekeepers

Hub: `mem:dom/DOM_SWE_HOOKS`.

## `swe_pre_tool_init_gate.py` — PreToolUse (all tools)

Block ALL tools until WF_INIT chain complete. TWO-TIER circuit breaker, both clearing on the next docread.

- **Tier 1 "recovery"** (3+ consecutive init denies with no docread, no `mcp_unavailable`): Serena may still be reachable — unlocks ONLY recovery/diagnostic Bash: `claude mcp list`/`get`, `ps`/`pgrep`, restricted log reads under `~/Library/Caches/claude-cli-nodejs/`, `~/.cache/claude-cli-nodejs/`, `~/.serena/logs/`, project `.serena/`, plus `--reset-sentinel`. NEVER Read/Grep/Glob the codebase.
- **Tier 2 "degraded"** (an `mcp_unavailable` event from `PostToolUseFailure` on a genuine Serena connection failure): unlocks Read/Grep/Glob/LS/ToolSearch + hardened read-only Bash.
- Edits/Write/NotebookEdit/mutating Bash stay denied in BOTH tiers.
- Hardened Bash classifier rejects: backtick/`$()`/`<()`/`>()`/redirection (except `2>/dev/null`, `2>&1`)/`tee`/`xargs`/`-exec`/`-execdir`/`-delete`/`sed -i`/`perl -i`. Every `;`/`&&`/`||`/`&`/pipe-stage's primary command must be in the allowlist. Excludes `python3 -m unittest`/`pytest` (execute code). git limited to `status`/`log`/`diff`/`show`/`branch`/`rev-parse` without `-c`/`--output`/`-o`.
- Events emitted: `init_deny`, `degraded`, `mcp_unavailable`.
- Allowed pre-init: `read_memory` (wf/* and init-chain), `write_memory`, `edit_memory`, `list_memories`, swe_wm tools, `ToolSearch`, Serena project-setup tools.
- Blocked pre-init: `Bash`, `Grep`, `Glob`, `Edit`, `Write` (non-WM), `find_symbol`, `get_symbols_overview`, all other tools.
- Sentinel on entry to WF_CLASSIFY unlocks all tools for the session.

### Sentinel Recovery (self-healing)

Recreate a missing sentinel automatically when a valid WM exists for the session — prevents deadlock on mid-session pivots where the daemon blocks re-running the init chain but the gate demands it.

Recovery points, checked in order:

1. `swe_user_prompt_workflow.py` — create sentinel when WM valid but sentinel missing, before any tool call.
2. `swe_pre_tool_init_gate.py` — WM-based fallback when the prompt hook did not fire or failed.

### Manual Reset

- One session: `python3 hooks/pre/swe_pre_tool_init_gate.py --reset-sentinel <session_id>`.
- ALL sentinels (next init chain recreates them): `python3 hooks/pre/swe_pre_tool_init_gate.py --reset-sentinel`.

## `swe_pre_edit_validate.py` — PreToolUse (Edit/Write/Serena)

- Block edits in planning states (WF_VERIFY is edit-allowed); in execution states DENY until the per-task sweep sentinel exists (WF_CLASSIFY 4d/4e verified).
- Test-artifact edits additionally require `dev/DEV_TESTS` + `feature/FEATURE_TESTS` docreads when those memories exist.
- **HARD BLOCK** (delegation economics): denies further main-agent edits at ≥12 consecutive undelegated task-work calls (`DRIFT_HARD_THRESHOLD`, tracked by `swe_post_orchestrator_drift.py`, see `mem:dom/DOM_SWE_HOOKS_POST`). Cleared by any Agent/Task delegation (resets the counter) or by recording `single-agent: <reason>` in WM `## Workflow Context` (tight single-file coupled-fix exception only, per `mem:feature/FEATURE_SUBAGENTS`).
- Exempt for spawned-agent tool calls — the block applies to the main orchestrator agent only, never to a subagent already doing delegated work.

## `swe_pre_memory_index_gate.py` — PreToolUse (Edit/Write/write_memory/edit_memory)

- HARD-DENY spec/report/research/project links entering MEMORY.md (state-independent; the post-hook only advises).
- ALSO DENIES a `write_memory`/direct-`Write` that creates or overwrites a dom/ref/dev/feature memory with no `obligations:` field (`obligations: []` passes; `edit_memory` partial edits exempt) — Change Set H, see `mem:ref/REF_MEMORY_STYLE`.

## `swe_pre_bash_test_gate.py` — PreToolUse (Bash)

Validate test commands against WF_DEBUG_TDD.

## `swe_pre_search_docs_gate.py` — PreToolUse (Grep/Glob/search_for_pattern/Bash-inspection)

`Read` is NOT matched in hooks.json — `is_gated_call` never gates it, so excluding it from the matcher saves a hook subprocess per Read call.

- DOCS-FIRST blocking gate.
- Bash classification is by the PRIMARY (first pipe stage) command of each `;`/`&&`/newline group: work commands (test runners, builds, formatters, git commit) are NOT gated even when piped through head/tail/grep output filters; a sequenced `cat`/`grep` after a build IS gated (standalone recon).
- BUDGET model: one docs consult (`docread`) clears the next `GATED_CALL_BUDGET` (currently 15) gated calls; each allowed call appends a `gated` event; deny when the budget is spent or no `docread` exists. Clearance survives turn boundaries. Budget refill requires a FRESH docread (re-reads don't refill; credited memory searches always do).
- Deny message: budget refill ≠ completed research; lists pending related docs (docpending) as designated next reads; instructs write_memory backfill when discovery was required.
- Spawned agents are NEVER gated: the gate exempts them BEFORE any sentinel/budget check.
  - PRIMARY signal: `core.session.is_spawned_agent(input)` — a non-empty `agent_id`/`agent_type` in the hook payload (Claude Code stamps these ONLY on subagent tool calls; `session_id` is the SAME parent id for main + subagent, so it cannot discriminate).
  - FALLBACK: `core.session.is_subagent_transcript(transcript_path)` — the `<session>/subagents/agent-*.jsonl` shape, used when the payload carries the subagent's own path. Insufficient alone: the hook usually receives the PARENT transcript path for a subagent call, so `is_subagent_transcript` missed it and the subagent got gated on the parent's spent budget — hence the agent_id-first check.
- Undocumented area (no reasonable feature memories from both searches): deny message routes to a FOREGROUND Agent running `/swe-feature-onboard` (new area) or `/swe-feature-update` (stale docs) — no `run_in_background`, WAIT for completion, then read the memories it wrote to clear the gate. Manual grepping is NOT the remedy.

## `swe_pre_question_consent_gate.py` — PreToolUse (AskUserQuestion)

Deny questions while `auto_approve`/`blanket_consent` is set in WM (override tag for destructive/scope changes).

## `swe_pre_agent_model_gate.py` — PreToolUse (Agent/Task)

Enforces orchestrator + swarm delegation with complexity-based model tiers. FOUR independent DENY checks:

1. Missing `model` param — required for every subagent_type except fixed-model built-ins (`claude-code-guide`, `statusline-setup`).
2. Prompt lacks the subagent bypass marker ("BYPASS WF_INIT" / "you are a subagent" / "swarm agent") — without it the spawned agent re-runs the init chain.
3. `model: "opus"` on a routine-keyword prompt (tests/lint/grep/inventory/read-only audit) with no design/architecture keyword — override via literal `[opus-justified: <reason>]` tag in the prompt (`[premium-justified: <reason>]` accepted as an alias, same requirement).
4. `model: "fable"` on ANY subagent call — fable is NEVER delegated by default, regardless of task shape — override via literal `[fable-justified: <reason>]` tag (`[premium-justified: <reason>]` alias also accepted).

Rationale: the orchestrator already runs the premium model; delegation moves work OFF it.

Pure functions `missing_model_reason`/`missing_bypass_marker_reason`/`opus_on_routine_reason`/`fable_without_justification_reason` are unit-tested.
