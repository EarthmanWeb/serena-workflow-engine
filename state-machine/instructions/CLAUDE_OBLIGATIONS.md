# CLAUDE_OBLIGATIONS - Behavioral Constraints

## READ COMPLETELY - ALWAYS OBEY EVERYTHING IN THIS FILE

DO NOT BE CONVERSATIONAL when performing tasks. Concise, functional language ONLY:

- WRONG: "Let me update" - RIGHT: "Updating:"
- WRONG: "I found this code" - RIGHT: "Found code:"
- WRONG: "I think the issue is" - RIGHT: "Issue Found:"
- WRONG: "Now I need to" - RIGHT: "Next:"
- WRONG: "I need to add" - RIGHT: "Adding:"
- WRONG: "Here's a summary of the changes" - RIGHT: "Summary of changes:"
- Use bullet points, numbered lists, and tables for clarity
- Remote environment - request operator output when debugging only if necessary and cannot be obtained via MCP tools

## Core Coding Principles

**KISS -> DRY -> YAGNI** (priority order)

- Simple, readable code
- Always search for existing features before creating new ones
- Avoid over-engineering, stick to specs
- Build only when needed

## NEVER Do

- [ ] Use fallbacks or defensive programming - fail fast instead, no fallback masking
- [ ] Synthesize data or "fake" data unless EXPLICITLY asked
- [ ] Chalk problems up to 'caching' unless caching exists in the code
- [ ] Use `as any` type assertions (TypeScript)
- [ ] Guess file paths (use Serena tools)
- [ ] Run dev servers (user manages these)
- [ ] Implement workarounds without asking
- [ ] Proceed when memories conflict with user instructions

## ALWAYS Do

- [ ] **"Let It Fail":**  Remove and do not add defensive code, Allow Clear failures
- [ ] Check _INDEX or INDEX_FEATURES when navigating features
- [ ] Use Serena tools before Read/Edit
- [ ] Update WORKING_MEMORY after significant steps
- [ ] Ask for clarification when uncertain
- [ ] Follow existing patterns (check docs and existing code first)
- [ ] Document new patterns or deviations in Serena memories
- [ ] Ensure cleanup after tasks (remove temp files, branches, agents)
- [ ] Communicate blockers or uncertainties immediately

## If Debugging Is Needed

1. FOLLOW project-specific debugging patterns (check REF_* memories)
2. LOG all findings in WORKING_MEMORY
3. SUMMARIZE issues and proposed fixes for user review

## User Interaction

If user frustrated: verify their instructions followed exactly, offer to update docs if conflict exists

## On Conflicts

If user instruction contradicts memory:
1. STOP
2. ASK for clarification
3. UPDATE memory after confirmation

# Working Style Rules

## CRITICAL: NO TIME CONSTRAINTS
- There are **NO time constraints** on any task
- **ALWAYS prioritize thoroughness and accuracy over speed**
- Never rush through tasks or skip steps to save time
- Take the time needed to do things correctly the first time

## Parallel Processing
- Use swarms to parallel process tasks when appropriate
- Spawn multiple agents for independent subtasks
- Leverage `mcp__claude-flow__` or `mcp__ruv-swarm__` tools for coordination

## Quality Standards
- Complete validation of all work (syntax checks, line counts, etc.)
- Follow all architectural patterns exactly as specified
- Never cut corners or make assumptions to save time
- MAKE NO ASSUMPTIONS - Research any assumptions in codebase OR on Web before asserting any direction