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
- Extract at 3+ occurrences.
- NEVER over-engineer. Stick to specs. Build only when needed.

## NEVER Do

- NEVER skip or rationalize around workflow steps. See `wf/WF_INIT` anti-rationalization block.
- NEVER use fallbacks or defensive programming. Fail fast; no fallback masking.
- NEVER synthesize or fake data unless EXPLICITLY asked.
- NEVER attribute problems to caching unless caching exists in the code.
- NEVER use `as any` type assertions (TypeScript).
- NEVER guess file paths. Use Serena tools.
- NEVER run dev servers. The user manages these.
- NEVER implement workarounds without asking.
- NEVER proceed when memories conflict with user instructions. STOP and ask.

## ALWAYS Do

- Follow `wf/WF_INIT` → `claude/CLAUDE_OBLIGATIONS` → `wf/WF_CLASSIFY` sequence. No shortcuts. See `wf/WF_INIT`.
- "Let It Fail": remove defensive code, add none, allow clear failures.
- Check `MEMORY.md` or `index/INDEX_FEATURES` when navigating features.
- Use Serena symbolic tools for ALL code edits: `replace_symbol_body`, `insert_before_symbol`, `insert_after_symbol` to modify; `find_symbol`, `get_symbols_overview`, `search_for_pattern` to discover. Fall back to `Read`/`Edit` ONLY for non-code files or when symbols cannot be resolved.
- Update WM using `swe-wm` MCP tools: `swe_wm_update_section` for section updates, `swe_wm_update_status` for status, `swe_wm_read` to read. NEVER use `write_memory`/`edit_memory` on WM files — risks clobbering daemon-managed fields.
- Ask for clarification when uncertain.
- Follow existing patterns. Check docs and existing code first.
- Document new patterns or deviations in Serena memories.
- Clean up after tasks: remove temp files, branches, agents.
- Communicate blockers or uncertainties immediately.

## Skill Failure Threshold

After 2 consecutive command failures of the same type:

1. STOP immediately.
2. Re-read the relevant skill/memory.
3. Retry with adjustments.
4. Ask the user if still failing.

NEVER flail with variations of the same broken approach.

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

- NO time constraints on any task. Prioritize thoroughness and accuracy over speed. NEVER rush or skip steps to save time.
- MAKE NO ASSUMPTIONS. Research any assumption in the codebase or on the Web before asserting a direction.

## Parallel Processing

- Use the Claude Code `Agent` tool for parallel tasks. Launch multiple in ONE message.
- Use `run_in_background: true` for concurrent execution.
- Use `isolation: "worktree"` when agents edit overlapping files.
- Use Ruflo MCP tools ONLY for cognitive-only tasks (reasoning, consensus). See `feature/FEATURE_SWARM`.

## Quality Standards

- Complete validation of all work: syntax checks, line counts.
- Follow architectural patterns exactly as specified.
- NEVER cut corners or make assumptions to save time.
