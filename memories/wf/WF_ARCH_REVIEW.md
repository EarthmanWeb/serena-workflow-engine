---
name: WF_ARCH_REVIEW
description: Single planning gate for major code changes — design, architecture compliance, parallel-execution assessment, single-question consent gate.
metadata:
  type: workflow
---

# WF_ARCH_REVIEW — Design, Compliance Review & Approval

> **On step WF_ARCH_REVIEW**

Single planning gate for **major** code changes: design, architecture compliance, parallel-execution assessment, single question + consent gate.

## Entry Conditions

- Enter ONLY when WF_CLASSIFY Step 3b routed here: task is a **new feature**, a **major module addition**, touches **>5 files**, or crosses **3+ layers**.
- Minor patches (≤5 files, no open design questions) NEVER enter here — they go straight to `WF_EXECUTE` with `arch_review_skipped: true`.
- If you arrived here for a trivial one-file patch, this is a mis-route: note it and proceed. Do NOT pad a small change with ceremony.

## SPEC Fast-Path

- If a `SPEC_*` memory is loaded (check WM), SKIP steps 1-4 and reference the SPEC by name. Go to step 5 (Parallel Execution Assessment), then the Single Question + Consent Gate.
- If no SPEC loaded, follow steps 1-4.
- Feature knowledge (`FEATURE_*`/`REF_*`/`DOM_*`/`SYS_*`/`ARCH_*`) is already loaded by the WF_CLASSIFY Step 4d sweep — check WM `Memories loaded`, do NOT re-read it. What remains: `DEV_*` standards + compliance-checklist derivation (steps 2b, 2c), run AFTER questions are answered (see "Heavy Memory Load").

When WM `gherkin_spec_needed: true`, read `mem:ref/REF_WF_ARCH_REVIEW_GHERKIN_GATE` before Step 1.

## Steps

### 1-2c. Feature/Layer/Standards Memory Load & Compliance Checklist

Skipped entirely by the SPEC Fast-Path. Full procedure: `mem:ref/REF_WF_ARCH_REVIEW_MEMORY_LOAD`.

### 3. Design With Explicit File Paths

- Files to modify (with what changes).
- Files to create (with justification and naming-convention source from `DEV_*`).
- Data flow between components.
- Integration points (registration/wiring for new components).
- Test coverage plan.

### 4. Architecture Compliance Check

- Which layer OWNS this logic?
- Is logic placed in the correct layer?
- Does it follow the project's documented data-flow pattern?
- Compliance checklist (Step 2c) is consistent with the design?

STOP-condition catalogue (layer violations, presentation-layer rules, project-specific checks): `mem:ref/REF_WF_ARCH_REVIEW_LAYER_VIOLATIONS`.

### 5. Parallel Execution Assessment

Fan-out is the DEFAULT plan whenever the task has **2+ independent tracks** — not just at 6+ files / 3+ layers. Per `mem:feature/FEATURE_SUBAGENTS`, orchestrator mode also applies at 6+ files, 3+ layers, or an explicit operator fan-out request.

When ANY threshold is met, list tracks explicitly:

| Track | Owner files | Independent? | Model tier                   |
| ----- | ----------- | ------------ | ---------------------------- |
| A     | `path/a/**` | yes          | sonnet (implementation)      |
| B     | `path/b/**` | yes          | haiku (mechanical/routine)   |
| C     | `path/c/**` | yes          | opus (concurrency/FSM logic) |

- Use Claude Code `Agent` tool with `run_in_background: true`.
- Use `isolation: "worktree"` when tracks may edit overlapping files.
- Model tier follows the FEATURE_SUBAGENTS routing table (haiku=routine, sonnet=implementation, opus=novel design/hard cross-file debugging/security-sensitive changes/concurrency-FSM logic/broad refactors/explicit operator request) — `model` is passed explicitly on every Agent call, never omitted.
- Note `parallel_agents: true` in WM along with the tracks table.

Parallel subagents launch during `WF_EXECUTE` — no separate orchestration state. If no independent tracks exist, proceed as single-agent implementation and state why fan-out does not apply.

## Single Question + Consent Gate

This is the ONE question gate in the workflow. There is NO separate "May I proceed?" approval step — answering the questions IS consent.

### Template Check (New Files)

Before proposing new files: check existing patterns in similar files, read relevant `SYS_*`/`REF_*` memory for the file type, follow established feature conventions from `FEATURE_[KEY]`.

### Consent-Skip Check (Initial-Prompt Blanket Consent)

Set `blanket_consent: true` ONLY on an EXPLICIT no-question phrase in the INITIAL user prompt: "no questions", "don't ask me questions" / "don't ask me any questions", "don't ask me anything", "skip all questions".

- "get it done", "continue to completion", "don't stop till finished", "run to completion" NEVER set `blanket_consent` — they skip ONLY the final validate-or-continue plan question. Ask every design/approach question normally.
- Selecting "Continue through to completion" in the consent-gate question NEVER sets `blanket_consent` — it skips ONLY the separate plan review.
- Blanket consent given: SKIP the whole question call. For each design/approach question pick the most logical option, act on it, and RECORD it in WM `## Open Decisions` as `- [ ] <decision> — options: A | B — deferred: chose <A>`. Go directly to `WF_EXECUTE` (parallel subagents, if planned, launch there).
- PERSIST the grant: note `blanket_consent: true` in WM `Context` (via `swe_wm_update_section`). While set, a PreToolUse gate DENIES `AskUserQuestion` until WF_DONE — record each new decision as a deferred entry and keep working. WF_DONE asks every deferred entry via AskUserQuestion. Only a destructive action or genuine scope change may ask earlier, using the literal tag `[consent-override]` + reason in the question text (the tag asserts the condition holds; it is not a bypass).
- Scope: the flag covers ONE task. Re-entry into `WF_CLASSIFY` from any later state (pivot, new task after WF_DONE) clears it automatically.
- Otherwise: assemble and ask the single question call — exact template + validate-or-continue question text/options: `mem:ref/REF_WF_ARCH_REVIEW_CONSENT_TEMPLATE`.

### Non-Interactive Session Check

Applies ONLY when `AskUserQuestion` is unavailable: a spawned subagent, or a headless `-p` / SDK print run. There: pick the most reasonable answer for every design question, record each as a deferred `## Open Decisions` entry, proceed to `WF_EXECUTE`.

- An interactive or Remote Control session is ALWAYS interactive — the user is reachable via push. NEVER treat it as non-interactive and NEVER treat it as consent.

### Heavy Memory Load (After Questions Answered)

Feature knowledge is already in context from the WF_CLASSIFY Step 4d sweep. Load ONLY the edit-time standards, scoped to the chosen approach's files:

1. `read_memory("feature/FEATURE_DEV_STANDARDS")` and the relevant `DEV_*`/`DOM_*`/`SYS_*` memories for the languages/layers the chosen approach touches (steps 2/2b).
2. Derive `## Compliance Checklist` in WM (step 2c) from those memories.

Scope this load to the chosen approach. Do NOT sweep memories for approaches not selected.

### Handle Final-Question Response

| Selection                         | Action                                                                                                                               |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| "Validate the plan with me first" | Present the assembled plan (files table, constraints, data flow, test plan, parallel rec). Get explicit go-ahead, then `WF_EXECUTE`. |
| "Continue through to completion"  | Read `WF_EXECUTE` directly (parallel subagents launch there).                                                                        |
| Consent-skip (blanket consent)    | Read `WF_EXECUTE` directly (parallel subagents launch there).                                                                        |

A non-design blocker surfacing here may use `WF_CLARIFY` (reusable ask-user subroutine for non-design blockers only). Design/approach questions are NEVER routed there — they belong in the single question call above.

## Routing

| Condition                        | Next Step    |
| -------------------------------- | ------------ |
| Consent-skip (blanket consent)   | `WF_EXECUTE` |
| "Continue through to completion" | `WF_EXECUTE` |
| "Validate the plan" → go-ahead   | `WF_EXECUTE` |
| Non-design blocker               | `WF_CLARIFY` |

Parallel subagent work runs inside `WF_EXECUTE` (note `parallel_agents: true` in WM); no separate orchestration state.

Update WM via `/swe-wm-update --from WF_ARCH_REVIEW` before transitioning.
