# WF_INIT - Session Initialization

---

## ⚡ SPAWNED AGENT BYPASS — CHECK THIS FIRST

**Before ANY initialization, check if you are a spawned agent:**

### How to detect you are a spawned agent:

Your initial prompt contains ANY of these indicators:
- `"You are a swarm agent"`
- `"BYPASS WF_INIT"`
- `"You are the [role] agent"`
- `"Do NOT follow CLAUDE.md workflow"`
- Agent role assignment from a coordinator (e.g., "You are r1", "You are agent-features")
- Explicit task-only instructions without a user conversation

### If you ARE a spawned agent:

- ✅ **SKIP this entire file (WF_INIT)**
- ✅ **SKIP WF_START, WF_CLASSIFY, and all workflow steps**
- ✅ **Do NOT create a WM file**
- ✅ **Do NOT read CLAUDE_OBLIGATIONS**
- ✅ **Execute ONLY the task in your initial prompt**
- ✅ You MAY read Serena memories if they help your specific task
- ✅ You MAY use any tool (Read, Grep, Glob, Serena, etc.) immediately

**⛔ Spawned agents that run WF_INIT waste their entire context window on workflow initialization instead of doing their assigned task. This is the #1 cause of swarm failure.**

### If you are NOT a spawned agent:

Continue to the anti-rationalization block below. You are a primary session and MUST follow the full workflow.

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
- ❌ "The hook didn't block me, so it's fine" - **The hook allowlist (`ToolSearch`, `Read`, `Glob`, `Grep`, `list_memories`) exists so WF_INIT can run — not so you can use those tools to do task work before init. The hook cannot tell the difference. YOU must.**

**If you find yourself making a tool call that searches code, edits files, or does ANYTHING implementation-related before completing initialization: STOP. You are violating the workflow. This includes using allowed tools like `Read`, `Grep`, `Glob`, or `list_memories` for task work — the hook won't block you, but you are still in violation.**

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

### Multi-Level Extraction with `depth`

Both `get_symbols_overview` and `find_symbol` accept a `depth` parameter (default 0):

| depth | Returns |
|-------|---------|
| `0` | Top-level symbols only (classes, standalone functions, constants) |
| `1` | Top-level + immediate children (e.g. class methods, function-local variables) |
| `2+` | Deeper nesting levels |

**Recommended workflow:**
1. `get_symbols_overview(path, depth=1)` — see file structure with children
2. `find_symbol("ClassName", depth=1, include_body=False)` — list all methods without reading bodies
3. `find_symbol("ClassName/methodName", include_body=True)` — read only what you need

### Language Server Coverage

Not all file types return rich symbols. Known behavior:

| File Type | Symbol Quality | Notes |
|-----------|---------------|-------|
| **PHP** | Excellent | Functions, classes, variables, DOM elements in templates |
| **Python** | Excellent | Classes, functions, variables |
| **TypeScript/JavaScript** | Good | Named exports, classes, functions. jQuery wrappers may return empty |
| **Markdown** | Limited | Headings only (H2/H3 as symbols) |
| **SCSS/CSS** | Poor | Language server rarely exposes selectors or variables |
| **JSON/YAML/Config** | None | No symbolic structure — use `Read` or `search_for_pattern` |

**When symbol extraction returns empty**, fall back to `search_for_pattern` with regex (e.g. `^\\.classname`, `^\\$variable`).

**NEVER read an entire file when you can extract the specific symbols you need.**
The only exceptions are:

- Config files (`.json`, `.env`) that have no symbolic structure
- Files where the language server returns empty/poor results (SCSS, CSS)
- When you explicitly need the full file context (e.g. reviewing a template's complete layout)

**Rationale:** Symbol extraction is token-efficient, precise, and leverages the language servers that Serena maintains for this project. Reading full files wastes context window and risks missing the relevant code in noise.

## MANDATORY: BROWSER DEVTOOLS — SCENARIOS FIRST

**Before using ANY `mcp__browser-devtools__` tool (navigation, interaction, screenshot, etc.), you MUST first call:**

```
mcp__browser-devtools__scenario-list()
```

**Check if a saved scenario already handles what you need** (login, navigation, common flows). If a matching scenario exists, use `mcp__browser-devtools__scenario-run({ name: "..." })` instead of individual tool calls.

**Individual browser tool calls (click, fill, navigate) are fragile and can crash the browser.** Scenarios batch steps into a single resilient call with error handling, sleeps, and recovery logic built in.

**Rules:**
- ❌ **NEVER** call `navigation_go-to`, `interaction_click`, `interaction_fill`, or other browser tools directly without first checking `scenario-list`
- ✅ **ALWAYS** prefer `scenario-run` over manual step-by-step browser interaction
- ✅ If no scenario exists for your flow, create one with `scenario-add` for reuse
- ✅ Only fall back to individual tools for one-off inspection (e.g. a single `a11y_take-aria-snapshot` after a scenario completes)

**USING BROWSER DEVTOOLS WITHOUT CHECKING SCENARIOS = WORKFLOW VIOLATION**

---

## CRITICAL: STEP REPORTING ENFORCEMENT

**After reading ANY WF** memory, your IMMEDIATE FIRST output MUST be the step report line._*

**For WF_INIT only**, include the plugin version from the SessionStart banner (shown in system-reminder):

```
> **🎬 On step WF_INIT (v1.1.2)**
```

For all other steps:

```
> **🚀 On step WF_START**
```

**DO NOT:**

- Read tool results and immediately start working
- Output analysis before the step report
- Skip the step report because you're "in the middle of something"

**The step report is a BLOCKING requirement.** You cannot proceed with any other output until the step has been reported to the user.

If your last output did NOT include a step report line, and you just read a WF_* memory, you have violated the workflow.
