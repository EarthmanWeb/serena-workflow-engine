---
name: WF_EXECUTE
description: Workflow state — do the work. Tool routing, feature/WM verification, layered implementation, Serena edit-tool signatures, parallel execution, next-step routing.
metadata:
  type: workflow
---

# WF_EXECUTE — Do The Work

> **On step WF_EXECUTE**

## Tool Routing & Verify-Before-Assert

- Use the sanctioned MCP tool first when one covers the operation: `wp_cli` for WordPress/DB, `swe-wm` for Working Memory, Serena memory tools for `.serena` memories.
- NEVER hand-roll a Bash equivalent: no `docker exec ... wp`, no raw `mysql`, no `Write` into memory dirs. Known workaround patterns are hard-denied by the Bash policy gate.
- If the sanctioned tool errors, FIX its configuration (e.g. re-run `/swe-wp-cli-setup`). A broken sanctioned path is a blocker to repair, NEVER a license to work around it.
- Precede any factual claim about backend/environment state (DB, environments, containers, remote data) with a verification call (`wp_cli`, `terminus`, `docker`, `sps_log`/QM) in the SAME turn. Cannot verify → label "unverified" or ask. NEVER assert unverified state as fact.
- NEGATIVE findings need a POSITIVE CONTROL. Before "X is empty/missing/not registered/returns nothing", run one probe proving the method CAN detect X when present (known-good key, unescaped vs escaped match, published vs draft page). An unvalidated negative is "probe unverified", not "X is absent" — wrong option keys, ACF-escaped slashes, 404s on drafts have each produced false "missing" conclusions.

## Memories Are Hypotheses

- Memories are HYPOTHESES about the code, not ground truth. Verify every load-bearing claim (paths, URLs, class mappings, version numbers) against the code/environment before acting on it.
- Doc drift: on ANY doc↔code conflict, correct the memory in the same session — immediate edit, or add to a WM doc-drift list flushed at WF_VERIFY. A memory contradicting the code is a FINDING, never context to obey.

## Doc Claims Ledger

Track every actionable value taken from a memory in WM `## Doc Claims Used`: record ONE row on FIRST use as `pending`, update to `confirmed` on success or `corrected → <true value>` after fixing the memory. `WF_VERIFY`/`WF_DONE` BLOCKED while any row is `pending` (`corrected` with no true value also blocks). Row format + parser API: `mem:ref/REF_WF_EXECUTE_DOC_CLAIMS`.

## Compliance Checklist at Entry

SEEDED at WF_CLASSIFY: every Tier-0 digest given the PLANNED disposition (Step 4d) arrives here as an unchecked `- [ ] <obligation text> (mem:<name>)` item, body still unread. At the START of WF_EXECUTE — INCLUDING `arch_review_skipped` routes — FINALIZE the seeded `## Compliance Checklist` in WM: add items from loaded `DEV_*`/`DOM_*` rules scoped to the touched files (≤10 items total, seeded + added); drop/adjust seeded items the file scope makes irrelevant. If WF_ARCH_REVIEW already wrote one, finalize it in place.

Before implementing a still-digest-only item, read its citing memory body THEN — on-miss, before the dependent edit — verify against the body, not the digest. Re-check the whole checklist before declaring done: rules apply at edit time, not just at classify-time read.

## Feature Memory Verification

Check WM for `Feature Key(s)`; verify `FEATURE_[KEY]` is read for each. Not loaded → `read_memory("index/INDEX_FEATURES")` then `read_memory("feature/FEATURE_[KEY]")` per key. No Feature Key(s) in WM → go to `WF_CLASSIFY`. Proceed only after all are loaded.

## WM Check

- Verify WM exists and reflects the current task before starting work; if stale/missing, invoke `/swe-wm-update --from WF_EXECUTE`.
- Update WM (`swe_wm_update`) at state transitions and task completion ONLY. NO mid-state incremental updates — no per-subtask or per-edit WM writes.

## Before Starting Work

If multi-layer (touches >1 architectural layer), read `arch/ARCH_SWE`. For each layer, load context:

```
read_memory("sys/SYS_[SYSTEM]")               # System docs
read_memory("ref/REF_[PATTERN]")              # Coding patterns
read_memory("dom/DOM_[DOMAIN]")               # Domain behavior
read_memory("feature/FEATURE_DEV_STANDARDS")  # Dev standards index
read_memory("dev/DEV_PHP")                    # If touching PHP
read_memory("dev/DEV_JAVASCRIPT")             # If touching JS
```

Do NOT write code until relevant memories are loaded.

- `[doc-gate]` enforces DEV_* reads per file type before an Edit/Write/Bash-write is allowed: every `feature/*`/`dev/*` memory whose `paths:` glob matches the target, else an extension-based fallback (`dev/DEV_<LANG>` + `feature/FEATURE_DEV_STANDARDS`). Reads are session-scoped. Read the governing memories up front — do not wait for a denial.

## Multi-Layer Implementation

1. Read architecture docs (`arch/ARCH_SWE`, `dom/DOM_*`); understand data flow from `arch/ARCH_SWE`.
2. Implement each layer per `SYS_*`/`REF_*` patterns.
3. Read the project's test-standards memory (e.g. `dev/DEV_TESTS`/`feature/FEATURE_TESTS`, if present), implement tests, run and verify.

## Single-Layer Implementation

Use Serena tools directly: `find_symbol` (locate code) → `get_symbols_overview` (file structure) → `Edit` / `replace_symbol_body` (make changes).

## Serena Edit Tool Signatures

**⚠️ MANDATORY — fetch the live schema before your FIRST Serena write/edit call this session**, for EVERY `mcp__plugin_swe_serena__*` param-taking tool (`replace_content`, `replace_symbol_body`, `insert_*`, `edit_memory`, `write_memory`): schemas are deferred, not loaded until fetched. Guessing params fails validation and wastes a turn.

```
ToolSearch("select:mcp__plugin_swe_serena__replace_content")   # or edit_memory, write_memory, …
```

Param cheat-sheet: `mem:ref/REF_WF_EXECUTE_SERENA_EDIT_TOOLS`.

## Parallel Execution — Orchestrator Mode

Parallel subagents launch here. Orchestrator mode is MANDATORY per `mem:feature/FEATURE_SUBAGENTS` when ANY hold: ≥2 independent subtasks exist, `parallel_agents: true` noted in WM, 6+ files affected, or 3+ layers touched. Read that memory for the full stage loop, model-tier routing, prompt contract, anti-patterns BEFORE launching. Do NOT do the file-edit/test-run work yourself when its conditions apply.

Hard-block thresholds (enforced by `swe_post_orchestrator_drift.py` / `swe_pre_edit_validate.py`, full rules `mem:feature/FEATURE_SUBAGENTS`): 6 consecutive main-agent task-work calls = advisory nudge; 12 = HARD edit-gate block until a delegation or a recorded `single-agent: <reason>` resets it.

```javascript
Agent({ description: "Task A", run_in_background: true, model: "<tier>",  // haiku=routine, sonnet=implementation, opus=design/hard debug/security/concurrency — see FEATURE_SUBAGENTS
  isolation: "worktree",
  prompt: "You are a subagent. BYPASS WF_INIT. [task]... You own <files>; do NOT edit <other agent's files>. Commit your own checkpoint; retry on index.lock; never push. Report: files changed, findings, blockers." })
```

- Launch ALL agents in ONE message; `isolation: "worktree"` when agents edit overlapping files.
- Collect results from background task notifications, then chain the next stage's agents immediately — do not do the next stage's work yourself.
- `swe_pre_agent_model_gate.py` enforces explicit `model` + bypass line; an orchestrator-drift nudge here flags self-performed file/test work that should have been delegated.
- Any waiting/polling work (test runs, builds, CI, deploys, remote queues) launched here MUST go to ONE background subagent that runs the work AND polls it itself, reporting on completion — NEVER `Bash run_in_background` + a blocking poll loop in the orchestrator. See `mem:feature/FEATURE_SUBAGENTS`.

## Rules

- Make ONLY approved changes. Do NOT expand scope without asking.
- Tests required for functional code; integration tests required for components interacting with external systems.

### New File Creation

1. Check naming conventions + required boilerplate (headers, guards, defaults) from the relevant `DEV_*` memory.
2. Register/wire the new file per `FEATURE_[KEY]` or `DOM_*` patterns.
3. Verify any compliance checklist items in WM.

Missing registration is the most common cause of "code is correct but doesn't work" failures.

## Next Step

Created/modified file, or completed a phase → `WF_CHECKPOINT`. All work done (including tests) → `WF_VERIFY`. Update WM with progress via `/swe-wm-update`, read that WF_* memory, report the new step to user.
