---
name: WF_RESEARCH
description: Research-only workflow state — questions/exploration with no code changes; verify before asserting, check memories first, then explore with Serena, then route.
metadata:
  type: workflow
---

# WF_RESEARCH — Research Only

> **On step WF_RESEARCH**

## Verify Before Assert

- Research findings ARE factual claims.
- Any statement about backend/environment state (DB contents, existing environments, container state, remote data) MUST be preceded by a verification call (`wp_cli`, `terminus`, `docker`, logs) in the SAME turn.
- When you cannot verify, label the finding "unverified". NEVER present plausible inference as fact.

## Step 1 — Check Knowledge Base First

- Before exploring code, check whether existing memories answer the question:
  - `list_memories(topic="dom")` — domain behavior docs
  - `list_memories(topic="ref")` — reference patterns
  - `list_memories(topic="feature")` — feature configs
- Read every memory relevant to the question. Memories may hold file paths, architecture notes, and behavioral patterns that shortcut code exploration.

## Step 2 — Explore with Serena Tools

- When memories do not fully answer the question, explore with:
  - `mcp__plugin_swe_serena__find_symbol`
  - `mcp__plugin_swe_serena__get_symbols_overview`
  - `mcp__plugin_swe_serena__search_for_pattern`

## Step 3 — Report Findings

- Report findings directly to the user.

## Rules

- NEVER make code changes in this path.
- NEVER create files.
- Information gathering only.

## Routing

| Condition                             | Next Step     |
| ------------------------------------- | ------------- |
| Research complete, user wants changes | `WF_CLASSIFY` |
| Research complete, no changes needed  | `WF_DONE`     |

- Route to `WF_CLASSIFY` to classify the task and load feature context when the user wants to implement based on findings.
- Run `/swe-wm-update` to update WM before transitioning.
