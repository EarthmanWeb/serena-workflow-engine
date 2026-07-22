---
name: Read docs means list memories
description: When user says "read the docs", run list_memories to find relevant Serena memories
metadata:
  type: feedback
---

When the user says "read the docs" or "read docs", they mean: run `list_memories` to discover relevant Serena memories for the topic, then read the ones that apply.

**Why:** The user has extensive documentation stored in Serena memories. "Docs" = Serena memories, not external documentation or READMEs.

**How to apply:** Any time the user says "read the docs" or "check the docs", immediately call `mcp__plugin_swe_serena__list_memories()` and read the relevant ones before proceeding.
