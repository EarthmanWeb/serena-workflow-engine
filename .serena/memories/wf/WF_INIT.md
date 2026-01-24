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

**If you find yourself making a tool call that searches code, edits files, or does ANYTHING implementation-related before completing initialization: STOP. You are violating the workflow.**

---

## CRITICAL: MANDATORY ENTRY POINT - FOLLOW AND REPORT ALL WORKFLOW STEPS START TO FINISH BY READING WF_START

**BEFORE responding to ANY user message, if you do not remember reading these, you MUST:**
1. READ and COMPLY WITH [CLAUDE_OBLIGATIONS](CLAUDE_OBLIGATIONS.md)

**THEN IN ALL CASES, you MUST:***
2. READ and COMPLY WITH [WF_START](WF_START.md) fully

**NO EXCEPTIONS.** This includes:
- Meta-work (modifying the workflow itself)
- Simple questions
- Continuing previous conversations
- ANY interaction whatsoever

If you respond without first reading WF_START, you have failed to follow instructions.

## CRITICAL: STEP REPORTING ENFORCEMENT

**After reading ANY WF_* memory, your IMMEDIATE FIRST output MUST be the step report line.**

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
