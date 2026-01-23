# WF_QUICKSTART - Consolidated Entry Point

> **⚡ On step WF_QUICKSTART**

## Purpose
Single-read initialization combining essential workflow rules. Replaces reading WF_INIT + CLAUDE_OBLIGATIONS + WF_START separately.

---

## Core Rules (from CLAUDE_OBLIGATIONS)

**Language:** Concise, functional. No "Let me..." or "I think...". Use "Found:", "Next:", "Issue:".

**Principles:** KISS → DRY → YAGNI

**Never:**
- Skip workflow steps
- Use defensive fallbacks (fail fast)
- Guess file paths
- Proceed when uncertain

**Always:**
- Use Serena tools before Read/Edit
- Ask for clarification when uncertain
- Follow existing patterns

---

## Task Routing (Immediate Decision)

| Task Type | Route To | WORKING_MEMORY? |
|-----------|----------|-----------------|
| Simple lookup ("find X", "show Y") | `WF_RESEARCH_LITE` | No |
| Research/exploration | `WF_RESEARCH` | Yes |
| Code change/feature/bug | `WF_CLASSIFY` | Yes |
| Continue previous work | `WF_CONTINUE` | Yes (existing) |

---

## When WORKING_MEMORY Required

**Create if:** Code changes, multi-step tasks, debugging, cross-feature work

**Skip if:** Simple lookups returning in < 3 tool calls

**Naming:** `WORKING_MEMORY_<SESSION_ID>_<descriptor>`

**Template:** See `REF_WORKING_MEMORY` (only read if creating)

---

## Swarm Agent Bypass

If spawned as swarm agent with explicit role assignment:
- Skip this workflow
- Follow coordinator instructions only
- Read CLAUDE_OBLIGATIONS, _INDEX only

---

## Quick Reference

```
Session ID: From hook context (8-char UUID)
Features: See INDEX_FEATURES  
Standards: See REF_DEV_STANDARDS
```

**Token budget for init:** < 500 tokens (this file only)
