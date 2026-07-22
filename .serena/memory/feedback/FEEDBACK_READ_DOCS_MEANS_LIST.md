---
name: "Read docs" = list memories
description: When the user says "read/check the docs", list Serena memories and read the relevant ones — not external docs.
metadata:
  type: feedback
---

# "Read the docs" = list memories

When the user says "read the docs" / "check the docs", they mean: call `list_memories`, then read the relevant Serena memories. NOT external documentation or READMEs.

**Why:** The user's documentation is stored in Serena memories. "Docs" = Serena memories here.

**How to apply:** On any "read the docs" / "check the docs", immediately call `mcp__plugin_swe_serena__list_memories()` and read the applicable memories before proceeding.
