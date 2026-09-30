---
name: CLAUDE_OBLIGATIONS
description: Behavioral constraints Claude MUST obey for every task — response style, coding principles, prohibitions, mandatory actions, failure thresholds, conflict handling.
metadata:
  type: reference
---

# CLAUDE_OBLIGATIONS — Behavioral Constraints

Read COMPLETELY. Obey every rule below on every task.

## Response Style

- Non-conversational, functional language ONLY. Lead with the command.
- "Updating:" NOT "Let me update". "Found code:" NOT "I found this code". "Issue Found:" NOT "I think the issue is". "Next:" NOT "Now I need to". "Adding:" NOT "I need to add". "Summary of changes:" NOT "Here's a summary of the changes".
- Use bullets, numbered lists, tables.
- Remote environment: request operator output only when debugging AND it cannot be obtained via MCP tools.

## Core Coding Principles

Priority order: KISS → DRY → YAGNI.

- Write simple, readable code.
- Search for existing features before creating new ones.
- Extract at 2+ occurrences.
- Do not over-engineer. Stick to specs. Build only when needed.

## Do Not

- NEVER skip or rationalize around workflow steps — this corrupts the FSM state and is easy to talk yourself into ("just this once", "it's simple"). See `wf/WF_INIT` anti-rationalization block.
- NEVER use fallbacks or defensive programming. Fail fast; no fallback masking.
- Do not synthesize or fake data unless explicitly asked.
- Do not attribute problems to caching unless caching exists in the code.
- Do not use `as any` type assertions (TypeScript).
- Do not guess file paths — use Serena tools.
- Do not run dev servers; the user manages these.
- Do not implement workarounds without asking.
- NEVER proceed when memories conflict with user instructions — silently picking one loses the other's requirement. STOP and ask.

## Always Do

- Follow `wf/WF_INIT` → `claude/CLAUDE_OBLIGATIONS` → `wf/WF_CLASSIFY` sequence. No shortcuts. See `wf/WF_INIT`.
- "Let It Fail": remove defensive code, add none, allow clear failures.
- Check `MEMORY.md` or `index/INDEX_FEATURES` when navigating features.
- Use Serena symbolic tools for code edits: `replace_symbol_body`, `insert_before_symbol`, `insert_after_symbol` to modify; `find_symbol`, `get_symbols_overview`, `search_for_pattern` to discover. Fall back to `Read`/`Edit` only for non-code files or when symbols cannot be resolved.
- Update WM using `swe-wm` MCP tools: `swe_wm_update_section` for section updates, `swe_wm_update_status` for status, `swe_wm_read` to read. NEVER use `write_memory`/`edit_memory` on WM files — these bypass the daemon and can clobber the `Workflow Context`/`Transitions` fields the state machine depends on.
- Ask for clarification when uncertain.
- Follow existing patterns. Check docs and existing code first.
- Document new patterns or deviations in Serena memories.
- Clean up after tasks: remove temp files, branches, agents.
- Communicate blockers or uncertainties immediately.

## Skill Execution Is VERBATIM

- A skill's literal commands ARE the implementation. Run them EXACTLY as written — NEVER substitute improvised shell pipelines, loops, scratch files (/tmp or elsewhere), or awk/sed variants for a step that has a documented command.
- A skill step with NO literal command and no named tool is a SKILL GAP: STOP and report the gap. Do NOT invent a command to fill it.
- Prefer the named MCP/Serena tool a skill cites over any shell equivalent. Shell fallbacks are used ONLY where the skill documents them.

## Skill Failure Threshold

After 2 consecutive command failures of the same type:

1. STOP immediately.
2. Re-read the relevant skill/memory.
3. Retry ONCE with the skill's own documented alternative (never an invented variant).
4. Ask the user if still failing.

Do not flail with variations of the same broken approach.

## Debugging

1. Follow project-specific debugging patterns. Check `REF_*` memories.
2. Log all findings in WM.
3. Summarize issues and proposed fixes for user review.

## User Interaction

- When the user is frustrated: verify their instructions were followed exactly; offer to update docs if a conflict exists.

## On Conflicts

When a user instruction contradicts a memory:

1. STOP.
2. ASK for clarification.
3. UPDATE the memory after confirmation.

## Working Style

- No time constraints on any task. Prioritize thoroughness and accuracy over speed; do not rush or skip steps to save time.
- MAKE NO ASSUMPTIONS. Research any assumption in the codebase or on the Web before asserting a direction.

## Parallel Processing

- Orchestrator mode is the DEFAULT for 2+ independent subtasks: classify, split into disjoint-file tracks, launch ALL as parallel background subagents in ONE message, collect, verify, chain the next stage — do NOT do the task work yourself. Every `Agent` call sets `model` explicitly: `haiku`=routine, `sonnet`=implementation, `opus`=novel design, hard/cross-system debugging, security, concurrency/FSM logic, or operator request (tag `[opus-justified: <reason>]`) — NEVER downgrade hard work to clear the gate, `fable`=NEVER for subagents without `[fable-justified: <reason>]`. See `feature/FEATURE_SUBAGENTS` for the full stage loop, model-tier table, and prompt contract.
- Parallel + cheaper agents are the PRIMARY token-reduction lever, not a nicety — solo main-agent grinding past 12 undelegated task-work calls is edit-gate BLOCKED (`swe_pre_edit_validate.py`) until a delegation happens or `single-agent: <reason>` is recorded in WM Context.
- Any waiting/polling work (test runs, builds, CI, deploys, remote queues) MUST run inside ONE background subagent that both does the work and polls it, then reports on completion — NEVER start it with `Bash run_in_background` and poll it yourself with a blocking loop.
- A subagent failure report goes to a NEW, explicitly scoped debug agent — NEVER let a delegated agent free-debug past its task; see `feature/FEATURE_SUBAGENTS` "Scope Limits on Failure".

## Quality Standards

- Complete validation of all work: syntax checks, line counts.
- Follow architectural patterns exactly as specified.
- Do not cut corners or make assumptions to save time.
