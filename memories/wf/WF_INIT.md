# WF_INIT - Session Initialization

---

## 🚫 ANTI-RATIONALIZATION BLOCK - READ FIRST

**YOU WILL BE TEMPTED TO SKIP STEPS. DO NOT.**

Common rationalizations that are **NEVER VALID**:

- ❌ "This is a simple task" - **Complexity is irrelevant. Follow ALL steps.**
- ❌ "I already know what to do" - **The workflow exists for consistency, not knowledge.**
- ❌ "The user wants a quick answer" - **Speed is not a valid reason to skip steps.**
- ❌ "I can batch this with other calls" - **NEVER combine workflow steps with implementation actions.**
- ❌ "CLAUDE_OBLIGATIONS doesn't apply here" - **It ALWAYS applies. Read it EVERY time.**
- ❌ "WM already exists" - **Verify and UPDATE it. Don't assume.**
- ❌ "This task has nothing to do with the codebase" - **ALL tasks run through the workflow. No exceptions for GitHub issues, external tools, or "unrelated" work.**

**If you find yourself making a tool call that searches code, edits files, or does ANYTHING implementation-related before completing initialization: STOP. You are violating the workflow.**

---

## CRITICAL: MANDATORY ENTRY POINT - FOLLOW AND REPORT ALL WORKFLOW STEPS START TO FINISH BY READING WF_START

**BEFORE responding to ANY user message, if you do not remember reading these, you MUST:**

1. READ and COMPLY WITH CLAUDE_OBLIGATIONS:

```
mcp__plugin_swe_serena__read_memory("claude/CLAUDE_OBLIGATIONS")
```

**THEN IN ALL CASES, you MUST:***
2. READ and COMPLY WITH [WF_START](WF_START.md) fully

**NO EXCEPTIONS.** This includes:

- Meta-work (modifying the workflow itself)
- Simple questions
- Continuing previous conversations
- ANY interaction whatsoever

If you respond without first reading WF_START, you have failed to follow instructions.

## MANDATORY: PREFER SYMBOL EXTRACTION OVER FILE READS

**When looking for specific references, all supported file types MUST be parsed with Serena's symbolic tools instead of reading entire files.**

This applies to:

- **Markdown files** (`.md`) — including WM files, memories, and documentation
- **PHP files** — classes, functions, hooks
- **JavaScript/TypeScript files** — modules, classes, functions
- **Python files** — classes, functions, variables

**Use these tools FIRST:**

- `get_symbols_overview` — understand file structure without reading it
- `find_symbol` with `include_body=True` — read only the symbol you need
- `find_referencing_symbols` — trace dependencies between symbols
- `search_for_pattern` — targeted search when symbol name is unknown

**NEVER read an entire file when you can extract the specific symbols you need.**
The only exceptions are:

- Config files (`.json`, `.env`) that have no symbolic structure
- Files where the language server is unavailable or not responding
- When you explicitly need the full file context (e.g. reviewing a template's complete layout)

**Rationale:** Symbol extraction is token-efficient, precise, and leverages the language servers that Serena maintains for this project. Reading full files wastes context window and risks missing the relevant code in noise.

## CRITICAL: STEP REPORTING ENFORCEMENT

**After reading ANY WF** memory, your IMMEDIATE FIRST output MUST be the step report line._*

Example:

```
> **🚀 On step WF_START**
```

**DO NOT:**

- Read tool results and immediately start working
- Output analysis before the step report
- Skip the step report because you're "in the middle of something"

**The step report is a BLOCKING requirement.** You cannot proceed with any other output until the step has been reported to the user.

If your last output did NOT include a step report line, and you just read a WF_* memory, you have violated the workflow.
